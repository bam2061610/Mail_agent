"""add awaiting_response to emails

Revision ID: 20260410_0008
Revises: 20260408_0007
Create Date: 2026-04-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0008"
down_revision = "20260408_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _has_column("emails", "awaiting_response"):
        return
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("awaiting_response", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade() -> None:
    if not _has_column("emails", "awaiting_response"):
        return
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.drop_column("awaiting_response")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
