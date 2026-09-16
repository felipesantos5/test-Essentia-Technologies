from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from clinic_api.config import Settings
from clinic_api.errors import BusinessRuleError
from clinic_api.models import Appointment, AppointmentStatus, Doctor
from clinic_api.services.catalog import list_active_doctors
from clinic_api.services.slots import generate_slots, iter_dates


@dataclass(frozen=True, slots=True)
class DaySlots:
    day: date
    slots: list[datetime]


@dataclass(frozen=True, slots=True)
class DoctorAvailability:
    doctor: Doctor
    days: list[DaySlots]


@dataclass(frozen=True, slots=True)
class Availability:
    date_from: date
    date_to: date
    doctors: list[DoctorAvailability]


def get_availability(
    session: Session,
    *,
    settings: Settings,
    now: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
    specialty_id: int | None = None,
    doctor_id: int | None = None,
) -> Availability:
    """Free slots per doctor: weekly schedule minus active appointments and past times."""
    tz = settings.tz
    date_from = date_from or now.astimezone(tz).date()
    date_to = date_to or date_from + timedelta(days=settings.availability_default_days - 1)
    _validate_range(date_from, date_to, settings.availability_max_days)

    doctors = list_active_doctors(session, specialty_id=specialty_id, doctor_id=doctor_id)
    range_start = datetime.combine(date_from, time.min, tzinfo=tz)
    range_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    booked = _booked_starts(session, doctors, range_start, range_end)

    result: list[DoctorAvailability] = []
    for doctor in doctors:
        days = []
        for day in iter_dates(date_from, date_to):
            free = [
                slot
                for slot in generate_slots(doctor.schedules, day, tz)
                if slot > now and (doctor.id, slot) not in booked
            ]
            if free:
                days.append(DaySlots(day=day, slots=free))
        result.append(DoctorAvailability(doctor=doctor, days=days))
    return Availability(date_from=date_from, date_to=date_to, doctors=result)


def _validate_range(date_from: date, date_to: date, max_days: int) -> None:
    if date_to < date_from:
        raise BusinessRuleError(
            "INVALID_DATE_RANGE",
            "date_to must be on or after date_from.",
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )
    if (date_to - date_from).days + 1 > max_days:
        raise BusinessRuleError(
            "DATE_RANGE_TOO_LARGE",
            f"Availability can be queried for at most {max_days} days at a time.",
            {"max_days": max_days},
        )


def _booked_starts(
    session: Session, doctors: Sequence[Doctor], range_start: datetime, range_end: datetime
) -> set[tuple[int, datetime]]:
    if not doctors:
        return set()
    rows = session.execute(
        select(Appointment.doctor_id, Appointment.starts_at).where(
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.doctor_id.in_([doctor.id for doctor in doctors]),
            Appointment.starts_at >= range_start,
            Appointment.starts_at < range_end,
        )
    )
    # Aware datetimes hash by instant, so UTC rows match local slot starts.
    return {(doctor_id, starts_at) for doctor_id, starts_at in rows.tuples()}
