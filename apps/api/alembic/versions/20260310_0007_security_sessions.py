"""Add server-side sessions for auth hardening

Revision ID: 20260310_0007
Revises: 20260310_0006
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0007"
down_revision = "20260310_0006"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "user_sessions"):
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_jti", sa.String(length=120), nullable=False),
            sa.Column("token_key_id", sa.String(length=120), nullable=False),
            sa.Column("auth_method", sa.String(length=40), nullable=False, server_default="password"),
            sa.Column("source_ip", sa.String(length=80), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_reason", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
        op.create_index("ix_user_sessions_token_jti", "user_sessions", ["token_jti"], unique=True)
        op.create_index("ix_user_sessions_token_key_id", "user_sessions", ["token_key_id"], unique=False)
        op.create_index("ix_user_sessions_issued_at", "user_sessions", ["issued_at"], unique=False)
        op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)
        op.create_index("ix_user_sessions_last_seen_at", "user_sessions", ["last_seen_at"], unique=False)
        op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "user_sessions"):
        op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
        op.drop_index("ix_user_sessions_last_seen_at", table_name="user_sessions")
        op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
        op.drop_index("ix_user_sessions_issued_at", table_name="user_sessions")
        op.drop_index("ix_user_sessions_token_key_id", table_name="user_sessions")
        op.drop_index("ix_user_sessions_token_jti", table_name="user_sessions")
        op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
        op.drop_table("user_sessions")
