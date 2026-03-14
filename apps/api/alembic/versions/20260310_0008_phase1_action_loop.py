"""Add phase 1 action-loop workflow fields

Revision ID: 20260310_0008
Revises: 20260310_0007
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0008"
down_revision = "20260310_0007"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    beneficiary_columns = [
        ("assigned_case_worker", sa.String(length=120), True, None),
        ("assigned_site", sa.String(length=120), True, None),
        ("household_stability_signal", sa.Integer(), True, None),
        ("economic_stress_signal", sa.Integer(), True, None),
        ("family_support_signal", sa.Integer(), True, None),
        ("health_change_signal", sa.Integer(), True, None),
        ("motivation_signal", sa.Integer(), True, None),
    ]
    for column_name, column_type, nullable, server_default in beneficiary_columns:
        if not _has_column(inspector, "beneficiaries", column_name):
            op.add_column(
                "beneficiaries",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    intervention_columns = [
        ("support_channel", sa.String(length=40), True, None),
        ("status", sa.String(length=40), False, sa.text("'queued'")),
        ("verification_status", sa.String(length=40), True, None),
        ("assigned_to", sa.String(length=120), True, None),
        ("assigned_site", sa.String(length=120), True, None),
        ("due_at", sa.DateTime(), True, None),
        ("completed_at", sa.DateTime(), True, None),
        ("verified_at", sa.DateTime(), True, None),
        ("verification_note", sa.Text(), True, None),
        ("dismissal_reason", sa.String(length=255), True, None),
        ("attempt_count", sa.Integer(), False, sa.text("0")),
        ("source", sa.String(length=40), False, sa.text("'manual'")),
        ("risk_level", sa.String(length=20), True, None),
        ("priority_rank", sa.Integer(), True, None),
    ]
    for column_name, column_type, nullable, server_default in intervention_columns:
        if not _has_column(inspector, "interventions", column_name):
            op.add_column(
                "interventions",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    setting_columns = [
        ("worker_count", sa.Integer(), False, sa.text("4")),
        ("label_definition_preset", sa.String(length=40), False, sa.text("'custom'")),
        ("dropout_inactivity_days", sa.Integer(), False, sa.text("30")),
        ("prediction_window_days", sa.Integer(), False, sa.text("30")),
    ]
    for column_name, column_type, nullable, server_default in setting_columns:
        if not _has_column(inspector, "program_operational_settings", column_name):
            op.add_column(
                "program_operational_settings",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for column_name in [
        "prediction_window_days",
        "dropout_inactivity_days",
        "label_definition_preset",
        "worker_count",
    ]:
        if _has_column(inspector, "program_operational_settings", column_name):
            op.drop_column("program_operational_settings", column_name)

    for column_name in [
        "priority_rank",
        "risk_level",
        "source",
        "attempt_count",
        "dismissal_reason",
        "verification_note",
        "verified_at",
        "completed_at",
        "due_at",
        "assigned_site",
        "assigned_to",
        "verification_status",
        "status",
        "support_channel",
    ]:
        if _has_column(inspector, "interventions", column_name):
            op.drop_column("interventions", column_name)

    for column_name in [
        "motivation_signal",
        "health_change_signal",
        "family_support_signal",
        "economic_stress_signal",
        "household_stability_signal",
        "assigned_site",
        "assigned_case_worker",
    ]:
        if _has_column(inspector, "beneficiaries", column_name):
            op.drop_column("beneficiaries", column_name)
