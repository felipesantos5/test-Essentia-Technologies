from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from clinic_api.errors import NotFoundError
from clinic_api.models import Clinic, Doctor, PaymentMethod, Specialty


def get_clinic(session: Session) -> Clinic:
    clinic = session.get(Clinic, 1)
    if clinic is None:
        raise NotFoundError("CLINIC_NOT_CONFIGURED", "Clinic information has not been seeded.")
    return clinic


def list_specialties(session: Session) -> Sequence[Specialty]:
    return session.scalars(select(Specialty).order_by(Specialty.name)).all()


def get_specialty(session: Session, specialty_id: int) -> Specialty:
    specialty = session.get(Specialty, specialty_id)
    if specialty is None:
        raise NotFoundError(
            "SPECIALTY_NOT_FOUND",
            f"Specialty {specialty_id} not found.",
            {"specialty_id": specialty_id},
        )
    return specialty


def list_active_doctors(
    session: Session, *, specialty_id: int | None = None, doctor_id: int | None = None
) -> Sequence[Doctor]:
    if specialty_id is not None:
        get_specialty(session, specialty_id)

    query = (
        select(Doctor)
        .options(joinedload(Doctor.specialty), selectinload(Doctor.schedules))
        .where(Doctor.is_active.is_(True))
        .order_by(Doctor.full_name)
    )
    if specialty_id is not None:
        query = query.where(Doctor.specialty_id == specialty_id)
    if doctor_id is not None:
        query = query.where(Doctor.id == doctor_id)
    doctors = session.scalars(query).all()

    if doctor_id is not None and not doctors:
        raise NotFoundError(
            "DOCTOR_NOT_FOUND", f"Active doctor {doctor_id} not found.", {"doctor_id": doctor_id}
        )
    return doctors


def list_active_payment_methods(session: Session) -> Sequence[PaymentMethod]:
    query = (
        select(PaymentMethod)
        .where(PaymentMethod.is_active.is_(True))
        .order_by(PaymentMethod.sort_order, PaymentMethod.name)
    )
    return session.scalars(query).all()
