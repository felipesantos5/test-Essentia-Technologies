from datetime import datetime
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StringConstraints

from clinic_api.models import Appointment, AppointmentStatus
from clinic_api.schemas.catalog import Money
from clinic_api.schemas.patients import NormalizedEmail, PatientRead
from clinic_api.services.slots import WEEKDAY_NAMES_PT_BR

OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "patient_id": 1,
                    "doctor_id": 2,
                    "starts_at": "2026-09-17T08:40:00-03:00",
                    "notes": "Primeira consulta.",
                }
            ]
        }
    )

    patient_id: PositiveInt
    doctor_id: PositiveInt
    starts_at: datetime = Field(
        description="Slot start from /availability. Values without offset use the clinic timezone."
    )
    notes: OptionalText = None


class AppointmentCancel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"patient_email": "joao.pereira@example.com", "reason": "Viagem."}]
        }
    )

    patient_email: NormalizedEmail = Field(
        description="Must match the appointment's patient; acts as a lightweight ownership check."
    )
    reason: OptionalText = None


class AppointmentDoctorRead(BaseModel):
    id: int
    full_name: str
    specialty: str


class AppointmentRead(BaseModel):
    id: int
    status: AppointmentStatus
    starts_at: datetime
    ends_at: datetime
    weekday_name: str
    price: Money
    notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    patient: PatientRead
    doctor: AppointmentDoctorRead

    @classmethod
    def from_model(cls, appointment: Appointment, tz: ZoneInfo) -> Self:
        starts_at = appointment.starts_at.astimezone(tz)
        return cls(
            id=appointment.id,
            status=appointment.status,
            starts_at=starts_at,
            ends_at=appointment.ends_at.astimezone(tz),
            weekday_name=WEEKDAY_NAMES_PT_BR[starts_at.weekday()],
            price=Money.from_cents(appointment.price_cents),
            notes=appointment.notes,
            cancellation_reason=appointment.cancellation_reason,
            cancelled_at=appointment.cancelled_at.astimezone(tz)
            if appointment.cancelled_at
            else None,
            patient=PatientRead.model_validate(appointment.patient),
            doctor=AppointmentDoctorRead(
                id=appointment.doctor.id,
                full_name=appointment.doctor.full_name,
                specialty=appointment.doctor.specialty.name,
            ),
        )
