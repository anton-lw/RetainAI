"""Add embedded operations dispatch fields

Revision ID: 20260310_0009
Revises: 20260310_0008
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0009"
down_revision = "20260310_0008"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    connector_columns = [
        ("writeback_enabled", sa.Boolean(), False, sa.text("0")),
        ("writeback_mode", sa.String(length=80), False, sa.text("'none'")),
        ("writeback_resource_path", sa.String(length=500), True, None),
        ("writeback_field_mapping", sa.JSON(), False, sa.text("'{}'")),
        ("last_dispatched_at", sa.DateTime(), True, None),
    ]
    for column_name, column_type, nullable, server_default in connector_columns:
        if not _has_column(inspector, "data_connectors", column_name):
            op.add_column(
                "data_connectors",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    setting_columns = [
        ("low_risk_channel", sa.String(length=20), False, sa.text("'sms'")),
        ("medium_risk_channel", sa.String(length=20), False, sa.text("'call'")),
        ("high_risk_channel", sa.String(length=20), False, sa.text("'visit'")),
        ("escalation_window_days", sa.Integer(), False, sa.text("7")),
        ("escalation_max_attempts", sa.Integer(), False, sa.text("2")),
    ]
    for column_name, column_type, nullable, server_default in setting_columns:
        if not _has_column(inspector, "program_operational_settings", column_name):
            op.add_column(
                "program_operational_settings",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    if not _has_table(inspector, "connector_dispatch_runs"):
        op.create_table(
            "connector_dispatch_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("connector_id", sa.String(length=36), sa.ForeignKey("data_connectors.id"), nullable=False),
            sa.Column("triggered_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
            sa.Column("target_mode", sa.String(length=80), nullable=False, server_default="none"),
            sa.Column("payload_preview", sa.JSON(), nullable=True),
            sa.Column("records_sent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_included", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("log_excerpt", sa.Text(), nullable=True),
        )
        op.create_index("ix_connector_dispatch_runs_connector_id", "connector_dispatch_runs", ["connector_id"], unique=False)
        op.create_index("ix_connector_dispatch_runs_triggered_by_user_id", "connector_dispatch_runs", ["triggered_by_user_id"], unique=False)
        op.create_index("ix_connector_dispatch_runs_status", "connector_dispatch_runs", ["status"], unique=False)
        op.create_index("ix_connector_dispatch_runs_target_mode", "connector_dispatch_runs", ["target_mode"], unique=False)
        op.create_index("ix_connector_dispatch_runs_started_at", "connector_dispatch_runs", ["started_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "connector_dispatch_runs"):
        op.drop_index("ix_connector_dispatch_runs_started_at", table_name="connector_dispatch_runs")
        op.drop_index("ix_connector_dispatch_runs_target_mode", table_name="connector_dispatch_runs")
        op.drop_index("ix_connector_dispatch_runs_status", table_name="connector_dispatch_runs")
        op.drop_index("ix_connector_dispatch_runs_triggered_by_user_id", table_name="connector_dispatch_runs")
        op.drop_index("ix_connector_dispatch_runs_connector_id", table_name="connector_dispatch_runs")
        op.drop_table("connector_dispatch_runs")

    for column_name in [
        "escalation_max_attempts",
        "escalation_window_days",
        "high_risk_channel",
        "medium_risk_channel",
        "low_risk_channel",
    ]:
        if _has_column(inspector, "program_operational_settings", column_name):
            op.drop_column("program_operational_settings", column_name)

    for column_name in [
        "last_dispatched_at",
        "writeback_field_mapping",
        "writeback_resource_path",
        "writeback_mode",
        "writeback_enabled",
    ]:
        if _has_column(inspector, "data_connectors", column_name):
            op.drop_column("data_connectors", column_name)
