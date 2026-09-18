from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_api.services import patients
from tests.conftest import FIXED_NOW, SAO_PAULO
from tests.factories import create_appointment, create_doctor, create_patient


def test_search_patients_by_email_is_case_insensitive(client: TestClient, session: Session) -> None:
    patient = create_patient(session)

    body = client.get("/api/v1/patients", params={"email": " Bruno.Tavares@Example.com "}).json()

    assert body == [
        {
            "id": patient.id,
            "full_name": "Bruno Tavares",
            "email": "bruno.tavares@example.com",
            "phone": "(11) 95555-0001",
        }
    ]


def test_search_patients_with_unknown_email_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/v1/patients", params={"email": "nobody@example.com"})

    assert response.status_code == 200
    assert response.json() == []


def test_create_patient_normalizes_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/patients",
        json={
            "full_name": "  Fernanda Ribeiro ",
            "email": "Fernanda.Ribeiro@Example.com",
            "phone": "(11) 97777-2002",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] == "Fernanda Ribeiro"
    assert response.json()["email"] == "fernanda.ribeiro@example.com"


def test_create_patient_with_existing_email_returns_409(
    client: TestClient, session: Session
) -> None:
    create_patient(session)

    response = client.post(
        "/api/v1/patients",
        json={
            "full_name": "Outro Nome",
            "email": "BRUNO.TAVARES@example.com",
            "phone": "(11) 90000-0000",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PATIENT_EMAIL_ALREADY_EXISTS"


def test_concurrent_registration_with_same_email_returns_409(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The lookup misses (as if the other request committed right after it); the unique index
    # on `patients.email` still has to turn the collision into the same 409.
    create_patient(session)
    monkeypatch.setattr(patients, "find_patients", lambda *_args, **_kwargs: [])

    response = client.post(
        "/api/v1/patients",
        json={
            "full_name": "Outro Nome",
            "email": "bruno.tavares@example.com",
            "phone": "(11) 90000-0000",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PATIENT_EMAIL_ALREADY_EXISTS"


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "Ana", "email": "not-an-email", "phone": "(11) 90000-0000"},
        {"full_name": "Ana Lima", "email": "ana@example.com", "phone": "call me"},
        {"full_name": "", "email": "ana@example.com", "phone": "(11) 90000-0000"},
    ],
)
def test_create_patient_validates_payload(client: TestClient, payload: dict[str, str]) -> None:
    response = client.post("/api/v1/patients", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_unknown_patient_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/patients/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_list_patient_appointments_filters_upcoming_and_status(
    client: TestClient, session: Session
) -> None:
    doctor = create_doctor(session)
    patient = create_patient(session)
    past = create_appointment(
        session,
        patient=patient,
        doctor=doctor,
        starts_at=datetime(2026, 9, 10, 8, 0, tzinfo=SAO_PAULO),
    )
    upcoming = create_appointment(
        session,
        patient=patient,
        doctor=doctor,
        starts_at=datetime(2026, 9, 17, 8, 0, tzinfo=SAO_PAULO),
    )
    create_appointment(
        session,
        patient=patient,
        doctor=doctor,
        starts_at=datetime(2026, 9, 17, 9, 0, tzinfo=SAO_PAULO),
        cancelled_at=FIXED_NOW,
    )
    url = f"/api/v1/patients/{patient.id}/appointments"

    all_ids = [item["id"] for item in client.get(url).json()]
    upcoming_scheduled = client.get(url, params={"status": "scheduled", "upcoming": "true"}).json()
    past_items = client.get(url, params={"upcoming": "false", "status": ""}).json()

    assert len(all_ids) == 3
    assert [item["id"] for item in upcoming_scheduled] == [upcoming.id]
    assert [item["id"] for item in past_items] == [past.id]


def test_list_appointments_of_unknown_patient_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/patients/999/appointments")

    assert response.status_code == 404
