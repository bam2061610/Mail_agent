import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_safe_settings_view, save_runtime_settings
from app.db import open_account_session, open_global_session
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import (
    MailboxCreateRequest,
    MailboxResponse,
    MailboxUpdateRequest,
    OperationStatusResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from app.services.imap_folder_service import ensure_folders
from app.services.imap_scanner import connect_imap, scan_inbox
from app.services.mailbox_service import (
    create_mailbox,
    delete_mailbox,
    get_mailbox,
    list_mailboxes,
    to_runtime_mailbox,
    update_mailbox,
)
from app.services.permission_service import require_permission
from app.services.smtp_sender import test_smtp_connection

router = APIRouter(prefix="/api", tags=["settings"])
logger = logging.getLogger(__name__)


@router.get("/settings", response_model=SettingsResponse)
def get_settings(current_user: User = Depends(require_permission("read"))) -> SettingsResponse:
    return SettingsResponse(**get_safe_settings_view())


@router.post("/settings", response_model=SettingsResponse)
def update_settings(
    request: SettingsUpdateRequest,
    current_user: User = Depends(require_permission("manage_settings")),
) -> SettingsResponse:
    save_runtime_settings(request.model_dump(exclude_none=True))
    _log_mailbox_action("settings_updated", {"updated_keys": list(request.model_dump(exclude_none=True).keys())}, current_user)
    return SettingsResponse(**get_safe_settings_view())


@router.get("/mailboxes", response_model=list[MailboxResponse])
def get_mailboxes(current_user: User = Depends(require_permission("read"))) -> list[MailboxResponse]:
    return [MailboxResponse(**item) for item in list_mailboxes(redact_secrets=True)]


@router.post("/mailboxes", response_model=MailboxResponse)
def create_mailbox_route(
    request: MailboxCreateRequest,
    current_user: User = Depends(require_permission("manage_mailboxes")),
) -> MailboxResponse:
    payload = create_mailbox(request.model_dump())
    _log_mailbox_action("mailbox_created", payload, current_user)
    return MailboxResponse(**payload)


@router.put("/mailboxes/{mailbox_id}", response_model=MailboxResponse)
def update_mailbox_route(
    mailbox_id: str,
    request: MailboxUpdateRequest,
    current_user: User = Depends(require_permission("manage_mailboxes")),
) -> MailboxResponse:
    payload = update_mailbox(mailbox_id, request.model_dump(exclude_none=True))
    if payload is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    _log_mailbox_action("mailbox_updated", payload, current_user)
    return MailboxResponse(**payload)


@router.delete("/mailboxes/{mailbox_id}", response_model=OperationStatusResponse)
def delete_mailbox_route(
    mailbox_id: str,
    current_user: User = Depends(require_permission("manage_mailboxes")),
) -> OperationStatusResponse:
    deleted = delete_mailbox(mailbox_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    _log_mailbox_action("mailbox_deleted", {"mailbox_id": mailbox_id}, current_user)
    return OperationStatusResponse()


@router.post("/mailboxes/{mailbox_id}/test-connection", response_model=OperationStatusResponse)
def test_mailbox_connection(
    mailbox_id: str,
    current_user: User = Depends(require_permission("manage_mailboxes")),
) -> OperationStatusResponse:
    mailbox = get_mailbox(mailbox_id, redact_secrets=False)
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    runtime_mailbox = to_runtime_mailbox(mailbox)
    connection = None
    try:
        connection = connect_imap(runtime_mailbox)
        status, _ = connection.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("INBOX select failed")
        ensure_folders(runtime_mailbox)
        test_smtp_connection(runtime_mailbox)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Connection test failed: {exc}") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                logger.warning("Mailbox IMAP close failed during connection test", exc_info=True)
            try:
                connection.logout()
            except Exception:  # noqa: BLE001
                logger.warning("Mailbox IMAP logout failed during connection test", exc_info=True)
    return OperationStatusResponse()


@router.post("/mailboxes/{mailbox_id}/scan", response_model=OperationStatusResponse)
def scan_single_mailbox(
    mailbox_id: str,
    current_user: User = Depends(require_permission("run_scan")),
) -> OperationStatusResponse:
    mailbox = get_mailbox(mailbox_id, redact_secrets=False)
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    db = open_account_session(mailbox_id)
    try:
        result = scan_inbox(db, to_runtime_mailbox(mailbox))
        _log_mailbox_action(
            "mailbox_scan_finished",
            {
                "mailbox_id": mailbox_id,
                "created_count": result.created_count,
                "skipped_count": result.skipped_count,
                "errors_count": len(result.errors),
            },
            current_user,
        )
    finally:
        db.close()
    return OperationStatusResponse()


def _log_mailbox_action(action_type: str, payload: dict, user: User | None = None) -> None:
    db = open_global_session()
    try:
        db.add(
            ActionLog(
                user_id=user.id if user else None,
                action_type=action_type,
                actor=user.email if user else "user",
                details_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.commit()
    finally:
        db.close()
