"""Initial schema: clinic, catalog, schedules, patients and appointments.

Revision ID: 0001
Revises:
Create Date: 2026-09-16

Written by hand: autogenerate does not render the partial unique indexes on appointments.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULED_ONLY = sa.text("status = 'scheduled'")


def upgrade() -> None:
    op.create_table(
        "clinic",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("greeting_message", sa.Text(), nullable=False),
        sa.Column("closing_message", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_clinic_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinic")),
    )

    op.create_table(
        "specialties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("price_cents > 0", name=op.f("ck_specialties_price_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specialties")),
        sa.UniqueConstraint("name", name=op.f("uq_specialties_name")),
    )

    op.create_table(
        "doctors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("crm", sa.String(length=20), nullable=False),
        sa.Column("specialty_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["specialty_id"],
            ["specialties.id"],
            name=op.f("fk_doctors_specialty_id_specialties"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctors")),
        sa.UniqueConstraint("crm", name=op.f("uq_doctors_crm")),
    )
    op.create_index(op.f("ix_doctors_specialty_id"), "doctors", ["specialty_id"])

    op.create_table(
        "doctor_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_doctor_schedules_weekday_range")
        ),
        sa.CheckConstraint(
            "start_time < end_time", name=op.f("ck_doctor_schedules_start_before_end")
        ),
        sa.CheckConstraint(
            "slot_minutes > 0", name=op.f("ck_doctor_schedules_slot_minutes_positive")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctors.id"],
            name=op.f("fk_doctor_schedules_doctor_id_doctors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_schedules")),
        sa.UniqueConstraint(
            "doctor_id",
            "weekday",
            "start_time",
            name=op.f("uq_doctor_schedules_doctor_id_weekday_start_time"),
        ),
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patients")),
        sa.UniqueConstraint("email", name=op.f("uq_patients_email")),
    )

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("max_installments", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "max_installments IS NULL OR max_installments >= 1",
            name=op.f("ck_payment_methods_max_installments_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_methods")),
        sa.UniqueConstraint("code", name=op.f("uq_payment_methods_code")),
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_appointments_ends_after_start")),
        sa.CheckConstraint("price_cents > 0", name=op.f("ck_appointments_price_positive")),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_appointments_cancelled_at_matches_status"),
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled')",
            name=op.f("ck_appointments_appointment_status"),
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctors.id"],
            name=op.f("fk_appointments_doctor_id_doctors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_appointments_patient_id_patients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
    )
    op.create_index(
        "ix_appointments_patient_id_status_starts_at",
        "appointments",
        ["patient_id", "status", "starts_at"],
    )
    op.create_index(
        "uq_appointments_doctor_id_starts_at_scheduled",
        "appointments",
        ["doctor_id", "starts_at"],
        unique=True,
        sqlite_where=SCHEDULED_ONLY,
        postgresql_where=SCHEDULED_ONLY,
    )
    op.create_index(
        "uq_appointments_patient_id_starts_at_scheduled",
        "appointments",
        ["patient_id", "starts_at"],
        unique=True,
        sqlite_where=SCHEDULED_ONLY,
        postgresql_where=SCHEDULED_ONLY,
    )


def downgrade() -> None:
    op.drop_index("uq_appointments_patient_id_starts_at_scheduled", table_name="appointments")
    op.drop_index("uq_appointments_doctor_id_starts_at_scheduled", table_name="appointments")
    op.drop_index("ix_appointments_patient_id_status_starts_at", table_name="appointments")
    op.drop_table("appointments")
    op.drop_table("payment_methods")
    op.drop_table("patients")
    op.drop_table("doctor_schedules")
    op.drop_index(op.f("ix_doctors_specialty_id"), table_name="doctors")
    op.drop_table("doctors")
    op.drop_table("specialties")
    op.drop_table("clinic")
