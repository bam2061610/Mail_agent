import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.action_log import ActionLog
from app.models.email import Email
from app.models.user import User
from app.schemas.email import EmailListItem
from app.schemas.system import (
    AutomationRule,
    AutomationRuleCreateRequest,
    AutomationRuleReorderRequest,
    AutomationRuleUpdateRequest,
    ManualScanResponse,
    MessageTemplate,
    MessageTemplateCreateRequest,
    MessageTemplateUpdateRequest,
    OperationStatusResponse,
    PreferenceProfileResponse,
    SentReviewRunResponse,
)
from app.services.ai_analyzer import analyze_pending
from app.services.attachment_service import build_attachment_download_payload, get_attachment
from app.services.diagnostics_service import mark_analyze_result, mark_scan_result
from app.services.imap_scanner import scan_all_mailboxes
from app.services.preference_profile import get_preference_profile, rebuild_preference_profile
from app.services.rule_engine import create_rule, delete_rule, list_rules, reorder_rules, update_rule
from app.services.sent_review_service import review_pending_sent
from app.services.spam_service import list_spam_emails
from app.services.template_service import create_template, delete_template, list_templates, update_template
from app.services.mailbox_service import SENT_DIRECTION_VALUES
from app.services.permission_service import require_permission

router = APIRouter(tags=["actions"])


@router.post("/api/scan", response_model=ManualScanResponse)
def manual_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("run_scan")),
) -> ManualScanResponse:
    runtime_settings = get_effective_settings()
    imported_count = 0
    analyzed_count = 0
    errors: list[str] = []
    details: dict[str, dict[str, int]] = {}

    try:
        scan_result = scan_all_mailboxes(db, runtime_settings)
        imported_count = scan_result.total_created_count
        errors.extend(scan_result.errors)
        mark_scan_result(
            success=len(scan_result.errors) == 0,
            imported_count=scan_result.total_created_count,
            skipped_count=scan_result.total_skipped_count,
            errors_count=len(scan_result.errors),
            error_text="; ".join(scan_result.errors[:3]) if scan_result.errors else None,
        )
        details["scan"] = {
            "mailboxes_scanned": len(scan_result.mailbox_results),
            "created_count": scan_result.total_created_count,
            "skipped_count": scan_result.total_skipped_count,
        }
    except Exception as exc:  # noqa: BLE001
        mark_scan_result(success=False, error_text=str(exc))
        errors.append(f"scan_failed: {exc}")

    try:
        analysis_result = analyze_pending(db, runtime_settings)
        analyzed_count = analysis_result.analyzed_count
        errors.extend(analysis_result.errors)
        mark_analyze_result(
            success=analysis_result.failed_count == 0 and len(analysis_result.errors) == 0,
            analyzed_count=analysis_result.analyzed_count,
            failed_count=analysis_result.failed_count,
            skipped_count=analysis_result.skipped_count,
            error_text="; ".join(analysis_result.errors[:3]) if analysis_result.errors else None,
        )
        details["analysis"] = {
            "selected_count": analysis_result.selected_count,
            "failed_count": analysis_result.failed_count,
            "skipped_count": analysis_result.skipped_count,
        }
    except Exception as exc:  # noqa: BLE001
        mark_analyze_result(success=False, error_text=str(exc))
        errors.append(f"analysis_failed: {exc}")

    try:
        sent_review_result = review_pending_sent(db, runtime_settings)
        errors.extend(sent_review_result.errors)
        details["sent_review"] = {
            "selected_count": sent_review_result.selected_count,
            "reviewed_count": sent_review_result.reviewed_count,
            "failed_count": sent_review_result.failed_count,
        }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"sent_review_failed: {exc}")

    return ManualScanResponse(
        imported_count=imported_count,
        analyzed_count=analyzed_count,
        errors=errors,
        details=details,
    )


