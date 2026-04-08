from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect

import app.db as app_db
from app.config import get_effective_settings
from app.models.mailbox_account import MailboxAccount

SECRET_FIELDS = {"imap_password", "smtp_password"}
SENT_FOLDER_HINTS = ("sent", "outbox")
SENT_DIRECTION_VALUES = ("sent", "outbound")


def is_sent_folder(folder_name: str | None) -> bool:
    if not folder_name:
        return False
    normalized = folder_name.strip().lower()
    return any(hint in normalized for hint in SENT_FOLDER_HINTS)


def is_outgoing_direction(direction: str | None) -> bool:
    if not direction:
        return False
    return direction.strip().lower() in SENT_DIRECTION_VALUES


def get_thread_lookup_keys(email) -> list[str]:
    keys: list[str] = []
    for value in [getattr(email, "thread_id", None), getattr(email, "message_id", None)]:
        normalized = (value or "").strip()
        if not normalized or normalized in keys:
            continue
        keys.append(normalized)
    return keys


def list_mailboxes(redact_secrets: bool = True) -> list[dict[str, Any]]:
    if not _mailbox_table_exists():
        return []
    db = app_db.SessionLocal()
    try:
        rows = (
            db.query(MailboxAccount)
            .order_by(MailboxAccount.is_default_outgoing.desc(), MailboxAccount.created_at.asc())
            .all()
        )
        payload = [_mailbox_to_dict(row) for row in rows]
        if not redact_secrets:
            return payload

        redacted: list[dict[str, Any]] = []
        for item in payload:
            clean = item.copy()
            clean["has_imap_password"] = bool(clean.get("imap_password"))
            clean["has_smtp_password"] = bool(clean.get("smtp_password"))
            for field in SECRET_FIELDS:
                clean.pop(field, None)
            redacted.append(clean)
        return redacted
    finally:
        db.close()


def get_mailbox(mailbox_id: str, redact_secrets: bool = True) -> dict[str, Any] | None:
    if not _mailbox_table_exists():
        return None
    db = app_db.SessionLocal()
    try:
        row = db.get(MailboxAccount, mailbox_id)
        if row is None:
            return None
        payload = _mailbox_to_dict(row)
        if not redact_secrets:
            return payload
        sanitized = payload.copy()
        sanitized["has_imap_password"] = bool(sanitized.get("imap_password"))
        sanitized["has_smtp_password"] = bool(sanitized.get("smtp_password"))
        for field in SECRET_FIELDS:
            sanitized.pop(field, None)
        return sanitized
    finally:
        db.close()


