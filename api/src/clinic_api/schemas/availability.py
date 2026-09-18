from datetime import date, datetime
from typing import Self

from pydantic import BaseModel

from clinic_api.schemas.catalog import Money, SpecialtyRead
from clinic_api.schemas.common import WEEKDAY_NAMES_PT_BR
from clinic_api.services.availability import Availability, DaySlots, DoctorAvailability


class AvailableDayRead(BaseModel):
    date: date
    weekday_name: str
    slots: list[datetime]

    @classmethod
    def from_domain(cls, day: DaySlots) -> Self:
        return cls(
            date=day.day,
            weekday_name=WEEKDAY_NAMES_PT_BR[day.day.weekday()],
            slots=list(day.slots),
        )


class DoctorAvailabilityRead(BaseModel):
    doctor_id: int
    doctor_name: str
    specialty: SpecialtyRead
    days: list[AvailableDayRead]

    @classmethod
    def from_domain(cls, item: DoctorAvailability) -> Self:
        doctor = item.doctor
        return cls(
            doctor_id=doctor.id,
            doctor_name=doctor.full_name,
            specialty=SpecialtyRead(
                id=doctor.specialty_id,
                name=doctor.specialty_name,
                consultation_price=Money.from_cents(doctor.price_cents),
            ),
            days=[AvailableDayRead.from_domain(day) for day in item.days],
        )


class AvailabilityRead(BaseModel):
    timezone: str
    date_from: date
    date_to: date
    doctors: list[DoctorAvailabilityRead]

    @classmethod
    def from_domain(cls, availability: Availability, timezone: str) -> Self:
        return cls(
            timezone=timezone,
            date_from=availability.date_from,
            date_to=availability.date_to,
            doctors=[DoctorAvailabilityRead.from_domain(item) for item in availability.doctors],
        )
