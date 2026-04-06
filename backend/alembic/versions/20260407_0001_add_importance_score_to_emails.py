"""add importance score to emails

Revision ID: 20260407_0001
Revises:
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("importance_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.drop_column("importance_score")
