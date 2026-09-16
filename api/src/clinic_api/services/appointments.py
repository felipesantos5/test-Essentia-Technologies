from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from clinic_api.errors import BusinessRuleError, ConflictError, NotFoundError
from clinic_api.models import Appointment, AppointmentStatus, Doctor
from clinic_api.schemas.appointments import AppointmentCancel, AppointmentCreate
from clinic_api.services.patients import get_patient
from clinic_api.services.slots import find_slot


def _with_relations() -> Select[tuple[Appointment]]:
    return select(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.specialty),
    )


def get_appointment(session: Session, appointment_id: int) -> Appointment:
    appointment = session.scalar(_with_relations().where(Appointment.id == appointment_id))
    if appointment is None:
        raise _appointment_not_found(appointment_id)
    return appointment


def list_patient_appointments(
    session: Session,
    *,
    patient_id: int,
    now: datetime,
    status: AppointmentStatus | None = None,
    upcoming: bool | None = None,
) -> Sequence[Appointment]:
    get_patient(session, patient_id)
    query = _with_relations().where(Appointment.patient_id == patient_id)
    if status is not None:
        query = query.where(Appointment.status == status)
    if upcoming is True:
        query = query.where(Appointment.starts_at > now)
    elif upcoming is False:
        query = query.where(Appointment.starts_at <= now)
    return session.scalars(query.order_by(Appointment.starts_at)).all()


def book_appointment(
    session: Session, data: AppointmentCreate, *, now: datetime, tz: ZoneInfo
) -> Appointment:
    patient = get_patient(session, data.patient_id)
    doctor = session.scalar(
        select(Doctor)
        .options(joinedload(Doctor.specialty), selectinload(Doctor.schedules))
        .where(Doctor.id == data.doctor_id, Doctor.is_active.is_(True))
    )
    if doctor is None:
        raise NotFoundError(
            "DOCTOR_NOT_FOUND",
            f"Active doctor {data.doctor_id} not found.",
            {"doctor_id": data.doctor_id},
        )

    starts_at = data.starts_at if data.starts_at.tzinfo else data.starts_at.replace(tzinfo=tz)
    details = {"doctor_id": doctor.id, "starts_at": starts_at.astimezone(tz).isoformat()}
    if starts_at <= now:
        raise BusinessRuleError("SLOT_IN_PAST", "The requested time is in the past.", details)
    slot = find_slot(doctor.schedules, starts_at, tz)
    if slot is None:
        raise BusinessRuleError(
            "SLOT_OUTSIDE_SCHEDULE",
            "The requested time is not a slot in the doctor's schedule. Check /availability.",
            details,
        )
    slot_start, slot_end = slot
    _ensure_no_conflict(session, doctor.id, patient.id, slot_start, slot_end)

    appointment = Appointment(
        patient=patient,
        doctor=doctor,
        starts_at=slot_start,
        ends_at=slot_end,
        status=AppointmentStatus.SCHEDULED,
        price_cents=doctor.specialty.price_cents,
        notes=data.notes or None,
    )
    session.add(appointment)
    try:
        session.commit()
    except IntegrityError as exc:
        # Lost a race against a concurrent booking: the committed row now explains the conflict.
        session.rollback()
        _ensure_no_conflict(session, doctor.id, patient.id, slot_start, slot_end)
        raise ConflictError("SLOT_UNAVAILABLE", "This slot was just booked.", details) from exc
    return get_appointment(session, appointment.id)


def cancel_appointment(
    session: Session, appointment_id: int, data: AppointmentCancel, *, now: datetime
) -> Appointment:
    appointment = session.scalar(_with_relations().where(Appointment.id == appointment_id))
    # An email mismatch is reported as "not found" to avoid confirming someone else's booking.
    if appointment is None or appointment.patient.email != data.patient_email:
        raise _appointment_not_found(appointment_id)

    if appointment.status is AppointmentStatus.CANCELLED:
        raise ConflictError(
            "APPOINTMENT_ALREADY_CANCELLED",
            "This appointment was already cancelled.",
            {"appointment_id": appointment_id},
        )
    if appointment.starts_at <= now:
        raise BusinessRuleError(
            "APPOINTMENT_IN_PAST",
            "Past appointments cannot be cancelled.",
            {"appointment_id": appointment_id},
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now
    appointment.cancellation_reason = data.reason or None
    session.commit()
    return appointment


def _ensure_no_conflict(
    session: Session, doctor_id: int, patient_id: int, starts_at: datetime, ends_at: datetime
) -> None:
    overlapping = session.scalars(
        select(Appointment).where(
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
            or_(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id),
        )
    ).all()

    for existing in overlapping:
        if existing.doctor_id == doctor_id and existing.patient_id == patient_id:
            raise ConflictError(
                "APPOINTMENT_ALREADY_BOOKED",
                "The patient already has this appointment booked.",
                {"appointment_id": existing.id},
            )
    if any(existing.doctor_id == doctor_id for existing in overlapping):
        raise ConflictError(
            "SLOT_UNAVAILABLE",
            "This slot is no longer available for the doctor.",
            {"doctor_id": doctor_id},
        )
    if overlapping:
        raise ConflictError(
            "PATIENT_TIME_CONFLICT",
            "The patient already has another appointment at this time.",
            {"appointment_id": overlapping[0].id},
        )


def _appointment_not_found(appointment_id: int) -> NotFoundError:
    return NotFoundError(
        "APPOINTMENT_NOT_FOUND",
        f"Appointment {appointment_id} not found.",
        {"appointment_id": appointment_id},
    )
