from dataclasses import asdict

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.action_log import ActionLog
from app.schemas.email import EmailListItem, WaitingThreadItem
from app.schemas.system import (
    AutomationRule,
    AutomationRuleCreateRequest,
    AutomationRuleReorderRequest,
    AutomationRuleUpdateRequest,
    ManualScanResponse,
    OperationStatusResponse,
    PreferenceProfileResponse,
)
from app.services.ai_analyzer import analyze_pending
from app.services.followup_tracker import get_waiting_threads
from app.services.imap_scanner import scan_inbox
from app.services.preference_profile import get_preference_profile, rebuild_preference_profile
from app.services.rule_engine import create_rule, delete_rule, list_rules, reorder_rules, update_rule
from app.services.spam_service import list_spam_emails

router = APIRouter(tags=["actions"])


@router.post("/api/scan", response_model=ManualScanResponse)
def manual_scan(db: Session = Depends(get_db)) -> ManualScanResponse:
    runtime_settings = get_effective_settings()
    imported_count = 0
    analyzed_count = 0
    errors: list[str] = []
    details: dict[str, dict[str, int]] = {}

    try:
        scan_result = scan_inbox(db, runtime_settings)
        imported_count = scan_result.created_count
        errors.extend(scan_result.errors)
        details["scan"] = {
            "scanned_messages": scan_result.scanned_messages,
            "fetched_messages": scan_result.fetched_messages,
            "skipped_count": scan_result.skipped_count,
        }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"scan_failed: {exc}")

    try:
        analysis_result = analyze_pending(db, runtime_settings)
        analyzed_count = analysis_result.analyzed_count
        errors.extend(analysis_result.errors)
        details["analysis"] = {
            "selected_count": analysis_result.selected_count,
            "failed_count": analysis_result.failed_count,
            "skipped_count": analysis_result.skipped_count,
        }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"analysis_failed: {exc}")

    return ManualScanResponse(
        imported_count=imported_count,
        analyzed_count=analyzed_count,
        errors=errors,
        details=details,
    )


@router.get("/api/followups", response_model=list[WaitingThreadItem])
def list_followups(db: Session = Depends(get_db)) -> list[WaitingThreadItem]:
    return [WaitingThreadItem(**asdict(item)) for item in get_waiting_threads(db)]


@router.get("/api/preferences", response_model=PreferenceProfileResponse)
def get_preferences(db: Session = Depends(get_db)) -> PreferenceProfileResponse:
    return PreferenceProfileResponse(**get_preference_profile(db))


@router.post("/api/preferences/rebuild", response_model=PreferenceProfileResponse)
def rebuild_preferences(db: Session = Depends(get_db)) -> PreferenceProfileResponse:
    profile = rebuild_preference_profile(db)
    return PreferenceProfileResponse(**profile)


@router.get("/api/rules", response_model=list[AutomationRule])
def get_rules() -> list[dict]:
    return list_rules()


@router.post("/api/rules", response_model=AutomationRule)
def create_automation_rule(request: AutomationRuleCreateRequest, db: Session = Depends(get_db)) -> dict:
    rule = create_rule(request.model_dump())
    db.add(
        ActionLog(
            action_type="rule_created",
            actor="user",
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
) -> dict:
    rule = update_rule(rule_id, request.model_dump(exclude_none=True))
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.add(
        ActionLog(
            action_type="rule_updated",
            actor="user",
            details_json=json.dumps(rule, ensure_ascii=False),
        )
    )
    db.commit()
    return rule


@router.delete("/api/rules/{rule_id}", response_model=OperationStatusResponse)
def delete_automation_rule(rule_id: str, db: Session = Depends(get_db)) -> OperationStatusResponse:
    deleted = delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.add(
        ActionLog(
            action_type="rule_deleted",
            actor="user",
            details_json=json.dumps({"rule_id": rule_id}, ensure_ascii=False),
        )
    )
    db.commit()
    return OperationStatusResponse()


@router.post("/api/rules/reorder", response_model=list[AutomationRule])
def reorder_automation_rules(
    request: AutomationRuleReorderRequest,
    db: Session = Depends(get_db),
) -> list[dict]:
    rules = reorder_rules([item.model_dump() for item in request.items])
    db.add(
        ActionLog(
            action_type="rule_updated",
            actor="user",
            details_json=json.dumps({"reordered_ids": [item.id for item in request.items]}, ensure_ascii=False),
        )
    )
    db.commit()
    return rules


@router.get("/api/spam", response_model=list[EmailListItem])
def get_spam_log(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list:
    return list_spam_emails(db, limit=limit, offset=offset)
