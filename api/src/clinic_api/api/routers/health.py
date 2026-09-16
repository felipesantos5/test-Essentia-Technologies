from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from clinic_api.api.deps import SessionDep

router = APIRouter(tags=["health"])


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@router.get("/health", summary="Liveness and database connectivity")
def health(session: SessionDep, response: Response) -> HealthRead:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthRead(status="degraded", database="unavailable")
    return HealthRead(status="ok", database="ok")
