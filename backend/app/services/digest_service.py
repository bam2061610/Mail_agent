import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.action_log import ActionLog
from app.models.email import Email
from app.models.task import Task

STATE_FILE_PATH = DATA_DIR / "digest_state.json"


@dataclass(slots=True)
class CatchupDigest:
    generated_at: datetime
    since: datetime
    away_hours: int
    should_show: bool
    important_new: list[dict]
    waiting_or_overdue: list[dict]
    spam_review: list[dict]
    recent_sent: list[dict]
    followups_due: list[dict]
    top_actions: list[str]


def generate_catchup_digest(db_session: Session, config, now: datetime | None = None) -> CatchupDigest:
    current_time = now or datetime.now(timezone.utc)
    state = _load_state()
    last_seen_at = _parse_dt(state.get("last_seen_at"))
    catchup_hours = max(1, int(getattr(config, "catchup_absence_hours", 8) or 8))
    if last_seen_at is None:
        # First run fallback: look back one day.
        last_seen_at = current_time - timedelta(hours=24)

    away_hours = max(0, int((current_time - last_seen_at).total_seconds() // 3600))
    should_show = away_hours >= catchup_hours
    since = last_seen_at

    important_new_rows = (
        db_session.query(Email)
        .filter(
            Email.direction == "inbound",
            Email.is_spam.is_(False),
            Email.date_received.is_not(None),
            Email.date_received >= since,
            or_(Email.priority.in_(["critical", "high"]), Email.requires_reply.is_(True)),
        )
        .order_by(Email.date_received.desc(), Email.id.desc())
        .limit(12)
        .all()
    )
    waiting_tasks = (
        db_session.query(Task)
        .filter(
            Task.task_type == "followup",
            Task.state.in_(["waiting_reply", "overdue_reply"]),
            # Always surface overdue follow-ups in catch-up, even if they started
            # before the current "since" window.
            or_(
                Task.state == "overdue_reply",
                Task.followup_started_at.is_(None),
                Task.followup_started_at >= since,
            ),
        )
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .limit(12)
        .all()
    )
    spam_rows = (
        db_session.query(Email)
        .filter(
            Email.is_spam.is_(True),
            Email.updated_at >= since,
        )
        .order_by(Email.updated_at.desc(), Email.id.desc())
        .limit(12)
        .all()
    )
    recent_sent_rows = (
        db_session.query(Email)
        .filter(
            Email.direction == "sent",
            Email.date_received.is_not(None),
            Email.date_received >= since,
        )
        .order_by(Email.date_received.desc(), Email.id.desc())
        .limit(12)
        .all()
    )
    followups_due_tasks = (
        db_session.query(Task)
        .filter(
            Task.task_type == "followup",
            Task.state.in_(["waiting_reply", "overdue_reply"]),
            or_(
                and_(
                    Task.expected_reply_by.is_not(None),
                    Task.expected_reply_by <= current_time,
                ),
                and_(
                    Task.expected_reply_by.is_(None),
                    Task.state == "overdue_reply",
                ),
            ),
        )
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .limit(12)
        .all()
    )

    important_new = [_email_card(item) for item in important_new_rows]
    waiting_or_overdue = [_task_email_card(task, _latest_thread_email(db_session, task.thread_id)) for task in waiting_tasks]
    spam_review = [_email_card(item) for item in spam_rows]
    recent_sent = [_email_card(item) for item in recent_sent_rows]
    followups_due = [_task_email_card(task, _latest_thread_email(db_session, task.thread_id)) for task in followups_due_tasks]

    top_actions = _build_top_actions(
        important_new_count=len(important_new),
        overdue_count=sum(1 for item in waiting_or_overdue if item.get("state") == "overdue_reply"),
        spam_count=len(spam_review),
        followup_due_count=len(followups_due),
    )

    db_session.add(
        ActionLog(
            action_type="digest_generated",
            actor="system",
            details_json=json.dumps(
                {
                    "since": since.isoformat(),
                    "away_hours": away_hours,
                    "should_show": should_show,
                    "important_new_count": len(important_new),
                    "waiting_or_overdue_count": len(waiting_or_overdue),
                    "spam_review_count": len(spam_review),
                    "recent_sent_count": len(recent_sent),
                    "followups_due_count": len(followups_due),
                },
                ensure_ascii=False,
            ),
        )
    )
    db_session.commit()

    return CatchupDigest(
        generated_at=current_time,
        since=since,
        away_hours=away_hours,
        should_show=should_show,
        important_new=important_new,
        waiting_or_overdue=waiting_or_overdue,
        spam_review=spam_review,
        recent_sent=recent_sent,
        followups_due=followups_due,
        top_actions=top_actions,
    )


def mark_digest_seen(db_session: Session, when: datetime | None = None) -> dict[str, str]:
    now = when or datetime.now(timezone.utc)
    state = _load_state()
    state["last_seen_at"] = now.isoformat()
    state["last_digest_viewed_at"] = now.isoformat()
    _save_state(state)
    db_session.add(
        ActionLog(
            action_type="digest_viewed",
            actor="user",
            details_json=json.dumps({"seen_at": now.isoformat()}, ensure_ascii=False),
        )
    )
    db_session.commit()
    return {
        "last_seen_at": state["last_seen_at"],
        "last_digest_viewed_at": state["last_digest_viewed_at"],
    }


def get_digest_state() -> dict[str, str | None]:
    state = _load_state()
    return {
        "last_seen_at": state.get("last_seen_at"),
        "last_digest_viewed_at": state.get("last_digest_viewed_at"),
    }


def _build_top_actions(
    important_new_count: int,
    overdue_count: int,
    spam_count: int,
    followup_due_count: int,
) -> list[str]:
    items: list[str] = []
    if overdue_count:
        items.append(f"Resolve overdue follow-ups first ({overdue_count}).")
    if important_new_count:
        items.append(f"Review important new inbound threads ({important_new_count}).")
    if followup_due_count:
        items.append(f"Check follow-ups due now ({followup_due_count}).")
    if spam_count:
        items.append(f"Audit newly blocked spam ({spam_count}).")
    if not items:
        items.append("No urgent catch-up actions detected.")
    return items[:5]


def _email_card(email: Email) -> dict:
    return {
        "email_id": email.id,
        "thread_id": email.thread_id or email.message_id or f"email-{email.id}",
        "subject": email.subject,
        "sender_email": email.sender_email,
        "sender_name": email.sender_name,
        "mailbox_name": email.mailbox_name,
        "priority": email.priority,
        "status": email.status,
        "date_received": email.date_received.isoformat() if email.date_received else None,
    }


def _task_email_card(task: Task, email: Email | None) -> dict:
    return {
        "task_id": task.id,
        "thread_id": task.thread_id,
        "state": task.state,
        "email_id": email.id if email is not None else task.email_id,
        "subject": (email.subject if email is not None else None) or task.title,
        "sender_email": email.sender_email if email is not None else None,
        "sender_name": email.sender_name if email is not None else None,
        "mailbox_name": email.mailbox_name if email is not None else None,
        "expected_reply_by": task.expected_reply_by.isoformat() if task.expected_reply_by else None,
    }


def _latest_thread_email(db_session: Session, thread_id: str | None) -> Email | None:
    if not thread_id:
        return None
    return (
        db_session.query(Email)
        .filter(or_(Email.thread_id == thread_id, Email.message_id == thread_id), Email.direction == "inbound")
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .first()
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_state() -> dict:
    if not STATE_FILE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(payload: dict) -> None:
    STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
