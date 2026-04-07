from collections.abc import Generator
from contextvars import ContextVar, Token
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATA_DIR, settings

Base = declarative_base()
_CURRENT_MAILBOX_ID: ContextVar[str] = ContextVar("CURRENT_MAILBOX_ID", default="default")
_ACCOUNT_ENGINE_CACHE: dict[str, object] = {}
_ACCOUNT_SESSION_CACHE: dict[str, sessionmaker] = {}


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


def open_global_session():
    return SessionLocal()


def create_tables() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sqlite_path = _sqlite_file_path(settings.database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    from app.models import (  # noqa: F401
        action_log,
        attachment,
        contact,
        email,
        mailbox_account,
        runtime_setting,
        session_token,
        task,
        user,
    )

    _ensure_account_tables(engine)

    ensure_account_database("default")
    try:
        from app.services.mailbox_service import list_mailboxes

        for mailbox in list_mailboxes(redact_secrets=False):
            mailbox_id = str(mailbox.get("id") or "").strip()
            if mailbox_id:
                ensure_account_database(mailbox_id)
    except Exception:  # noqa: BLE001
        pass


def _ensure_account_tables(target_engine) -> None:
    Base.metadata.create_all(bind=target_engine)
    _ensure_email_columns(target_engine)
    _ensure_runtime_setting_columns(target_engine)
    _ensure_task_columns(target_engine)
    _ensure_attachment_columns(target_engine)
    _ensure_action_log_columns(target_engine)


def _ensure_email_columns(target_engine) -> None:
    inspector = inspect(target_engine)
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
        "importance_score": "INTEGER DEFAULT NULL",
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
        "imap_uid": "VARCHAR(100)",
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

    with target_engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE emails ADD COLUMN {column_name} {column_sql}"))


def _ensure_task_columns(target_engine) -> None:
    inspector = inspect(target_engine)
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

    with target_engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_sql}"))


def _ensure_runtime_setting_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    if "runtime_settings" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("runtime_settings")}
    required_columns = {
        "ai_auto_spam_enabled": "BOOLEAN",
        "summary_language": "VARCHAR(20)",
        "scan_since_date": "VARCHAR(50)",
        "run_background_jobs": "BOOLEAN",
        "run_mail_watchers": "BOOLEAN",
    }

    with target_engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE runtime_settings ADD COLUMN {column_name} {column_sql}"))


def _ensure_attachment_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    if "attachments" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("attachments")}
    required_columns = {
        "content_id": "VARCHAR(255)",
        "is_inline": "BOOLEAN NOT NULL DEFAULT 0",
    }

    with target_engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE attachments ADD COLUMN {column_name} {column_sql}"))


def _ensure_action_log_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    if "action_log" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("action_log")}
    required_columns = {
        "user_id": "INTEGER",
    }

    with target_engine.begin() as connection:
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE action_log ADD COLUMN {column_name} {column_sql}"))


def get_current_mailbox_id() -> str:
    return _CURRENT_MAILBOX_ID.get()


def set_current_mailbox_id(mailbox_id: str | None) -> Token[str]:
    normalized = str(mailbox_id or "default").strip() or "default"
    return _CURRENT_MAILBOX_ID.set(normalized)


def reset_current_mailbox_id(token: Token[str]) -> None:
    _CURRENT_MAILBOX_ID.reset(token)


def resolve_mailbox_id_from_request(request: Request | None = None) -> str:
    if request is not None:
        mailbox_id = request.query_params.get("mailbox_id") or request.headers.get("X-Mailbox-Id")
        if mailbox_id:
            return str(mailbox_id).strip() or "default"
    return get_current_mailbox_id()


def get_account_database_url(mailbox_id: str | None = None) -> str:
    resolved_mailbox_id = mailbox_id or get_current_mailbox_id()
    return f"sqlite:///{_account_database_path(resolved_mailbox_id).as_posix()}"


def ensure_account_database(mailbox_id: str | None = None) -> None:
    mailbox_id = str(mailbox_id or get_current_mailbox_id()).strip() or "default"
    session = open_account_session(mailbox_id)
    try:
        session.close()
    finally:
        pass


def list_account_database_ids() -> list[str]:
    root = _account_db_root()
    mailbox_ids: list[str] = ["default"]
    if root.exists():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if (child / "mail_agent.db").exists():
                mailbox_ids.append(child.name)
    unique_ids: list[str] = []
    for mailbox_id in mailbox_ids:
        if mailbox_id not in unique_ids:
            unique_ids.append(mailbox_id)
    return unique_ids


def open_account_session(mailbox_id: str | None = None):
    mailbox_id = str(mailbox_id or get_current_mailbox_id()).strip() or "default"
    cache_key = get_account_database_url(mailbox_id)
    session_factory = _ACCOUNT_SESSION_CACHE.get(cache_key)
    if session_factory is None:
        account_engine = _ACCOUNT_ENGINE_CACHE.get(cache_key)
        if account_engine is None:
            account_path = _account_database_path(mailbox_id)
            account_path.parent.mkdir(parents=True, exist_ok=True)
            account_engine = create_engine(
                cache_key,
                connect_args=_sqlite_connect_args(cache_key),
            )
            _ACCOUNT_ENGINE_CACHE[cache_key] = account_engine
        _ensure_account_tables(account_engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=account_engine)
        _ACCOUNT_SESSION_CACHE[cache_key] = session_factory
    return session_factory()


def get_global_db() -> Generator:
    db = open_global_session()
    try:
        yield db
    finally:
        db.close()


def get_db(request: Request) -> Generator:
    mailbox_id = resolve_mailbox_id_from_request(request)
    db = open_account_session(mailbox_id)
    try:
        yield db
    finally:
        db.close()


def _account_database_path(mailbox_id: str) -> Path:
    root = _account_db_root()
    safe_mailbox_id = "".join(ch for ch in mailbox_id if ch.isalnum() or ch in {"-", "_", "."}) or "default"
    return root / safe_mailbox_id / "mail_agent.db"


def _account_db_root() -> Path:
    sqlite_path = _sqlite_file_path(settings.database_url)
    if sqlite_path is not None:
        return sqlite_path.parent / "account_dbs"
    return DATA_DIR / "account_dbs"


def dispose_database_engines() -> None:
    try:
        engine.dispose()
    except Exception:  # noqa: BLE001
        pass

    for account_engine in list(_ACCOUNT_ENGINE_CACHE.values()):
        try:
            account_engine.dispose()
        except Exception:  # noqa: BLE001
            pass

    _ACCOUNT_ENGINE_CACHE.clear()
    _ACCOUNT_SESSION_CACHE.clear()
