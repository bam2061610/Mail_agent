import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email
from app.services.feedback_service import record_decision_feedback


@dataclass(slots=True)
class SpamReviewResult:
    email_id: int
    status: str
    is_spam: bool
    spam_source: str | None
    spam_reason: str | None


def list_spam_emails(
    db_session: Session,
    limit: int = 100,
    offset: int = 0,
    mailbox_id: str | None = None,
) -> list[Email]:
    query = db_session.query(Email).filter(Email.is_spam.is_(True))
    if mailbox_id:
        query = query.filter(Email.mailbox_id == mailbox_id)
    emails = (
        query.order_by(Email.updated_at.desc(), Email.date_received.desc().nullslast(), Email.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    annotate_spam_review_metadata(db_session, emails)
    return emails


def restore_email_from_spam(db_session: Session, email: Email, actor: str = "user") -> SpamReviewResult:
    previous_payload = {
        "previous_status": email.status,
        "previous_spam_source": email.spam_source,
        "previous_spam_reason": email.spam_reason,
    }
    record_decision_feedback(
        db_session=db_session,
        email=email,
        decision_type="spam",
        verdict="restore_spam",
        details={"source": "spam_review"},
        actor=actor,
    )
    email.is_spam = False
    email.status = "read"
    email.spam_source = None
    email.spam_reason = None
    email.updated_at = datetime.now(timezone.utc)
    db_session.add(email)
    db_session.add(
        ActionLog(
            email_id=email.id,
            action_type="email_restored_from_spam",
            actor=actor,
            details_json=json.dumps(previous_payload, ensure_ascii=False),
        )
    )
    return SpamReviewResult(
        email_id=email.id,
        status=email.status,
        is_spam=email.is_spam,
        spam_source=email.spam_source,
        spam_reason=email.spam_reason,
    )


def confirm_email_spam(
    db_session: Session,
    email: Email,
    actor: str = "user",
    source: str = "spam_review",
) -> SpamReviewResult:
    record_decision_feedback(
        db_session=db_session,
        email=email,
        decision_type="spam",
        verdict="confirm_spam",
        details={"source": source},
        actor=actor,
    )
    email.is_spam = True
    email.status = "spam"
    if not email.spam_source:
        email.spam_source = "user"
    if not email.spam_reason:
        email.spam_reason = "Confirmed as spam by user"
    email.updated_at = datetime.now(timezone.utc)
    db_session.add(email)
    db_session.add(
        ActionLog(
            email_id=email.id,
            action_type="spam_confirmed",
            actor=actor,
            details_json=json.dumps(
                {
                    "source": source,
                    "spam_source": email.spam_source,
                    "spam_reason": email.spam_reason,
                },
                ensure_ascii=False,
            ),
        )
    )
    return SpamReviewResult(
        email_id=email.id,
        status=email.status,
        is_spam=email.is_spam,
        spam_source=email.spam_source,
        spam_reason=email.spam_reason,
    )


def annotate_spam_review_metadata(db_session: Session, emails: list[Email]) -> None:
    if not emails:
        return
    email_ids = [email.id for email in emails]
    logs = (
        db_session.query(ActionLog)
        .filter(
            ActionLog.email_id.in_(email_ids),
            ActionLog.action_type.in_(
                [
                    "email_marked_spam",
                    "spam_confirmed",
                    "ai_spam_confirmed",
                    "email_restored_from_spam",
                    "ai_spam_restored",
                ]
            ),
        )
        .order_by(ActionLog.created_at.desc(), ActionLog.id.desc())
        .all()
    )
    latest_by_email: dict[int, ActionLog] = {}
    for log in logs:
        if log.email_id is None or log.email_id in latest_by_email:
            continue
        latest_by_email[log.email_id] = log

    for email in emails:
        latest_log = latest_by_email.get(email.id)
        setattr(email, "spam_action_at", latest_log.created_at if latest_log else None)
        setattr(email, "spam_action_actor", latest_log.actor if latest_log else None)
