import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_api.config import Settings
from clinic_api.schemas.catalog import Money
from clinic_api.seed import seed_database
from tests.conftest import FIXED_NOW


@pytest.fixture
def seeded(session: Session, settings: Settings) -> None:
    seed_database(session, settings, FIXED_NOW)


@pytest.mark.parametrize(
    ("cents", "formatted"),
    [(38000, "R$ 380,00"), (123456, "R$ 1.234,56"), (5, "R$ 0,05")],
)
def test_money_formats_brazilian_reais(cents: int, formatted: str) -> None:
    assert Money.from_cents(cents).formatted == formatted


@pytest.mark.usefixtures("seeded")
def test_get_clinic_returns_configured_messages(client: TestClient) -> None:
    body = client.get("/api/v1/clinic").json()

    assert body["name"] == "Clínica Essentia Saúde"
    assert body["greeting_message"].startswith("Olá!")
    assert body["closing_message"]


def test_get_clinic_without_seed_returns_not_configured(client: TestClient) -> None:
    response = client.get("/api/v1/clinic")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLINIC_NOT_CONFIGURED"


@pytest.mark.usefixtures("seeded")
def test_list_specialties_includes_formatted_price(client: TestClient) -> None:
    specialties = {item["name"]: item for item in client.get("/api/v1/specialties").json()}

    assert specialties["Cardiologia"]["consultation_price"] == {
        "amount": "380.00",
        "currency": "BRL",
        "formatted": "R$ 380,00",
    }


@pytest.mark.usefixtures("seeded")
def test_list_doctors_filters_by_specialty(client: TestClient) -> None:
    specialties = {item["name"]: item["id"] for item in client.get("/api/v1/specialties").json()}

    doctors = client.get(
        "/api/v1/doctors", params={"specialty_id": specialties["Cardiologia"]}
    ).json()

    assert [doctor["full_name"] for doctor in doctors] == ["Dr. Carlos Eduardo Lima"]
    assert doctors[0]["working_hours"][0]["weekday_name"] == "terça-feira"


@pytest.mark.usefixtures("seeded")
def test_list_doctors_treats_blank_filter_as_absent(client: TestClient) -> None:
    response = client.get("/api/v1/doctors?specialty_id=")

    assert response.status_code == 200
    assert len(response.json()) == 4


@pytest.mark.usefixtures("seeded")
def test_list_doctors_with_unknown_specialty_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/doctors", params={"specialty_id": 999})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPECIALTY_NOT_FOUND"


@pytest.mark.usefixtures("seeded")
def test_payment_info_lists_prices_and_active_methods_in_order(client: TestClient) -> None:
    body = client.get("/api/v1/payment-info").json()

    assert len(body["consultation_prices"]) == 4
    assert [method["code"] for method in body["payment_methods"]] == [
        "pix",
        "credit_card",
        "debit_card",
        "cash",
    ]
    assert body["payment_methods"][1]["max_installments"] == 3
