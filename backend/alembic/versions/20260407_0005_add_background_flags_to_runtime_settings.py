"""add background service flags to runtime settings

Revision ID: 20260407_0005
Revises: 20260407_0004
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0005"
down_revision = "20260407_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        if not _has_column("runtime_settings", "run_background_jobs"):
            batch_op.add_column(sa.Column("run_background_jobs", sa.Boolean(), nullable=True))
        if not _has_column("runtime_settings", "run_mail_watchers"):
            batch_op.add_column(sa.Column("run_mail_watchers", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runtime_settings", schema=None) as batch_op:
        if _has_column("runtime_settings", "run_mail_watchers"):
            batch_op.drop_column("run_mail_watchers")
        if _has_column("runtime_settings", "run_background_jobs"):
            batch_op.drop_column("run_background_jobs")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
