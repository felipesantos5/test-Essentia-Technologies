"""Index appointments by start time for the period listing behind the panel.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_appointments_starts_at"), "appointments", ["starts_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_appointments_starts_at"), table_name="appointments")
