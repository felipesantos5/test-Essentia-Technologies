from typing import Any, Literal

from pydantic import BaseModel

# Index = Python weekday (Monday = 0); used wherever a date is rendered for the patient.
WEEKDAY_NAMES_PT_BR = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries documenting the standard error envelope."""
    return {code: {"model": ErrorResponse} for code in status_codes}
