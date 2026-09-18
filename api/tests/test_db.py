from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.dialects import sqlite

from clinic_api.models import UTCDateTime


def test_sqlite_connections_get_the_expected_pragmas(engine: Engine) -> None:
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar()

    assert foreign_keys == 1
    assert journal_mode == "wal"


def test_utc_datetime_stores_utc_and_returns_aware_values() -> None:
    column = UTCDateTime()
    sao_paulo_noon = datetime.fromisoformat("2026-09-16T12:00:00-03:00")

    stored = column.process_bind_param(sao_paulo_noon, sqlite.dialect())
    loaded = column.process_result_value(stored, sqlite.dialect())

    assert stored == datetime(2026, 9, 16, 15, 0)  # noqa: DTZ001 - naive UTC is the stored form
    assert loaded == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)


def test_utc_datetime_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="naive datetimes are not allowed"):
        UTCDateTime().process_bind_param(datetime(2026, 9, 16, 12, 0), sqlite.dialect())  # noqa: DTZ001
