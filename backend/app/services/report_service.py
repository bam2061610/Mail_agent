from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email
from app.services.mailbox_service import SENT_DIRECTION_VALUES


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
    sent_count = email_query.filter(Email.direction.in_(SENT_DIRECTION_VALUES)).count()
    received_count = email_query.filter(Email.direction == "inbound").count()
    spam_count = email_query.filter(Email.is_spam.is_(True)).count()

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
            "closed_threads": 0,
            "waiting_threads": 0,
            "overdue_followups": 0,
            "spam_count": spam_count,
            "restored_from_spam_count": restored_from_spam_count,
        },
        "rows": payload_rows,
    }


def build_sent_review_report(db: Session, filters: ReportFilters) -> dict[str, Any]:
    query = _filtered_email_query(db, filters).filter(Email.direction.in_(SENT_DIRECTION_VALUES))
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


def normalize_recipient_addresses(addresses: list[str] | None) -> list[str]:
    if not addresses:
        return []
    cleaned: list[str] = []
    for item in addresses:
        value = (item or "").strip()
        if not value or value in cleaned:
            continue
        cleaned.append(value)
    return cleaned


REPORT_TYPE_LABELS_EMAIL: dict[str, str] = {
    "activity": "Активность",
    "sent_review": "Проверка исходящих",
}

SUMMARY_KEY_LABELS_EMAIL: dict[str, str] = {
    "sent_emails_count": "Отправлено",
    "received_emails_count": "Получено",
    "active_threads": "Активных тредов",
    "closed_threads": "Закрытых",
    "spam_count": "Спам",
    "restored_from_spam_count": "Восстановлено",
    "total_sent": "Всего отправлено",
    "problematic_count": "Проблемных",
}


def build_report_email_body(payload: dict[str, Any], *, max_summary_lines: int = 30) -> str:
    report_type = payload.get("report_type", "unknown")
    type_label = REPORT_TYPE_LABELS_EMAIL.get(report_type, report_type)
    summary_lines = []
    for key, value in (payload.get("summary") or {}).items():
        label = SUMMARY_KEY_LABELS_EMAIL.get(key, key)
        if isinstance(value, dict):
            formatted = ", ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, list):
            formatted = ", ".join(str(item) for item in value[:5])
        else:
            formatted = str(value)
        summary_lines.append(f"  {label}: {formatted}")
    rows = payload.get("rows") or []
    lines = [
        f"Orhun Mail Agent — {type_label}",
        "",
        f"Дата: {payload.get('generated_at', '')}",
        f"Строк в отчёте: {len(rows)}",
        "",
        "Краткая сводка",
        "─" * 30,
        *summary_lines[:max_summary_lines],
    ]
    return "\n".join(lines)


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
