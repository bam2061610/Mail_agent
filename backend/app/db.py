from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATA_DIR, settings

Base = declarative_base()


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _sqlite_file_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw_path = database_url.replace("sqlite:///", "", 1)
    if raw_path == ":memory:":
        return None
    return Path(raw_path)


engine = create_engine(
    settings.database_url,
    connect_args=_sqlite_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sqlite_path = _sqlite_file_path(settings.database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    from app.models import attachment, action_log, contact, email, task, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_email_columns()
    _ensure_task_columns()
    _ensure_attachment_columns()
    _ensure_action_log_columns()


def _ensure_email_columns() -> None:
    inspector = inspect(engine)
    if "emails" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("emails")}
    required_columns = {
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
        "sent_review_summary": "TEXT",
        "sent_review_status": "VARCHAR(50)",
        "sent_review_issues_json": "TEXT",
        "sent_review_score": "FLOAT",
        "sent_review_suggested_improvement": "TEXT",
        "sent_reviewed_at": "DATETIME",
    }

    with engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE emails ADD COLUMN {column_name} {column_sql}"))


def _ensure_task_columns() -> None:
    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("tasks")}
    required_columns = {
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

    with engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_sql}"))


def _ensure_attachment_columns() -> None:
    inspector = inspect(engine)
    if "attachments" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("attachments")}
    required_columns = {
        "content_id": "VARCHAR(255)",
        "is_inline": "BOOLEAN NOT NULL DEFAULT 0",
    }

    with engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE attachments ADD COLUMN {column_name} {column_sql}"))


def _ensure_action_log_columns() -> None:
    inspector = inspect(engine)
    if "action_log" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("action_log")}
    required_columns = {
        "user_id": "INTEGER",
    }

    with engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE action_log ADD COLUMN {column_name} {column_sql}"))


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
