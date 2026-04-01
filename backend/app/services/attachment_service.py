import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from email.message import Message
from email.utils import collapse_rfc2231_value
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.attachment import Attachment

logger = logging.getLogger(__name__)

ATTACHMENTS_ROOT = Path(__file__).resolve().parents[2] / "data" / "attachments"
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


def get_attachment_file_path(attachment: Attachment) -> Path:
    return Path(attachment.local_storage_path).resolve()


def _persist_attachment_bytes(storage_dir: Path, attachment: ParsedAttachment) -> Path:
    digest = hashlib.sha1(attachment.payload).hexdigest()[:14]
    safe_name = _sanitize_filename(attachment.filename)
    target = storage_dir / f"{digest}_{safe_name}"
    if not target.exists():
        target.write_bytes(attachment.payload)
    return target


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