@router.get("/api/preferences", response_model=PreferenceProfileResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> PreferenceProfileResponse:
    return PreferenceProfileResponse(**get_preference_profile(db))


@router.post("/api/preferences/rebuild", response_model=PreferenceProfileResponse)
def rebuild_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> PreferenceProfileResponse:
    profile = rebuild_preference_profile(db)
    return PreferenceProfileResponse(**profile)


@router.get("/api/rules", response_model=list[AutomationRule])
def get_rules(current_user: User = Depends(require_permission("read"))) -> list[dict]:
    return list_rules()


@router.post("/api/rules", response_model=AutomationRule)
def create_automation_rule(
    request: AutomationRuleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rules")),
) -> dict:
    rule = create_rule(request.model_dump())
    db.add(
        ActionLog(
            action_type="rule_created",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps(rule, ensure_ascii=False),
        )
    )
    db.commit()
    return rule


@router.put("/api/rules/{rule_id}", response_model=AutomationRule)
def update_automation_rule(
    rule_id: str,
    request: AutomationRuleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rules")),
) -> dict:
    rule = update_rule(rule_id, request.model_dump(exclude_none=True))
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.add(
        ActionLog(
            action_type="rule_updated",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps(rule, ensure_ascii=False),
        )
    )
    db.commit()
    return rule


@router.delete("/api/rules/{rule_id}", response_model=OperationStatusResponse)
def delete_automation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rules")),
) -> OperationStatusResponse:
    deleted = delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.add(
        ActionLog(
            action_type="rule_deleted",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps({"rule_id": rule_id}, ensure_ascii=False),
        )
    )
    db.commit()
    return OperationStatusResponse()


@router.post("/api/rules/reorder", response_model=list[AutomationRule])
def reorder_automation_rules(
    request: AutomationRuleReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rules")),
) -> list[dict]:
    rules = reorder_rules([item.model_dump() for item in request.items])
    db.add(
        ActionLog(
            action_type="rule_updated",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps({"reordered_ids": [item.id for item in request.items]}, ensure_ascii=False),
        )
    )
    db.commit()
    return rules


@router.get("/api/spam", response_model=list[EmailListItem])
def get_spam_log(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    mailbox_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> list:
    return list_spam_emails(db, limit=limit, offset=offset, mailbox_id=mailbox_id)


@router.get("/api/sent/reviews", response_model=list[EmailListItem])
def get_sent_reviews(
    mailbox_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> list[EmailListItem]:
    orm_query = db.query(Email).filter(Email.direction.in_(SENT_DIRECTION_VALUES))
    if mailbox_id:
        orm_query = orm_query.filter(Email.mailbox_id == mailbox_id)
    if status:
        orm_query = orm_query.filter(Email.sent_review_status == status)
    else:
        orm_query = orm_query.filter(Email.sent_review_status.is_not(None))
    return (
        orm_query.order_by(Email.sent_reviewed_at.desc().nullslast(), Email.date_received.desc().nullslast(), Email.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/api/sent/review/run", response_model=SentReviewRunResponse)
def run_sent_review_batch(
    limit: int | None = Query(default=None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("run_sent_review")),
) -> SentReviewRunResponse:
    summary = review_pending_sent(db, get_effective_settings(), limit=limit)
    return SentReviewRunResponse(
        selected_count=summary.selected_count,
        reviewed_count=summary.reviewed_count,
        failed_count=summary.failed_count,
        errors=summary.errors,
    )


@router.get("/api/attachments/{attachment_id}/download")
def download_attachment_by_id(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
):
    attachment = get_attachment(db, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        file_path, _, media_type, headers = build_attachment_download_payload(attachment)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment file missing")
    db.add(
        ActionLog(
            email_id=attachment.email_id,
            action_type="attachment_downloaded",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps({"attachment_id": attachment.id, "filename": attachment.filename}, ensure_ascii=False),
        )
    )
    db.commit()
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers=headers,
    )


@router.get("/api/templates", response_model=list[MessageTemplate])
def get_templates(
    language: str | None = Query(default=None),
    current_user: User = Depends(require_permission("read")),
) -> list[dict]:
    return list_templates(language=language)


@router.post("/api/templates", response_model=MessageTemplate)
def create_message_template(
    request: MessageTemplateCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_settings")),
) -> dict:
    template = create_template(request.model_dump())
    db.add(
        ActionLog(
            action_type="template_created",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps(template, ensure_ascii=False),
        )
    )
    db.commit()
    return template


@router.put("/api/templates/{template_id}", response_model=MessageTemplate)
def update_message_template(
    template_id: str,
    request: MessageTemplateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_settings")),
) -> dict:
    template = update_template(template_id, request.model_dump(exclude_none=True))
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    db.add(
        ActionLog(
            action_type="template_updated",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps(template, ensure_ascii=False),
        )
    )
    db.commit()
    return template


@router.delete("/api/templates/{template_id}", response_model=OperationStatusResponse)
def delete_message_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_settings")),
) -> OperationStatusResponse:
    deleted = delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    db.add(
        ActionLog(
            action_type="template_deleted",
            user_id=current_user.id,
            actor=current_user.email,
            details_json=json.dumps({"template_id": template_id}, ensure_ascii=False),
        )
    )
    db.commit()
    return OperationStatusResponse()
