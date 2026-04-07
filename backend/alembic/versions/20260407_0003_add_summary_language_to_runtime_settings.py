"""add summary language to runtime settings

Revision ID: 20260407_0003
Revises: 20260407_0002
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0003"
down_revision = "20260407_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _has_column("runtime_settings", "summary_language"):
        return
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("summary_language", sa.String(length=20), nullable=True))


def downgrade() -> None:
    if not _has_column("runtime_settings", "summary_language"):
        return
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        batch_op.drop_column("summary_language")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
