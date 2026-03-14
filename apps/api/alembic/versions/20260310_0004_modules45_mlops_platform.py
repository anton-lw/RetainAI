"""Add module 4/5 analytics settings and federated learning metadata

Revision ID: 20260310_0004
Revises: 20260310_0003
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0004"
down_revision = "20260310_0003"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "model_versions", "mlflow_run_id"):
        op.add_column("model_versions", sa.Column("mlflow_run_id", sa.String(length=120), nullable=True))
        op.create_index("ix_model_versions_mlflow_run_id", "model_versions", ["mlflow_run_id"], unique=False)

    if not _has_table(inspector, "program_operational_settings"):
        op.create_table(
            "program_operational_settings",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("program_id", sa.String(length=36), sa.ForeignKey("programs.id"), nullable=False, unique=True),
            sa.Column("weekly_followup_capacity", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("medium_risk_multiplier", sa.Float(), nullable=False, server_default="2.0"),
            sa.Column("high_risk_share_floor", sa.Float(), nullable=False, server_default="0.08"),
            sa.Column("review_window_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_program_operational_settings_program_id", "program_operational_settings", ["program_id"], unique=True)

    if not _has_table(inspector, "federated_learning_rounds"):
        op.create_table(
            "federated_learning_rounds",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("round_name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="collecting"),
            sa.Column("aggregation_note", sa.Text(), nullable=True),
            sa.Column("aggregated_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_federated_learning_rounds_round_name", "federated_learning_rounds", ["round_name"], unique=True)
        op.create_index("ix_federated_learning_rounds_status", "federated_learning_rounds", ["status"], unique=False)

    if not _has_table(inspector, "federated_model_updates"):
        op.create_table(
            "federated_model_updates",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("round_id", sa.String(length=36), sa.ForeignKey("federated_learning_rounds.id"), nullable=False),
            sa.Column("source_program_id", sa.String(length=36), sa.ForeignKey("programs.id"), nullable=True),
            sa.Column("model_version_id", sa.String(length=36), sa.ForeignKey("model_versions.id"), nullable=True),
            sa.Column("deployment_label", sa.String(length=120), nullable=False),
            sa.Column("training_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("positive_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_federated_model_updates_round_id", "federated_model_updates", ["round_id"], unique=False)
        op.create_index("ix_federated_model_updates_source_program_id", "federated_model_updates", ["source_program_id"], unique=False)
        op.create_index("ix_federated_model_updates_model_version_id", "federated_model_updates", ["model_version_id"], unique=False)
        op.create_index("ix_federated_model_updates_deployment_label", "federated_model_updates", ["deployment_label"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "federated_model_updates"):
        op.drop_index("ix_federated_model_updates_deployment_label", table_name="federated_model_updates")
        op.drop_index("ix_federated_model_updates_model_version_id", table_name="federated_model_updates")
        op.drop_index("ix_federated_model_updates_source_program_id", table_name="federated_model_updates")
        op.drop_index("ix_federated_model_updates_round_id", table_name="federated_model_updates")
        op.drop_table("federated_model_updates")

    if _has_table(inspector, "federated_learning_rounds"):
        op.drop_index("ix_federated_learning_rounds_status", table_name="federated_learning_rounds")
        op.drop_index("ix_federated_learning_rounds_round_name", table_name="federated_learning_rounds")
        op.drop_table("federated_learning_rounds")

    if _has_table(inspector, "program_operational_settings"):
        op.drop_index("ix_program_operational_settings_program_id", table_name="program_operational_settings")
        op.drop_table("program_operational_settings")

    if _has_column(inspector, "model_versions", "mlflow_run_id"):
        op.drop_index("ix_model_versions_mlflow_run_id", table_name="model_versions")
        op.drop_column("model_versions", "mlflow_run_id")
