from datetime import time
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict

from clinic_api.models import Doctor, DoctorSchedule, Specialty
from clinic_api.services.slots import WEEKDAY_NAMES_PT_BR


class Money(BaseModel):
    amount: Decimal
    currency: Literal["BRL"] = "BRL"
    formatted: str

    @classmethod
    def from_cents(cls, cents: int) -> Self:
        amount = (Decimal(cents) / 100).quantize(Decimal("0.01"))
        integer, _, fraction = f"{amount:,.2f}".partition(".")
        return cls(amount=amount, formatted=f"R$ {integer.replace(',', '.')},{fraction}")


class SpecialtyRead(BaseModel):
    id: int
    name: str
    consultation_price: Money

    @classmethod
    def from_model(cls, specialty: Specialty) -> Self:
        return cls(
            id=specialty.id,
            name=specialty.name,
            consultation_price=Money.from_cents(specialty.price_cents),
        )


class WorkingHoursRead(BaseModel):
    weekday: int
    weekday_name: str
    start_time: time
    end_time: time
    slot_minutes: int

    @classmethod
    def from_model(cls, schedule: DoctorSchedule) -> Self:
        return cls(
            weekday=schedule.weekday,
            weekday_name=WEEKDAY_NAMES_PT_BR[schedule.weekday],
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            slot_minutes=schedule.slot_minutes,
        )


class DoctorRead(BaseModel):
    id: int
    full_name: str
    crm: str
    specialty: SpecialtyRead
    working_hours: list[WorkingHoursRead]

    @classmethod
    def from_model(cls, doctor: Doctor) -> Self:
        return cls(
            id=doctor.id,
            full_name=doctor.full_name,
            crm=doctor.crm,
            specialty=SpecialtyRead.from_model(doctor.specialty),
            working_hours=[WorkingHoursRead.from_model(block) for block in doctor.schedules],
        )


class PaymentMethodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    max_installments: int | None


class PaymentInfoRead(BaseModel):
    consultation_prices: list[SpecialtyRead]
    payment_methods: list[PaymentMethodRead]


class ClinicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    address: str
    phone: str
    email: str
    greeting_message: str
    closing_message: str
