from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any

import imaplib
from sqlalchemy.orm import Session

from app.models.email import Email
from app.services.imap_scanner import connect_imap

logger = logging.getLogger(__name__)

FOLDER_KIND_CANDIDATES: dict[str, list[str]] = {
    "inbox": ["INBOX", "Inbox"],
    "spam": [
        "Spam",
        "Junk",
        "Junk E-mail",
        "Bulk Mail",
        "[Gmail]/Spam",
        "[Gmail]/Junk",
    ],
    "archive": [
        "Archive",
        "Archived",
        "All Mail",
        "[Gmail]/All Mail",
    ],
    "reply_later": ["Reply Later"],
    "sent": [
        "Sent",
        "Sent Items",
        "Sent Messages",
        "INBOX.Sent",
        "INBOX.Sent Items",
        "INBOX.Sent Messages",
        "[Gmail]/Sent Mail",
    ],
}


@dataclass(slots=True)
class MailboxActionResult:
    status: str
    folder: str | None
    message_id: str | None
    action: str
    details: dict[str, Any]


def archive_email_via_imap(db_session: Session, email: Email, mailbox_config) -> MailboxActionResult:
    return move_email_via_imap(db_session, email, mailbox_config, "archive", mark_seen=True, set_archived=True)


def spam_email_via_imap(db_session: Session, email: Email, mailbox_config) -> MailboxActionResult:
    return move_email_via_imap(db_session, email, mailbox_config, "spam", mark_seen=True, set_spam=True)


def reply_later_email_via_imap(db_session: Session, email: Email, mailbox_config) -> MailboxActionResult:
    return move_email_via_imap(
        db_session,
        email,
        mailbox_config,
        "reply_later",
        mark_seen=True,
        set_reply_later=True,
    )


def move_email_via_imap(
    db_session: Session,
    email: Email,
    mailbox_config,
    folder_kind: str,
    *,
    mark_seen: bool = True,
    set_archived: bool = False,
    set_spam: bool = False,
    set_reply_later: bool = False,
) -> MailboxActionResult:
    if not getattr(email, "message_id", None):
        raise ValueError("Email message_id is required for IMAP actions")

    source_folder = _normalize_folder_name(getattr(email, "folder", None)) or "INBOX"
    target_folder = folder_kind  # fallback if IMAP unavailable
    imap_moved = False
    message_uid = None

    connection = connect_imap(mailbox_config)
    try:
        target_folder = resolve_target_folder(connection, folder_kind)
        if _normalize_folder_name(source_folder) != _normalize_folder_name(target_folder):
            message_uid = _find_message_uid(connection, source_folder, email.message_id)
            if message_uid is None:
                logger.warning(
                    "Message %s not found in IMAP folder %s; DB-only update",
                    email.message_id,
                    source_folder,
                )
            elif _ensure_folder_exists(connection, target_folder):
                if mark_seen:
                    _safe_uid_command(connection, "store", message_uid, "+FLAGS.SILENT", r"(\Seen)")
                copy_status, _ = _safe_uid_command(connection, "copy", message_uid, target_folder)
                if _is_ok(copy_status):
                    _safe_uid_command(connection, "store", message_uid, "+FLAGS.SILENT", r"(\Deleted)")
                    _safe_expunge(connection)
                    email.folder = target_folder
                    imap_moved = True
                else:
                    logger.warning("IMAP copy to %s failed; DB-only update", target_folder)
            else:
                logger.warning("IMAP folder %s unavailable; DB-only update", target_folder)
        else:
            # already in correct folder — still apply DB status below
            pass
    except Exception:
        logger.warning(
            "IMAP action failed for email_id=%s kind=%s; falling back to DB-only update",
            email.id,
            folder_kind,
            exc_info=True,
        )
    finally:
        _close_connection(connection)

    _apply_db_status(db_session, email, set_archived=set_archived, set_spam=set_spam, set_reply_later=set_reply_later)
    db_session.commit()

    return MailboxActionResult(
        status="moved" if imap_moved else "db_only",
        folder=target_folder,
        message_id=email.message_id,
        action=folder_kind,
        details={
            "source_folder": source_folder,
            "target_folder": target_folder,
            "message_uid": message_uid.decode("utf-8", "ignore") if isinstance(message_uid, bytes) else message_uid,
            "imap_moved": imap_moved,
        },
    )


