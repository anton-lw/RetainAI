"""Add connector sync state, webhook fields, and beneficiary contact fields

Revision ID: 20260310_0003
Revises: 20260310_0002
Create Date: 2026-03-10 23:45:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260310_0003"
down_revision = "20260310_0002"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "beneficiaries" in tables:
        beneficiary_columns = _column_names(inspector, "beneficiaries")
        with op.batch_alter_table("beneficiaries") as batch_op:
            if "preferred_contact_phone" not in beneficiary_columns:
                batch_op.add_column(sa.Column("preferred_contact_phone", sa.String(length=40), nullable=True))
            if "preferred_contact_channel" not in beneficiary_columns:
                batch_op.add_column(sa.Column("preferred_contact_channel", sa.String(length=40), nullable=True))

    if "data_connectors" in tables:
        connector_columns = _column_names(inspector, "data_connectors")
        with op.batch_alter_table("data_connectors") as batch_op:
            if "sync_state" not in connector_columns:
                batch_op.add_column(sa.Column("sync_state", sa.JSON(), nullable=False, server_default="{}"))
            if "webhook_enabled" not in connector_columns:
                batch_op.add_column(sa.Column("webhook_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "encrypted_webhook_secret" not in connector_columns:
                batch_op.add_column(sa.Column("encrypted_webhook_secret", sa.Text(), nullable=True))
            if "last_webhook_at" not in connector_columns:
                batch_op.add_column(sa.Column("last_webhook_at", sa.DateTime(), nullable=True))

        connector_columns = _column_names(inspector, "data_connectors")
        if "last_webhook_at" in connector_columns:
            index_names = {index["name"] for index in inspector.get_indexes("data_connectors")}
            index_name = op.f("ix_data_connectors_last_webhook_at")
            if index_name not in index_names:
                op.create_index(index_name, "data_connectors", ["last_webhook_at"], unique=False)
            index_name = op.f("ix_data_connectors_webhook_enabled")
            if index_name not in index_names:
                op.create_index(index_name, "data_connectors", ["webhook_enabled"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "data_connectors" in tables:
        index_names = {index["name"] for index in inspector.get_indexes("data_connectors")}
        webhook_index = op.f("ix_data_connectors_webhook_enabled")
        webhook_at_index = op.f("ix_data_connectors_last_webhook_at")
        if webhook_index in index_names:
            op.drop_index(webhook_index, table_name="data_connectors")
        if webhook_at_index in index_names:
            op.drop_index(webhook_at_index, table_name="data_connectors")

        connector_columns = _column_names(inspector, "data_connectors")
        with op.batch_alter_table("data_connectors") as batch_op:
            if "last_webhook_at" in connector_columns:
                batch_op.drop_column("last_webhook_at")
            if "encrypted_webhook_secret" in connector_columns:
                batch_op.drop_column("encrypted_webhook_secret")
            if "webhook_enabled" in connector_columns:
                batch_op.drop_column("webhook_enabled")
            if "sync_state" in connector_columns:
                batch_op.drop_column("sync_state")

    if "beneficiaries" in tables:
        beneficiary_columns = _column_names(inspector, "beneficiaries")
        with op.batch_alter_table("beneficiaries") as batch_op:
            if "preferred_contact_channel" in beneficiary_columns:
                batch_op.drop_column("preferred_contact_channel")
            if "preferred_contact_phone" in beneficiary_columns:
                batch_op.drop_column("preferred_contact_phone")
