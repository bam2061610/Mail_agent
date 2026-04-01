from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    settings.database_url,
    connect_args=_sqlite_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    if settings.database_url.startswith("sqlite:///./"):
        Path("data").mkdir(parents=True, exist_ok=True)

    from app.models import action_log, contact, email, task  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_email_columns()
    _ensure_task_columns()


def _ensure_email_columns() -> None:
    inspector = inspect(engine)
    if "emails" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("emails")}
    required_columns = {
        "action_description": "TEXT",
        "key_dates_json": "TEXT",
        "key_amounts_json": "TEXT",
        "ai_analyzed": "BOOLEAN NOT NULL DEFAULT 0",
        "last_reply_sent_at": "DATETIME",
        "spam_source": "VARCHAR(50)",
        "spam_reason": "TEXT",
        "applied_rules_json": "TEXT",
        "focus_flag": "BOOLEAN NOT NULL DEFAULT 0",
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
    }

    with engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_sql}"))


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
