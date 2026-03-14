"""Add operational label and tracing protocol fields

Revision ID: 20260314_0011
Revises: 20260310_0010
Create Date: 2026-03-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0011"
down_revision = "20260310_0010"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    intervention_columns = [
        ("protocol_step", sa.String(length=20), True, None),
    ]
    for column_name, column_type, nullable, server_default in intervention_columns:
        if not _has_column(inspector, "interventions", column_name):
            op.add_column(
                "interventions",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    if _has_column(inspector, "interventions", "protocol_step") and not _has_index(
        inspector,
        "interventions",
        "ix_interventions_protocol_step",
    ):
        op.create_index("ix_interventions_protocol_step", "interventions", ["protocol_step"], unique=False)

    setting_columns = [
        ("label_noise_strategy", sa.String(length=40), False, sa.text("'operational_soft_labels'")),
        ("soft_label_weight", sa.Float(), False, sa.text("0.35")),
        ("silent_transfer_detection_enabled", sa.Boolean(), False, sa.text("1")),
        ("tracing_sms_delay_days", sa.Integer(), False, sa.text("3")),
        ("tracing_call_delay_days", sa.Integer(), False, sa.text("7")),
        ("tracing_visit_delay_days", sa.Integer(), False, sa.text("14")),
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

    if _has_index(inspector, "interventions", "ix_interventions_protocol_step"):
        op.drop_index("ix_interventions_protocol_step", table_name="interventions")

    if _has_column(inspector, "interventions", "protocol_step"):
        op.drop_column("interventions", "protocol_step")

    for column_name in [
        "tracing_visit_delay_days",
        "tracing_call_delay_days",
        "tracing_sms_delay_days",
        "silent_transfer_detection_enabled",
        "soft_label_weight",
        "label_noise_strategy",
    ]:
        if _has_column(inspector, "program_operational_settings", column_name):
            op.drop_column("program_operational_settings", column_name)
