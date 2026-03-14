"""Initial RetainAI schema

Revision ID: 20260310_0001
Revises:
Create Date: 2026-03-10 18:45:00
"""
from __future__ import annotations

from alembic import op

from app.db import Base
import app.models  # noqa: F401


revision = "20260310_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
