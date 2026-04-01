from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.email import Email
from app.models.task import Task
from app.schemas.system import DigestResponse, StatsResponse
from app.services.followup_tracker import detect_overdue_threads

router = APIRouter(tags=["dashboard"])


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    today_start = datetime.combine(date.today(), time.min)
    detect_overdue_threads(db)
    db.flush()
    new_count = db.query(func.count(Email.id)).filter(Email.status == "new", Email.direction == "inbound").scalar() or 0
    waiting_reply_count = db.query(func.count(Email.id)).filter(
        Email.requires_reply.is_(True),
        Email.direction == "inbound",
        Email.status != "replied",
    ).scalar() or 0
    analyzed_today_count = db.query(func.count(Email.id)).filter(
        Email.ai_analyzed.is_(True),
        Email.updated_at >= today_start,
    ).scalar() or 0
    total_inbox_count = db.query(func.count(Email.id)).filter(Email.direction == "inbound").scalar() or 0
    spam_count = db.query(func.count(Email.id)).filter(Email.is_spam.is_(True)).scalar() or 0
    waiting_count = db.query(func.count(Task.id)).filter(
        Task.task_type == "followup",
        Task.state == "waiting_reply",
    ).scalar() or 0
    overdue_count = db.query(func.count(Task.id)).filter(
        Task.task_type == "followup",
        Task.state == "overdue_reply",
    ).scalar() or 0
    overdue_days = max(1, get_effective_settings().followup_overdue_days)
    due_window_start = today_start - timedelta(days=overdue_days)
    due_window_end = datetime.combine(date.today(), time.max) - timedelta(days=overdue_days)
    followup_due_today_count = db.query(func.count(Task.id)).filter(
        Task.task_type == "followup",
        Task.state.in_(["waiting_reply", "overdue_reply"]),
        or_(
            and_(
                Task.expected_reply_by.is_not(None),
                Task.expected_reply_by >= today_start,
                Task.expected_reply_by <= datetime.combine(date.today(), time.max),
            ),
            and_(
                Task.expected_reply_by.is_(None),
                Task.followup_started_at.is_not(None),
                Task.followup_started_at >= due_window_start,
                Task.followup_started_at <= due_window_end,
            ),
        ),
    ).scalar() or 0
    return StatsResponse(
        new_count=new_count,
        waiting_reply_count=waiting_reply_count,
        analyzed_today_count=analyzed_today_count,
        total_inbox_count=total_inbox_count,
        spam_count=spam_count,
        waiting_count=waiting_count,
        overdue_count=overdue_count,
        followup_due_today_count=followup_due_today_count,
    )


@router.get("/api/digest", response_model=DigestResponse)
def get_digest(db: Session = Depends(get_db)) -> DigestResponse:
    today = date.today()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)
    emails_received_today = db.query(func.count(Email.id)).filter(
        Email.direction == "inbound",
        Email.date_received >= today_start,
        Email.date_received <= today_end,
    ).scalar() or 0
    important_emails = db.query(func.count(Email.id)).filter(
        Email.direction == "inbound",
        Email.priority.in_(["critical", "high"]),
        Email.date_received >= today_start,
        Email.date_received <= today_end,
    ).scalar() or 0
    unanswered_emails = db.query(func.count(Email.id)).filter(
        Email.direction == "inbound",
        Email.requires_reply.is_(True),
        Email.status != "replied",
    ).scalar() or 0
    analyzed_count = db.query(func.count(Email.id)).filter(
        Email.ai_analyzed.is_(True),
        Email.date_received >= today_start,
        Email.date_received <= today_end,
    ).scalar() or 0
    return DigestResponse(
        date=today.isoformat(),
        emails_received_today=emails_received_today,
        important_emails=important_emails,
        unanswered_emails=unanswered_emails,
        analyzed_count=analyzed_count,
    )
