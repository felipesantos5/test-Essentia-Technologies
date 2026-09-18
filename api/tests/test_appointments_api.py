from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_api.models import Doctor, Patient
from clinic_api.services import appointments
from tests.conftest import SAO_PAULO
from tests.factories import THURSDAY, create_appointment, create_doctor, create_patient

THURSDAY_8AM = datetime(2026, 9, 17, 8, 0, tzinfo=SAO_PAULO)


@pytest.fixture
def doctor(session: Session) -> Doctor:
    return create_doctor(session)


@pytest.fixture
def patient(session: Session) -> Patient:
    return create_patient(session)


def _book(client: TestClient, patient: Patient, doctor: Doctor, starts_at: str) -> Any:
    return client.post(
        "/api/v1/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "starts_at": starts_at},
    )


def _error_code(response: Any) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


class TestBookAppointment:
    def test_books_free_slot_and_returns_details_for_the_confirmation_email(
        self, client: TestClient, patient: Patient, doctor: Doctor
    ) -> None:
        response = client.post(
            "/api/v1/appointments",
            json={
                "patient_id": patient.id,
                "doctor_id": doctor.id,
                "starts_at": "2026-09-17T08:00:00-03:00",
                "notes": "Dor no peito.",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "scheduled"
        assert body["starts_at"] == "2026-09-17T08:00:00-03:00"
        assert body["ends_at"] == "2026-09-17T08:30:00-03:00"
        assert body["weekday_name"] == "quinta-feira"
        assert body["price"]["formatted"] == "R$ 380,00"
        assert body["patient"]["email"] == "bruno.tavares@example.com"
        assert body["doctor"] == {
            "id": doctor.id,
            "full_name": "Dra. Helena Duarte",
            "specialty": "Cardiologia",
        }

    @pytest.mark.parametrize("starts_at", ["2026-09-17T08:00:00", "2026-09-17T11:00:00Z"])
    def test_accepts_naive_local_time_and_other_offsets(
        self, client: TestClient, patient: Patient, doctor: Doctor, starts_at: str
    ) -> None:
        response = _book(client, patient, doctor, starts_at)

        assert response.status_code == 201
        assert response.json()["starts_at"] == "2026-09-17T08:00:00-03:00"

    def test_rejects_past_slot(self, client: TestClient, patient: Patient, doctor: Doctor) -> None:
        response = _book(client, patient, doctor, "2026-09-16T08:30:00-03:00")

        assert response.status_code == 422
        assert _error_code(response) == "SLOT_IN_PAST"

    @pytest.mark.parametrize(
        "starts_at",
        ["2026-09-17T08:15:00-03:00", "2026-09-17T10:00:00-03:00", "2026-09-18T08:00:00-03:00"],
    )
    def test_rejects_time_outside_schedule(
        self, client: TestClient, patient: Patient, doctor: Doctor, starts_at: str
    ) -> None:
        response = _book(client, patient, doctor, starts_at)

        assert response.status_code == 422
        assert _error_code(response) == "SLOT_OUTSIDE_SCHEDULE"

    def test_rejects_slot_taken_by_another_patient(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        other = create_patient(session, full_name="Carla Mendes", email="carla@example.com")
        create_appointment(session, patient=other, doctor=doctor, starts_at=THURSDAY_8AM)

        response = _book(client, patient, doctor, THURSDAY_8AM.isoformat())

        assert response.status_code == 409
        assert _error_code(response) == "SLOT_UNAVAILABLE"

    def test_repeated_booking_is_reported_as_already_booked(
        self, client: TestClient, patient: Patient, doctor: Doctor
    ) -> None:
        assert _book(client, patient, doctor, THURSDAY_8AM.isoformat()).status_code == 201

        response = _book(client, patient, doctor, THURSDAY_8AM.isoformat())

        assert response.status_code == 409
        assert _error_code(response) == "APPOINTMENT_ALREADY_BOOKED"

    def test_rejects_patient_overlap_with_another_doctor(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        other_doctor = create_doctor(
            session,
            full_name="Dr. Otávio Nunes",
            crm="CRM-SP 100002",
            specialty_name="Dermatologia",
            blocks=((THURSDAY, "08:15", "09:15", 60),),
        )
        create_appointment(
            session,
            patient=patient,
            doctor=other_doctor,
            starts_at=datetime(2026, 9, 17, 8, 15, tzinfo=SAO_PAULO),
            minutes=60,
        )

        response = _book(client, patient, doctor, "2026-09-17T08:30:00-03:00")

        assert response.status_code == 409
        assert _error_code(response) == "PATIENT_TIME_CONFLICT"

    def test_cancelled_slot_can_be_booked_again(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        other = create_patient(session, full_name="Carla Mendes", email="carla@example.com")
        create_appointment(
            session,
            patient=other,
            doctor=doctor,
            starts_at=THURSDAY_8AM,
            cancelled_at=datetime(2026, 9, 15, tzinfo=SAO_PAULO),
        )

        response = _book(client, patient, doctor, THURSDAY_8AM.isoformat())

        assert response.status_code == 201

    @pytest.mark.parametrize(
        ("field", "code"), [("patient_id", "PATIENT_NOT_FOUND"), ("doctor_id", "DOCTOR_NOT_FOUND")]
    )
    def test_unknown_patient_or_doctor_returns_404(
        self, client: TestClient, patient: Patient, doctor: Doctor, field: str, code: str
    ) -> None:
        payload = {
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "starts_at": THURSDAY_8AM.isoformat(),
            field: 999,
        }

        response = client.post("/api/v1/appointments", json=payload)

        assert response.status_code == 404
        assert _error_code(response) == code

    def test_inactive_doctor_cannot_be_booked(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        doctor.is_active = False
        session.commit()

        response = _book(client, patient, doctor, THURSDAY_8AM.isoformat())

        assert response.status_code == 404
        assert _error_code(response) == "DOCTOR_NOT_FOUND"

    def test_booking_that_loses_a_race_is_rejected_by_the_database(
        self,
        client: TestClient,
        session: Session,
        patient: Patient,
        doctor: Doctor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Simulates a concurrent booking committed between the conflict check and the insert:
        # the check sees nothing, and the partial unique index has to catch the collision.
        other = create_patient(session, full_name="Carla Mendes", email="carla@example.com")
        create_appointment(session, patient=other, doctor=doctor, starts_at=THURSDAY_8AM)
        monkeypatch.setattr(appointments, "_ensure_no_conflict", lambda *_args: None)

        response = _book(client, patient, doctor, THURSDAY_8AM.isoformat())

        assert response.status_code == 409
        assert _error_code(response) == "SLOT_UNAVAILABLE"


class TestCancelAppointment:
    def test_cancels_future_appointment_keeping_history(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        appointment = create_appointment(
            session, patient=patient, doctor=doctor, starts_at=THURSDAY_8AM
        )

        response = client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"patient_email": "Bruno.Tavares@example.com", "reason": "Viagem."},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["cancellation_reason"] == "Viagem."
        assert body["cancelled_at"] == "2026-09-16T09:00:00-03:00"
        assert client.get(f"/api/v1/appointments/{appointment.id}").json()["status"] == "cancelled"

    def test_email_mismatch_is_reported_as_not_found(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        appointment = create_appointment(
            session, patient=patient, doctor=doctor, starts_at=THURSDAY_8AM
        )

        response = client.post(
            f"/api/v1/appointments/{appointment.id}/cancel",
            json={"patient_email": "someone.else@example.com"},
        )

        assert response.status_code == 404
        assert _error_code(response) == "APPOINTMENT_NOT_FOUND"

    def test_cancelling_twice_returns_409(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        appointment = create_appointment(
            session, patient=patient, doctor=doctor, starts_at=THURSDAY_8AM
        )
        url = f"/api/v1/appointments/{appointment.id}/cancel"
        client.post(url, json={"patient_email": patient.email})

        response = client.post(url, json={"patient_email": patient.email})

        assert response.status_code == 409
        assert _error_code(response) == "APPOINTMENT_ALREADY_CANCELLED"

    def test_past_appointment_cannot_be_cancelled(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        appointment = create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 16, 8, 0, tzinfo=SAO_PAULO),
        )

        response = client.post(
            f"/api/v1/appointments/{appointment.id}/cancel", json={"patient_email": patient.email}
        )

        assert response.status_code == 422
        assert _error_code(response) == "APPOINTMENT_IN_PAST"


class TestListAppointments:
    def test_lists_the_period_in_order_including_cancelled(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        later = create_appointment(session, patient=patient, doctor=doctor, starts_at=THURSDAY_8AM)
        earlier = create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 16, 9, 30, tzinfo=SAO_PAULO),
        )
        cancelled = create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 17, 9, 0, tzinfo=SAO_PAULO),
            cancelled_at=datetime(2026, 9, 15, tzinfo=SAO_PAULO),
        )
        create_appointment(  # outside the default 7-day window
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 24, 8, 0, tzinfo=SAO_PAULO),
        )

        body = client.get("/api/v1/appointments").json()

        assert (body["date_from"], body["date_to"]) == ("2026-09-16", "2026-09-22")
        assert body["timezone"] == "America/Sao_Paulo"
        assert [item["id"] for item in body["appointments"]] == [earlier.id, later.id, cancelled.id]
        assert body["appointments"][0]["starts_at"] == "2026-09-16T09:30:00-03:00"

    def test_filters_by_status_and_doctor(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        other_doctor = create_doctor(
            session, full_name="Dr. Otávio Nunes", crm="CRM-SP 100002", specialty_name="Pediatria"
        )
        scheduled = create_appointment(
            session, patient=patient, doctor=doctor, starts_at=THURSDAY_8AM
        )
        create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 17, 9, 0, tzinfo=SAO_PAULO),
            cancelled_at=datetime(2026, 9, 15, tzinfo=SAO_PAULO),
        )
        elsewhere = create_appointment(
            session,
            patient=patient,
            doctor=other_doctor,
            starts_at=datetime(2026, 9, 17, 9, 30, tzinfo=SAO_PAULO),
        )

        by_status = client.get("/api/v1/appointments", params={"status": "scheduled"}).json()
        by_doctor = client.get("/api/v1/appointments", params={"doctor_id": other_doctor.id}).json()

        assert [item["id"] for item in by_status["appointments"]] == [scheduled.id, elsewhere.id]
        assert [item["id"] for item in by_doctor["appointments"]] == [elsewhere.id]

    def test_period_boundaries_follow_the_clinic_timezone(
        self, client: TestClient, session: Session, patient: Patient, doctor: Doctor
    ) -> None:
        # 23:30 in São Paulo is already the next day in UTC; the listing must not move it.
        late = create_appointment(
            session,
            patient=patient,
            doctor=doctor,
            starts_at=datetime(2026, 9, 17, 23, 30, tzinfo=SAO_PAULO),
        )

        on_the_17th = client.get(
            "/api/v1/appointments", params={"date_from": "2026-09-17", "date_to": "2026-09-17"}
        ).json()
        from_the_18th = client.get(
            "/api/v1/appointments", params={"date_from": "2026-09-18"}
        ).json()

        assert [item["id"] for item in on_the_17th["appointments"]] == [late.id]
        assert from_the_18th["appointments"] == []

    @pytest.mark.parametrize(
        ("params", "status_code", "code"),
        [
            ({"date_from": "2026-09-20", "date_to": "2026-09-19"}, 422, "INVALID_DATE_RANGE"),
            ({"date_from": "2026-09-16", "date_to": "2026-10-16"}, 422, "DATE_RANGE_TOO_LARGE"),
            ({"doctor_id": 999}, 404, "DOCTOR_NOT_FOUND"),
        ],
    )
    def test_rejects_invalid_filters(
        self, client: TestClient, params: dict[str, str], status_code: int, code: str
    ) -> None:
        response = client.get("/api/v1/appointments", params=params)

        assert response.status_code == status_code
        assert _error_code(response) == code


def test_get_unknown_appointment_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/appointments/999")

    assert response.status_code == 404
    assert _error_code(response) == "APPOINTMENT_NOT_FOUND"
