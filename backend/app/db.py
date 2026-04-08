from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Generator
from contextvars import ContextVar, Token
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATA_DIR, settings
from app.core.process_lock import acquire_process_lock, release_process_lock

Base = declarative_base()
_CURRENT_MAILBOX_ID: ContextVar[str] = ContextVar("CURRENT_MAILBOX_ID", default="default")
_ACCOUNT_ENGINE_CACHE: dict[str, object] = {}
_ACCOUNT_SESSION_CACHE: dict[str, sessionmaker] = {}
BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
ALEMBIC_SCRIPT_PATH = BACKEND_DIR / "alembic"
SCHEMA_LOCK_PATH = DATA_DIR / "schema-migrations.lock"
SCHEMA_LOCK_WAIT_SECONDS = 60.0
logger = logging.getLogger(__name__)


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
    _prepare_sqlite_paths()
    _load_models()
    lock = _acquire_schema_lock()
    try:
        _run_database_migrations(settings.database_url)
        for mailbox_id in _discover_mailbox_ids():
            _run_database_migrations(get_account_database_url(mailbox_id))
    finally:
        release_process_lock(lock)


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
    current = get_current_mailbox_id()
    if current != "default":
        return current
    for mid in list_account_database_ids():
        if mid != "default":
            return mid
    return current


def get_account_database_url(mailbox_id: str | None = None) -> str:
    resolved_mailbox_id = mailbox_id or get_current_mailbox_id()
    return f"sqlite:///{_account_database_path(resolved_mailbox_id).as_posix()}"


def ensure_account_database(mailbox_id: str | None = None) -> None:
    mailbox_id = str(mailbox_id or get_current_mailbox_id()).strip() or "default"
    _prepare_sqlite_paths()
    _load_models()
    lock = _acquire_schema_lock()
    try:
        _run_database_migrations(get_account_database_url(mailbox_id))
    finally:
        release_process_lock(lock)


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
        ensure_account_database(mailbox_id)
        account_engine = _ACCOUNT_ENGINE_CACHE.get(cache_key)
        if account_engine is None:
            account_path = _account_database_path(mailbox_id)
            account_path.parent.mkdir(parents=True, exist_ok=True)
            account_engine = create_engine(
                cache_key,
                connect_args=_sqlite_connect_args(cache_key),
            )
            _ACCOUNT_ENGINE_CACHE[cache_key] = account_engine
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
        logger.warning("Failed to dispose primary database engine", exc_info=True)

    for account_engine in list(_ACCOUNT_ENGINE_CACHE.values()):
        try:
            account_engine.dispose()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to dispose account database engine", exc_info=True)

    _ACCOUNT_ENGINE_CACHE.clear()
    _ACCOUNT_SESSION_CACHE.clear()


def _prepare_sqlite_paths() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sqlite_path = _sqlite_file_path(settings.database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    _account_db_root().mkdir(parents=True, exist_ok=True)


def _load_models() -> None:
    from app.models import (  # noqa: F401
        action_log,
        attachment,
        contact,
        email,
        mailbox_account,
        rule,
        runtime_setting,
        session_token,
        task,
        template,
        user,
    )


def _discover_mailbox_ids() -> list[str]:
    mailbox_ids = ["default"]
    try:
        from app.services.mailbox_service import list_mailboxes

        for mailbox in list_mailboxes(redact_secrets=False):
            mailbox_id = str(mailbox.get("id") or "").strip()
            if mailbox_id and mailbox_id not in mailbox_ids:
                mailbox_ids.append(mailbox_id)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to discover mailbox ids for account database migration", exc_info=True)
    return mailbox_ids


def _run_database_migrations(database_url: str) -> None:
    sqlite_path = _sqlite_file_path(database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    alembic_command = importlib.import_module("alembic.command")
    alembic_config = importlib.import_module("alembic.config")

    config = alembic_config.Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    alembic_command.upgrade(config, "head")


def _acquire_schema_lock():
    deadline = time.monotonic() + SCHEMA_LOCK_WAIT_SECONDS
    while True:
        lock = acquire_process_lock(SCHEMA_LOCK_PATH)
        if lock.acquired:
            return lock
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for schema migration lock: {SCHEMA_LOCK_PATH}")
        time.sleep(0.1)
