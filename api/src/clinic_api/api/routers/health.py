from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from clinic_api.api.deps import SessionDep
from clinic_api.schemas.common import HealthRead

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness and database connectivity")
def health(session: SessionDep, response: Response) -> HealthRead:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthRead(status="degraded", database="unavailable")
    return HealthRead(status="ok", database="ok")
