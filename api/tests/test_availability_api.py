from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_api.models import Doctor
from tests.conftest import FIXED_NOW
from tests.factories import create_appointment, create_doctor, create_patient

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def doctor(session: Session) -> Doctor:
    return create_doctor(session)


def _slots_by_date(body: dict[str, object]) -> dict[str, list[str]]:
    doctors = body["doctors"]
    assert isinstance(doctors, list)
    return {day["date"]: day["slots"] for day in doctors[0]["days"]}


def test_availability_excludes_past_and_booked_slots(
    client: TestClient, session: Session, doctor: Doctor
) -> None:
    patient = create_patient(session)
    create_appointment(
        session,
        patient=patient,
        doctor=doctor,
        starts_at=datetime(2026, 9, 17, 8, 30, tzinfo=SAO_PAULO),
    )

    response = client.get(
        "/api/v1/availability", params={"date_from": "2026-09-16", "date_to": "2026-09-17"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "America/Sao_Paulo"
    assert _slots_by_date(body) == {
        "2026-09-16": ["2026-09-16T09:30:00-03:00"],
        "2026-09-17": [
            "2026-09-17T08:00:00-03:00",
            "2026-09-17T09:00:00-03:00",
            "2026-09-17T09:30:00-03:00",
        ],
    }
    assert body["doctors"][0]["days"][1]["weekday_name"] == "quinta-feira"


def test_cancelled_appointment_frees_the_slot(
    client: TestClient, session: Session, doctor: Doctor
) -> None:
    create_appointment(
        session,
        patient=create_patient(session),
        doctor=doctor,
        starts_at=datetime(2026, 9, 17, 8, 0, tzinfo=SAO_PAULO),
        cancelled_at=FIXED_NOW,
    )

    body = client.get("/api/v1/availability", params={"date_from": "2026-09-17"}).json()

    assert "2026-09-17T08:00:00-03:00" in _slots_by_date(body)["2026-09-17"]


@pytest.mark.usefixtures("doctor")
def test_availability_defaults_to_the_next_seven_days(client: TestClient) -> None:
    body = client.get("/api/v1/availability?doctor_id=&specialty_id=").json()

    assert (body["date_from"], body["date_to"]) == ("2026-09-16", "2026-09-22")
    assert list(_slots_by_date(body)) == ["2026-09-16", "2026-09-17"]


@pytest.mark.usefixtures("doctor")
@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"date_from": "2026-09-20", "date_to": "2026-09-19"}, "INVALID_DATE_RANGE"),
        ({"date_from": "2026-09-16", "date_to": "2026-09-30"}, "DATE_RANGE_TOO_LARGE"),
        ({"date_from": "16/09/2026"}, "VALIDATION_ERROR"),
    ],
)
def test_availability_rejects_invalid_ranges(
    client: TestClient, params: dict[str, str], code: str
) -> None:
    response = client.get("/api/v1/availability", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


@pytest.mark.usefixtures("doctor")
def test_availability_for_unknown_doctor_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/availability", params={"doctor_id": 999})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCTOR_NOT_FOUND"
