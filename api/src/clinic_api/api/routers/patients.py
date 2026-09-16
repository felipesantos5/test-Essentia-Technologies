from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from pydantic import BeforeValidator

from clinic_api.api.deps import NowDep, SessionDep, SettingsDep
from clinic_api.api.params import OptionalBoolQuery, blank_as_none
from clinic_api.models import AppointmentStatus
from clinic_api.schemas.appointments import AppointmentRead
from clinic_api.schemas.common import error_responses
from clinic_api.schemas.patients import PatientCreate, PatientRead
from clinic_api.services import appointments, patients

router = APIRouter(prefix="/patients", tags=["patients"])

PatientId = Annotated[int, Path(gt=0)]
EmailQuery = Annotated[
    str | None,
    Query(description="Exact, case-insensitive match. Returns an empty list when not found."),
    BeforeValidator(blank_as_none),
]
StatusQuery = Annotated[AppointmentStatus | None, Query(), BeforeValidator(blank_as_none)]


@router.get("", summary="Search patients by email")
def search_patients(session: SessionDep, email: EmailQuery = None) -> list[PatientRead]:
    return [
        PatientRead.model_validate(item) for item in patients.find_patients(session, email=email)
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Register a patient",
    responses=error_responses(409, 422),
)
def create_patient(data: PatientCreate, session: SessionDep) -> PatientRead:
    return PatientRead.model_validate(patients.create_patient(session, data))


@router.get("/{patient_id}", summary="Get a patient", responses=error_responses(404))
def get_patient(patient_id: PatientId, session: SessionDep) -> PatientRead:
    return PatientRead.model_validate(patients.get_patient(session, patient_id))


@router.get(
    "/{patient_id}/appointments",
    summary="List a patient's appointments",
    description="`upcoming=true` keeps only future appointments; `false` only past ones.",
    responses=error_responses(404),
)
def list_patient_appointments(
    patient_id: PatientId,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    status: StatusQuery = None,
    upcoming: OptionalBoolQuery = None,
) -> list[AppointmentRead]:
    items = appointments.list_patient_appointments(
        session, patient_id=patient_id, now=now, status=status, upcoming=upcoming
    )
    return [AppointmentRead.from_model(item, settings.tz) for item in items]
