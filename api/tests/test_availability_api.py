from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_api.api.deps import get_now
from clinic_api.models import Doctor, Patient
from clinic_api.services.availability import AvailabilityCache
from tests.conftest import FIXED_NOW, SAO_PAULO
from tests.factories import create_appointment, create_doctor, create_patient

THURSDAY = {"date_from": "2026-09-17", "date_to": "2026-09-17"}


@pytest.fixture
def doctor(session: Session) -> Doctor:
    return create_doctor(session)


def _slots_by_date(body: dict[str, object]) -> dict[str, list[str]]:
    doctors = body["doctors"]
    assert isinstance(doctors, list)
    return {day["date"]: day["slots"] for day in doctors[0]["days"]}


def _thursday_slots(client: TestClient) -> list[str]:
    return _slots_by_date(client.get("/api/v1/availability", params=THURSDAY).json())["2026-09-17"]


def _book(client: TestClient, patient: Patient, doctor: Doctor, starts_at: str) -> int:
    response = client.post(
        "/api/v1/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "starts_at": starts_at},
    )
    assert response.status_code == 201
    appointment_id = response.json()["id"]
    assert isinstance(appointment_id, int)
    return appointment_id


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
def test_default_date_from_is_the_clinic_local_date(client: TestClient) -> None:
    # 01:00 UTC on the 17th is still 22:00 on the 16th in São Paulo.
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_now] = lambda: datetime(2026, 9, 17, 1, 0, tzinfo=UTC)

    body = client.get("/api/v1/availability").json()

    assert body["date_from"] == "2026-09-16"


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


class TestAvailabilityCache:
    def test_repeated_query_is_served_from_cache_until_a_booking_invalidates_it(
        self, client: TestClient, session: Session, doctor: Doctor
    ) -> None:
        patient = create_patient(session)
        assert "2026-09-17T08:00:00-03:00" in _thursday_slots(client)

        # Written straight to the database, so only a fresh computation can see it.
        create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 17, 8, 0, tzinfo=SAO_PAULO),
        )
        assert "2026-09-17T08:00:00-03:00" in _thursday_slots(client)

        _book(client, patient, doctor, "2026-09-17T08:30:00-03:00")

        assert _thursday_slots(client) == ["2026-09-17T09:00:00-03:00", "2026-09-17T09:30:00-03:00"]

    def test_cancellation_invalidates_the_cache(
        self, client: TestClient, session: Session, doctor: Doctor
    ) -> None:
        patient = create_patient(session)
        appointment_id = _book(client, patient, doctor, "2026-09-17T08:00:00-03:00")
        assert "2026-09-17T08:00:00-03:00" not in _thursday_slots(client)

        response = client.post(
            f"/api/v1/appointments/{appointment_id}/cancel",
            json={"patient_email": patient.email},
        )
        assert response.status_code == 200

        assert "2026-09-17T08:00:00-03:00" in _thursday_slots(client)

    @pytest.mark.usefixtures("doctor")
    def test_cached_entry_never_offers_a_slot_that_already_started(
        self, client: TestClient, availability_cache: AvailabilityCache
    ) -> None:
        params = {"date_from": "2026-09-16", "date_to": "2026-09-17"}
        assert "2026-09-16" in _slots_by_date(
            client.get("/api/v1/availability", params=params).json()
        )

        app = client.app
        assert isinstance(app, FastAPI)
        app.dependency_overrides[get_now] = lambda: FIXED_NOW + timedelta(minutes=45)  # 09:45
        body = client.get("/api/v1/availability", params=params).json()

        assert len(availability_cache) == 1
        assert list(_slots_by_date(body)) == ["2026-09-17"]

    @pytest.mark.usefixtures("doctor")
    def test_each_filter_combination_has_its_own_entry(
        self, client: TestClient, availability_cache: AvailabilityCache
    ) -> None:
        client.get("/api/v1/availability", params=THURSDAY)
        client.get("/api/v1/availability", params={**THURSDAY, "specialty_id": 1})
        client.get("/api/v1/availability", params=THURSDAY)

        assert len(availability_cache) == 2

    @pytest.mark.usefixtures("doctor")
    def test_failed_lookups_are_not_cached(
        self, client: TestClient, availability_cache: AvailabilityCache
    ) -> None:
        client.get("/api/v1/availability", params={"doctor_id": 999})
        client.get(
            "/api/v1/availability", params={"date_from": "2026-09-20", "date_to": "2026-09-19"}
        )

        assert len(availability_cache) == 0
