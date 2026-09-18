"""Idempotent seed with fictitious clinic data. Safe to run on every container start.

Reference data is upserted by natural key. Sample appointments are created only on an empty
table and are placed relative to "now", so the demo agenda never goes stale.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clinic_api.config import Settings, get_settings
from clinic_api.db import get_session_factory
from clinic_api.models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Doctor,
    DoctorSchedule,
    Patient,
    PaymentMethod,
    Specialty,
)
from clinic_api.services.slots import find_slot, generate_slots, iter_dates

logger = logging.getLogger(__name__)

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY = range(6)
# Every seeded doctor works at least once a week, so two weeks always contain the wanted slot.
SLOT_SEARCH_DAYS = 14


@dataclass(frozen=True)
class ScheduleSeed:
    weekday: int
    start: str
    end: str
    slot_minutes: int


@dataclass(frozen=True)
class DoctorSeed:
    full_name: str
    crm: str
    specialty: str
    schedule: tuple[ScheduleSeed, ...]


@dataclass(frozen=True)
class PatientSeed:
    full_name: str
    email: str
    phone: str


@dataclass(frozen=True)
class PaymentMethodSeed:
    code: str
    name: str
    description: str
    max_installments: int | None = None


CLINIC = {
    "name": "Clínica Essentia Saúde",
    "address": "Av. Paulista, 1000, conjunto 101 - Bela Vista, São Paulo - SP",
    "phone": "(11) 4000-1234",
    "email": "contato@clinica-essentia.example",
    "greeting_message": (
        "Olá! Bem-vindo(a) à Clínica Essentia Saúde. Sou a assistente virtual e posso ajudar "
        "com horários disponíveis, agendamentos, cancelamentos e informações sobre valores e "
        "formas de pagamento. Como posso ajudar?"
    ),
    "closing_message": (
        "Obrigada por falar com a Clínica Essentia Saúde! Se precisar de algo mais, é só "
        "chamar. Cuide-se!"
    ),
}

SPECIALTY_PRICES_CENTS = {
    "Clínica Geral": 25000,
    "Cardiologia": 38000,
    "Dermatologia": 32000,
    "Pediatria": 30000,
}

DOCTORS = (
    DoctorSeed(
        "Dra. Ana Beatriz Souza",
        "CRM-SP 123456",
        "Clínica Geral",
        (
            ScheduleSeed(MONDAY, "08:00", "12:00", 30),
            ScheduleSeed(MONDAY, "13:00", "17:00", 30),
            ScheduleSeed(WEDNESDAY, "08:00", "12:00", 30),
            ScheduleSeed(FRIDAY, "13:00", "17:00", 30),
            ScheduleSeed(SATURDAY, "08:00", "12:00", 30),
        ),
    ),
    DoctorSeed(
        "Dr. Carlos Eduardo Lima",
        "CRM-SP 234567",
        "Cardiologia",
        (
            ScheduleSeed(TUESDAY, "14:00", "18:00", 40),
            ScheduleSeed(THURSDAY, "08:00", "12:00", 40),
        ),
    ),
    DoctorSeed(
        "Dra. Mariana Costa",
        "CRM-SP 345678",
        "Dermatologia",
        (
            ScheduleSeed(TUESDAY, "09:00", "12:00", 30),
            ScheduleSeed(WEDNESDAY, "14:00", "18:00", 30),
            ScheduleSeed(FRIDAY, "09:00", "12:00", 30),
        ),
    ),
    DoctorSeed(
        "Dr. Rafael Almeida",
        "CRM-SP 456789",
        "Pediatria",
        tuple(ScheduleSeed(weekday, "08:00", "11:00", 45) for weekday in range(MONDAY, SATURDAY)),
    ),
)

# `example.com` is reserved (RFC 2606): confirmation emails can never reach a real person.
PATIENTS = (
    PatientSeed("João Pereira", "joao.pereira@example.com", "(11) 98888-1001"),
    PatientSeed("Maria Oliveira", "maria.oliveira@example.com", "(11) 98888-1002"),
    PatientSeed("Pedro Santos", "pedro.santos@example.com", "(11) 98888-1003"),
    PatientSeed("Luiza Fernandes", "luiza.fernandes@example.com", "(11) 98888-1004"),
    PatientSeed("Ricardo Gomes", "ricardo.gomes@example.com", "(11) 98888-1005"),
)
DEMO_PATIENT_PHONE = "(11) 90000-0000"

PAYMENT_METHODS = (
    PaymentMethodSeed("pix", "Pix", "Pagamento à vista via Pix, antecipado ou no dia da consulta."),
    PaymentMethodSeed(
        "credit_card",
        "Cartão de crédito",
        "Visa, Mastercard, Elo e American Express. Parcelamento em até 3x sem juros.",
        max_installments=3,
    ),
    PaymentMethodSeed("debit_card", "Cartão de débito", "Visa, Mastercard e Elo, à vista."),
    PaymentMethodSeed("cash", "Dinheiro", "Pagamento à vista na recepção."),
)


def seed_database(session: Session, settings: Settings, now: datetime) -> None:
    _upsert_clinic(session)
    specialties = _upsert_specialties(session)
    doctors = _upsert_doctors(session, specialties)
    patients = _upsert_patients(session, settings)
    _upsert_payment_methods(session)

    if not session.scalar(select(func.count()).select_from(Appointment)):
        _create_sample_appointments(session, doctors, patients, settings.tz, now)
    session.commit()


def _upsert_clinic(session: Session) -> None:
    clinic = session.get(Clinic, 1) or Clinic(id=1)
    for field, value in CLINIC.items():
        setattr(clinic, field, value)
    session.add(clinic)


def _upsert_specialties(session: Session) -> dict[str, Specialty]:
    existing = {specialty.name: specialty for specialty in session.scalars(select(Specialty))}
    for name, price_cents in SPECIALTY_PRICES_CENTS.items():
        specialty = existing.get(name) or Specialty(name=name)
        specialty.price_cents = price_cents
        session.add(specialty)
        existing[name] = specialty
    return existing


def _upsert_doctors(session: Session, specialties: dict[str, Specialty]) -> dict[str, Doctor]:
    existing = {doctor.crm: doctor for doctor in session.scalars(select(Doctor))}
    for seed in DOCTORS:
        doctor = existing.get(seed.crm) or Doctor(crm=seed.crm)
        doctor.full_name = seed.full_name
        doctor.specialty = specialties[seed.specialty]
        doctor.is_active = True
        # Schedules are only created once: replacing them in place would trip the
        # (doctor_id, weekday, start_time) unique constraint inside a single flush.
        if not doctor.schedules:
            doctor.schedules = [
                DoctorSchedule(
                    weekday=block.weekday,
                    start_time=time.fromisoformat(block.start),
                    end_time=time.fromisoformat(block.end),
                    slot_minutes=block.slot_minutes,
                )
                for block in seed.schedule
            ]
        session.add(doctor)
        existing[seed.crm] = doctor
    return existing


def _upsert_patients(session: Session, settings: Settings) -> dict[str, Patient]:
    seeds = list(PATIENTS)
    if settings.demo_patient_email:
        seeds.append(
            PatientSeed(settings.demo_patient_name, settings.demo_patient_email, DEMO_PATIENT_PHONE)
        )

    existing = {patient.email: patient for patient in session.scalars(select(Patient))}
    for seed in seeds:
        email = seed.email.lower()
        patient = existing.get(email) or Patient(email=email)
        patient.full_name = seed.full_name
        patient.phone = seed.phone
        session.add(patient)
        existing[email] = patient
    return existing


def _upsert_payment_methods(session: Session) -> None:
    existing = {method.code: method for method in session.scalars(select(PaymentMethod))}
    for sort_order, seed in enumerate(PAYMENT_METHODS):
        method = existing.get(seed.code) or PaymentMethod(code=seed.code)
        method.name = seed.name
        method.description = seed.description
        method.max_installments = seed.max_installments
        method.is_active = True
        method.sort_order = sort_order
        session.add(method)


def _create_sample_appointments(
    session: Session,
    doctors: dict[str, Doctor],
    patients: dict[str, Patient],
    tz: ZoneInfo,
    now: datetime,
) -> None:
    today = now.astimezone(tz).date()
    general, cardio, derma, pediatrics = (doctors[seed.crm] for seed in DOCTORS)

    def book(
        patient_email: str, doctor: Doctor, starts_at: datetime, *, cancelled: bool = False
    ) -> None:
        slot = find_slot(doctor.schedules, starts_at, tz)
        if slot is None:
            raise LookupError(f"{starts_at} is not a slot in {doctor.full_name}'s schedule")
        session.add(
            Appointment(
                patient=patients[patient_email],
                doctor=doctor,
                starts_at=slot[0],
                ends_at=slot[1],
                status=AppointmentStatus.CANCELLED if cancelled else AppointmentStatus.SCHEDULED,
                price_cents=doctor.specialty.price_cents,
                cancelled_at=now if cancelled else None,
                cancellation_reason="Imprevisto pessoal." if cancelled else None,
            )
        )

    book("joao.pereira@example.com", cardio, _nth_slot(cardio, today + timedelta(days=1), tz, 1))
    book("maria.oliveira@example.com", general, _nth_slot(general, today + timedelta(days=1), tz))
    book("pedro.santos@example.com", derma, _nth_slot(derma, today + timedelta(days=2), tz, 2))
    book(
        "ricardo.gomes@example.com",
        general,
        _nth_slot(general, today + timedelta(days=3), tz, 3),
        cancelled=True,
    )
    # Already happened: used to demonstrate that past appointments cannot be cancelled.
    book("luiza.fernandes@example.com", pediatrics, _nth_slot(pediatrics, today - timedelta(7), tz))


def _nth_slot(doctor: Doctor, start_day: date, tz: ZoneInfo, index: int = 0) -> datetime:
    slots = (
        slot
        for day in iter_dates(start_day, start_day + timedelta(days=SLOT_SEARCH_DAYS))
        for slot in generate_slots(doctor.schedules, day, tz)
    )
    for position, slot in enumerate(slots):
        if position == index:
            return slot
    raise LookupError(f"no slot #{index} for {doctor.full_name} from {start_day}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    with get_session_factory()() as session:
        seed_database(session, settings, datetime.now(UTC))
    logger.info("Seed completed for %s", settings.database_url)


if __name__ == "__main__":
    main()
