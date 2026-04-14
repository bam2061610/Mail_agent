from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.imap_scanner import connect_imap, extract_raw_message_id

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

# Fallback candidates when OMA root folder cannot be created
SPAM_FALLBACKS = ["Spam", "Junk", "Junk E-mail", "Bulk Mail", "INBOX.Spam", "INBOX.Junk"]
ARCHIVE_FALLBACKS = ["Archive", "Archived", "All Mail", "[Gmail]/All Mail", "INBOX.Archive"]
PROCESSED_FALLBACKS = ["Processed", "Done", "INBOX.Processed"]
REPLY_LATER_FALLBACKS = ["Reply Later", "ReplyLater", "INBOX.ReplyLater", "INBOX.Reply Later"]

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
        raw_message_id = extract_raw_message_id(message_id)
        resolved_uid = _normalize_uid(imap_uid)

        logger.info(
            "IMAP move start: mailbox=%s mailbox_name=%s mailbox_email=%s uid=%r source_hint=%r source=%r target_hint=%r target=%r raw_message_id=%r",
            getattr(mailbox, "id", None),
            getattr(mailbox, "name", None),
            getattr(mailbox, "email_address", None) or getattr(mailbox, "imap_username", None),
            resolved_uid,
            source_folder,
            resolved_source_folder,
            target_folder,
            resolved_target_folder,
            raw_message_id,
        )

        if resolved_target_folder is None:
            # Last-resort: try to create a folder with the canonical English name directly
            suffix = TARGET_FOLDER_SUFFIXES.get(target_folder.strip().lower())
            if suffix:
                for candidate in [f"INBOX{state.separator}{suffix}", suffix]:
                    created = _ensure_folder_exists(connection, {}, candidate)
                    if created:
                        resolved_target_folder = created
                        logger.info("IMAP move: last-resort folder created: %r", created)
                        break
            if resolved_target_folder is None:
                raise RuntimeError(
                    f"Target IMAP folder for {target_folder!r} could not be resolved or created. "
                    f"Folder state: spam={state.spam_folder!r} archive={state.archive_folder!r} "
                    f"processed={state.processed_folder!r} reply_later={state.reply_later_folder!r} "
                    f"root={state.root_folder!r}"
                )

        if resolved_source_folder and resolved_target_folder and resolved_source_folder.lower() == resolved_target_folder.lower():
            if resolved_uid is None and raw_message_id:
                resolved_uid = _find_message_uid(connection, resolved_source_folder, raw_message_id)
            verified_target_uid = _verify_message_in_target_folder(
                connection,
                resolved_target_folder,
                target_uid=resolved_uid,
                message_id=raw_message_id,
            )
            if verified_target_uid is None:
                raise RuntimeError(
                    f"IMAP verification failed: message not found in target folder {resolved_target_folder}"
                )
            return ImapMoveResult(
                status="noop",
                source_uid=resolved_uid,
                target_uid=verified_target_uid,
                source_folder=resolved_source_folder,
                target_folder=resolved_target_folder,
                used_move_command=False,
            )

        if not resolved_source_folder:
            raise RuntimeError("Source IMAP folder could not be resolved")

        if resolved_uid is None and raw_message_id:
            resolved_uid = _find_message_uid(connection, resolved_source_folder, raw_message_id)
        if resolved_uid is None:
            raise RuntimeError("Message UID could not be determined for IMAP move")

        logger.info(
            "IMAP move: selecting source folder=%r uid=%r target=%r method=%s raw_message_id=%r",
            resolved_source_folder,
            resolved_uid,
            resolved_target_folder,
            "MOVE" if _connection_supports_move(connection) else "COPY+DELETE",
            raw_message_id,
        )
        sel_status, _ = _select_folder(connection, resolved_source_folder, readonly=False)
        if not _is_ok(sel_status):
            raise RuntimeError(
                f"Cannot open source IMAP folder {resolved_source_folder!r} for writing "
                f"(SELECT returned {sel_status!r})"
            )

        used_move_command = _connection_supports_move(connection)
        move_method = "MOVE" if used_move_command else "COPY+DELETE"
        logger.info("IMAP move: server supports MOVE=%s method=%s", used_move_command, move_method)

        def _try_move_or_copy(uid: str) -> str | None:
            if used_move_command:
                move_status, move_data = _safe_uid_command(connection, "move", uid, resolved_target_folder)
                if not _is_ok(move_status):
                    raise RuntimeError(f"IMAP MOVE command failed with status={move_status}")
                return _extract_uid_from_response(move_data)

            copy_status, copy_data = _safe_uid_command(connection, "copy", uid, resolved_target_folder)
            if not _is_ok(copy_status):
                raise RuntimeError(f"IMAP COPY command failed with status={copy_status}")
            store_status, store_data = _safe_uid_command(connection, "store", uid, "+FLAGS.SILENT", r"(\Deleted)")
            if not _is_ok(store_status):
                raise RuntimeError(f"IMAP STORE command failed with status={store_status}")
            expunge_status, expunge_data = _safe_expunge(connection)
            if not _is_ok(expunge_status):
                raise RuntimeError(f"IMAP EXPUNGE command failed with status={expunge_status}")
            return _extract_uid_from_response(copy_data) or _extract_uid_from_response(store_data) or _extract_uid_from_response(expunge_data)

        move_command_error: Exception | None = None
        try:
            target_uid_candidate = _try_move_or_copy(resolved_uid)
        except Exception as exc:  # noqa: BLE001
            move_command_error = exc
            target_uid_candidate = None

        if move_command_error is not None and raw_message_id:
            logger.warning(
                "IMAP move failed with stored uid=%r raw_message_id=%r; retrying with fresh UID search in %r",
                resolved_uid,
                raw_message_id,
                resolved_source_folder,
            )
            fresh_uid = _find_message_uid(connection, resolved_source_folder, raw_message_id)
            if fresh_uid and fresh_uid != resolved_uid:
                logger.info("IMAP move retry with fresh uid=%r", fresh_uid)
                _select_folder(connection, resolved_source_folder, readonly=False)
                try:
                    target_uid_candidate = _try_move_or_copy(fresh_uid)
                    resolved_uid = fresh_uid
                    move_command_error = None
                except Exception as retry_exc:  # noqa: BLE001
                    move_command_error = retry_exc
            elif fresh_uid is None:
                # Message not in source folder — search all folders
                logger.warning(
                    "Message not found in %r for raw_message_id=%r; searching other folders",
                    resolved_source_folder,
                    raw_message_id,
                )
                for folder_path in [f for f in [state.archive_folder, state.spam_folder,
                                                  state.processed_folder, state.reply_later_folder,
                                                  "INBOX"] if f and f != resolved_source_folder]:
                    try:
                        alt_uid = _find_message_uid(connection, folder_path, raw_message_id)
                        if alt_uid:
                            logger.info("Found message in %r uid=%r; re-selecting and retrying", folder_path, alt_uid)
                            _select_folder(connection, folder_path, readonly=False)
                            try:
                                target_uid_candidate = _try_move_or_copy(alt_uid)
                                resolved_uid = alt_uid
                                move_command_error = None
                                break
                            except Exception as alt_exc:  # noqa: BLE001
                                move_command_error = alt_exc
                    except Exception:  # noqa: BLE001
                        continue

        if move_command_error is not None:
            raise RuntimeError(
                f"IMAP move failed: could not move uid={resolved_uid} from {resolved_source_folder} to {resolved_target_folder}"
            ) from move_command_error

        verified_target_uid = _verify_message_in_target_folder(
            connection,
            resolved_target_folder,
            target_uid=target_uid_candidate,
            message_id=raw_message_id,
        )
        if verified_target_uid is None:
            raise RuntimeError(
                f"IMAP verification failed: message not found in target folder {resolved_target_folder}"
            )

        logger.info(
            "IMAP move success: source=%r target=%r source_uid=%r target_uid=%r method=%s raw_message_id=%r",
            resolved_source_folder,
            resolved_target_folder,
            resolved_uid,
            verified_target_uid,
            move_method,
            raw_message_id,
        )
        return ImapMoveResult(
            status="moved",
            source_uid=resolved_uid,
            target_uid=verified_target_uid,
            source_folder=resolved_source_folder,
            target_folder=resolved_target_folder,
            used_move_command=used_move_command,
        )
    except Exception:
        logger.exception(
            "Failed to move IMAP message mailbox=%s mailbox_name=%s mailbox_email=%s source_hint=%r target_hint=%r",
            getattr(mailbox, "id", None),
            getattr(mailbox, "name", None),
            getattr(mailbox, "email_address", None) or getattr(mailbox, "imap_username", None),
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

    if root_folder is not None:
        # Preferred: use OMA/* hierarchy
        archive_folder = _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Archive"))
        spam_folder = _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Spam"))
        processed_folder = _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "Processed"))
        reply_later_folder = _ensure_folder_exists(connection, available_lookup, _compose_child_folder(root_folder, separator, "ReplyLater"))
    else:
        # Fallback: discover or create standard folders the server accepts
        inbox_prefix = f"INBOX{separator}"
        spam_folder = (
            _find_in_lookup(available_lookup, SPAM_FALLBACKS)
            or _ensure_folder_exists(connection, available_lookup, f"{inbox_prefix}Spam")
            or _ensure_folder_exists(connection, available_lookup, "Spam")
        )
        archive_folder = (
            _find_in_lookup(available_lookup, ARCHIVE_FALLBACKS)
            or _ensure_folder_exists(connection, available_lookup, f"{inbox_prefix}Archive")
            or _ensure_folder_exists(connection, available_lookup, "Archive")
        )
        processed_folder = (
            _find_in_lookup(available_lookup, PROCESSED_FALLBACKS)
            or _ensure_folder_exists(connection, available_lookup, f"{inbox_prefix}Processed")
            or _ensure_folder_exists(connection, available_lookup, "Processed")
        )
        reply_later_folder = (
            _find_in_lookup(available_lookup, REPLY_LATER_FALLBACKS)
            or _ensure_folder_exists(connection, available_lookup, f"{inbox_prefix}ReplyLater")
            or _ensure_folder_exists(connection, available_lookup, "Reply Later")
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
    logger.info(
        "IMAP folder state for mailbox=%s: root=%s spam=%s archive=%s processed=%s reply_later=%s",
        getattr(mailbox, "id", None),
        root_folder,
        spam_folder,
        archive_folder,
        processed_folder,
        reply_later_folder,
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
        return "."

    if not _is_ok(status) or not folder_list:
        return "."

    for entry in folder_list:
        parsed = _parse_list_entry(entry)
        if parsed is not None:
            separator, _folder_name = parsed
            if separator and separator != "NIL":
                return separator
    return "."


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

    # imaplib strips "* LIST " prefix before returning data, but some
    # server responses or imaplib versions may include it — handle both.
    match = re.match(
        r'^(?:\* LIST\s+)?\((?P<flags>.*?)\)\s+(?P<delimiter>NIL|"(?:[^"\\]|\\.)*"|[^ ]+)\s+(?P<name>.+)$',
        decoded,
    )
    if not match:
        return None

    delimiter = _unquote_imap_value(match.group("delimiter"))
    folder_name = _unquote_imap_value(match.group("name"))
    return delimiter, folder_name


def _find_in_lookup(available_lookup: dict[str, str], candidates: list[str]) -> str | None:
    for name in candidates:
        found = available_lookup.get(name.strip().lower())
        if found:
            return found
    return None


def _ensure_folder_exists(connection: Any, available_lookup: dict[str, str], folder_name: str) -> str | None:
    if not folder_name:
        return None
    existing = _match_existing_folder(available_lookup, folder_name)
    if existing:
        return existing

    create = getattr(connection, "create", None)
    if not callable(create):
        logger.warning("IMAP connection does not support CREATE; skipping folder %s", folder_name)
        return None
    # Quote folder names containing spaces (IMAP requires it)
    folder_arg = f'"{folder_name}"' if " " in folder_name else folder_name
    status, _ = create(folder_arg)
    if not _is_ok(status):
        logger.warning("Unable to create IMAP folder %s; folder actions will be skipped", folder_name)
        return None
    available_lookup[folder_name.strip().lower()] = folder_name
    logger.info("Created IMAP folder: %s", folder_name)
    # Subscribe so the folder is usable for COPY/MOVE on all servers
    try:
        subscribe = getattr(connection, "subscribe", None)
        if callable(subscribe):
            subscribe(folder_name)
    except Exception:  # noqa: BLE001
        pass
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

    # Priority 1: use pre-resolved state attributes (these are real server folder names)
    attr_map: dict[str, str | None] = {
        "archive": state.archive_folder,
        "archived": state.archive_folder,
        "spam": state.spam_folder,
        "processed": state.processed_folder,
        "reply_later": state.reply_later_folder,
        "replylater": state.reply_later_folder,
        "reply later": state.reply_later_folder,
    }
    from_attr = attr_map.get(lowered)
    if from_attr:
        return from_attr

    # Priority 2: compose via root folder (only when root is available)
    suffix = TARGET_FOLDER_SUFFIXES.get(lowered)
    if suffix and state.root_folder:
        return _compose_child_folder(state.root_folder, state.separator, suffix)

    # Priority 3: handle paths that start with OMA prefix
    if state.root_folder and lowered.startswith(ROOT_FOLDER.lower()):
        raw_suffix = normalized[len(ROOT_FOLDER):].lstrip("/.\\")
        if not raw_suffix:
            return state.root_folder
        raw_lowered = raw_suffix.lower()
        mapped_suffix = TARGET_FOLDER_SUFFIXES.get(raw_lowered)
        if mapped_suffix:
            return _compose_child_folder(state.root_folder, state.separator, mapped_suffix)
        segments = [s for s in re.split(r"[/.\\\\]", raw_suffix) if s]
        if not segments:
            return state.root_folder
        return f"{state.root_folder}{state.separator}{state.separator.join(segments)}"

    # Priority 4: match against any known folder name in state
    for actual in [f for f in [state.root_folder, state.archive_folder, state.spam_folder,
                                state.processed_folder, state.reply_later_folder] if f]:
        if actual.lower() == lowered:
            return actual

    # Priority 5: return as-is only when the hint is NOT a recognized keyword.
    # A raw keyword that couldn't be resolved (e.g. "spam" when no Spam folder
    # was found/created) must NOT be used as a folder name — return None so the
    # caller can raise a clear error rather than silently failing with
    # "NO NONEXISTENT" from the server.
    if lowered not in attr_map and lowered not in TARGET_FOLDER_SUFFIXES:
        return normalized
    return None


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
    raw_message_id = extract_raw_message_id(message_id)
    if not raw_message_id:
        return None

    status, _ = _select_folder(connection, folder, readonly=True)
    if not _is_ok(status):
        raise RuntimeError(f"Unable to select folder {folder}")

    search_status, data = _safe_uid_command(connection, "search", None, "HEADER", "Message-ID", raw_message_id)
    if not _is_ok(search_status) or not data or not data[0]:
        return None

    uids = [item.decode("utf-8", errors="ignore") if isinstance(item, bytes) else str(item) for item in data[0].split() if item]
    return uids[0] if uids else None


def _verify_message_in_target_folder(
    connection: Any,
    folder: str,
    *,
    target_uid: str | None = None,
    message_id: str | None = None,
) -> str | None:
    status, _ = _select_folder(connection, folder, readonly=True)
    if not _is_ok(status):
        raise RuntimeError(f"Unable to select target folder {folder}")

    if target_uid:
        fetch_status, fetch_data = _safe_uid_command(connection, "fetch", target_uid, "(UID)")
        if _is_ok(fetch_status) and fetch_data and any(item for item in fetch_data if item):
            return target_uid

    if message_id:
        return _find_message_uid(connection, folder, message_id)

    return None


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


def _safe_expunge(connection: Any):
    expunge = getattr(connection, "expunge", None)
    if callable(expunge):
        return expunge()
    return "NO", None


def _extract_uid_from_response(data: Any) -> str | None:
    if not data:
        return None

    candidates: list[str] = []
    for item in data:
        if isinstance(item, tuple):
            payload = item[1] if len(item) > 1 else None
            if isinstance(payload, bytes):
                candidates.extend(token.decode("utf-8", errors="ignore") for token in payload.split())
            elif payload is not None:
                candidates.extend(str(payload).split())
        elif isinstance(item, bytes):
            candidates.extend(token.decode("utf-8", errors="ignore") for token in item.split())
        else:
            candidates.extend(str(item).split())

    for token in reversed(candidates):
        cleaned = token.strip().strip("[](),")
        if cleaned.isdigit():
            return cleaned
    return None


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

