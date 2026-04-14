import hashlib
import imaplib
import json
import ssl
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime, parseaddr

from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_effective_settings
from app.exceptions import ImapError
from app.models.email import Email
from app.models.action_log import ActionLog
from app.db import open_account_session
from app.services.attachment_service import ParsedAttachment, extract_attachments, save_attachments, save_attachment_metadata
from app.services.followup_tracker import close_waiting
from app.services.language_service import update_email_languages
from app.services.mailbox_service import get_enabled_mailbox_configs
from app.services.diagnostics_service import mark_mailbox_scan_result
from app.services.rule_engine import apply_rules_to_email

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ParsedMailboxAddress:
    email: str
    name: str | None = None


@dataclass(slots=True)
class ParsedEmailMessage:
    message_id: str
    source_message_id: str | None
    in_reply_to: str | None
    references: list[str]
    thread_id: str
    subject: str | None
    sender_email: str | None
    sender_name: str | None
    recipients: list[dict[str, str | None]]
    cc: list[dict[str, str | None]]
    date_received: datetime | None
    body_text: str | None
    body_html: str | None
    attachments: list[ParsedAttachment]
    imap_uid: str | None = None
    folder: str = "INBOX"
    direction: str = "inbound"
    fallback_message_id_used: bool = False


@dataclass(slots=True)
class SaveEmailResult:
    status: str
    email_id: int | None
    message_id: str


@dataclass(slots=True)
class ScanSummary:
    mailbox: str
    scanned_messages: int
    fetched_messages: int
    created_count: int
    skipped_count: int
    errors: list[str]


@dataclass(slots=True)
class MultiMailboxScanSummary:
    total_created_count: int
    total_skipped_count: int
    mailbox_results: list[ScanSummary]
    errors: list[str]


@retry(
    retry=retry_if_exception_type(ImapError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def connect_imap(settings) -> imaplib.IMAP4_SSL:
    imap_username = getattr(settings, "imap_username", None) or getattr(settings, "imap_user", None)
    imap_password = getattr(settings, "imap_password", None)
    if not settings.imap_host or not imap_username or not imap_password:
        raise ImapError("IMAP credentials are not fully configured")

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connection = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=ssl_context)
        connection.login(imap_username, imap_password)
        return connection
    except imaplib.IMAP4.error as exc:
        logger.warning("IMAP authentication failed", exc_info=True)
        raise ImapError(str(exc)) from exc
    except OSError as exc:
        logger.warning("IMAP connection failed", exc_info=True)
        raise ImapError(str(exc)) from exc


MAX_INITIAL_SCAN_DAYS = 14


def _parse_scan_since_date(raw_value) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        value = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return None
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_scan_since_cutoff(settings) -> datetime:
    raw_value = getattr(settings, "scan_since_date", None)
    if raw_value is None and not hasattr(settings, "scan_since_date"):
        raw_value = getattr(get_effective_settings(), "scan_since_date", None)

    parsed = _parse_scan_since_date(raw_value)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc) - timedelta(days=MAX_INITIAL_SCAN_DAYS)


def _imap_date_criterion(cutoff: datetime | None = None) -> str:
    """Return IMAP SINCE criterion for the configured scan start date."""
    effective_cutoff = cutoff or (datetime.now(timezone.utc) - timedelta(hours=24))
    return f'SINCE {effective_cutoff.strftime("%d-%b-%Y")}'


def _is_older_than_cutoff(date_received: datetime | None, cutoff: datetime) -> bool:
    if date_received is None:
        return False
    normalized = date_received
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    else:
        normalized = normalized.astimezone(timezone.utc)
    return normalized < cutoff


