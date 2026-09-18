from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_api.api.deps import get_availability_cache, get_now
from clinic_api.config import Settings, get_settings
from clinic_api.db import Base, create_db_engine, get_session
from clinic_api.main import create_app
from clinic_api.services.availability import AvailabilityCache

API_KEY = "test-api-key"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
# Wednesday, 2026-09-16 09:00 in America/Sao_Paulo.
FIXED_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_key=SecretStr(API_KEY),
        timezone="America/Sao_Paulo",
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def availability_cache(settings: Settings) -> AvailabilityCache:
    # Per test: the app's process-wide cache would leak entries between test databases.
    return AvailabilityCache(ttl_seconds=settings.availability_cache_ttl_seconds)


@pytest.fixture
def client(
    settings: Settings,
    session_factory: sessionmaker[Session],
    availability_cache: AvailabilityCache,
) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    app.dependency_overrides[get_availability_cache] = lambda: availability_cache
    with TestClient(app, headers={"X-API-Key": API_KEY}) as test_client:
        yield test_client
