from __future__ import annotations

from datetime import UTC, datetime, time
from enum import StrEnum
from typing import override

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clinic_api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Persists aware datetimes as naive UTC and returns them UTC-aware.

    SQLite has no timezone support, so `DateTime(timezone=True)` would silently drop offsets.
    """

    impl = DateTime
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; pass a timezone-aware value")
        return value.astimezone(UTC).replace(tzinfo=None)

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


SCHEDULED_ONLY = text("status = 'scheduled'")


class Clinic(Base):
    __tablename__ = "clinic"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(255))
    greeting_message: Mapped[str] = mapped_column(Text)
    closing_message: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Specialty(Base):
    __tablename__ = "specialties"
    __table_args__ = (CheckConstraint("price_cents > 0", name="price_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    price_cents: Mapped[int] = mapped_column(Integer)

    doctors: Mapped[list[Doctor]] = relationship(back_populates="specialty")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    crm: Mapped[str] = mapped_column(String(20), unique=True)
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    specialty: Mapped[Specialty] = relationship(back_populates="doctors")
    schedules: Mapped[list[DoctorSchedule]] = relationship(
        back_populates="doctor",
        cascade="all, delete-orphan",
        order_by="(DoctorSchedule.weekday, DoctorSchedule.start_time)",
    )


class DoctorSchedule(Base):
    """Recurring weekly working block, in clinic local time. Weekday follows Python: Monday=0."""

    __tablename__ = "doctor_schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_time < end_time", name="start_before_end"),
        CheckConstraint("slot_minutes > 0", name="slot_minutes_positive"),
        UniqueConstraint("doctor_id", "weekday", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int] = mapped_column(SmallInteger)

    doctor: Mapped[Doctor] = relationship(back_populates="schedules")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    appointments: Mapped[list[Appointment]] = relationship(back_populates="patient")


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    __table_args__ = (
        CheckConstraint(
            "max_installments IS NULL OR max_installments >= 1", name="max_installments_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(255))
    max_installments: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint("price_cents > 0", name="price_positive"),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="cancelled_at_matches_status",
        ),
        # A doctor and a patient can each hold only one active appointment per start time.
        # Cancelled rows are kept as history, hence the partial indexes.
        Index(
            "uq_appointments_doctor_id_starts_at_scheduled",
            "doctor_id",
            "starts_at",
            unique=True,
            sqlite_where=SCHEDULED_ONLY,
            postgresql_where=SCHEDULED_ONLY,
        ),
        Index(
            "uq_appointments_patient_id_starts_at_scheduled",
            "patient_id",
            "starts_at",
            unique=True,
            sqlite_where=SCHEDULED_ONLY,
            postgresql_where=SCHEDULED_ONLY,
        ),
        Index("ix_appointments_patient_id_status_starts_at", "patient_id", "status", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)  # period listings
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Stored as VARCHAR + CHECK constraint (portable across SQLite and Postgres); the lambda
    # persists the values ("scheduled"), not the member names ("SCHEDULED").
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            name="appointment_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AppointmentStatus.SCHEDULED,
    )
    price_cents: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    patient: Mapped[Patient] = relationship(back_populates="appointments")
    doctor: Mapped[Doctor] = relationship()
