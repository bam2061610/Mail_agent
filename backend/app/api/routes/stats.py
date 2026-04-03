from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.email import Email
from app.models.user import User
from app.schemas.system import CatchupDigestResponse, DigestResponse, DigestSeenResponse, StatsResponse
from app.services.digest_service import generate_catchup_digest, mark_digest_seen
from app.services.permission_service import require_permission

router = APIRouter(tags=["dashboard"])


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> StatsResponse:
    today_start = datetime.combine(date.today(), time.min)
    new_count = db.query(func.count(Email.id)).filter(Email.status == "new", Email.direction == "inbound").scalar() or 0
    analyzed_today_count = db.query(func.count(Email.id)).filter(
        Email.ai_analyzed.is_(True),
        Email.updated_at >= today_start,
    ).scalar() or 0
    total_inbox_count = db.query(func.count(Email.id)).filter(Email.direction == "inbound").scalar() or 0
    spam_count = db.query(func.count(Email.id)).filter(Email.is_spam.is_(True)).scalar() or 0
    return StatsResponse(
        new_count=new_count,
        waiting_reply_count=0,
        analyzed_today_count=analyzed_today_count,
        total_inbox_count=total_inbox_count,
        spam_count=spam_count,
        waiting_count=0,
        overdue_count=0,
        followup_due_today_count=0,
    )


@router.get("/api/digest", response_model=DigestResponse)
def get_digest(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_digest")),
) -> DigestResponse:
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


@router.get("/api/digest/catchup", response_model=CatchupDigestResponse)
def get_catchup_digest(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_digest")),
) -> CatchupDigestResponse:
    digest = generate_catchup_digest(db, get_effective_settings())
    return CatchupDigestResponse(
        generated_at=digest.generated_at.isoformat(),
        since=digest.since.isoformat(),
        away_hours=digest.away_hours,
        should_show=digest.should_show,
        important_new=digest.important_new,
        waiting_or_overdue=digest.waiting_or_overdue,
        spam_review=digest.spam_review,
        recent_sent=digest.recent_sent,
        followups_due=digest.followups_due,
        top_actions=digest.top_actions,
    )


@router.post("/api/digest/mark-seen", response_model=DigestSeenResponse)
def mark_catchup_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_digest")),
) -> DigestSeenResponse:
    state = mark_digest_seen(db)
    return DigestSeenResponse(
        last_seen_at=state["last_seen_at"],
        last_digest_viewed_at=state["last_digest_viewed_at"],
    )


@router.post("/api/digest/rebuild", response_model=CatchupDigestResponse)
def rebuild_catchup_digest(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_digest")),
) -> CatchupDigestResponse:
    digest = generate_catchup_digest(db, get_effective_settings())
    return CatchupDigestResponse(
        generated_at=digest.generated_at.isoformat(),
        since=digest.since.isoformat(),
        away_hours=digest.away_hours,
        should_show=digest.should_show,
        important_new=digest.important_new,
        waiting_or_overdue=digest.waiting_or_overdue,
        spam_review=digest.spam_review,
        recent_sent=digest.recent_sent,
        followups_due=digest.followups_due,
        top_actions=digest.top_actions,
    )
