from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.attachment import Attachment
from app.models.email import Email
from app.services.attachment_service import delete_email_attachments

logger = logging.getLogger(__name__)

RETENTION_DAYS = 10


@dataclass(slots=True)
class RetentionCleanupResult:
    cutoff_at: datetime
    scanned_count: int = 0
    pruned_count: int = 0
    attachment_count: int = 0
    email_ids: list[int] = field(default_factory=list)


def cleanup_email_retention(
    db_session: Session,
    *,
    now: datetime | None = None,
    retention_days: int = RETENTION_DAYS,
) -> RetentionCleanupResult:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    cutoff = current_time - timedelta(days=max(1, int(retention_days)))
    attachment_exists = db_session.query(Attachment.id).filter(Attachment.email_id == Email.id).exists()
    old_emails = (
        db_session.query(Email)
        .filter(Email.date_received.isnot(None), Email.date_received < _to_naive_utc(cutoff))
        .filter(or_(Email.body_text.isnot(None), Email.body_html.isnot(None), Email.has_attachments.is_(True), attachment_exists))
        .order_by(Email.date_received.asc().nullsfirst(), Email.id.asc())
        .all()
    )

    result = RetentionCleanupResult(cutoff_at=cutoff, scanned_count=len(old_emails))
    if not old_emails:
        return result

    for email in old_emails:
        attachment_count = delete_email_attachments(db_session, email.id, delete_files=True)
        if attachment_count:
            result.attachment_count += attachment_count
        email.body_text = None
        email.body_html = None
        email.has_attachments = False
        db_session.add(email)
        db_session.add(
            ActionLog(
                email_id=email.id,
                action_type="retention_pruned",
                actor="system",
                details_json=json.dumps(
                    {
                        "retention_days": int(retention_days),
                        "attachments_removed": attachment_count,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        result.pruned_count += 1
        result.email_ids.append(email.id)

    db_session.commit()
    logger.info(
        "Retention cleanup pruned %s email(s) and removed %s attachment(s) older than %s",
        result.pruned_count,
        result.attachment_count,
        result.cutoff_at.isoformat(),
    )
    return result


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)