def create_mailbox(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_mailbox_table()
    db = app_db.SessionLocal()
    try:
        return _create_mailbox_with_session(db, payload, commit=True)
    finally:
        db.close()


def create_mailbox_with_session(db, payload: dict[str, Any]) -> dict[str, Any]:
    return _create_mailbox_with_session(db, payload, commit=False)


def _create_mailbox_with_session(db, payload: dict[str, Any], *, commit: bool) -> dict[str, Any]:
    existing = db.query(MailboxAccount).all()
    now = datetime.now(timezone.utc)
    mailbox = MailboxAccount(
        id=str(payload.get("id") or uuid4()),
        name=str(payload.get("name") or payload.get("email_address") or "Mailbox").strip(),
        email_address=str(payload.get("email_address") or "").strip().lower(),
        imap_host=str(payload.get("imap_host") or "").strip(),
        imap_port=int(payload.get("imap_port") or 993),
        imap_username=str(payload.get("imap_username") or payload.get("email_address") or "").strip(),
        imap_password=str(payload.get("imap_password") or "").strip(),
        smtp_host=str(payload.get("smtp_host") or "").strip(),
        smtp_port=int(payload.get("smtp_port") or 465),
        smtp_username=str(payload.get("smtp_username") or payload.get("email_address") or "").strip(),
        smtp_password=str(payload.get("smtp_password") or "").strip(),
        smtp_use_tls=bool(payload.get("smtp_use_tls", True)),
        smtp_use_ssl=bool(payload.get("smtp_use_ssl", True)),
        enabled=bool(payload.get("enabled", True)),
        is_default_outgoing=bool(payload.get("is_default_outgoing", not existing)),
        created_at=now,
        updated_at=now,
    )
    if mailbox.is_default_outgoing:
        for item in existing:
            item.is_default_outgoing = False
    db.add(mailbox)
    if commit:
        db.commit()
    else:
        db.flush()
    app_db.ensure_account_database(mailbox.id)
    payload = _mailbox_to_dict(mailbox)
    payload["has_imap_password"] = bool(payload.get("imap_password"))
    payload["has_smtp_password"] = bool(payload.get("smtp_password"))
    for field in SECRET_FIELDS:
        payload.pop(field, None)
    return payload


def update_mailbox(mailbox_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    _ensure_mailbox_table()
    db = app_db.SessionLocal()
    try:
        return _update_mailbox_with_session(db, mailbox_id, payload)
    finally:
        db.close()


def delete_mailbox(mailbox_id: str) -> bool:
    _ensure_mailbox_table()
    db = app_db.SessionLocal()
    try:
        return _delete_mailbox_with_session(db, mailbox_id)
    finally:
        db.close()


def update_mailbox_with_session(db, mailbox_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _update_mailbox_with_session(db, mailbox_id, payload)


def delete_mailbox_with_session(db, mailbox_id: str) -> bool:
    return _delete_mailbox_with_session(db, mailbox_id)


def _update_mailbox_with_session(db, mailbox_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    mailbox = db.get(MailboxAccount, mailbox_id)
    if mailbox is None:
        return None

    for key in [
        "name",
        "email_address",
        "imap_host",
        "imap_port",
        "imap_username",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "enabled",
        "is_default_outgoing",
        "smtp_use_tls",
        "smtp_use_ssl",
    ]:
        if key in payload and payload[key] is not None:
            setattr(mailbox, key, payload[key])
    if payload.get("imap_password"):
        mailbox.imap_password = str(payload["imap_password"])
    if payload.get("smtp_password"):
        mailbox.smtp_password = str(payload["smtp_password"])
    mailbox.updated_at = datetime.now(timezone.utc)

    if mailbox.is_default_outgoing:
        for item in db.query(MailboxAccount).filter(MailboxAccount.id != mailbox_id).all():
            item.is_default_outgoing = False

    db.commit()
    return get_mailbox(mailbox_id, redact_secrets=True)


def _delete_mailbox_with_session(db, mailbox_id: str) -> bool:
    mailbox = db.get(MailboxAccount, mailbox_id)
    if mailbox is None:
        return False
    db.delete(mailbox)
    db.flush()
    remaining = db.query(MailboxAccount).order_by(MailboxAccount.created_at.asc()).all()
    if remaining and not any(item.is_default_outgoing for item in remaining):
        remaining[0].is_default_outgoing = True
    db.commit()
    return True


def get_enabled_mailbox_configs() -> list[SimpleNamespace]:
    _ensure_mailbox_table()
    db = app_db.SessionLocal()
    try:
        enabled = (
            db.query(MailboxAccount)
            .filter(MailboxAccount.enabled.is_(True))
            .order_by(MailboxAccount.is_default_outgoing.desc(), MailboxAccount.created_at.asc())
            .all()
        )
        if enabled:
            return [to_runtime_mailbox(_mailbox_to_dict(item)) for item in enabled]
    finally:
        db.close()

    fallback = get_default_runtime_mailbox_from_settings()
    return [fallback] if fallback else []


def get_outgoing_mailbox_for_email(email) -> SimpleNamespace | None:
    _ensure_mailbox_table()
    if getattr(email, "mailbox_id", None):
        mailbox = get_mailbox(str(email.mailbox_id), redact_secrets=False)
        if mailbox and mailbox.get("enabled", True):
            return to_runtime_mailbox(mailbox)

    db = app_db.SessionLocal()
    try:
        all_mailboxes = (
            db.query(MailboxAccount)
            .filter(MailboxAccount.enabled.is_(True))
            .order_by(MailboxAccount.is_default_outgoing.desc(), MailboxAccount.created_at.asc())
            .all()
        )
        if all_mailboxes:
            default = next((item for item in all_mailboxes if item.is_default_outgoing), all_mailboxes[0])
            return to_runtime_mailbox(_mailbox_to_dict(default))
    finally:
        db.close()
    return get_default_runtime_mailbox_from_settings()


def get_default_runtime_mailbox_from_settings() -> SimpleNamespace | None:
    settings = get_effective_settings()
    if not settings.imap_host and not settings.smtp_host:
        return None
    return SimpleNamespace(
        id="default",
        name="Default mailbox",
        email_address=getattr(settings, "smtp_user", "") or getattr(settings, "imap_user", ""),
        imap_host=getattr(settings, "imap_host", ""),
        imap_port=getattr(settings, "imap_port", 993),
        imap_username=getattr(settings, "imap_user", ""),
        imap_password=getattr(settings, "imap_password", ""),
        smtp_host=getattr(settings, "smtp_host", ""),
        smtp_port=getattr(settings, "smtp_port", 465),
        smtp_username=getattr(settings, "smtp_user", ""),
        smtp_password=getattr(settings, "smtp_password", ""),
        smtp_use_tls=getattr(settings, "smtp_use_tls", True),
        smtp_use_ssl=getattr(settings, "smtp_use_ssl", True),
        enabled=True,
        is_default_outgoing=True,
    )


def to_runtime_mailbox(mailbox: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(mailbox.get("id") or ""),
        name=str(mailbox.get("name") or mailbox.get("email_address") or "Mailbox"),
        email_address=str(mailbox.get("email_address") or "").strip().lower(),
        imap_host=str(mailbox.get("imap_host") or "").strip(),
        imap_port=int(mailbox.get("imap_port") or 993),
        imap_username=str(mailbox.get("imap_username") or mailbox.get("email_address") or "").strip(),
        imap_password=str(mailbox.get("imap_password") or "").strip(),
        smtp_host=str(mailbox.get("smtp_host") or "").strip(),
        smtp_port=int(mailbox.get("smtp_port") or 465),
        smtp_username=str(mailbox.get("smtp_username") or mailbox.get("email_address") or "").strip(),
        smtp_password=str(mailbox.get("smtp_password") or "").strip(),
        smtp_use_tls=bool(mailbox.get("smtp_use_tls", True)),
        smtp_use_ssl=bool(mailbox.get("smtp_use_ssl", True)),
        enabled=bool(mailbox.get("enabled", True)),
        is_default_outgoing=bool(mailbox.get("is_default_outgoing", False)),
    )


def _mailbox_to_dict(mailbox: MailboxAccount | Any) -> dict[str, Any]:
    return {
        "id": str(mailbox.id),
        "name": mailbox.name,
        "email_address": mailbox.email_address,
        "imap_host": mailbox.imap_host,
        "imap_port": mailbox.imap_port,
        "imap_username": mailbox.imap_username,
        "imap_password": mailbox.imap_password,
        "smtp_host": mailbox.smtp_host,
        "smtp_port": mailbox.smtp_port,
        "smtp_username": mailbox.smtp_username,
        "smtp_password": mailbox.smtp_password,
        "smtp_use_tls": mailbox.smtp_use_tls,
        "smtp_use_ssl": mailbox.smtp_use_ssl,
        "enabled": mailbox.enabled,
        "is_default_outgoing": mailbox.is_default_outgoing,
        "created_at": mailbox.created_at.isoformat() if mailbox.created_at else None,
        "updated_at": mailbox.updated_at.isoformat() if mailbox.updated_at else None,
    }


def _ensure_mailbox_table() -> None:
    if _mailbox_table_exists():
        return
    app_db.create_tables()
    if _mailbox_table_exists():
        return
    # Legacy or manually modified environments can report a current Alembic revision
    # while still missing this table. Create just the mailbox table as a targeted recovery.
    MailboxAccount.__table__.create(bind=app_db.engine, checkfirst=True)
    if not _mailbox_table_exists():
        raise RuntimeError("Mailbox schema is unavailable after migration bootstrap")


def _mailbox_table_exists() -> bool:
    try:
        return "mailbox_accounts" in inspect(app_db.engine).get_table_names()
    except Exception:  # noqa: BLE001
        return False
