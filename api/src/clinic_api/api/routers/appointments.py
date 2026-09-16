from typing import Annotated

from fastapi import APIRouter, Path, status

from clinic_api.api.deps import NowDep, SessionDep, SettingsDep
from clinic_api.schemas.appointments import AppointmentCancel, AppointmentCreate, AppointmentRead
from clinic_api.schemas.common import error_responses
from clinic_api.services import appointments

router = APIRouter(prefix="/appointments", tags=["appointments"])

AppointmentId = Annotated[int, Path(gt=0)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment",
    description=(
        "The time must be a free slot returned by `/availability`. Conflicts return 409 with "
        "`SLOT_UNAVAILABLE`, `PATIENT_TIME_CONFLICT` or `APPOINTMENT_ALREADY_BOOKED`."
    ),
    responses=error_responses(404, 409, 422),
)
def book_appointment(
    data: AppointmentCreate, session: SessionDep, settings: SettingsDep, now: NowDep
) -> AppointmentRead:
    appointment = appointments.book_appointment(session, data, now=now, tz=settings.tz)
    return AppointmentRead.from_model(appointment, settings.tz)


@router.get("/{appointment_id}", summary="Get an appointment", responses=error_responses(404))
def get_appointment(
    appointment_id: AppointmentId, session: SessionDep, settings: SettingsDep
) -> AppointmentRead:
    appointment = appointments.get_appointment(session, appointment_id)
    return AppointmentRead.from_model(appointment, settings.tz)


@router.post(
    "/{appointment_id}/cancel",
    summary="Cancel an appointment",
    description="Keeps the record with status `cancelled`. Past appointments cannot be cancelled.",
    responses=error_responses(404, 409, 422),
)
def cancel_appointment(
    appointment_id: AppointmentId,
    data: AppointmentCancel,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
) -> AppointmentRead:
    appointment = appointments.cancel_appointment(session, appointment_id, data, now=now)
    return AppointmentRead.from_model(appointment, settings.tz)
