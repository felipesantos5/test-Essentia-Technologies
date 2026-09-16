from fastapi import APIRouter

from clinic_api.api.deps import NowDep, SessionDep, SettingsDep
from clinic_api.api.params import OptionalDateQuery, OptionalIdQuery
from clinic_api.schemas.availability import AvailabilityRead
from clinic_api.schemas.common import error_responses
from clinic_api.services.availability import get_availability

router = APIRouter(tags=["availability"])


@router.get(
    "/availability",
    summary="Free appointment slots per doctor",
    description=(
        "Computed from each doctor's weekly schedule minus active appointments and past times. "
        "Defaults to the next 7 days; the range is limited by `CLINIC_AVAILABILITY_MAX_DAYS`. "
        "Slot times are returned in the clinic timezone with an explicit UTC offset."
    ),
    responses=error_responses(404, 422),
)
def availability(
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    specialty_id: OptionalIdQuery = None,
    doctor_id: OptionalIdQuery = None,
    date_from: OptionalDateQuery = None,
    date_to: OptionalDateQuery = None,
) -> AvailabilityRead:
    result = get_availability(
        session,
        settings=settings,
        now=now,
        date_from=date_from,
        date_to=date_to,
        specialty_id=specialty_id,
        doctor_id=doctor_id,
    )
    return AvailabilityRead.from_domain(result, settings.timezone)
