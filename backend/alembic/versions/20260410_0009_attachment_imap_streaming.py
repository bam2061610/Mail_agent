"""attachment imap streaming columns

Revision ID: 20260410_0009
Revises: 20260410_0008
Create Date: 2026-04-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0009"
down_revision = "20260410_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _has_column("attachments", "imap_uid"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.add_column(sa.Column("imap_uid", sa.String(100), nullable=True))
    if not _has_column("attachments", "imap_part_number"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.add_column(sa.Column("imap_part_number", sa.String(50), nullable=True))
    if _has_column("attachments", "local_storage_path"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.alter_column("local_storage_path", nullable=True)


def downgrade() -> None:
    if _has_column("attachments", "imap_part_number"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.drop_column("imap_part_number")
    if _has_column("attachments", "imap_uid"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.drop_column("imap_uid")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}
