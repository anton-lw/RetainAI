"""Add validation evidence and shadow-mode tables

Revision ID: 20260310_0010
Revises: 20260310_0009
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0010"
down_revision = "20260310_0009"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "program_validation_settings"):
        op.create_table(
            "program_validation_settings",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("program_id", sa.String(length=36), sa.ForeignKey("programs.id"), nullable=False, unique=True),
            sa.Column("shadow_mode_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("shadow_prediction_window_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("minimum_precision_at_capacity", sa.Float(), nullable=False, server_default="0.7"),
            sa.Column("minimum_recall_at_capacity", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("require_fairness_review", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_evaluation_status", sa.String(length=40), nullable=True),
            sa.Column("last_shadow_run_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index(
            "ix_program_validation_settings_program_id",
            "program_validation_settings",
            ["program_id"],
            unique=True,
        )
        op.create_index(
            "ix_program_validation_settings_shadow_mode_enabled",
            "program_validation_settings",
            ["shadow_mode_enabled"],
            unique=False,
        )
        op.create_index(
            "ix_program_validation_settings_last_evaluation_status",
            "program_validation_settings",
            ["last_evaluation_status"],
            unique=False,
        )
        op.create_index(
            "ix_program_validation_settings_last_shadow_run_at",
            "program_validation_settings",
            ["last_shadow_run_at"],
            unique=False,
        )

    if not _has_table(inspector, "evaluation_reports"):
        op.create_table(
            "evaluation_reports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("program_scope", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("cohort_scope", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("temporal_strategy", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("algorithm", sa.String(length=120), nullable=False),
            sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("samples_evaluated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("positive_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("report_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_evaluation_reports_created_by_user_id", "evaluation_reports", ["created_by_user_id"], unique=False)
        op.create_index("ix_evaluation_reports_temporal_strategy", "evaluation_reports", ["temporal_strategy"], unique=False)
        op.create_index("ix_evaluation_reports_status", "evaluation_reports", ["status"], unique=False)
        op.create_index("ix_evaluation_reports_created_at", "evaluation_reports", ["created_at"], unique=False)

    if not _has_table(inspector, "shadow_runs"):
        op.create_table(
            "shadow_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("program_id", sa.String(length=36), sa.ForeignKey("programs.id"), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="captured"),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("top_k_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_captured", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("high_risk_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("due_now_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("matured_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("observed_positive_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actioned_cases", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("top_k_precision", sa.Float(), nullable=True),
            sa.Column("top_k_recall", sa.Float(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_shadow_runs_program_id", "shadow_runs", ["program_id"], unique=False)
        op.create_index("ix_shadow_runs_created_by_user_id", "shadow_runs", ["created_by_user_id"], unique=False)
        op.create_index("ix_shadow_runs_status", "shadow_runs", ["status"], unique=False)
        op.create_index("ix_shadow_runs_snapshot_date", "shadow_runs", ["snapshot_date"], unique=False)
        op.create_index("ix_shadow_runs_created_at", "shadow_runs", ["created_at"], unique=False)
        op.create_index("ix_shadow_runs_completed_at", "shadow_runs", ["completed_at"], unique=False)

    if not _has_table(inspector, "shadow_run_cases"):
        op.create_table(
            "shadow_run_cases",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("shadow_run_id", sa.String(length=36), sa.ForeignKey("shadow_runs.id"), nullable=False),
            sa.Column("beneficiary_id", sa.String(length=36), sa.ForeignKey("beneficiaries.id"), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("rank_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("included_in_top_k", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("risk_level", sa.String(length=20), nullable=False),
            sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("queue_bucket", sa.String(length=30), nullable=False, server_default="Monitor"),
            sa.Column("queue_rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("assigned_worker", sa.String(length=120), nullable=True),
            sa.Column("assigned_site", sa.String(length=120), nullable=True),
            sa.Column("recommended_action", sa.String(length=255), nullable=False),
            sa.Column("observed_outcome", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("observed_at", sa.Date(), nullable=True),
            sa.Column("action_logged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_shadow_run_cases_shadow_run_id", "shadow_run_cases", ["shadow_run_id"], unique=False)
        op.create_index("ix_shadow_run_cases_beneficiary_id", "shadow_run_cases", ["beneficiary_id"], unique=False)
        op.create_index("ix_shadow_run_cases_snapshot_date", "shadow_run_cases", ["snapshot_date"], unique=False)
        op.create_index("ix_shadow_run_cases_rank_order", "shadow_run_cases", ["rank_order"], unique=False)
        op.create_index("ix_shadow_run_cases_included_in_top_k", "shadow_run_cases", ["included_in_top_k"], unique=False)
        op.create_index("ix_shadow_run_cases_observed_outcome", "shadow_run_cases", ["observed_outcome"], unique=False)
        op.create_index("ix_shadow_run_cases_observed_at", "shadow_run_cases", ["observed_at"], unique=False)
        op.create_index("ix_shadow_run_cases_created_at", "shadow_run_cases", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "shadow_run_cases"):
        op.drop_index("ix_shadow_run_cases_created_at", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_observed_at", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_observed_outcome", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_included_in_top_k", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_rank_order", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_snapshot_date", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_beneficiary_id", table_name="shadow_run_cases")
        op.drop_index("ix_shadow_run_cases_shadow_run_id", table_name="shadow_run_cases")
        op.drop_table("shadow_run_cases")

    if _has_table(inspector, "shadow_runs"):
        op.drop_index("ix_shadow_runs_completed_at", table_name="shadow_runs")
        op.drop_index("ix_shadow_runs_created_at", table_name="shadow_runs")
        op.drop_index("ix_shadow_runs_snapshot_date", table_name="shadow_runs")
        op.drop_index("ix_shadow_runs_status", table_name="shadow_runs")
        op.drop_index("ix_shadow_runs_created_by_user_id", table_name="shadow_runs")
        op.drop_index("ix_shadow_runs_program_id", table_name="shadow_runs")
        op.drop_table("shadow_runs")

    if _has_table(inspector, "evaluation_reports"):
        op.drop_index("ix_evaluation_reports_created_at", table_name="evaluation_reports")
        op.drop_index("ix_evaluation_reports_status", table_name="evaluation_reports")
        op.drop_index("ix_evaluation_reports_temporal_strategy", table_name="evaluation_reports")
        op.drop_index("ix_evaluation_reports_created_by_user_id", table_name="evaluation_reports")
        op.drop_table("evaluation_reports")

    if _has_table(inspector, "program_validation_settings"):
        op.drop_index("ix_program_validation_settings_last_shadow_run_at", table_name="program_validation_settings")
        op.drop_index("ix_program_validation_settings_last_evaluation_status", table_name="program_validation_settings")
        op.drop_index("ix_program_validation_settings_shadow_mode_enabled", table_name="program_validation_settings")
        op.drop_index("ix_program_validation_settings_program_id", table_name="program_validation_settings")
        op.drop_table("program_validation_settings")
