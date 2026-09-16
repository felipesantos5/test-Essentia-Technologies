from fastapi import APIRouter

from clinic_api.api.deps import SessionDep
from clinic_api.api.params import OptionalIdQuery
from clinic_api.schemas.catalog import (
    ClinicRead,
    DoctorRead,
    PaymentInfoRead,
    PaymentMethodRead,
    SpecialtyRead,
)
from clinic_api.schemas.common import error_responses
from clinic_api.services import catalog

router = APIRouter(tags=["clinic"])


@router.get(
    "/clinic",
    summary="Clinic contact data and configured greeting/closing messages",
    responses=error_responses(404),
)
def get_clinic(session: SessionDep) -> ClinicRead:
    return ClinicRead.model_validate(catalog.get_clinic(session))


@router.get("/specialties", summary="Specialties with consultation prices")
def list_specialties(session: SessionDep) -> list[SpecialtyRead]:
    return [SpecialtyRead.from_model(item) for item in catalog.list_specialties(session)]


@router.get(
    "/doctors",
    summary="Active doctors with specialty and weekly working hours",
    responses=error_responses(404),
)
def list_doctors(session: SessionDep, specialty_id: OptionalIdQuery = None) -> list[DoctorRead]:
    doctors = catalog.list_active_doctors(session, specialty_id=specialty_id)
    return [DoctorRead.from_model(doctor) for doctor in doctors]


@router.get("/payment-info", summary="Consultation prices and accepted payment methods")
def get_payment_info(session: SessionDep) -> PaymentInfoRead:
    return PaymentInfoRead(
        consultation_prices=[
            SpecialtyRead.from_model(item) for item in catalog.list_specialties(session)
        ],
        payment_methods=[
            PaymentMethodRead.model_validate(method)
            for method in catalog.list_active_payment_methods(session)
        ],
    )
