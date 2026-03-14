"""Add runtime policy, queue retry, and federated hardening fields

Revision ID: 20260310_0006
Revises: 20260310_0005
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0006"
down_revision = "20260310_0005"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "jobs"):
        columns = _column_names(inspector, "jobs")
        with op.batch_alter_table("jobs") as batch_op:
            if "max_attempts" not in columns:
                batch_op.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
            if "retry_backoff_seconds" not in columns:
                batch_op.add_column(sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="45"))
            if "last_error_at" not in columns:
                batch_op.add_column(sa.Column("last_error_at", sa.DateTime(), nullable=True))
            if "dead_lettered_at" not in columns:
                batch_op.add_column(sa.Column("dead_lettered_at", sa.DateTime(), nullable=True))

    if _has_table(inspector, "federated_learning_rounds"):
        columns = _column_names(inspector, "federated_learning_rounds")
        with op.batch_alter_table("federated_learning_rounds") as batch_op:
            if "round_nonce" not in columns:
                batch_op.add_column(sa.Column("round_nonce", sa.String(length=120), nullable=False, server_default="bootstrap"))
        op.execute("UPDATE federated_learning_rounds SET round_nonce = id WHERE round_nonce = 'bootstrap' OR round_nonce IS NULL")
        index_names = {index["name"] for index in inspector.get_indexes("federated_learning_rounds")}
        if "ix_federated_learning_rounds_round_nonce" not in index_names:
            op.create_index("ix_federated_learning_rounds_round_nonce", "federated_learning_rounds", ["round_nonce"], unique=False)

    if _has_table(inspector, "federated_model_updates"):
        columns = _column_names(inspector, "federated_model_updates")
        with op.batch_alter_table("federated_model_updates") as batch_op:
            if "source_nonce" not in columns:
                batch_op.add_column(sa.Column("source_nonce", sa.String(length=120), nullable=True))
            if "update_fingerprint" not in columns:
                batch_op.add_column(sa.Column("update_fingerprint", sa.String(length=120), nullable=True))
            if "verified_at" not in columns:
                batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))
        index_names = {index["name"] for index in inspector.get_indexes("federated_model_updates")}
        if "ix_federated_model_updates_source_nonce" not in index_names:
            op.create_index("ix_federated_model_updates_source_nonce", "federated_model_updates", ["source_nonce"], unique=False)
        if "ix_federated_model_updates_update_fingerprint" not in index_names:
            op.create_index("ix_federated_model_updates_update_fingerprint", "federated_model_updates", ["update_fingerprint"], unique=False)
        if "ix_federated_model_updates_verified_at" not in index_names:
            op.create_index("ix_federated_model_updates_verified_at", "federated_model_updates", ["verified_at"], unique=False)
        unique_constraints = {item["name"] for item in inspector.get_unique_constraints("federated_model_updates")}
        if "uq_federated_update_fingerprint" not in unique_constraints:
            with op.batch_alter_table("federated_model_updates") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_federated_update_fingerprint",
                    ["round_id", "update_fingerprint"],
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "federated_model_updates"):
        index_names = {index["name"] for index in inspector.get_indexes("federated_model_updates")}
        unique_constraints = {item["name"] for item in inspector.get_unique_constraints("federated_model_updates")}
        with op.batch_alter_table("federated_model_updates") as batch_op:
            if "uq_federated_update_fingerprint" in unique_constraints:
                batch_op.drop_constraint("uq_federated_update_fingerprint", type_="unique")
        if "ix_federated_model_updates_verified_at" in index_names:
            op.drop_index("ix_federated_model_updates_verified_at", table_name="federated_model_updates")
        if "ix_federated_model_updates_update_fingerprint" in index_names:
            op.drop_index("ix_federated_model_updates_update_fingerprint", table_name="federated_model_updates")
        if "ix_federated_model_updates_source_nonce" in index_names:
            op.drop_index("ix_federated_model_updates_source_nonce", table_name="federated_model_updates")
        columns = _column_names(inspector, "federated_model_updates")
        with op.batch_alter_table("federated_model_updates") as batch_op:
            if "verified_at" in columns:
                batch_op.drop_column("verified_at")
            if "update_fingerprint" in columns:
                batch_op.drop_column("update_fingerprint")
            if "source_nonce" in columns:
                batch_op.drop_column("source_nonce")

    if _has_table(inspector, "federated_learning_rounds"):
        index_names = {index["name"] for index in inspector.get_indexes("federated_learning_rounds")}
        if "ix_federated_learning_rounds_round_nonce" in index_names:
            op.drop_index("ix_federated_learning_rounds_round_nonce", table_name="federated_learning_rounds")
        columns = _column_names(inspector, "federated_learning_rounds")
        with op.batch_alter_table("federated_learning_rounds") as batch_op:
            if "round_nonce" in columns:
                batch_op.drop_column("round_nonce")

    if _has_table(inspector, "jobs"):
        columns = _column_names(inspector, "jobs")
        with op.batch_alter_table("jobs") as batch_op:
            if "dead_lettered_at" in columns:
                batch_op.drop_column("dead_lettered_at")
            if "last_error_at" in columns:
                batch_op.drop_column("last_error_at")
            if "retry_backoff_seconds" in columns:
                batch_op.drop_column("retry_backoff_seconds")
            if "max_attempts" in columns:
                batch_op.drop_column("max_attempts")
