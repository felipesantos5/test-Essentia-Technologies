from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from clinic_api.models import (
    Appointment,
    AppointmentStatus,
    Doctor,
    DoctorSchedule,
    Patient,
    Specialty,
)

WEDNESDAY, THURSDAY = 2, 3

# (weekday, start, end, slot minutes). With FIXED_NOW (Wed 09:00) only 09:30 is still free today.
DEFAULT_BLOCKS = ((WEDNESDAY, "08:00", "10:00", 30), (THURSDAY, "08:00", "10:00", 30))


def create_doctor(
    session: Session,
    *,
    full_name: str = "Dra. Helena Duarte",
    crm: str = "CRM-SP 100001",
    specialty_name: str = "Cardiologia",
    price_cents: int = 38000,
    blocks: tuple[tuple[int, str, str, int], ...] = DEFAULT_BLOCKS,
) -> Doctor:
    specialty = Specialty(name=specialty_name, price_cents=price_cents)
    doctor = Doctor(
        full_name=full_name,
        crm=crm,
        specialty=specialty,
        schedules=[
            DoctorSchedule(
                weekday=weekday,
                start_time=time.fromisoformat(start),
                end_time=time.fromisoformat(end),
                slot_minutes=slot_minutes,
            )
            for weekday, start, end, slot_minutes in blocks
        ],
    )
    session.add(doctor)
    session.commit()
    return doctor


def create_patient(
    session: Session,
    *,
    full_name: str = "Bruno Tavares",
    email: str = "bruno.tavares@example.com",
    phone: str = "(11) 95555-0001",
) -> Patient:
    patient = Patient(full_name=full_name, email=email, phone=phone)
    session.add(patient)
    session.commit()
    return patient


def create_appointment(
    session: Session,
    *,
    patient: Patient,
    doctor: Doctor,
    starts_at: datetime,
    minutes: int = 30,
    cancelled_at: datetime | None = None,
) -> Appointment:
    appointment = Appointment(
        patient=patient,
        doctor=doctor,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        status=AppointmentStatus.CANCELLED if cancelled_at else AppointmentStatus.SCHEDULED,
        price_cents=doctor.specialty.price_cents,
        cancelled_at=cancelled_at,
    )
    session.add(appointment)
    session.commit()
    return appointment