def append_sent_copy_to_imap(
    mailbox_config,
    message: EmailMessage,
    *,
    folder_kind: str = "sent",
    save_copy_as_seen: bool = True,
) -> str:
    connection = connect_imap(mailbox_config)
    try:
        folder = resolve_target_folder(connection, folder_kind)
        if not _ensure_folder_exists(connection, folder):
            logger.warning("Sent folder %s unavailable; skipping sent copy", folder)
            return folder
        flags = "\\Seen" if save_copy_as_seen else None
        date_time = format_datetime(datetime.now(timezone.utc))
        raw_bytes = message.as_bytes()
        append_args = [folder]
        if flags:
            append_args.append(flags)
        append_args.append(date_time)
        append_args.append(raw_bytes)
        status, _ = connection.append(*append_args)
        if not _is_ok(status):
            logger.warning("Unable to append message to IMAP folder %s", folder)
        return folder
    except Exception:
        logger.warning("Failed to append sent message copy to IMAP folder", exc_info=True)
        return folder_kind
    finally:
        _close_connection(connection)


def resolve_target_folder(connection: Any, folder_kind: str) -> str:
    normalized_kind = (folder_kind or "").strip().lower()
    candidates = FOLDER_KIND_CANDIDATES.get(normalized_kind, [folder_kind])
    available = _list_folders(connection)
    existing = _match_existing_folder(available, candidates)
    if existing:
        return existing
    if normalized_kind == "reply_later":
        return "Reply Later"
    if normalized_kind == "spam":
        return "Spam"
    if normalized_kind == "archive":
        return "Archive"
    if normalized_kind == "sent":
        return "Sent"
    return folder_kind


def _ensure_folder_exists(connection: Any, folder_name: str) -> bool:
    available = _list_folders(connection)
    if _match_existing_folder(available, [folder_name]):
        return True
    result = getattr(connection, "create", None)
    if callable(result):
        status, _ = result(folder_name)
        if _is_ok(status):
            return True
    logger.warning("Unable to create IMAP folder %s; will skip IMAP move", folder_name)
    return False


def _apply_db_status(
    db_session: Session,
    email: Email,
    *,
    set_archived: bool,
    set_spam: bool,
    set_reply_later: bool,
) -> None:
    if set_archived:
        email.status = "archived"
        email.requires_reply = False
    elif set_spam:
        email.status = "spam"
        email.is_spam = True
        email.spam_source = "user"
        email.spam_reason = "Moved to spam folder"
        email.requires_reply = False
    elif set_reply_later:
        email.status = "archived"
        email.requires_reply = False
    email.updated_at = datetime.now(timezone.utc)
    db_session.add(email)


def _find_message_uid(connection: Any, folder: str, message_id: str) -> bytes | None:
    status, _ = _select_folder(connection, folder)
    if not _is_ok(status):
        raise RuntimeError(f"Unable to select folder {folder}")
    search_status, data = _safe_uid_command(connection, "search", None, "HEADER", "Message-ID", message_id)
    if not _is_ok(search_status) or not data or not data[0]:
        return None
    uids = data[0].split()
    return uids[0] if uids else None


def _list_folders(connection: Any) -> list[str]:
    try:
        status, folder_list = connection.list()
    except Exception:  # noqa: BLE001
        return []
    if not _is_ok(status) or not folder_list:
        return []
    folders: list[str] = []
    for entry in folder_list:
        if entry is None:
            continue
        decoded = entry.decode("utf-8", errors="ignore") if isinstance(entry, bytes) else str(entry)
        parts = decoded.rsplit('" ', 1)
        if len(parts) >= 2:
            folders.append(parts[-1].strip().strip('"'))
    return folders


def _match_existing_folder(available: list[str], candidates: list[str]) -> str | None:
    normalized_available = {item.strip().lower(): item for item in available if item}
    for candidate in candidates:
        if not candidate:
            continue
        existing = normalized_available.get(candidate.strip().lower())
        if existing:
            return existing
    return None


def _normalize_folder_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    return normalized or None


def _safe_uid_command(connection: Any, command: str, *args: Any):
    uid = getattr(connection, "uid", None)
    if not callable(uid):
        raise RuntimeError("IMAP connection does not support UID commands")
    return uid(command, *args)


def _select_folder(connection: Any, folder: str):
    select = getattr(connection, "select", None)
    if not callable(select):
        raise RuntimeError("IMAP connection does not support select")
    return select(folder, readonly=True)


def _safe_expunge(connection: Any) -> None:
    expunge = getattr(connection, "expunge", None)
    if callable(expunge):
        expunge()


def _is_ok(status: Any) -> bool:
    return str(status).upper() == "OK"


def _close_connection(connection: Any | None) -> None:
    if connection is None:
        return
    try:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
    except Exception:  # noqa: BLE001
        pass
    try:
        logout = getattr(connection, "logout", None)
        if callable(logout):
            logout()
    except Exception:  # noqa: BLE001
        pass
