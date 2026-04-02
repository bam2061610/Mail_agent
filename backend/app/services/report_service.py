from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email
from app.models.task import Task
from app.models.user import User


@dataclass(slots=True)
class ReportFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    mailbox_id: str | None = None
    user_id: int | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None


def build_activity_report(db: Session, filters: ReportFilters) -> dict[str, Any]:
    email_query = _filtered_email_query(db, filters)
    sent_count = email_query.filter(Email.direction == "sent").count()
    received_count = email_query.filter(Email.direction == "inbound").count()
    spam_count = email_query.filter(Email.is_spam.is_(True)).count()

    waiting_query = db.query(Task).filter(Task.task_type == "followup")
    if filters.date_from:
        waiting_query = waiting_query.filter(Task.created_at >= filters.date_from)
    if filters.date_to:
        waiting_query = waiting_query.filter(Task.created_at <= filters.date_to)
    waiting_threads = waiting_query.filter(Task.state == "waiting_reply").count()
    overdue_threads = waiting_query.filter(Task.state == "overdue_reply").count()
    closed_threads = waiting_query.filter(Task.state == "closed").count()

    active_threads = db.query(func.count(func.distinct(func.coalesce(Email.thread_id, Email.message_id)))).filter(
        Email.direction == "inbound",
        Email.status.in_(["new", "read", "replied"]),
    )
    if filters.date_from:
        active_threads = active_threads.filter(Email.date_received >= filters.date_from)
    if filters.date_to:
        active_threads = active_threads.filter(Email.date_received <= filters.date_to)
    if filters.mailbox_id:
        active_threads = active_threads.filter(Email.mailbox_id == filters.mailbox_id)
    active_threads_count = active_threads.scalar() or 0

    restored_from_spam_count = (
        db.query(func.count(ActionLog.id))
        .filter(ActionLog.action_type.in_(["ai_spam_restored", "email_restored_from_spam"]))
        .scalar()
        or 0
    )

    rows = (
        email_query.order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(200)
        .all()
    )
    payload_rows = [
        {
            "email_id": item.id,
            "thread_id": item.thread_id or item.message_id or f"email-{item.id}",
            "subject": item.subject,
            "sender": item.sender_email,
            "mailbox": item.mailbox_name or item.mailbox_address or item.mailbox_id,
            "status": item.status,
            "priority": item.priority,
            "category": item.category,
            "waiting_days": _thread_wait_days(db, item.thread_id or item.message_id),
            "assigned_user": item.assigned_to_user_id,
            "last_activity_at": (item.updated_at or item.date_received).isoformat() if (item.updated_at or item.date_received) else None,
        }
        for item in rows
    ]

    return {
        "report_type": "activity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": _filters_dict(filters),
        "summary": {
            "sent_emails_count": sent_count,
            "received_emails_count": received_count,
            "active_threads": active_threads_count,
            "closed_threads": closed_threads,
            "waiting_threads": waiting_threads,
            "overdue_followups": overdue_threads,
            "spam_count": spam_count,
            "restored_from_spam_count": restored_from_spam_count,
        },
        "rows": payload_rows,
    }


def build_followup_report(db: Session, filters: ReportFilters) -> dict[str, Any]:
    query = db.query(Task).filter(Task.task_type == "followup", Task.state.in_(["waiting_reply", "overdue_reply", "closed"]))
    if filters.date_from:
        query = query.filter(or_(Task.followup_started_at.is_(None), Task.followup_started_at >= filters.date_from))
    if filters.date_to:
        query = query.filter(or_(Task.followup_started_at.is_(None), Task.followup_started_at <= filters.date_to))
    if filters.user_id:
        query = query.filter(Task.assigned_to_user_id == filters.user_id)
    if filters.status:
        query = query.filter(Task.state == filters.status)
    rows = query.order_by(Task.updated_at.desc(), Task.id.desc()).limit(300).all()

    payload_rows: list[dict[str, Any]] = []
    waiting_count = 0
    overdue_count = 0
    for task in rows:
        if task.state == "waiting_reply":
            waiting_count += 1
        if task.state == "overdue_reply":
            overdue_count += 1
        latest_email = _latest_thread_email(db, task.thread_id)
        wait_days = 0
        followup_started_at = _as_utc(task.followup_started_at)
        if followup_started_at:
            wait_days = max(0, (datetime.now(timezone.utc) - followup_started_at).days)
        payload_rows.append(
            {
                "task_id": task.id,
                "thread_id": task.thread_id,
                "state": task.state,
                "subject": latest_email.subject if latest_email else task.title,
                "sender": latest_email.sender_email if latest_email else None,
                "mailbox": latest_email.mailbox_name if latest_email else None,
                "waiting_days": wait_days,
                "expected_reply_by": task.expected_reply_by.isoformat() if task.expected_reply_by else None,
                "assigned_user": task.assigned_to_user_id,
                "last_activity_at": task.updated_at.isoformat() if task.updated_at else None,
            }
        )

    return {
        "report_type": "followups",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": _filters_dict(filters),
        "summary": {
            "total_threads": len(payload_rows),
            "waiting_threads": waiting_count,
            "overdue_threads": overdue_count,
        },
        "rows": payload_rows,
    }


