import pytest
from fastapi.testclient import TestClient

from tests.conftest import API_KEY


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}, {"X-API-Key": ""}])
def test_protected_routes_reject_missing_or_invalid_key(
    client: TestClient, headers: dict[str, str]
) -> None:
    client.headers.pop("X-API-Key")

    response = client.get("/api/v1/specialties", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


def test_protected_routes_accept_valid_key(client: TestClient) -> None:
    response = client.get("/api/v1/specialties", headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
