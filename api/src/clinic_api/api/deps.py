import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from clinic_api.config import Settings, get_settings
from clinic_api.db import get_session
from clinic_api.errors import AuthenticationError


def get_now() -> datetime:
    return datetime.now(UTC)


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    settings: SettingsDep, api_key: Annotated[str | None, Security(_api_key_header)]
) -> None:
    expected = settings.api_key.get_secret_value().encode()
    if api_key is None or not secrets.compare_digest(api_key.encode(), expected):
        raise AuthenticationError("INVALID_API_KEY", "Missing or invalid X-API-Key header.")
