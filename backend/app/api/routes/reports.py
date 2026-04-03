import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import ReportResponse, ReportSendRequest, ReportSendResponse
from app.services.export_service import export_report
from app.services.mailbox_service import get_default_runtime_mailbox_from_settings
from app.services.permission_service import require_permission
from app.services.report_service import (
    build_report_email_body,
    build_activity_report,
    build_sent_review_report,
    normalize_recipient_addresses,
    parse_report_filters,
)
from app.services.mail.smtp_send import send_email

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = logging.getLogger(__name__)


@router.get("/activity", response_model=ReportResponse)
def report_activity(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    mailbox_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> ReportResponse:
    filters = parse_report_filters(
        date_from=date_from,
        date_to=date_to,
        mailbox_id=mailbox_id,
        user_id=user_id,
        status=status,
        priority=priority,
        category=category,
    )
    payload = build_activity_report(db, filters)
    _log_report_action(db, current_user, "report_generated", {"report_type": "activity", "filters": payload.get("filters")})
    return ReportResponse(**payload)


@router.get("/sent-review", response_model=ReportResponse)
def report_sent_review(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    mailbox_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> ReportResponse:
    filters = parse_report_filters(
        date_from=date_from,
        date_to=date_to,
        mailbox_id=mailbox_id,
        user_id=user_id,
        status=status,
        priority=priority,
        category=category,
    )
    payload = build_sent_review_report(db, filters)
    _log_report_action(db, current_user, "report_generated", {"report_type": "sent_review", "filters": payload.get("filters")})
    return ReportResponse(**payload)


@router.get("/activity/export")
def export_activity(
    format: str = Query(default="csv", pattern="^(csv|pdf)$"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    mailbox_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> Response:
    filters = parse_report_filters(
        date_from=date_from,
        date_to=date_to,
        mailbox_id=mailbox_id,
        user_id=user_id,
        status=status,
        priority=priority,
        category=category,
    )
    payload = build_activity_report(db, filters)
    artifact = export_report(payload, "activity_report", format)
    _log_report_action(db, current_user, f"report_exported_{format}", {"report_type": "activity", "filters": payload.get("filters")})
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.get("/sent-review/export")
def export_sent_review(
    format: str = Query(default="csv", pattern="^(csv|pdf)$"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    mailbox_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> Response:
    filters = parse_report_filters(
        date_from=date_from,
        date_to=date_to,
        mailbox_id=mailbox_id,
        user_id=user_id,
        status=status,
        priority=priority,
        category=category,
    )
    payload = build_sent_review_report(db, filters)
    artifact = export_report(payload, "sent_review_report", format)
    _log_report_action(db, current_user, f"report_exported_{format}", {"report_type": "sent_review", "filters": payload.get("filters")})
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.post("/send", response_model=ReportSendResponse)
def send_report_email(
    request: ReportSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> ReportSendResponse:
    filters = parse_report_filters(
        date_from=request.date_from,
        date_to=request.date_to,
        mailbox_id=request.mailbox_id,
        user_id=request.user_id,
        status=request.status,
        priority=request.priority,
        category=request.category,
    )
    report_type = request.report_type.strip().lower()
    if report_type == "activity":
        payload = build_activity_report(db, filters)
    elif report_type == "sent-review":
        payload = build_sent_review_report(db, filters)
    else:
        raise HTTPException(status_code=400, detail="Unsupported report_type")

    to_addresses = normalize_recipient_addresses(request.to)
    cc_addresses = normalize_recipient_addresses(request.cc)
    bcc_addresses = normalize_recipient_addresses(request.bcc)
    if not to_addresses:
        raise HTTPException(status_code=422, detail="At least one recipient email is required")

    smtp_config = get_default_runtime_mailbox_from_settings() or get_effective_settings()
    smtp_username = getattr(smtp_config, "smtp_username", None) or getattr(smtp_config, "smtp_user", None)
    if not getattr(smtp_config, "smtp_host", None) or not smtp_username:
        raise HTTPException(status_code=422, detail="SMTP is not configured for report delivery")
    subject = f"Orhun Mail Agent report: {payload.get('report_type')} ({payload.get('generated_at')})"
    body = build_report_email_body(payload)
    try:
        result = send_email(
            to=to_addresses,
            cc=cc_addresses,
            bcc=bcc_addresses,
            subject=subject,
            body=body,
            config=smtp_config,
        )
    except ValueError as exc:
        logger.warning("Report email validation failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception(
            "Report email delivery failed: report_type=%s recipients=%s cc=%s bcc_count=%s",
            payload.get("report_type"),
            to_addresses,
            cc_addresses,
            len(bcc_addresses),
        )
        raise HTTPException(status_code=502, detail="Could not send report email due to SMTP delivery failure") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected report email failure: report_type=%s recipients=%s cc=%s bcc_count=%s",
            payload.get("report_type"),
            to_addresses,
            cc_addresses,
            len(bcc_addresses),
        )
        raise HTTPException(status_code=502, detail="Could not send report email due to unexpected delivery failure") from exc

    _log_report_action(
        db,
        current_user,
        "report_emailed",
        {
            "report_type": payload.get("report_type"),
            "recipients": to_addresses,
            "cc": cc_addresses,
            "bcc_count": len(bcc_addresses),
            "message_id": result.message_id,
            "filters": payload.get("filters"),
        },
    )
    return ReportSendResponse(
        report_type=payload.get("report_type", report_type),
        recipients=to_addresses,
        subject=subject,
    )


def _log_report_action(db: Session, user: User, action_type: str, payload: dict) -> None:
    db.add(
        ActionLog(
            user_id=user.id,
            action_type=action_type,
            actor=user.email,
            details_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    db.commit()
