from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.imap_scanner import connect_imap

logger = logging.getLogger(__name__)

ROOT_FOLDER = "OMA"
TARGET_FOLDER_SUFFIXES = {
    "archive": "Archive",
    "archived": "Archive",
    "spam": "Spam",
    "processed": "Processed",
    "reply_later": "ReplyLater",
    "replylater": "ReplyLater",
    "reply later": "ReplyLater",
}

_FOLDER_STATE_CACHE: dict[str, "MailboxFolderState"] = {}


@dataclass(slots=True)
class MailboxFolderState:
    separator: str
    root_folder: str | None
    archive_folder: str | None
    spam_folder: str | None
    processed_folder: str | None
    reply_later_folder: str | None


@dataclass(slots=True)
class ImapMoveResult:
    status: str
    source_uid: str | None
    target_uid: str | None
    source_folder: str | None
    target_folder: str
    used_move_command: bool


def ensure_folders(mailbox) -> MailboxFolderState:
    cache_key = _mailbox_cache_key(mailbox)
    cached = _FOLDER_STATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    connection = connect_imap(mailbox)
    try:
        return _ensure_folders_on_connection(connection, mailbox, cache_key)
    finally:
        _close_connection(connection)


def move_email(
    mailbox,
    imap_uid: str | bytes | None,
    target_folder: str,
    *,
    source_folder: str | None = None,
    message_id: str | None = None,
) -> ImapMoveResult:
    connection = connect_imap(mailbox)
    try:
        state = _get_folder_state(connection, mailbox)
        resolved_source_folder = _resolve_folder_hint(state, source_folder or "INBOX")
        resolved_target_folder = _resolve_folder_hint(state, target_folder)
        if resolved_target_folder is None:
            raise RuntimeError("Target IMAP folder could not be resolved")

        if resolved_source_folder and resolved_target_folder and resolved_source_folder.lower() == resolved_target_folder.lower():
            resolved_uid = _normalize_uid(imap_uid)
            if resolved_uid is None and message_id:
                resolved_uid = _find_message_uid(connection, resolved_source_folder, message_id)
            return ImapMoveResult(
                status="noop",
                source_uid=resolved_uid,
                target_uid=resolved_uid,
                source_folder=resolved_source_folder,
                target_folder=resolved_target_folder,
                used_move_command=False,
            )

        if not resolved_source_folder:
            raise RuntimeError("Source IMAP folder could not be resolved")

        resolved_uid = _normalize_uid(imap_uid)
        if resolved_uid is None and message_id:
            resolved_uid = _find_message_uid(connection, resolved_source_folder, message_id)
        if resolved_uid is None:
            raise RuntimeError("Message UID could not be determined for IMAP move")

        _select_folder(connection, resolved_source_folder, readonly=False)
        used_move_command = _connection_supports_move(connection)
        if used_move_command:
            move_status, _ = _safe_uid_command(connection, "move", resolved_uid, resolved_target_folder)
            if not _is_ok(move_status):
                raise RuntimeError(f"IMAP MOVE failed for {resolved_source_folder} -> {resolved_target_folder}")
        else:
            copy_status, _ = _safe_uid_command(connection, "copy", resolved_uid, resolved_target_folder)
            if not _is_ok(copy_status):
                raise RuntimeError(f"Unable to copy message to {resolved_target_folder}")
            _safe_uid_command(connection, "store", resolved_uid, "+FLAGS.SILENT", r"(\Deleted)")
            _safe_expunge(connection)

        target_uid = _find_message_uid(connection, resolved_target_folder, message_id) if message_id else None
        return ImapMoveResult(
            status="moved",
            source_uid=resolved_uid,
            target_uid=target_uid,
            source_folder=resolved_source_folder,
            target_folder=resolved_target_folder,
            used_move_command=used_move_command,
        )
    except Exception:
        logger.exception(
            "Failed to move IMAP message mailbox=%s source=%s target=%s",
            getattr(mailbox, "id", None),
            source_folder,
            target_folder,
        )
        raise
    finally:
        _close_connection(connection)


