from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from clinic_api.db import Base

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_config(tmp_path: Path) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'migrations.db'}")
    return config


def test_migrations_match_models(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


def test_appointment_unique_indexes_are_partial(alembic_config: Config) -> None:
    # compare_metadata ignores index predicates, so assert them on the generated DDL directly.
    command.upgrade(alembic_config, "head")

    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as connection:
        index_sql = connection.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'index' AND name LIKE 'uq_appointments_%'"
            )
        ).all()
    engine.dispose()

    assert {name for name, _ in index_sql} == {
        "uq_appointments_doctor_id_starts_at_scheduled",
        "uq_appointments_patient_id_starts_at_scheduled",
    }
    assert all("WHERE status = 'scheduled'" in sql for _, sql in index_sql)


def test_migrations_downgrade_to_empty_database(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url") or "")
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    engine.dispose()

    assert tables == set()
