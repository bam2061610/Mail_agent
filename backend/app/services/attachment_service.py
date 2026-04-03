import hashlib
import json
import logging
import mimetypes
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from email.message import Message
from email.utils import collapse_rfc2231_value
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.action_log import ActionLog
from app.models.attachment import Attachment

logger = logging.getLogger(__name__)

ATTACHMENTS_ROOT = DATA_DIR / "attachments"
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class ParsedAttachment:
    filename: str
    content_type: str
    size_bytes: int
    content_id: str | None
    is_inline: bool
    payload: bytes


def extract_attachments(message: Message) -> list[ParsedAttachment]:
    attachments: list[ParsedAttachment] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if not _is_attachment_like(part):
            continue
        payload = part.get_payload(decode=True) or b""
        filename = _decode_filename(part.get_filename()) or f"attachment-{len(attachments) + 1}"
        content_type = part.get_content_type() or "application/octet-stream"
        content_id = (part.get("Content-ID") or "").strip() or None
        disposition = (part.get_content_disposition() or "").lower()
        attachments.append(
            ParsedAttachment(
                filename=filename,
                content_type=content_type,
                size_bytes=len(payload),
                content_id=content_id,
                is_inline=disposition == "inline",
                payload=payload,
            )
        )
    return attachments


def save_attachments(
    db_session: Session,
    email_id: int,
    mailbox_id: str | None,
    parsed_attachments: list[ParsedAttachment],
) -> list[Attachment]:
    saved: list[Attachment] = []
    if not parsed_attachments:
        return saved

    existing = db_session.query(Attachment).filter(Attachment.email_id == email_id).all()
    existing_keys = {(item.filename or "", item.size_bytes, item.content_type or "") for item in existing}
    storage_dir = ATTACHMENTS_ROOT / _sanitize_component(mailbox_id or "default") / str(email_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    for item in parsed_attachments:
        key = (item.filename, item.size_bytes, item.content_type)
        if key in existing_keys:
            continue
        storage_path = _persist_attachment_bytes(storage_dir, item)
        attachment = Attachment(
            email_id=email_id,
            filename=item.filename,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
            content_id=item.content_id,
            is_inline=item.is_inline,
            local_storage_path=str(storage_path),
        )
        db_session.add(attachment)
        db_session.flush()
        db_session.add(
            ActionLog(
                email_id=email_id,
                action_type="attachment_saved",
                actor="imap",
                details_json=json.dumps(
                    {
                        "attachment_id": attachment.id,
                        "filename": item.filename,
                        "size_bytes": item.size_bytes,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        saved.append(attachment)
    return saved


def list_email_attachments(db_session: Session, email_id: int) -> list[Attachment]:
    return (
        db_session.query(Attachment)
        .filter(Attachment.email_id == email_id)
        .order_by(Attachment.id.asc())
        .all()
    )


def get_attachment(db_session: Session, attachment_id: int) -> Attachment | None:
    return db_session.query(Attachment).filter(Attachment.id == attachment_id).first()


def delete_email_attachments(db_session: Session, email_id: int, *, delete_files: bool = True) -> int:
    attachments = list_email_attachments(db_session, email_id)
    if not attachments:
        return 0

    removed_count = 0
    for attachment in attachments:
        if delete_files:
            _delete_attachment_file(attachment)
        db_session.delete(attachment)
        removed_count += 1
    db_session.flush()
    return removed_count


def get_attachment_file_path(attachment: Attachment) -> Path:
    return Path(attachment.local_storage_path).resolve()


def build_attachment_download_payload(attachment: Attachment) -> tuple[Path, str, str, dict[str, str]]:
    file_path = get_attachment_file_path(attachment)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(str(file_path))

    filename = (attachment.filename or file_path.name or "attachment").strip() or "attachment"
    media_type = (
        (attachment.content_type or "").strip()
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    headers = {
        "Content-Disposition": build_content_disposition_header(filename),
        "X-Content-Type-Options": "nosniff",
    }
    return file_path, filename, media_type, headers


def build_content_disposition_header(filename: str) -> str:
    safe_ascii = _ascii_fallback_filename(filename)
    utf8_encoded = quote(filename, safe="")
    return f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{utf8_encoded}'


def _persist_attachment_bytes(storage_dir: Path, attachment: ParsedAttachment) -> Path:
    digest = hashlib.sha1(attachment.payload).hexdigest()[:14]
    safe_name = _sanitize_filename(attachment.filename)
    target = storage_dir / f"{digest}_{safe_name}"
    if not target.exists():
        target.write_bytes(attachment.payload)
    return target


def _delete_attachment_file(attachment: Attachment) -> None:
    try:
        file_path = Path(attachment.local_storage_path).resolve(strict=False)
    except Exception:  # noqa: BLE001
        logger.warning("Skipping attachment file cleanup for attachment_id=%s due to invalid path", attachment.id)
        return

    root = ATTACHMENTS_ROOT.resolve(strict=False)
    try:
        file_path.relative_to(root)
    except ValueError:
        logger.warning(
            "Skipping attachment file cleanup outside attachments root for attachment_id=%s path=%s",
            attachment.id,
            file_path,
        )
        return

    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
        except FileNotFoundError:
            return
        except OSError:  # noqa: BLE001
            logger.exception("Failed to delete attachment file for attachment_id=%s", attachment.id)


def _decode_filename(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        decoded = collapse_rfc2231_value(raw).strip()
    except Exception:  # noqa: BLE001
        decoded = raw.strip()
    return decoded or None


def _sanitize_component(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip())
    return cleaned.strip(".-") or "default"


def _sanitize_filename(filename: str) -> str:
    name = _sanitize_component(filename.replace("\\", "-").replace("/", "-"))
    return name[:220]


def _ascii_fallback_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace("\\", "-").replace("/", "-").replace('"', "")
    ascii_name = _sanitize_component(ascii_name)
    raw_suffix = Path(filename).suffix
    suffix = f".{re.sub(r'[^A-Za-z0-9]+', '', raw_suffix)}" if raw_suffix else ""
    if not ascii_name:
        return f"attachment{suffix.lower()}" if suffix else "attachment"
    if suffix and not ascii_name.lower().endswith(suffix.lower()):
        return f"{ascii_name}{suffix.lower()}"
    return ascii_name


def _is_attachment_like(part: Message) -> bool:
    filename = part.get_filename()
    disposition = (part.get_content_disposition() or "").lower()
    if filename:
        return True
    if disposition == "attachment":
        return True
    if disposition == "inline" and part.get("Content-ID"):
        return True
    return False