def _scan_folder(
    connection: imaplib.IMAP4_SSL,
    db_session: Session,
    folder: str,
    mailbox_id: str,
    mailbox_name: str | None,
    mailbox_address: str | None,
    existing_message_ids: set[str],
    scan_cutoff: datetime,
    direction: str = "inbound",
) -> tuple[int, int, int, int, list[str]]:
    """Scan a single IMAP folder. Returns (scanned, fetched, created, skipped, errors)."""
    errors: list[str] = []
    scanned_messages = 0
    fetched_messages = 0
    created_count = 0
    skipped_count = 0
    try:
        status, _ = connection.select(folder, readonly=True)
        if status != "OK":
            return 0, 0, 0, 0, [f"Unable to select folder {folder}"]
    except imaplib.IMAP4.error:
        return 0, 0, 0, 0, [f"Folder {folder} does not exist or is not accessible"]

    search_criterion = _imap_date_criterion(scan_cutoff)
    status, data = connection.uid("search", None, search_criterion)
    if status != "OK":
        return 0, 0, 0, 0, [f"Unable to search folder {folder}"]

    raw_uids = [uid for uid in data[0].split() if uid]
    # Sort UIDs numerically so newest (highest UID) messages are last and
    # the slice below always keeps the most recently delivered messages.
    try:
        raw_uids = sorted(raw_uids, key=lambda u: int(u))
    except (ValueError, TypeError):
        pass  # keep server order if UIDs are non-numeric
    max_emails_per_scan = max(1, int(getattr(get_effective_settings(), "max_emails_per_scan", 200) or 200))
    if len(raw_uids) > max_emails_per_scan:
        raw_uids = raw_uids[-max_emails_per_scan:]
    message_uids = raw_uids
    scanned_messages = len(message_uids)

    for uid in message_uids:
        header_message_id = _fetch_header_message_id(connection, uid)
        if header_message_id and header_message_id in existing_message_ids:
            skipped_count += 1
            continue

        try:
            raw_message = _fetch_full_message(connection, uid)
            fetched_messages += 1
            parsed_message = parse_email_message(raw_message)
            parsed_message.imap_uid = uid.decode("utf-8", errors="ignore") or None
            # NOTE: We intentionally do NOT apply _is_older_than_cutoff here.
            # IMAP SINCE already filters by the server's internal delivery date.
            # The email Date header can differ from the delivery date by up to 24 h
            # due to sender timezone offsets, and applying a strict cutoff on it
            # would falsely skip recently delivered messages.
            if direction == "sent":
                parsed_message.direction = "sent"
                parsed_message.folder = folder.lower()
            result = save_parsed_email(
                db_session,
                parsed_message,
                mailbox_id=str(mailbox_id),
                mailbox_name=mailbox_name,
                mailbox_address=mailbox_address,
            )
            if result.status == "created":
                created_count += 1
                existing_message_ids.add(result.message_id)
            else:
                skipped_count += 1
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            logger.warning("IMAP folder scan failed: folder=%s", folder, exc_info=True)
            errors.append(f"UID {uid.decode('utf-8', errors='ignore')}: {exc}")

    return scanned_messages, fetched_messages, created_count, skipped_count, errors


SENT_FOLDER_NAMES = [
    "Sent", "INBOX.Sent", "Sent Messages", "Sent Items",
    "[Gmail]/Sent Mail", "[Gmail]/&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-",
    "INBOX.Sent Messages", "INBOX.Sent Items",
    # Russian "Отправленные" in Modified UTF-7 (Yandex/Mail.ru/Dovecot)
    "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-",
    "INBOX.&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-",
    # Cyrillic sent-folder keywords that some servers expose as UTF-8 names
    "Отправленные", "INBOX.Отправленные",
]

# Russian keywords (lowercase) to recognise sent folders decoded from Modified UTF-7
_SENT_KEYWORDS_RU = ("отправ",)


def _decode_modified_utf7(value: str) -> str:
    """Best-effort decode of an IMAP Modified-UTF-7 folder name to a plain string.

    Modified UTF-7 wraps non-ASCII runs in ``&...&-`` using base64-encoded
    UTF-16BE, with ``,`` replacing ``/`` in the base64 alphabet.
    Falls back to the original string on any error.
    """
    try:
        # Replace &- (escaped literal &) with a placeholder, convert to standard
        # UTF-7 by swapping & → + and , → /, then decode.
        placeholder = "\x00"
        tmp = value.replace("&-", placeholder)
        tmp = tmp.replace("&", "+").replace(",", "/")
        result = tmp.encode("ascii", errors="ignore").decode("utf-7", errors="ignore")
        return result.replace(placeholder, "&")
    except Exception:  # noqa: BLE001
        return value


