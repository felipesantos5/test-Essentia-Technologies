import pytest
from pydantic import SecretStr, ValidationError

from clinic_api.config import Settings


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown timezone"):
        Settings(api_key=SecretStr("k"), timezone="Mars/Olympus_Mons")


def test_default_range_cannot_exceed_the_maximum() -> None:
    with pytest.raises(ValidationError, match="availability_default_days"):
        Settings(api_key=SecretStr("k"), availability_default_days=15, availability_max_days=14)


def test_blank_demo_email_means_no_demo_patient() -> None:
    settings = Settings(api_key=SecretStr("k"), demo_patient_email="")

    assert settings.demo_patient_email is None
