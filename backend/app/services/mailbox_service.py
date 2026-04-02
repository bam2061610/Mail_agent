import json
import logging
from datetime import datetime

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.config import DATA_DIR, get_effective_settings

logger = logging.getLogger(__name__)

MAILBOXES_FILE_PATH = DATA_DIR / "mailboxes.json"
SECRET_FIELDS = {"imap_password", "smtp_password"}


def list_mailboxes(redact_secrets: bool = True) -> list[dict[str, Any]]:
    payload = _load_mailboxes()
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


def get_mailbox(mailbox_id: str, redact_secrets: bool = True) -> dict[str, Any] | None:
    for mailbox in list_mailboxes(redact_secrets=False):
        if mailbox.get("id") == mailbox_id:
            if not redact_secrets:
                return mailbox
            sanitized = mailbox.copy()
            sanitized["has_imap_password"] = bool(sanitized.get("imap_password"))
            sanitized["has_smtp_password"] = bool(sanitized.get("smtp_password"))
            for field in SECRET_FIELDS:
                sanitized.pop(field, None)
            return sanitized
    return None


def create_mailbox(payload: dict[str, Any]) -> dict[str, Any]:
    mailboxes = _load_mailboxes()
    now = datetime.utcnow().isoformat()
    mailbox = {
        "id": payload.get("id") or str(uuid4()),
        "name": str(payload.get("name") or payload.get("email_address") or "Mailbox").strip(),
        "email_address": str(payload.get("email_address") or "").strip().lower(),
        "imap_host": str(payload.get("imap_host") or "").strip(),
        "imap_port": int(payload.get("imap_port") or 993),
        "imap_username": str(payload.get("imap_username") or payload.get("email_address") or "").strip(),
        "imap_password": str(payload.get("imap_password") or "").strip(),
        "smtp_host": str(payload.get("smtp_host") or "").strip(),
        "smtp_port": int(payload.get("smtp_port") or 465),
        "smtp_username": str(payload.get("smtp_username") or payload.get("email_address") or "").strip(),
        "smtp_password": str(payload.get("smtp_password") or "").strip(),
        "smtp_use_tls": bool(payload.get("smtp_use_tls", True)),
        "smtp_use_ssl": bool(payload.get("smtp_use_ssl", True)),
        "enabled": bool(payload.get("enabled", True)),
        "is_default_outgoing": bool(payload.get("is_default_outgoing", not mailboxes)),
        "created_at": now,
        "updated_at": now,
    }
    if mailbox["is_default_outgoing"]:
        for item in mailboxes:
            item["is_default_outgoing"] = False
    mailboxes.append(mailbox)
    _save_mailboxes(mailboxes)
    return get_mailbox(mailbox["id"], redact_secrets=True) or {}


def update_mailbox(mailbox_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    mailboxes = _load_mailboxes()
    updated_mailbox: dict[str, Any] | None = None
    for mailbox in mailboxes:
        if mailbox.get("id") != mailbox_id:
            continue
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
                mailbox[key] = payload[key]
        if payload.get("imap_password"):
            mailbox["imap_password"] = str(payload["imap_password"])
        if payload.get("smtp_password"):
            mailbox["smtp_password"] = str(payload["smtp_password"])
        mailbox["updated_at"] = datetime.utcnow().isoformat()
        updated_mailbox = mailbox
        break
    if updated_mailbox is None:
        return None
    if updated_mailbox.get("is_default_outgoing"):
        for mailbox in mailboxes:
            if mailbox.get("id") != mailbox_id:
                mailbox["is_default_outgoing"] = False
    _save_mailboxes(mailboxes)
    return get_mailbox(mailbox_id, redact_secrets=True)


def delete_mailbox(mailbox_id: str) -> bool:
    mailboxes = _load_mailboxes()
    filtered = [item for item in mailboxes if item.get("id") != mailbox_id]
    if len(filtered) == len(mailboxes):
        return False
    if filtered and not any(item.get("is_default_outgoing") for item in filtered):
        filtered[0]["is_default_outgoing"] = True
    _save_mailboxes(filtered)
    return True


def get_enabled_mailbox_configs() -> list[SimpleNamespace]:
    enabled = [item for item in list_mailboxes(redact_secrets=False) if item.get("enabled", True)]
    if enabled:
        return [to_runtime_mailbox(item) for item in enabled]

    fallback = get_default_runtime_mailbox_from_settings()
    return [fallback] if fallback else []


def get_outgoing_mailbox_for_email(email) -> SimpleNamespace | None:
    if getattr(email, "mailbox_id", None):
        mailbox = get_mailbox(str(email.mailbox_id), redact_secrets=False)
        if mailbox and mailbox.get("enabled", True):
            return to_runtime_mailbox(mailbox)

    all_mailboxes = [item for item in list_mailboxes(redact_secrets=False) if item.get("enabled", True)]
    if all_mailboxes:
        default = next((item for item in all_mailboxes if item.get("is_default_outgoing")), all_mailboxes[0])
        return to_runtime_mailbox(default)
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


def _load_mailboxes() -> list[dict[str, Any]]:
    if not MAILBOXES_FILE_PATH.exists():
        return []
    try:
        raw = json.loads(MAILBOXES_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not parse mailbox store: %s", MAILBOXES_FILE_PATH)
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _save_mailboxes(payload: list[dict[str, Any]]) -> None:
    MAILBOXES_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAILBOXES_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