def move_to_inbox(
    mailbox,
    imap_uid: str | bytes | None,
    *,
    source_folder: str | None = None,
    message_id: str | None = None,
) -> ImapMoveResult:
    return move_email(
        mailbox,
        imap_uid,
        "INBOX",
        source_folder=source_folder,
        message_id=message_id,
    )


def _ensure_folders_on_connection(connection: Any, mailbox: Any, cache_key: str) -> MailboxFolderState:
    cached = _FOLDER_STATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    separator = _discover_folder_separator(connection)
    available_folders = _list_folder_names(connection)
    available_lookup = {folder.strip().lower(): folder for folder in available_folders if folder}

    root_folder = _ensure_folder_exists(connection, available_lookup, ROOT_FOLDER)
    archive_folder = (
        _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Archive"))
        if root_folder else None
    )
    spam_folder = (
        _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Spam"))
        if root_folder else None
    )
    processed_folder = (
        _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Processed"))
        if root_folder else None
    )
    reply_later_folder = (
        _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "ReplyLater"))
        if root_folder else None
    )

    state = MailboxFolderState(
        separator=separator,
        root_folder=root_folder,
        archive_folder=archive_folder,
        spam_folder=spam_folder,
        processed_folder=processed_folder,
        reply_later_folder=reply_later_folder,
    )
    _FOLDER_STATE_CACHE[cache_key] = state
    logger.debug(
        "Ensured IMAP folders for mailbox=%s separator=%s",
        getattr(mailbox, "id", None),
        separator,
    )
    return state


def _get_folder_state(connection: Any, mailbox: Any) -> MailboxFolderState:
    cache_key = _mailbox_cache_key(mailbox)
    cached = _FOLDER_STATE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    return _ensure_folders_on_connection(connection, mailbox, cache_key)


def _mailbox_cache_key(mailbox: Any) -> str:
    mailbox_id = str(getattr(mailbox, "id", "") or "").strip()
    host = str(getattr(mailbox, "imap_host", "") or "").strip().lower()
    username = str(getattr(mailbox, "imap_username", "") or getattr(mailbox, "imap_user", "") or "").strip().lower()
    port = str(getattr(mailbox, "imap_port", "") or "").strip()
    if mailbox_id:
        return f"id:{mailbox_id}|{host}|{username}|{port}"
    return f"{host}|{username}|{port}"


def _discover_folder_separator(connection: Any) -> str:
    try:
        status, folder_list = connection.list()
    except Exception:  # noqa: BLE001
        return "/"

    if not _is_ok(status) or not folder_list:
        return "/"

    for entry in folder_list:
        parsed = _parse_list_entry(entry)
        if parsed is not None:
            separator, _folder_name = parsed
            if separator:
                return separator
    return "/"


def _list_folder_names(connection: Any) -> list[str]:
    try:
        status, folder_list = connection.list()
    except Exception:  # noqa: BLE001
        return []

    if not _is_ok(status) or not folder_list:
        return []

    folders: list[str] = []
    for entry in folder_list:
        parsed = _parse_list_entry(entry)
        if parsed is None:
            continue
        _separator, folder_name = parsed
        if folder_name:
            folders.append(folder_name)
    return folders


def _parse_list_entry(entry: Any) -> tuple[str | None, str | None] | None:
    if entry is None:
        return None
    decoded = entry.decode("utf-8", errors="ignore") if isinstance(entry, bytes) else str(entry)
    decoded = decoded.strip()
    if not decoded:
        return None

    match = re.match(r'^\* LIST \((?P<flags>.*?)\)\s+(?P<delimiter>NIL|"(?:[^"\\]|\\.)*"|[^ ]+)\s+(?P<name>.+)$', decoded)
    if not match:
        return None

    delimiter = _unquote_imap_value(match.group("delimiter"))
    folder_name = _unquote_imap_value(match.group("name"))
    return delimiter, folder_name


