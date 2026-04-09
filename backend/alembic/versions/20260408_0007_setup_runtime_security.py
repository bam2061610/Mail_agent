"""setup runtime settings, secure sessions, and db-backed stores

Revision ID: 20260408_0007
Revises: 20260408_0006
Create Date: 2026-04-08 00:10:00
"""

from __future__ import annotations

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "20260408_0007"
down_revision = "20260408_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_runtime_setting_columns(inspector)
    _migrate_session_tokens(inspector)
    _add_attachment_columns(inspector)
    _create_rules_table(inspector)
    _create_templates_table(inspector)
    _add_email_status_constraint(inspector)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "templates" in inspector.get_table_names():
        op.drop_table("templates")
    if "rules" in inspector.get_table_names():
        op.drop_table("rules")


def _add_runtime_setting_columns(inspector: sa.Inspector) -> None:
    if "runtime_settings" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("runtime_settings")}
    columns = {
        "key": "VARCHAR(255)",
        "value_json": "TEXT",
        "setup_completed": "BOOLEAN NOT NULL DEFAULT 0",
        "deepseek_api_key": "TEXT",
        "ai_analysis_enabled": "BOOLEAN",
        "scheduler_interval_minutes": "INTEGER",
        "max_emails_per_scan": "INTEGER",
    }
    for column_name, column_sql in columns.items():
        if column_name not in existing:
            op.execute(sa.text(f"ALTER TABLE runtime_settings ADD COLUMN {column_name} {column_sql}"))

    refreshed = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("runtime_settings")}
    if "deepseek_api_key" in refreshed and "openai_api_key" in refreshed:
        op.execute(
            sa.text(
                "UPDATE runtime_settings "
                "SET deepseek_api_key = COALESCE(deepseek_api_key, openai_api_key) "
                "WHERE key IS NULL"
            )
        )
    if "scheduler_interval_minutes" in refreshed and "scan_interval_minutes" in refreshed:
        op.execute(
            sa.text(
                "UPDATE runtime_settings "
                "SET scheduler_interval_minutes = COALESCE(scheduler_interval_minutes, scan_interval_minutes) "
                "WHERE key IS NULL"
            )
        )


def _migrate_session_tokens(inspector: sa.Inspector) -> None:
    if "session_tokens" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("session_tokens")}
    if "token_hash" not in existing:
        op.execute(sa.text("ALTER TABLE session_tokens ADD COLUMN token_hash VARCHAR(64)"))

    refreshed = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("session_tokens")}
    if "token" in refreshed:
        rows = op.get_bind().execute(sa.text("SELECT id, token FROM session_tokens")).fetchall()
        for row in rows:
            if not row.token:
                continue
            token_hash = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
            op.get_bind().execute(
                sa.text("UPDATE session_tokens SET token_hash = :token_hash WHERE id = :id"),
                {"id": row.id, "token_hash": token_hash},
            )

        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("session_tokens")}
        if "ix_session_tokens_token" in indexes:
            op.drop_index("ix_session_tokens_token", table_name="session_tokens")

        with op.batch_alter_table("session_tokens", schema=None) as batch_op:
            refreshed = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("session_tokens")}
            if "token" in refreshed:
                batch_op.drop_column("token")

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("session_tokens")}
    if "ix_session_tokens_token_hash" not in indexes:
        op.create_index("ix_session_tokens_token_hash", "session_tokens", ["token_hash"], unique=True)


def _add_attachment_columns(inspector: sa.Inspector) -> None:
    if "attachments" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("attachments")}
    if "content_hash" not in existing:
        op.execute(sa.text("ALTER TABLE attachments ADD COLUMN content_hash VARCHAR(64)"))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("attachments")}
    if "ix_attachments_content_hash" not in indexes:
        op.create_index("ix_attachments_content_hash", "attachments", ["content_hash"], unique=False)


def _create_rules_table(inspector: sa.Inspector) -> None:
    if "rules" in inspector.get_table_names():
        return
    op.create_table(
        "rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("conditions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _create_templates_table(inspector: sa.Inspector) -> None:
    if "templates" in inspector.get_table_names():
        return
    op.create_table(
        "templates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False, server_default="general"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _add_email_status_constraint(inspector: sa.Inspector) -> None:
    if "emails" not in inspector.get_table_names():
        return
    checks = {item.get("name") for item in inspector.get_check_constraints("emails")}
    if "ck_emails_status_valid" in checks:
        return
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_emails_status_valid",
            "status IN ('new','read','reply_later','processed','replied','archived','spam')",
        )