def build_sent_review_report(db: Session, filters: ReportFilters) -> dict[str, Any]:
    query = _filtered_email_query(db, filters).filter(Email.direction == "sent")
    rows = query.order_by(Email.date_received.desc().nullslast(), Email.id.desc()).limit(300).all()
    verdict_counts: dict[str, int] = {}
    problematic = 0
    issues: dict[str, int] = {}
    payload_rows = []
    for item in rows:
        verdict = item.sent_review_status or "pending"
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        if verdict in {"problematic", "needs_attention"}:
            problematic += 1
        for token in _extract_issue_tokens(item.sent_review_issues_json):
            issues[token] = issues.get(token, 0) + 1
        payload_rows.append(
            {
                "email_id": item.id,
                "thread_id": item.thread_id or item.message_id,
                "subject": item.subject,
                "mailbox": item.mailbox_name or item.mailbox_address or item.mailbox_id,
                "verdict": verdict,
                "summary": item.sent_review_summary,
                "score": item.sent_review_score,
                "reviewed_at": item.sent_reviewed_at.isoformat() if item.sent_reviewed_at else None,
            }
        )
    return {
        "report_type": "sent_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": _filters_dict(filters),
        "summary": {
            "total_sent": len(payload_rows),
            "verdict_counts": verdict_counts,
            "problematic_count": problematic,
            "common_issues": sorted(issues.items(), key=lambda item: item[1], reverse=True)[:10],
        },
        "rows": payload_rows,
    }


def build_team_activity_report(db: Session, filters: ReportFilters) -> dict[str, Any]:
    logs = db.query(ActionLog)
    if filters.date_from:
        logs = logs.filter(ActionLog.created_at >= filters.date_from)
    if filters.date_to:
        logs = logs.filter(ActionLog.created_at <= filters.date_to)
    if filters.user_id:
        logs = logs.filter(ActionLog.user_id == filters.user_id)
    log_rows = logs.order_by(ActionLog.created_at.desc(), ActionLog.id.desc()).limit(1000).all()

    by_user: dict[int, dict[str, Any]] = {}
    for item in log_rows:
        if item.user_id is None:
            continue
        bucket = by_user.setdefault(item.user_id, {"actions_count": 0, "actions": {}, "last_action_at": None})
        bucket["actions_count"] += 1
        bucket["actions"][item.action_type] = bucket["actions"].get(item.action_type, 0) + 1
        if bucket["last_action_at"] is None:
            bucket["last_action_at"] = item.created_at.isoformat() if item.created_at else None

    users = {item.id: item for item in db.query(User).all()}
    sent_by_user = (
        db.query(ActionLog.user_id, func.count(ActionLog.id))
        .filter(ActionLog.action_type == "email_sent")
        .group_by(ActionLog.user_id)
        .all()
    )
    sent_map = {user_id: count for user_id, count in sent_by_user if user_id is not None}

    rows = []
    for user_id, data in by_user.items():
        user = users.get(user_id)
        rows.append(
            {
                "user_id": user_id,
                "user_email": user.email if user else None,
                "user_name": user.full_name if user else None,
                "role": user.role if user else None,
                "actions_count": data["actions_count"],
                "sent_replies_count": sent_map.get(user_id, 0),
                "top_actions": sorted(data["actions"].items(), key=lambda item: item[1], reverse=True)[:8],
                "last_action_at": data["last_action_at"],
            }
        )
    rows.sort(key=lambda item: item["actions_count"], reverse=True)
    return {
        "report_type": "team_activity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": _filters_dict(filters),
        "summary": {
            "users_with_activity": len(rows),
            "total_actions": sum(item["actions_count"] for item in rows),
            "total_sent_replies": sum(item["sent_replies_count"] for item in rows),
        },
        "rows": rows,
    }


def _filtered_email_query(db: Session, filters: ReportFilters):
    query = db.query(Email)
    if filters.date_from:
        query = query.filter(or_(Email.date_received.is_(None), Email.date_received >= filters.date_from))
    if filters.date_to:
        query = query.filter(or_(Email.date_received.is_(None), Email.date_received <= filters.date_to))
    if filters.mailbox_id:
        query = query.filter(Email.mailbox_id == filters.mailbox_id)
    if filters.user_id:
        query = query.filter(Email.assigned_to_user_id == filters.user_id)
    if filters.status:
        query = query.filter(Email.status == filters.status)
    if filters.priority:
        query = query.filter(Email.priority == filters.priority)
    if filters.category:
        query = query.filter(Email.category == filters.category)
    return query


def parse_report_filters(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    mailbox_id: str | None = None,
    user_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
) -> ReportFilters:
    return ReportFilters(
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to, end_of_day=True),
        mailbox_id=mailbox_id,
        user_id=user_id,
        status=status,
        priority=priority,
        category=category,
    )


def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    parsed = _as_utc(parsed)
    if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        parsed = parsed + timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def _filters_dict(filters: ReportFilters) -> dict[str, Any]:
    return {
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "mailbox_id": filters.mailbox_id,
        "user_id": filters.user_id,
        "status": filters.status,
        "priority": filters.priority,
        "category": filters.category,
    }


def _latest_thread_email(db: Session, thread_id: str | None) -> Email | None:
    if not thread_id:
        return None
    return (
        db.query(Email)
        .filter(or_(Email.thread_id == thread_id, Email.message_id == thread_id))
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .first()
    )


def _thread_wait_days(db: Session, thread_id: str | None) -> int | None:
    if not thread_id:
        return None
    task = (
        db.query(Task)
        .filter(Task.thread_id == thread_id, Task.task_type == "followup", Task.state.in_(["waiting_reply", "overdue_reply"]))
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .first()
    )
    if not task or not task.followup_started_at:
        return None
    followup_started_at = _as_utc(task.followup_started_at)
    if followup_started_at is None:
        return None
    return max(0, (datetime.now(timezone.utc) - followup_started_at).days)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _extract_issue_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        import json

        parsed = json.loads(raw)
    except Exception:
        return [raw]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        return [str(key) for key in parsed.keys()]
    return [str(parsed)]
