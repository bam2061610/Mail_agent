"""backfill runtime schema gaps

Revision ID: 20260408_0006
Revises: 20260407_0005
Create Date: 2026-04-08 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0006"
down_revision = "20260407_0005"
branch_labels = None
depends_on = None

EMAIL_COLUMNS = {
    "folder": "VARCHAR(100) NOT NULL DEFAULT 'inbox'",
    "direction": "VARCHAR(50) NOT NULL DEFAULT 'inbound'",
    "status": "VARCHAR(50) NOT NULL DEFAULT 'new'",
    "action_description": "TEXT",
    "key_dates_json": "TEXT",
    "key_amounts_json": "TEXT",
    "ai_analyzed": "BOOLEAN NOT NULL DEFAULT 0",
    "ai_confidence": "FLOAT",
    "last_reply_sent_at": "DATETIME",
    "spam_source": "VARCHAR(50)",
    "spam_reason": "TEXT",
    "applied_rules_json": "TEXT",
    "focus_flag": "BOOLEAN NOT NULL DEFAULT 0",
    "detected_source_language": "VARCHAR(10)",
    "preferred_reply_language": "VARCHAR(10)",
    "mailbox_id": "VARCHAR(100)",
    "mailbox_name": "VARCHAR(255)",
    "mailbox_address": "VARCHAR(255)",
    "has_attachments": "BOOLEAN NOT NULL DEFAULT 0",
    "requires_reply": "BOOLEAN NOT NULL DEFAULT 0",
    "assigned_to_user_id": "INTEGER",
    "assigned_by_user_id": "INTEGER",
    "assigned_at": "DATETIME",
    "sent_by_user_id": "INTEGER",
    "sent_review_summary": "TEXT",
    "sent_review_status": "VARCHAR(50)",
    "sent_review_issues_json": "TEXT",
    "sent_review_score": "FLOAT",
    "sent_review_suggested_improvement": "TEXT",
    "sent_reviewed_at": "DATETIME",
}
TASK_COLUMNS = {
    "thread_id": "VARCHAR(255)",
    "followup_started_at": "DATETIME",
    "expected_reply_by": "DATETIME",
    "closed_at": "DATETIME",
    "close_reason": "VARCHAR(255)",
    "followup_draft": "TEXT",
    "assigned_to_user_id": "INTEGER",
    "assigned_by_user_id": "INTEGER",
    "assigned_at": "DATETIME",
}
RUNTIME_SETTING_COLUMNS = {
    "ai_auto_spam_enabled": "BOOLEAN",
}
ATTACHMENT_COLUMNS = {
    "content_id": "VARCHAR(255)",
    "is_inline": "BOOLEAN NOT NULL DEFAULT 0",
}
ACTION_LOG_COLUMNS = {
    "user_id": "INTEGER",
}


def upgrade() -> None:
    _add_columns_if_missing("emails", EMAIL_COLUMNS)
    _add_columns_if_missing("tasks", TASK_COLUMNS)
    _add_columns_if_missing("runtime_settings", RUNTIME_SETTING_COLUMNS)
    _add_columns_if_missing("attachments", ATTACHMENT_COLUMNS)
    _add_columns_if_missing("action_log", ACTION_LOG_COLUMNS)


def downgrade() -> None:
    _drop_columns_if_present("action_log", ACTION_LOG_COLUMNS)
    _drop_columns_if_present("attachments", ATTACHMENT_COLUMNS)
    _drop_columns_if_present("runtime_settings", RUNTIME_SETTING_COLUMNS)
    _drop_columns_if_present("tasks", TASK_COLUMNS)
    _drop_columns_if_present("emails", EMAIL_COLUMNS)


def _add_columns_if_missing(table_name: str, columns: dict[str, str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, column_sql in columns.items():
        if column_name in existing:
            continue
        op.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def _drop_columns_if_present(table_name: str, columns: dict[str, str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for column_name in columns:
            if column_name in existing:
                batch_op.drop_column(column_name)