def _find_sent_folders(connection: imaplib.IMAP4_SSL) -> list[str]:
    """Return all available sent-type folders on the server."""
    try:
        status, folder_list = connection.list()
        if status != "OK" or not folder_list:
            return []
        available: list[str] = []
        for entry in folder_list:
            if entry is None:
                continue
            decoded = entry.decode("utf-8", errors="ignore") if isinstance(entry, bytes) else str(entry)
            parts = decoded.rsplit('" ', 1)
            if len(parts) >= 2:
                folder_name = parts[-1].strip().strip('"')
                available.append(folder_name)

        found: list[str] = []
        seen_lower: set[str] = set()

        # First pass: exact matches against known names
        for candidate in SENT_FOLDER_NAMES:
            for avail in available:
                if avail.lower() == candidate.lower() and avail.lower() not in seen_lower:
                    found.append(avail)
                    seen_lower.add(avail.lower())

        # Second pass: fuzzy match on folder names containing "sent" (English)
        for avail in available:
            if "sent" in avail.lower() and avail.lower() not in seen_lower:
                found.append(avail)
                seen_lower.add(avail.lower())

        # Third pass: decode Modified-UTF-7 names and check for Russian keywords.
        # This catches servers that expose Cyrillic sent-folder names (e.g.
        # "Отправленные") encoded in the IMAP Modified-UTF-7 scheme.
        for avail in available:
            if avail.lower() in seen_lower:
                continue
            human_name = _decode_modified_utf7(avail).lower()
            if any(kw in human_name for kw in _SENT_KEYWORDS_RU):
                found.append(avail)
                seen_lower.add(avail.lower())

        return found
    except Exception:  # noqa: BLE001
        logger.warning("Optional sent-folder detection failed", exc_info=True)
    return []


def _find_sent_folder(connection: imaplib.IMAP4_SSL) -> str | None:
    """Return the first available sent folder (kept for backward compat)."""
    folders = _find_sent_folders(connection)
    return folders[0] if folders else None


def scan_inbox(db_session: Session, settings) -> ScanSummary:
    connection = connect_imap(settings)
    errors: list[str] = []
    scanned_messages = 0
    fetched_messages = 0
    created_count = 0
    skipped_count = 0
    mailbox_id = getattr(settings, "id", "default")
    mailbox_name = getattr(settings, "name", None)
    mailbox_address = getattr(settings, "email_address", None)
    existing_message_ids = _load_existing_message_ids(db_session, mailbox_id)
    scan_cutoff = _resolve_scan_since_cutoff(settings)

    try:
        # Scan INBOX (inbound)
        s, f, c, sk, errs = _scan_folder(
            connection, db_session, "INBOX", str(mailbox_id),
            mailbox_name, mailbox_address, existing_message_ids, scan_cutoff=scan_cutoff, direction="inbound",
        )
        scanned_messages += s
        fetched_messages += f
        created_count += c
        skipped_count += sk
        errors.extend(errs)

        # Scan all Sent folders (outbound)
        sent_folders = _find_sent_folders(connection)
        logger.info("Found %d sent folder(s): %s", len(sent_folders), sent_folders)
        for sent_folder in sent_folders:
            s, f, c, sk, errs = _scan_folder(
                connection, db_session, sent_folder, str(mailbox_id),
                mailbox_name, mailbox_address, existing_message_ids, scan_cutoff=scan_cutoff, direction="sent",
            )
            scanned_messages += s
            fetched_messages += f
            created_count += c
            skipped_count += sk
            errors.extend(errs)
    finally:
        try:
            connection.close()
        except imaplib.IMAP4.error:
            pass
        connection.logout()

    return ScanSummary(
        mailbox=mailbox_name or mailbox_address or "INBOX",
        scanned_messages=scanned_messages,
        fetched_messages=fetched_messages,
        created_count=created_count,
        skipped_count=skipped_count,
        errors=errors,
    )


