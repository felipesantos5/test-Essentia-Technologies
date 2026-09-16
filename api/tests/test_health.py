from fastapi.testclient import TestClient


def test_health_reports_database_ok_without_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-API-Key": ""})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
