"""Add ETL and ML pipeline persistence extensions

Revision ID: 20260310_0002
Revises: 20260310_0001
Create Date: 2026-03-10 22:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260310_0002"
down_revision = "20260310_0001"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "import_batches" in tables:
        import_batch_columns = _column_names(inspector, "import_batches")
        with op.batch_alter_table("import_batches") as batch_op:
            if "source_format" not in import_batch_columns:
                batch_op.add_column(sa.Column("source_format", sa.String(length=20), nullable=False, server_default="csv"))
            if "records_received" not in import_batch_columns:
                batch_op.add_column(sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"))
            if "duplicates_detected" not in import_batch_columns:
                batch_op.add_column(sa.Column("duplicates_detected", sa.Integer(), nullable=False, server_default="0"))
            if "quality_summary" not in import_batch_columns:
                batch_op.add_column(sa.Column("quality_summary", sa.JSON(), nullable=True))

    if "model_versions" in tables:
        model_version_columns = _column_names(inspector, "model_versions")
        with op.batch_alter_table("model_versions") as batch_op:
            if "training_profile" not in model_version_columns:
                batch_op.add_column(sa.Column("training_profile", sa.JSON(), nullable=True))

    if "data_quality_issues" not in tables:
        op.create_table(
            "data_quality_issues",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("import_batch_id", sa.String(length=36), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("issue_type", sa.String(length=80), nullable=False),
            sa.Column("field_name", sa.String(length=120), nullable=True),
            sa.Column("row_number", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("sample_value", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_data_quality_issues_created_at"), "data_quality_issues", ["created_at"], unique=False)
        op.create_index(op.f("ix_data_quality_issues_field_name"), "data_quality_issues", ["field_name"], unique=False)
        op.create_index(op.f("ix_data_quality_issues_import_batch_id"), "data_quality_issues", ["import_batch_id"], unique=False)
        op.create_index(op.f("ix_data_quality_issues_issue_type"), "data_quality_issues", ["issue_type"], unique=False)
        op.create_index(op.f("ix_data_quality_issues_severity"), "data_quality_issues", ["severity"], unique=False)

    if "feature_snapshots" not in tables:
        op.create_table(
            "feature_snapshots",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("beneficiary_id", sa.String(length=36), nullable=False),
            sa.Column("model_version_id", sa.String(length=36), nullable=True),
            sa.Column("source_kind", sa.String(length=30), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("label", sa.Integer(), nullable=True),
            sa.Column("uncertainty_score", sa.Float(), nullable=True),
            sa.Column("values", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiaries.id"]),
            sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_feature_snapshots_beneficiary_id"), "feature_snapshots", ["beneficiary_id"], unique=False)
        op.create_index(op.f("ix_feature_snapshots_created_at"), "feature_snapshots", ["created_at"], unique=False)
        op.create_index(op.f("ix_feature_snapshots_model_version_id"), "feature_snapshots", ["model_version_id"], unique=False)
        op.create_index(op.f("ix_feature_snapshots_snapshot_date"), "feature_snapshots", ["snapshot_date"], unique=False)
        op.create_index(op.f("ix_feature_snapshots_source_kind"), "feature_snapshots", ["source_kind"], unique=False)

    if "model_drift_reports" not in tables:
        op.create_table(
            "model_drift_reports",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("model_version_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="ok"),
            sa.Column("overall_psi", sa.Float(), nullable=False, server_default="0"),
            sa.Column("feature_reports", sa.JSON(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("monitored_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_model_drift_reports_model_version_id"), "model_drift_reports", ["model_version_id"], unique=False)
        op.create_index(op.f("ix_model_drift_reports_monitored_at"), "model_drift_reports", ["monitored_at"], unique=False)
        op.create_index(op.f("ix_model_drift_reports_status"), "model_drift_reports", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "model_drift_reports" in tables:
        op.drop_index(op.f("ix_model_drift_reports_status"), table_name="model_drift_reports")
        op.drop_index(op.f("ix_model_drift_reports_monitored_at"), table_name="model_drift_reports")
        op.drop_index(op.f("ix_model_drift_reports_model_version_id"), table_name="model_drift_reports")
        op.drop_table("model_drift_reports")

    if "feature_snapshots" in tables:
        op.drop_index(op.f("ix_feature_snapshots_source_kind"), table_name="feature_snapshots")
        op.drop_index(op.f("ix_feature_snapshots_snapshot_date"), table_name="feature_snapshots")
        op.drop_index(op.f("ix_feature_snapshots_model_version_id"), table_name="feature_snapshots")
        op.drop_index(op.f("ix_feature_snapshots_created_at"), table_name="feature_snapshots")
        op.drop_index(op.f("ix_feature_snapshots_beneficiary_id"), table_name="feature_snapshots")
        op.drop_table("feature_snapshots")

    if "data_quality_issues" in tables:
        op.drop_index(op.f("ix_data_quality_issues_severity"), table_name="data_quality_issues")
        op.drop_index(op.f("ix_data_quality_issues_issue_type"), table_name="data_quality_issues")
        op.drop_index(op.f("ix_data_quality_issues_import_batch_id"), table_name="data_quality_issues")
        op.drop_index(op.f("ix_data_quality_issues_field_name"), table_name="data_quality_issues")
        op.drop_index(op.f("ix_data_quality_issues_created_at"), table_name="data_quality_issues")
        op.drop_table("data_quality_issues")

    if "model_versions" in tables and "training_profile" in _column_names(inspector, "model_versions"):
        with op.batch_alter_table("model_versions") as batch_op:
            batch_op.drop_column("training_profile")

    if "import_batches" in tables:
        import_batch_columns = _column_names(inspector, "import_batches")
        with op.batch_alter_table("import_batches") as batch_op:
            if "quality_summary" in import_batch_columns:
                batch_op.drop_column("quality_summary")
            if "duplicates_detected" in import_batch_columns:
                batch_op.drop_column("duplicates_detected")
            if "records_received" in import_batch_columns:
                batch_op.drop_column("records_received")
            if "source_format" in import_batch_columns:
                batch_op.drop_column("source_format")
