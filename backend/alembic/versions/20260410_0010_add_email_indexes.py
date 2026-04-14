"""add performance indexes to emails

Revision ID: 20260410_0010
Revises: 20260410_0009
Create Date: 2026-04-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0010"
down_revision = "20260410_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("emails", schema=None) as batch_op:
        if _has_column("emails", "thread_id") and not _has_index("emails", "ix_emails_thread_id"):
            batch_op.create_index("ix_emails_thread_id", ["thread_id"])
        if _has_column("emails", "direction") and not _has_index("emails", "ix_emails_direction"):
            batch_op.create_index("ix_emails_direction", ["direction"])
        if _has_column("emails", "status") and not _has_index("emails", "ix_emails_status"):
            batch_op.create_index("ix_emails_status", ["status"])
        if _has_column("emails", "date_received") and not _has_index("emails", "ix_emails_date_received"):
            batch_op.create_index("ix_emails_date_received", ["date_received"])


def downgrade() -> None:
    with op.batch_alter_table("emails", schema=None) as batch_op:
        if _has_index("emails", "ix_emails_date_received"):
            batch_op.drop_index("ix_emails_date_received")
        if _has_index("emails", "ix_emails_status"):
            batch_op.drop_index("ix_emails_status")
        if _has_index("emails", "ix_emails_direction"):
            batch_op.drop_index("ix_emails_direction")
        if _has_index("emails", "ix_emails_thread_id"):
            batch_op.drop_index("ix_emails_thread_id")


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
