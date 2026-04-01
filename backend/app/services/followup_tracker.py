import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.models.action_log import ActionLog
from app.models.email import Email
from app.models.task import Task

WAITING_STATES = {"waiting_reply", "overdue_reply"}


@dataclass(slots=True)
class WaitingThreadSnapshot:
    task_id: int
    email_id: int | None
    thread_id: str
    state: str
    title: str
    subtitle: str | None
    started_at: datetime | None
    expected_reply_by: datetime | None
    wait_days: int
    latest_email_id: int | None
    latest_subject: str | None
    latest_sender_email: str | None
    latest_sender_name: str | None
    latest_ai_summary: str | None
    latest_date_received: datetime | None
    followup_draft: str | None


def mark_thread_waiting(
    db_session: Session,
    thread_id: str,
    started_at: datetime | None = None,
    expected_reply_by: datetime | None = None,
    email_id: int | None = None,
    actor: str = "system",
) -> Task:
    if not thread_id:
        raise ValueError("thread_id is required")

    now = started_at or datetime.utcnow()
    task = _get_or_create_followup_task(db_session, thread_id=thread_id, email_id=email_id)
    latest_email = _get_latest_thread_email(db_session, thread_id)
    task.email_id = email_id or latest_email.id if latest_email else task.email_id
    task.thread_id = thread_id
    task.task_type = "followup"
    task.title = latest_email.subject if latest_email and latest_email.subject else "Follow-up needed"
    task.subtitle = latest_email.sender_email if latest_email else task.subtitle
    task.state = "waiting_reply"
    task.current_step = "waiting_for_partner_reply"
    task.followup_started_at = now
    task.expected_reply_by = expected_reply_by
    task.closed_at = None
    task.close_reason = None
    db_session.add(task)
    db_session.flush()
    _log_action(
        db_session,
        email_id=task.email_id,
        task_id=task.id,
        action_type="waiting_started",
        actor=actor,
        details={
            "thread_id": thread_id,
            "started_at": now.isoformat(),
            "expected_reply_by": expected_reply_by.isoformat() if expected_reply_by else None,
        },
    )
    return task


def close_waiting(db_session: Session, thread_id: str, reason: str | None = None, actor: str = "system") -> Task | None:
    task = _get_followup_task(db_session, thread_id)
    if task is None:
        return None

    task.state = "closed"
    task.closed_at = datetime.utcnow()
    task.close_reason = reason
    task.current_step = "closed"
    db_session.add(task)
    _log_action(
        db_session,
        email_id=task.email_id,
        task_id=task.id,
        action_type="waiting_closed",
        actor=actor,
        details={"thread_id": thread_id, "reason": reason},
    )
    return task


def get_waiting_threads(db_session: Session, now: datetime | None = None) -> list[WaitingThreadSnapshot]:
    current_time = now or datetime.utcnow()
    detect_overdue_threads(db_session, current_time)
    db_session.flush()

    tasks = (
        db_session.query(Task)
        .filter(Task.task_type == "followup", Task.state.in_(tuple(WAITING_STATES)))
        .order_by(Task.expected_reply_by.asc().nulls_last(), Task.followup_started_at.asc().nulls_last(), Task.updated_at.desc())
        .all()
    )
    return [_build_snapshot(db_session, task, current_time) for task in tasks]


def detect_overdue_threads(db_session: Session, now: datetime | None = None, threshold_days: int = 3) -> list[Task]:
    current_time = now or datetime.utcnow()
    effective_threshold = max(1, getattr(get_effective_settings(), "followup_overdue_days", threshold_days))
    tasks = (
        db_session.query(Task)
        .filter(Task.task_type == "followup", Task.state == "waiting_reply")
        .all()
    )
    overdue_tasks: list[Task] = []
    for task in tasks:
        if _is_overdue(task, current_time, effective_threshold):
            task.state = "overdue_reply"
            task.current_step = "follow_up_due"
            db_session.add(task)
            overdue_tasks.append(task)
    return overdue_tasks


def compute_wait_days(db_session: Session, thread_id: str, now: datetime | None = None) -> int:
    task = _get_followup_task(db_session, thread_id)
    if task is None or task.followup_started_at is None:
        return 0
    current_time = now or datetime.utcnow()
    delta = current_time - task.followup_started_at
    return max(0, delta.days)


def get_thread_waiting_state(db_session: Session, thread_id: str, now: datetime | None = None) -> WaitingThreadSnapshot | None:
    current_time = now or datetime.utcnow()
    detect_overdue_threads(db_session, current_time)
    task = _get_followup_task(db_session, thread_id)
    if task is None or task.state not in WAITING_STATES:
        return None
    return _build_snapshot(db_session, task, current_time)


def _get_followup_task(db_session: Session, thread_id: str) -> Task | None:
    return (
        db_session.query(Task)
        .filter(Task.task_type == "followup", Task.thread_id == thread_id)
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .first()
    )


def _get_or_create_followup_task(db_session: Session, thread_id: str, email_id: int | None) -> Task:
    existing = _get_followup_task(db_session, thread_id)
    if existing is not None:
        return existing
    return Task(
        email_id=email_id,
        thread_id=thread_id,
        task_type="followup",
        title="Follow-up needed",
        state="waiting_reply",
    )


def _get_latest_thread_email(db_session: Session, thread_id: str) -> Email | None:
    return (
        db_session.query(Email)
        .filter((Email.thread_id == thread_id) | (Email.message_id == thread_id))
        .order_by(Email.date_received.desc().nulls_last(), Email.id.desc())
        .first()
    )


def _build_snapshot(db_session: Session, task: Task, now: datetime) -> WaitingThreadSnapshot:
    latest_email = _get_latest_thread_email(db_session, task.thread_id or "")
    wait_days = 0
    if task.followup_started_at is not None:
        wait_days = max(0, (now - task.followup_started_at).days)
    return WaitingThreadSnapshot(
        task_id=task.id,
        email_id=task.email_id,
        thread_id=task.thread_id or "",
        state=task.state,
        title=task.title,
        subtitle=task.subtitle,
        started_at=task.followup_started_at,
        expected_reply_by=task.expected_reply_by,
        wait_days=wait_days,
        latest_email_id=latest_email.id if latest_email else None,
        latest_subject=latest_email.subject if latest_email else None,
        latest_sender_email=latest_email.sender_email if latest_email else None,
        latest_sender_name=latest_email.sender_name if latest_email else None,
        latest_ai_summary=latest_email.ai_summary if latest_email else None,
        latest_date_received=latest_email.date_received if latest_email else None,
        followup_draft=task.followup_draft,
    )


def _is_overdue(task: Task, now: datetime, threshold_days: int) -> bool:
    if task.expected_reply_by:
        return now >= task.expected_reply_by
    if task.followup_started_at is None:
        return False
    return now >= task.followup_started_at + timedelta(days=threshold_days)


def _log_action(
    db_session: Session,
    email_id: int | None,
    task_id: int | None,
    action_type: str,
    actor: str,
    details: dict,
) -> None:
    db_session.add(
        ActionLog(
            email_id=email_id,
            task_id=task_id,
            action_type=action_type,
            actor=actor,
            details_json=json.dumps(details, ensure_ascii=False),
        )
    )
