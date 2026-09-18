"""Reusable query parameter types.

n8n's HTTP Request tool sends optional parameters the model left out as empty strings
(`?doctor_id=`), so blank values are treated as "not provided" instead of failing validation.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import Query
from pydantic import BeforeValidator

from clinic_api.models import AppointmentStatus


def blank_as_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalIdQuery = Annotated[int | None, Query(gt=0), BeforeValidator(blank_as_none)]
OptionalDateQuery = Annotated[
    date | None,
    Query(description="Local date in the clinic timezone (YYYY-MM-DD)."),
    BeforeValidator(blank_as_none),
]
OptionalBoolQuery = Annotated[bool | None, Query(), BeforeValidator(blank_as_none)]
# Exposed as `?status=`; the Python name avoids shadowing `fastapi.status` in the routers.
StatusFilterQuery = Annotated[
    AppointmentStatus | None, Query(alias="status"), BeforeValidator(blank_as_none)
]
