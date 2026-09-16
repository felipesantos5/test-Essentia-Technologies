from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clinic_api.config import Settings
from clinic_api.models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Doctor,
    Patient,
    PaymentMethod,
    Specialty,
)
from clinic_api.seed import seed_database
from clinic_api.services.slots import find_slot
from tests.conftest import FIXED_NOW


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_is_idempotent(session: Session, settings: Settings) -> None:
    seed_database(session, settings, FIXED_NOW)
    first_run = {
        model: _count(session, model)
        for model in (Clinic, Specialty, Doctor, Patient, PaymentMethod, Appointment)
    }

    seed_database(session, settings, FIXED_NOW)

    assert first_run == {model: _count(session, model) for model in first_run}
    assert first_run[Clinic] == 1
    assert first_run[Appointment] == 5


def test_seeded_appointments_fit_doctor_schedules(session: Session, settings: Settings) -> None:
    seed_database(session, settings, FIXED_NOW)

    for appointment in session.scalars(select(Appointment)):
        doctor = appointment.doctor
        slot = find_slot(doctor.schedules, appointment.starts_at, settings.tz)
        assert slot is not None
        assert slot[1] == appointment.ends_at
        assert appointment.price_cents == doctor.specialty.price_cents


def test_seed_has_future_and_past_scheduled_appointments(
    session: Session, settings: Settings
) -> None:
    seed_database(session, settings, FIXED_NOW)

    scheduled = session.scalars(
        select(Appointment).where(Appointment.status == AppointmentStatus.SCHEDULED)
    ).all()

    assert any(appointment.starts_at > FIXED_NOW for appointment in scheduled)
    assert any(appointment.starts_at < FIXED_NOW for appointment in scheduled)


def test_seed_adds_demo_patient_when_configured(session: Session, settings: Settings) -> None:
    demo_settings = Settings(
        database_url=settings.database_url,
        api_key=SecretStr("unused"),
        demo_patient_email="Me@Example.com",
        demo_patient_name="Demo Person",
    )

    seed_database(session, demo_settings, FIXED_NOW)

    patient = session.scalar(select(Patient).where(Patient.email == "me@example.com"))
    assert patient is not None
    assert patient.full_name == "Demo Person"
