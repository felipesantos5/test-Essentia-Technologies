from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Self
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from clinic_api.cache import TTLCache
from clinic_api.config import Settings
from clinic_api.errors import BusinessRuleError
from clinic_api.models import Appointment, AppointmentStatus, Doctor
from clinic_api.services.catalog import list_active_doctors
from clinic_api.services.slots import generate_slots, iter_dates


@dataclass(frozen=True, slots=True)
class DoctorSummary:
    """Plain copy of the doctor fields, so cached results hold no ORM instances."""

    id: int
    full_name: str
    specialty_id: int
    specialty_name: str
    price_cents: int

    @classmethod
    def from_model(cls, doctor: Doctor) -> Self:
        return cls(
            id=doctor.id,
            full_name=doctor.full_name,
            specialty_id=doctor.specialty.id,
            specialty_name=doctor.specialty.name,
            price_cents=doctor.specialty.price_cents,
        )


@dataclass(frozen=True, slots=True)
class DaySlots:
    day: date
    slots: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class DoctorAvailability:
    doctor: DoctorSummary
    days: tuple[DaySlots, ...]


@dataclass(frozen=True, slots=True)
class Availability:
    date_from: date
    date_to: date
    doctors: tuple[DoctorAvailability, ...]


@dataclass(frozen=True, slots=True)
class AvailabilityKey:
    date_from: date
    date_to: date
    specialty_id: int | None
    doctor_id: int | None


AvailabilityCache = TTLCache[AvailabilityKey, Availability]


def get_availability(
    session: Session,
    *,
    settings: Settings,
    cache: AvailabilityCache,
    now: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
    specialty_id: int | None = None,
    doctor_id: int | None = None,
) -> Availability:
    """Free slots per doctor: weekly schedule minus active appointments and past times.

    The cache holds the result before the past-time filter, which runs on every read, so an
    entry stays correct as the clock moves and never offers a slot that has already started.
    """
    tz = settings.tz
    date_from = date_from or now.astimezone(tz).date()
    date_to = date_to or date_from + timedelta(days=settings.availability_default_days - 1)
    validate_date_range(date_from, date_to, settings.availability_max_days)

    key = AvailabilityKey(date_from, date_to, specialty_id, doctor_id)
    unbooked = cache.get_or_compute(key, lambda: _unbooked_slots(session, key, tz))
    return _drop_past_slots(unbooked, now)


def validate_date_range(date_from: date, date_to: date, max_days: int) -> None:
    """Inclusive range with at most `max_days` days; shared by availability and listings."""
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


def _unbooked_slots(session: Session, key: AvailabilityKey, tz: ZoneInfo) -> Availability:
    doctors = list_active_doctors(session, specialty_id=key.specialty_id, doctor_id=key.doctor_id)
    range_start = datetime.combine(key.date_from, time.min, tzinfo=tz)
    range_end = datetime.combine(key.date_to + timedelta(days=1), time.min, tzinfo=tz)
    booked = _booked_starts(session, doctors, range_start, range_end)

    result: list[DoctorAvailability] = []
    for doctor in doctors:
        days = []
        for day in iter_dates(key.date_from, key.date_to):
            free = tuple(
                slot
                for slot in generate_slots(doctor.schedules, day, tz)
                if (doctor.id, slot) not in booked
            )
            if free:
                days.append(DaySlots(day=day, slots=free))
        result.append(DoctorAvailability(doctor=DoctorSummary.from_model(doctor), days=tuple(days)))
    return Availability(date_from=key.date_from, date_to=key.date_to, doctors=tuple(result))


def _drop_past_slots(availability: Availability, now: datetime) -> Availability:
    doctors = []
    for item in availability.doctors:
        days = []
        for day in item.days:
            upcoming = tuple(slot for slot in day.slots if slot > now)
            if upcoming:
                days.append(replace(day, slots=upcoming))
        doctors.append(replace(item, days=tuple(days)))
    return replace(availability, doctors=tuple(doctors))


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
