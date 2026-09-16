from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clinic_api.errors import ConflictError, NotFoundError
from clinic_api.models import Patient
from clinic_api.schemas.patients import PatientCreate


def find_patients(session: Session, *, email: str | None = None) -> Sequence[Patient]:
    query = select(Patient).order_by(Patient.full_name)
    if email is not None:
        query = query.where(Patient.email == email.strip().lower())
    return session.scalars(query).all()


def get_patient(session: Session, patient_id: int) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(
            "PATIENT_NOT_FOUND", f"Patient {patient_id} not found.", {"patient_id": patient_id}
        )
    return patient


def create_patient(session: Session, data: PatientCreate) -> Patient:
    if find_patients(session, email=data.email):
        raise _email_taken(data.email)

    patient = Patient(full_name=data.full_name, email=data.email, phone=data.phone)
    session.add(patient)
    try:
        session.commit()
    except IntegrityError as exc:  # concurrent registration with the same email
        session.rollback()
        raise _email_taken(data.email) from exc
    return patient


def _email_taken(email: str) -> ConflictError:
    return ConflictError(
        "PATIENT_EMAIL_ALREADY_EXISTS",
        "A patient with this email is already registered.",
        {"email": email},
    )
