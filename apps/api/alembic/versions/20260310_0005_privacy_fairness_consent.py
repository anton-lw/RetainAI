"""Add privacy policies, consent tracking, and fairness settings

Revision ID: 20260310_0005
Revises: 20260310_0004
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0005"
down_revision = "20260310_0004"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "beneficiaries"):
        beneficiary_columns = _column_names(inspector, "beneficiaries")
        with op.batch_alter_table("beneficiaries") as batch_op:
            if "modeling_consent_status" not in beneficiary_columns:
                batch_op.add_column(sa.Column("modeling_consent_status", sa.String(length=40), nullable=False, server_default="granted"))
            if "consent_captured_at" not in beneficiary_columns:
                batch_op.add_column(sa.Column("consent_captured_at", sa.DateTime(), nullable=True))
            if "consent_explained_at" not in beneficiary_columns:
                batch_op.add_column(sa.Column("consent_explained_at", sa.DateTime(), nullable=True))
            if "consent_method" not in beneficiary_columns:
                batch_op.add_column(sa.Column("consent_method", sa.String(length=80), nullable=True))
            if "consent_note" not in beneficiary_columns:
                batch_op.add_column(sa.Column("consent_note", sa.Text(), nullable=True))
            if "pii_token" not in beneficiary_columns:
                batch_op.add_column(sa.Column("pii_token", sa.String(length=80), nullable=True))
            if "pii_tokenized_at" not in beneficiary_columns:
                batch_op.add_column(sa.Column("pii_tokenized_at", sa.DateTime(), nullable=True))

        index_names = {index["name"] for index in inspector.get_indexes("beneficiaries")}
        if op.f("ix_beneficiaries_modeling_consent_status") not in index_names:
            op.create_index(op.f("ix_beneficiaries_modeling_consent_status"), "beneficiaries", ["modeling_consent_status"], unique=False)
        if op.f("ix_beneficiaries_pii_token") not in index_names:
            op.create_index(op.f("ix_beneficiaries_pii_token"), "beneficiaries", ["pii_token"], unique=True)

    if _has_table(inspector, "program_operational_settings"):
        columns = _column_names(inspector, "program_operational_settings")
        with op.batch_alter_table("program_operational_settings") as batch_op:
            if "fairness_reweighting_enabled" not in columns:
                batch_op.add_column(sa.Column("fairness_reweighting_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "fairness_target_dimensions" not in columns:
                batch_op.add_column(sa.Column("fairness_target_dimensions", sa.JSON(), nullable=False, server_default='["gender","region","household_type"]'))
            if "fairness_max_gap" not in columns:
                batch_op.add_column(sa.Column("fairness_max_gap", sa.Float(), nullable=False, server_default="0.15"))
            if "fairness_min_group_size" not in columns:
                batch_op.add_column(sa.Column("fairness_min_group_size", sa.Integer(), nullable=False, server_default="20"))

    if not _has_table(inspector, "program_data_policies"):
        op.create_table(
            "program_data_policies",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("program_id", sa.String(length=36), sa.ForeignKey("programs.id"), nullable=False, unique=True),
            sa.Column("storage_mode", sa.String(length=40), nullable=False, server_default="self_hosted"),
            sa.Column("data_residency_region", sa.String(length=80), nullable=False, server_default="eu-central"),
            sa.Column("cross_border_transfers_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pii_tokenization_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("consent_required", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("federated_learning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_program_data_policies_program_id", "program_data_policies", ["program_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "program_data_policies"):
        op.drop_index("ix_program_data_policies_program_id", table_name="program_data_policies")
        op.drop_table("program_data_policies")

    if _has_table(inspector, "program_operational_settings"):
        columns = _column_names(inspector, "program_operational_settings")
        with op.batch_alter_table("program_operational_settings") as batch_op:
            if "fairness_min_group_size" in columns:
                batch_op.drop_column("fairness_min_group_size")
            if "fairness_max_gap" in columns:
                batch_op.drop_column("fairness_max_gap")
            if "fairness_target_dimensions" in columns:
                batch_op.drop_column("fairness_target_dimensions")
            if "fairness_reweighting_enabled" in columns:
                batch_op.drop_column("fairness_reweighting_enabled")

    if _has_table(inspector, "beneficiaries"):
        index_names = {index["name"] for index in inspector.get_indexes("beneficiaries")}
        if op.f("ix_beneficiaries_pii_token") in index_names:
            op.drop_index(op.f("ix_beneficiaries_pii_token"), table_name="beneficiaries")
        if op.f("ix_beneficiaries_modeling_consent_status") in index_names:
            op.drop_index(op.f("ix_beneficiaries_modeling_consent_status"), table_name="beneficiaries")

        columns = _column_names(inspector, "beneficiaries")
        with op.batch_alter_table("beneficiaries") as batch_op:
            if "pii_tokenized_at" in columns:
                batch_op.drop_column("pii_tokenized_at")
            if "pii_token" in columns:
                batch_op.drop_column("pii_token")
            if "consent_note" in columns:
                batch_op.drop_column("consent_note")
            if "consent_method" in columns:
                batch_op.drop_column("consent_method")
            if "consent_explained_at" in columns:
                batch_op.drop_column("consent_explained_at")
            if "consent_captured_at" in columns:
                batch_op.drop_column("consent_captured_at")
            if "modeling_consent_status" in columns:
                batch_op.drop_column("modeling_consent_status")
