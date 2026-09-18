from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clinic_api.db import get_session
from clinic_api.main import create_app


def test_health_reports_database_ok_without_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-API-Key": ""})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_degraded_when_database_is_unreachable(client: TestClient) -> None:
    unreachable = create_engine("sqlite:////nonexistent/directory/clinic.db")

    def broken_session() -> Iterator[Session]:
        with Session(unreachable) as session:
            yield session

    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_session] = broken_session

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_unexpected_error_uses_error_envelope() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
