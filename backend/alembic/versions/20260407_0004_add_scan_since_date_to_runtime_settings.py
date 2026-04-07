"""add scan since date to runtime settings

Revision ID: 20260407_0004
Revises: 20260407_0003
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0004"
down_revision = "20260407_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scan_since_date", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        batch_op.drop_column("scan_since_date")