def _ensure_folder_exists(connection: Any, available_lookup: dict[str, str], folder_name: str) -> str:
    existing = _match_existing_folder(available_lookup, folder_name)
    if existing:
        return existing

    create = getattr(connection, "create", None)
    if not callable(create):
        logger.warning("IMAP connection does not support CREATE; skipping folder %s", folder_name)
        return None
    status, _ = create(folder_name)
    if not _is_ok(status):
        logger.warning("Unable to create IMAP folder %s; folder actions will be skipped", folder_name)
        return None
    available_lookup[folder_name.strip().lower()] = folder_name
    return folder_name


def _match_existing_folder(available_lookup: dict[str, str], folder_name: str) -> str | None:
    return available_lookup.get(folder_name.strip().lower())


def _compose_child_folder(root_folder: str, separator: str, suffix: str) -> str:
    return f"{root_folder}{separator}{suffix}"


def _resolve_folder_hint(state: MailboxFolderState, folder_hint: str | None) -> str | None:
    if not folder_hint:
        return None

    normalized = str(folder_hint).strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if lowered == "inbox":
        return "INBOX"

    suffix = TARGET_FOLDER_SUFFIXES.get(lowered)
    if suffix:
        return _compose_child_folder(state.root_folder, state.separator, suffix)

    if lowered.startswith(ROOT_FOLDER.lower()):
        raw_suffix = normalized[len(ROOT_FOLDER) :].lstrip("/.")
        if not raw_suffix:
            return state.root_folder

        raw_lowered = raw_suffix.lower()
        suffix = TARGET_FOLDER_SUFFIXES.get(raw_lowered)
        if suffix:
            return _compose_child_folder(state.root_folder, state.separator, suffix)

        segments = [segment for segment in re.split(r"[/.]", raw_suffix) if segment]
        if not segments:
            return state.root_folder
        return f"{state.root_folder}{state.separator}{state.separator.join(segments)}"

    for actual in [
        state.root_folder,
        state.archive_folder,
        state.spam_folder,
        state.processed_folder,
        state.reply_later_folder,
    ]:
        if actual.lower() == lowered:
            return actual

    return normalized


def _normalize_uid(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        decoded = value.decode("utf-8", errors="ignore").strip()
        return decoded or None
    normalized = str(value).strip()
    return normalized or None


def _find_message_uid(connection: Any, folder: str, message_id: str | None) -> str | None:
    if not message_id:
        return None

    status, _ = _select_folder(connection, folder, readonly=True)
    if not _is_ok(status):
        raise RuntimeError(f"Unable to select folder {folder}")

    search_status, data = _safe_uid_command(connection, "search", None, "HEADER", "Message-ID", message_id)
    if not _is_ok(search_status) or not data or not data[0]:
        return None

    uids = [item.decode("utf-8", errors="ignore") if isinstance(item, bytes) else str(item) for item in data[0].split() if item]
    return uids[0] if uids else None


def _safe_uid_command(connection: Any, command: str, *args: Any):
    uid = getattr(connection, "uid", None)
    if not callable(uid):
        raise RuntimeError("IMAP connection does not support UID commands")
    return uid(command, *args)


def _select_folder(connection: Any, folder: str, readonly: bool = False):
    select = getattr(connection, "select", None)
    if not callable(select):
        raise RuntimeError("IMAP connection does not support select")
    return select(folder, readonly=readonly)


def _connection_supports_move(connection: Any) -> bool:
    capabilities = getattr(connection, "capabilities", None)
    if capabilities:
        normalized = {str(item, "utf-8", "ignore").upper() if isinstance(item, bytes) else str(item).upper() for item in capabilities}
        if "MOVE" in normalized:
            return True

    capability = getattr(connection, "capability", None)
    if callable(capability):
        try:
            status, data = capability()
        except Exception:  # noqa: BLE001
            return False
        if not _is_ok(status) or not data:
            return False
        payload = b" ".join(item for item in data if isinstance(item, bytes))
        return b"MOVE" in payload.upper()
    return False


def _safe_expunge(connection: Any) -> None:
    expunge = getattr(connection, "expunge", None)
    if callable(expunge):
        expunge()


def _is_ok(status: Any) -> bool:
    return str(status).upper() == "OK"


def _unquote_imap_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.upper() == "NIL":
        return None
    if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
    cleaned = cleaned.replace(r"\\", "\\").replace(r"\"", '"')
    return cleaned


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