def scan_all_mailboxes(db_session: Session, settings) -> MultiMailboxScanSummary:
    mailbox_configs = get_enabled_mailbox_configs()
    mailbox_results: list[ScanSummary] = []
    all_errors: list[str] = []
    total_created = 0
    total_skipped = 0

    for mailbox in mailbox_configs:
        db_session.add(
            ActionLog(
                action_type="mailbox_scan_started",
                actor="scheduler",
                details_json=json.dumps({"mailbox_id": mailbox.id, "mailbox_name": mailbox.name}, ensure_ascii=False),
            )
        )
        db_session.commit()
        account_db = open_account_session(str(mailbox.id))
        try:
            result = scan_inbox(account_db, mailbox)
            mailbox_results.append(result)
            total_created += result.created_count
            total_skipped += result.skipped_count
            all_errors.extend(result.errors)
            mark_mailbox_scan_result(
                mailbox_id=str(mailbox.id),
                mailbox_name=mailbox.name or mailbox.email_address or mailbox.id,
                success=len(result.errors) == 0,
                created_count=result.created_count,
                skipped_count=result.skipped_count,
                errors_count=len(result.errors),
                error_text="; ".join(result.errors[:3]) if result.errors else None,
            )
            db_session.add(
                ActionLog(
                    action_type="mailbox_scan_finished",
                    actor="scheduler",
                    details_json=json.dumps(
                        {
                            "mailbox_id": mailbox.id,
                            "mailbox_name": mailbox.name,
                            "created_count": result.created_count,
                            "skipped_count": result.skipped_count,
                            "errors_count": len(result.errors),
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            db_session.commit()
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            error_text = f"{mailbox.name or mailbox.email_address}: {exc}"
            all_errors.append(error_text)
            mark_mailbox_scan_result(
                mailbox_id=str(mailbox.id),
                mailbox_name=mailbox.name or mailbox.email_address or mailbox.id,
                success=False,
                error_text=str(exc),
            )
            mailbox_results.append(
                ScanSummary(
                    mailbox=mailbox.name or mailbox.email_address or mailbox.id,
                    scanned_messages=0,
                    fetched_messages=0,
                    created_count=0,
                    skipped_count=0,
                    errors=[error_text],
                )
            )
        finally:
            account_db.close()

    return MultiMailboxScanSummary(
        total_created_count=total_created,
        total_skipped_count=total_skipped,
        mailbox_results=mailbox_results,
        errors=all_errors,
    )


def parse_email_message(raw_message_bytes: bytes) -> ParsedEmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(raw_message_bytes)

    source_message_id = _normalize_message_identifier(message.get("Message-ID"))
    in_reply_to = _normalize_message_identifier(message.get("In-Reply-To"))
    references = _parse_reference_ids(message.get("References"))
    subject = _decode_mime_header(message.get("Subject"))
    sender_name, sender_email = _parse_single_address(message.get("From"))
    recipients = _parse_address_list(message.get_all("To", []))
    cc = _parse_address_list(message.get_all("Cc", []))
    date_received = _parse_message_date(message.get("Date"))
    body_text, body_html = extract_bodies(message)
    attachments = extract_attachments(message)
    message_id, used_fallback = _ensure_message_id(
        source_message_id=source_message_id,
        subject=subject,
        sender_email=sender_email,
        date_received=date_received,
        body_text=body_text,
        body_html=body_html,
    )

    parsed_message = ParsedEmailMessage(
        message_id=message_id,
        source_message_id=source_message_id,
        in_reply_to=in_reply_to,
        references=references,
        thread_id="",
        subject=subject,
        sender_email=sender_email,
        sender_name=sender_name,
        recipients=[asdict(item) for item in recipients],
        cc=[asdict(item) for item in cc],
        date_received=date_received,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        fallback_message_id_used=used_fallback,
    )
    parsed_message.thread_id = resolve_thread_id(parsed_message)
    return parsed_message


def extract_bodies(message: Message) -> tuple[str | None, str | None]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue

            content_type = part.get_content_type()
            payload = _decode_message_part(part)
            if not payload:
                continue
            if content_type == "text/plain":
                text_parts.append(payload)
            elif content_type == "text/html":
                html_parts.append(payload)
    else:
        payload = _decode_message_part(message)
        if message.get_content_type() == "text/html":
            html_parts.append(payload)
        else:
            text_parts.append(payload)

    body_text = "\n\n".join(part.strip() for part in text_parts if part and part.strip()) or None
    body_html = "\n\n".join(part.strip() for part in html_parts if part and part.strip()) or None
    return body_text, body_html


def resolve_thread_id(parsed_message: ParsedEmailMessage) -> str:
    for candidate in [parsed_message.in_reply_to, *parsed_message.references]:
        normalized = _normalize_message_identifier(candidate)
        if normalized:
            return normalized
    return parsed_message.message_id


def save_parsed_email(
    db_session: Session,
    parsed_message: ParsedEmailMessage,
    mailbox_id: str,
    mailbox_name: str | None = None,
    mailbox_address: str | None = None,
) -> SaveEmailResult:
    message_id_for_storage = parsed_message.message_id
    existing_email = (
        db_session.query(Email)
        .filter(Email.message_id == parsed_message.message_id, Email.mailbox_id == mailbox_id)
        .first()
    )
    if existing_email is not None:
        if parsed_message.imap_uid and existing_email.imap_uid != parsed_message.imap_uid:
            existing_email.imap_uid = parsed_message.imap_uid
            db_session.add(existing_email)
            db_session.commit()
        return SaveEmailResult(
            status="skipped",
            email_id=existing_email.id,
            message_id=parsed_message.message_id,
        )

    duplicate_on_other_mailbox = (
        db_session.query(Email)
        .filter(Email.message_id == parsed_message.message_id, Email.mailbox_id != mailbox_id)
        .first()
    )
    if duplicate_on_other_mailbox is not None:
        message_id_for_storage = _mailbox_scoped_message_id(parsed_message.message_id, mailbox_id)

    resolved_thread_id = _resolve_thread_against_db(db_session, parsed_message)
    email_record = Email(
        message_id=message_id_for_storage,
        mailbox_id=mailbox_id,
        mailbox_name=mailbox_name,
        mailbox_address=(mailbox_address or "").lower() or None,
        imap_uid=parsed_message.imap_uid,
        thread_id=resolved_thread_id,
        subject=parsed_message.subject,
        sender_email=parsed_message.sender_email,
        sender_name=parsed_message.sender_name,
        recipients_json=json.dumps(parsed_message.recipients, ensure_ascii=False),
        cc_json=json.dumps(parsed_message.cc, ensure_ascii=False),
        date_received=_to_naive_utc(parsed_message.date_received),
        body_text=parsed_message.body_text,
        body_html=parsed_message.body_html,
        folder=parsed_message.folder.lower(),
        direction=parsed_message.direction,
    )
    db_session.add(email_record)
    db_session.flush()
    language_decision = update_email_languages(email_record)
    db_session.add(
        ActionLog(
            email_id=email_record.id,
            action_type="language_detected",
            actor="system",
            details_json=json.dumps(
                {
                    "detected_source_language": language_decision.detected_language,
                    "confidence": language_decision.confidence,
                    "reason": language_decision.reason,
                    "preferred_reply_language": email_record.preferred_reply_language,
                },
                ensure_ascii=False,
            ),
        )
    )
    apply_rules_to_email(db_session, email_record, source="import")
    saved_attachments = save_attachment_metadata(
        db_session=db_session,
        email_id=email_record.id,
        mailbox_id=mailbox_id,
        imap_uid=parsed_message.imap_uid,
        parsed_attachments=parsed_message.attachments,
    )
    if saved_attachments:
        email_record.has_attachments = True
        db_session.add(email_record)
    db_session.commit()
    if parsed_message.direction == "inbound" and email_record.thread_id:
        try:
            close_waiting(db_session, thread_id=email_record.thread_id, reason="inbound_reply_received", actor="system")
        except Exception:
            logger.warning("Auto-close followup failed for thread %s", email_record.thread_id, exc_info=True)
    db_session.refresh(email_record)
    return SaveEmailResult(
        status="created",
        email_id=email_record.id,
        message_id=message_id_for_storage,
    )


def _fetch_header_message_id(connection: imaplib.IMAP4_SSL, uid: bytes) -> str | None:
    status, data = connection.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    if status != "OK":
        return None

    raw_header = _extract_fetch_bytes(data)
    if not raw_header:
        return None

    header_message = BytesParser(policy=policy.default).parsebytes(raw_header)
    return _normalize_message_identifier(header_message.get("Message-ID"))


def _fetch_full_message(connection: imaplib.IMAP4_SSL, uid: bytes) -> bytes:
    status, data = connection.uid("fetch", uid, "(BODY.PEEK[])")
    if status != "OK":
        raise RuntimeError("Unable to fetch raw message")

    raw_message = _extract_fetch_bytes(data)
    if not raw_message:
        raise RuntimeError("Raw message payload is empty")
    return raw_message


def _extract_fetch_bytes(data: list) -> bytes | None:
    for item in data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return None


def _load_existing_message_ids(db_session: Session, mailbox_id: str) -> set[str]:
    rows = (
        db_session.query(Email.message_id)
        .filter(Email.message_id.isnot(None), Email.mailbox_id == mailbox_id)
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _decode_mime_header(value: str | None) -> str | None:
    if not value:
        return None

    decoded_chunks: list[str] = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            try:
                decoded_chunks.append(chunk.decode(encoding or "utf-8", errors="replace"))
            except LookupError:
                decoded_chunks.append(chunk.decode("utf-8", errors="replace"))
        else:
            decoded_chunks.append(chunk)
    decoded = "".join(decoded_chunks).strip()
    return decoded or None


def _parse_single_address(raw_value: str | None) -> tuple[str | None, str | None]:
    if not raw_value:
        return None, None

    name, email_address = parseaddr(raw_value)
    decoded_name = _decode_mime_header(name)
    normalized_email = email_address.strip().lower() or None
    return decoded_name, normalized_email


def _parse_address_list(raw_values: list[str]) -> list[ParsedMailboxAddress]:
    addresses: list[ParsedMailboxAddress] = []
    for name, email_address in getaddresses(raw_values):
        normalized_email = email_address.strip().lower()
        if not normalized_email:
            continue
        addresses.append(
            ParsedMailboxAddress(
                email=normalized_email,
                name=_decode_mime_header(name),
            )
        )
    return addresses


def _parse_message_date(raw_date: str | None) -> datetime | None:
    if not raw_date:
        return None
    try:
        parsed = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError, IndexError):
        return None

    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc)


def _decode_message_part(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
    except Exception:  # noqa: BLE001
        payload = None

    if payload is None:
        payload = part.get_payload()
        if isinstance(payload, str):
            return payload
        return ""

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _parse_reference_ids(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    candidates = raw_value.replace("\r", " ").replace("\n", " ").split()
    normalized = [_normalize_message_identifier(candidate) for candidate in candidates]
    return [item for item in normalized if item]


def _normalize_message_identifier(value: str | None) -> str | None:
    if not value:
        return None

    normalized = " ".join(value.strip().split())
    if not normalized:
        return None

    if "<" in normalized and ">" in normalized:
        start = normalized.find("<")
        end = normalized.rfind(">")
        if start < end:
            normalized = normalized[start : end + 1]

    return normalized


def extract_raw_message_id(message_id: str | None) -> str | None:
    """Return the RFC Message-ID part from a mailbox-scoped stored id.

    Scanner storage may append ``::mailbox_id`` for deduplication across mailboxes.
    IMAP SEARCH must always use the raw RFC Message-ID from the original message.
    """
    normalized = _normalize_message_identifier(message_id)
    if not normalized:
        return None
    if "::" not in normalized:
        return normalized
    raw_message_id, _mailbox_id = normalized.rsplit("::", 1)
    return _normalize_message_identifier(raw_message_id) or raw_message_id


def _ensure_message_id(
    source_message_id: str | None,
    subject: str | None,
    sender_email: str | None,
    date_received: datetime | None,
    body_text: str | None,
    body_html: str | None,
) -> tuple[str, bool]:
    if source_message_id:
        return source_message_id, False

    hash_source = "||".join(
        [
            subject or "",
            sender_email or "",
            date_received.isoformat() if date_received else "",
            (body_text or "")[:500],
            (body_html or "")[:500],
        ]
    )
    digest = hashlib.sha1(hash_source.encode("utf-8", errors="ignore")).hexdigest()
    return f"<generated-{digest}@local>", True


def _resolve_thread_against_db(db_session: Session, parsed_message: ParsedEmailMessage) -> str:
    for candidate in [parsed_message.in_reply_to, *parsed_message.references]:
        normalized = _normalize_message_identifier(candidate)
        if not normalized:
            continue

        parent_email = db_session.query(Email).filter(Email.message_id == normalized).first()
        if parent_email is not None:
            return parent_email.thread_id or parent_email.message_id or normalized
        return normalized

    return parsed_message.message_id


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _mailbox_scoped_message_id(message_id: str, mailbox_id: str) -> str:
    scoped = f"{message_id}::{mailbox_id}"
    if len(scoped) <= 250:
        return scoped
    digest = hashlib.sha1(scoped.encode("utf-8", errors="ignore")).hexdigest()
    return f"<scoped-{digest}@local>"
