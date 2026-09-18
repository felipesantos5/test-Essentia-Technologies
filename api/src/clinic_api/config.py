from functools import lru_cache
from typing import Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from `CLINIC_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="CLINIC_", extra="ignore")

    database_url: str = "sqlite:///./data/clinic.db"
    api_key: SecretStr
    timezone: str = "America/Sao_Paulo"
    availability_default_days: int = Field(default=7, ge=1)
    availability_max_days: int = Field(default=14, ge=1)
    # 0 disables the availability cache.
    availability_cache_ttl_seconds: int = Field(default=60, ge=0)
    demo_patient_email: EmailStr | None = None
    demo_patient_name: str = "Paciente Demo"

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value

    @field_validator("demo_patient_email", mode="before")
    @classmethod
    def _blank_email_as_none(cls, value: Any) -> Any:
        # docker-compose forwards an unset variable as an empty string.
        return None if value == "" else value

    @model_validator(mode="after")
    def _default_range_fits_max(self) -> Self:
        if self.availability_default_days > self.availability_max_days:
            raise ValueError("availability_default_days cannot exceed availability_max_days")
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
