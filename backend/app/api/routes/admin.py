import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import open_global_session
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import (
    AdminHealthResponse,
    AdminJobsResponse,
    AdminMailboxStatusResponse,
    BackupCreateRequest,
    BackupCreateResponse,
    BackupItem,
    BackupRestoreRequest,
    BackupRestoreResponse,
    BackupStatusResponse,
)
from app.services.backup_service import create_backup, get_backup_status, list_backups, restore_backup
from app.services.diagnostics_service import (
    collect_admin_health,
    collect_mailbox_statuses,
    mark_backup_result,
    mark_restore_result,
    read_ops_status,
)
from app.services.permission_service import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/backups", response_model=list[BackupItem])
def get_backups(current_user: User = Depends(require_admin())) -> list[BackupItem]:
    backups = [BackupItem(**item) for item in list_backups()]
    _log_admin_action(current_user, "diagnostics_checked", {"target": "backups", "count": len(backups)})
    return backups


@router.post("/backups/create", response_model=BackupCreateResponse)
def create_backup_route(
    request: BackupCreateRequest,
    current_user: User = Depends(require_admin()),
) -> BackupCreateResponse:
    try:
        result = create_backup(include_attachments=request.include_attachments, keep_last=request.keep_last, reason="admin_api")
        mark_backup_result(
            success=True,
            backup_name=result.backup_name,
            backup_path=result.backup_path,
            size_bytes=result.size_bytes,
            include_attachments=result.include_attachments,
        )
        _log_admin_action(
            current_user,
            "backup_created",
            {
                "backup_name": result.backup_name,
                "backup_path": result.backup_path,
                "include_attachments": result.include_attachments,
                "size_bytes": result.size_bytes,
                "pruned_backups": result.pruned_backups,
            },
        )
        return BackupCreateResponse(
            backup_name=result.backup_name,
            backup_path=result.backup_path,
            include_attachments=result.include_attachments,
            size_bytes=result.size_bytes,
            pruned_backups=result.pruned_backups,
        )
    except Exception as exc:  # noqa: BLE001
        mark_backup_result(success=False, error_text=str(exc))
        _log_admin_action(current_user, "backup_failed", {"error": str(exc)})
        raise HTTPException(status_code=400, detail=f"Backup creation failed: {exc}") from exc


@router.post("/backups/restore", response_model=BackupRestoreResponse)
def restore_backup_route(
    request: BackupRestoreRequest,
    current_user: User = Depends(require_admin()),
) -> BackupRestoreResponse:
    _log_admin_action(
        current_user,
        "restore_started",
        {"backup_name": request.backup_name, "restore_attachments": request.restore_attachments},
    )
    try:
        result = restore_backup(
            backup_name=request.backup_name,
            confirmation=request.confirmation,
            restore_attachments=request.restore_attachments,
            create_safety_backup=True,
        )
        mark_restore_result(success=True, backup_name=result.backup_name)
        _log_admin_action(
            current_user,
            "restore_completed",
            {
                "backup_name": result.backup_name,
                "restored_database": result.restored_database,
                "restored_config_files": result.restored_config_files,
                "restored_attachments": result.restored_attachments,
                "safety_backup_name": result.safety_backup_name,
            },
        )
        return BackupRestoreResponse(
            backup_name=result.backup_name,
            restored_database=result.restored_database,
            restored_config_files=result.restored_config_files,
            restored_attachments=result.restored_attachments,
            safety_backup_name=result.safety_backup_name,
        )
    except Exception as exc:  # noqa: BLE001
        mark_restore_result(success=False, backup_name=request.backup_name, error_text=str(exc))
        _log_admin_action(
            current_user,
            "restore_failed",
            {"backup_name": request.backup_name, "error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=f"Restore failed: {exc}") from exc


@router.get("/backups/status", response_model=BackupStatusResponse)
def get_backups_status(current_user: User = Depends(require_admin())) -> BackupStatusResponse:
    payload = get_backup_status()
    latest = payload.get("latest_backup")
    response = BackupStatusResponse(
        backups_count=payload.get("backups_count", 0),
        latest_backup=BackupItem(**latest) if isinstance(latest, dict) else None,
        backup_dir=payload.get("backup_dir", ""),
    )
    _log_admin_action(current_user, "diagnostics_checked", {"target": "backups_status"})
    return response


@router.get("/health", response_model=AdminHealthResponse)
def get_admin_health(
    test_mailboxes: bool = Query(default=False),
    current_user: User = Depends(require_admin()),
) -> AdminHealthResponse:
    db = open_global_session()
    try:
        diagnostics = collect_admin_health(
            db_session=db,
            scheduler_running=None,
            test_mailboxes=test_mailboxes,
        )
    finally:
        db.close()
    _log_admin_action(current_user, "diagnostics_checked", {"target": "health", "test_mailboxes": test_mailboxes})
    return AdminHealthResponse(**diagnostics)


@router.get("/diagnostics", response_model=AdminHealthResponse)
def get_admin_diagnostics(
    test_mailboxes: bool = Query(default=False),
    current_user: User = Depends(require_admin()),
) -> AdminHealthResponse:
    db = open_global_session()
    try:
        diagnostics = collect_admin_health(
            db_session=db,
            scheduler_running=None,
            test_mailboxes=test_mailboxes,
        )
    finally:
        db.close()
    _log_admin_action(current_user, "diagnostics_checked", {"target": "diagnostics", "test_mailboxes": test_mailboxes})
    return AdminHealthResponse(**diagnostics)


@router.get("/jobs", response_model=AdminJobsResponse)
def get_admin_jobs(current_user: User = Depends(require_admin())) -> AdminJobsResponse:
    status = read_ops_status()
    _log_admin_action(current_user, "diagnostics_checked", {"target": "jobs"})
    return AdminJobsResponse(
        scheduler=status.get("scheduler", {}),
        scan=status.get("scan", {}),
        analyze=status.get("analyze", {}),
        backup=status.get("backup", {}),
        restore=status.get("restore", {}),
    )


@router.get("/mailboxes/status", response_model=list[AdminMailboxStatusResponse])
def get_admin_mailboxes_status(
    test_connection: bool = Query(default=False),
    current_user: User = Depends(require_admin()),
) -> list[AdminMailboxStatusResponse]:
    statuses = [AdminMailboxStatusResponse(**item) for item in collect_mailbox_statuses(test_connection=test_connection)]
    failed = [item.mailbox_id for item in statuses if item.connection_ok is False]
    if failed:
        _log_admin_action(current_user, "mailbox_health_check_failed", {"failed_mailboxes": failed})
    _log_admin_action(current_user, "diagnostics_checked", {"target": "mailboxes_status", "test_connection": test_connection})
    return statuses


def _log_admin_action(user: User, action_type: str, payload: dict) -> None:
    db = open_global_session()
    try:
        db.add(
            ActionLog(
                user_id=user.id,
                action_type=action_type,
                actor=user.email,
                details_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.commit()
    finally:
        db.close()
