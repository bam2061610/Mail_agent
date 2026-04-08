import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import list_account_database_ids, open_account_session
from app.models.email import Email
from app.services.mailbox_service import get_enabled_mailbox_configs, list_mailboxes

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
BACKUPS_DIR = DATA_DIR / "backups"
OPS_STATUS_FILE_PATH = DATA_DIR / "ops_status.json"


def read_ops_status() -> dict[str, Any]:
    if not OPS_STATUS_FILE_PATH.exists():
        return _default_status()
    try:
        payload = json.loads(OPS_STATUS_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_status()
    if not isinstance(payload, dict):
        return _default_status()
    merged = _default_status()
    merged.update(payload)
    return merged


def write_ops_status(payload: dict[str, Any]) -> dict[str, Any]:
    OPS_STATUS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPS_STATUS_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def update_ops_status(updater) -> dict[str, Any]:
    payload = read_ops_status()
    updated = updater(payload) or payload
    return write_ops_status(updated)


def mark_scheduler_started() -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        scheduler = payload.setdefault("scheduler", {})
        scheduler["running"] = True
        scheduler["last_started_at"] = now
        return payload

    update_ops_status(_update)


def mark_scheduler_stopped() -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        scheduler = payload.setdefault("scheduler", {})
        scheduler["running"] = False
        scheduler["last_stopped_at"] = now
        return payload

    update_ops_status(_update)


def mark_scheduler_job_started() -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        scheduler = payload.setdefault("scheduler", {})
        scheduler["last_job_started_at"] = now
        return payload

    update_ops_status(_update)


def mark_scheduler_job_finished(result: dict[str, Any], success: bool, error_text: str | None = None) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        scheduler = payload.setdefault("scheduler", {})
        scheduler["last_job_finished_at"] = now
        scheduler["last_job_result"] = result
        if success:
            scheduler["last_job_success_at"] = now
            scheduler["last_job_error"] = None
        else:
            scheduler["last_job_failure_at"] = now
            scheduler["last_job_error"] = error_text
        return payload

    update_ops_status(_update)


def mark_scan_result(
    *,
    success: bool,
    imported_count: int = 0,
    skipped_count: int = 0,
    errors_count: int = 0,
    error_text: str | None = None,
) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        scan = payload.setdefault("scan", {})
        scan["last_result"] = {
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "errors_count": errors_count,
        }
        if success:
            scan["last_success_at"] = now
            scan["last_error"] = None
        else:
            scan["last_failure_at"] = now
            scan["last_error"] = error_text
        return payload

    update_ops_status(_update)


def mark_mailbox_scan_result(
    *,
    mailbox_id: str,
    mailbox_name: str,
    success: bool,
    created_count: int = 0,
    skipped_count: int = 0,
    errors_count: int = 0,
    error_text: str | None = None,
) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        mailboxes = payload.setdefault("mailboxes", {})
        mailbox_state = mailboxes.setdefault(mailbox_id, {})
        mailbox_state["mailbox_name"] = mailbox_name
        mailbox_state["checked_at"] = now
        mailbox_state["last_result"] = {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "errors_count": errors_count,
        }
        if success:
            mailbox_state["last_success_at"] = now
            mailbox_state["last_error"] = None
        else:
            mailbox_state["last_failure_at"] = now
            mailbox_state["last_error"] = error_text
        return payload

    update_ops_status(_update)


def mark_analyze_result(
    *,
    success: bool,
    analyzed_count: int = 0,
    failed_count: int = 0,
    skipped_count: int = 0,
    error_text: str | None = None,
) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        analyze = payload.setdefault("analyze", {})
        analyze["last_result"] = {
            "analyzed_count": analyzed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }
        if success:
            analyze["last_success_at"] = now
            analyze["last_error"] = None
        else:
            analyze["last_failure_at"] = now
            analyze["last_error"] = error_text
        return payload

    update_ops_status(_update)


def mark_backup_result(
    *,
    success: bool,
    backup_name: str | None = None,
    backup_path: str | None = None,
    size_bytes: int | None = None,
    include_attachments: bool | None = None,
    error_text: str | None = None,
) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        backup = payload.setdefault("backup", {})
        if success:
            backup["last_success_at"] = now
            backup["last_error"] = None
            backup["last_backup"] = {
                "name": backup_name,
                "path": backup_path,
                "size_bytes": size_bytes,
                "include_attachments": include_attachments,
            }
        else:
            backup["last_failure_at"] = now
            backup["last_error"] = error_text
        return payload

    update_ops_status(_update)


def mark_restore_result(
    *,
    success: bool,
    backup_name: str | None = None,
    error_text: str | None = None,
) -> None:
    now = _now_iso()

    def _update(payload: dict[str, Any]) -> dict[str, Any]:
        restore = payload.setdefault("restore", {})
        if success:
            restore["last_success_at"] = now
            restore["last_error"] = None
            restore["last_restore"] = {"name": backup_name}
        else:
            restore["last_failure_at"] = now
            restore["last_error"] = error_text
        return payload

    update_ops_status(_update)


def collect_mailbox_statuses(test_connection: bool = False) -> list[dict[str, Any]]:
    status_payload = read_ops_status()
    stored_mailboxes = status_payload.get("mailboxes", {})
    configured = list_mailboxes(redact_secrets=False)
    runtime_by_id = {item.id: item for item in get_enabled_mailbox_configs()}
    results: list[dict[str, Any]] = []

    for mailbox in configured:
        mailbox_id = str(mailbox.get("id") or "")
        mailbox_name = str(mailbox.get("name") or mailbox.get("email_address") or mailbox_id)
        stored = stored_mailboxes.get(mailbox_id, {})
        item = {
            "mailbox_id": mailbox_id,
            "mailbox_name": mailbox_name,
            "email_address": mailbox.get("email_address"),
            "enabled": bool(mailbox.get("enabled", True)),
            "last_checked_at": stored.get("checked_at"),
            "last_success_at": stored.get("last_success_at"),
            "last_failure_at": stored.get("last_failure_at"),
            "last_error": stored.get("last_error"),
            "last_result": stored.get("last_result"),
            "connection_ok": None,
            "connection_error": None,
        }
        if test_connection and mailbox_id in runtime_by_id and item["enabled"]:
            try:
                from app.services.imap_scanner import connect_imap

                connection = connect_imap(runtime_by_id[mailbox_id])
                status, _ = connection.select("INBOX", readonly=True)
                if status != "OK":
                    raise RuntimeError("INBOX select failed")
                try:
                    connection.close()
                except Exception:
                    pass
                connection.logout()
                item["connection_ok"] = True
            except Exception as exc:  # noqa: BLE001
                item["connection_ok"] = False
                item["connection_error"] = str(exc)
        results.append(item)
    return results


def collect_admin_health(
    db_session: Session,
    scheduler_running: bool | None = None,
    *,
    test_mailboxes: bool = False,
) -> dict[str, Any]:
    settings = get_effective_settings()
    status_payload = read_ops_status()
    scheduler_state = status_payload.get("scheduler", {})
    scan_state = status_payload.get("scan", {})
    analyze_state = status_payload.get("analyze", {})
    backup_state = status_payload.get("backup", {})
    restore_state = status_payload.get("restore", {})
    db_status = _check_db_access(db_session)
    mailbox_statuses = collect_mailbox_statuses(test_connection=test_mailboxes)

    smtp_ready = bool(getattr(settings, "smtp_host", None) and getattr(settings, "smtp_user", None))
    ai_ready = bool(getattr(settings, "deepseek_api_key", None) or getattr(settings, "openai_api_key", None))
    enabled_mailboxes = [item for item in mailbox_statuses if item.get("enabled")]
    any_mailbox_failure = any(item.get("last_failure_at") for item in enabled_mailboxes)

    now = datetime.now(timezone.utc)
    last_scan_ok = _parse_iso(scan_state.get("last_success_at"))
    last_analyze_ok = _parse_iso(analyze_state.get("last_success_at"))
    scheduler_interval = int(getattr(settings, "scheduler_interval_minutes", getattr(settings, "scan_interval_minutes", 5)))
    stale_scan = bool(last_scan_ok and (now - last_scan_ok).total_seconds() > max(3600, scheduler_interval * 180))
    stale_analyze = bool(last_analyze_ok and (now - last_analyze_ok).total_seconds() > max(3600, scheduler_interval * 180))

    overall_ok = db_status["ok"] and smtp_ready and ai_ready and not stale_scan and not stale_analyze and not any_mailbox_failure
    scheduler_effective_running = scheduler_running if scheduler_running is not None else bool(scheduler_state.get("running", False))

    attachments_usage = _collect_dir_usage(ATTACHMENTS_DIR)
    backups_usage = _collect_dir_usage(BACKUPS_DIR)
    account_dbs_usage = _collect_dir_usage(backend_paths(settings.database_url).account_dbs_dir)

    last_sent_at = _collect_last_sent_at()

    return {
        "overall_status": "ok" if overall_ok else "degraded",
        "server_time": _now_iso(),
        "app_env": getattr(settings, "app_env", "development"),
        "components": {
            "api": {"ok": True},
            "db": db_status,
            "scheduler": {
                "ok": scheduler_effective_running,
                "running": scheduler_effective_running,
                "last_started_at": scheduler_state.get("last_started_at"),
                "last_stopped_at": scheduler_state.get("last_stopped_at"),
                "last_job_started_at": scheduler_state.get("last_job_started_at"),
                "last_job_finished_at": scheduler_state.get("last_job_finished_at"),
                "last_job_success_at": scheduler_state.get("last_job_success_at"),
                "last_job_failure_at": scheduler_state.get("last_job_failure_at"),
                "last_job_error": scheduler_state.get("last_job_error"),
            },
            "imap_scan": {
                "ok": bool(scan_state.get("last_success_at")) and not stale_scan,
                "last_success_at": scan_state.get("last_success_at"),
                "last_failure_at": scan_state.get("last_failure_at"),
                "last_error": scan_state.get("last_error"),
                "last_result": scan_state.get("last_result"),
            },
            "ai_analyzer": {
                "ok": ai_ready and bool(analyze_state.get("last_success_at")) and not stale_analyze,
                "configured": ai_ready,
                "last_success_at": analyze_state.get("last_success_at"),
                "last_failure_at": analyze_state.get("last_failure_at"),
                "last_error": analyze_state.get("last_error"),
                "last_result": analyze_state.get("last_result"),
            },
            "smtp": {
                "ok": smtp_ready,
                "configured": smtp_ready,
                "last_sent_at": last_sent_at.isoformat() if last_sent_at else None,
            },
            "backup": {
                "ok": bool(backup_state.get("last_success_at")),
                "last_success_at": backup_state.get("last_success_at"),
                "last_failure_at": backup_state.get("last_failure_at"),
                "last_error": backup_state.get("last_error"),
                "last_backup": backup_state.get("last_backup"),
            },
            "restore": {
                "ok": not bool(restore_state.get("last_error")),
                "last_success_at": restore_state.get("last_success_at"),
                "last_failure_at": restore_state.get("last_failure_at"),
                "last_error": restore_state.get("last_error"),
                "last_restore": restore_state.get("last_restore"),
            },
        },
        "mailboxes": mailbox_statuses,
        "storage": {
            "attachments": attachments_usage,
            "backups": backups_usage,
            "account_databases": account_dbs_usage,
            "disk": _collect_disk_usage(DATA_DIR),
        },
        "jobs": {
            "last_successful_scan_at": scan_state.get("last_success_at"),
            "last_failed_scan_at": scan_state.get("last_failure_at"),
            "last_analyze_at": analyze_state.get("last_success_at"),
            "last_sent_email_at": last_sent_at.isoformat() if last_sent_at else None,
            "last_backup_at": backup_state.get("last_success_at"),
            "last_restore_at": restore_state.get("last_success_at"),
            "scheduler_running": scheduler_effective_running,
        },
    }


def _default_status() -> dict[str, Any]:
    return {
        "scheduler": {"running": False},
        "scan": {},
        "analyze": {},
        "backup": {},
        "restore": {},
        "mailboxes": {},
    }


def _collect_dir_usage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "file_count": 0, "size_bytes": 0}
    file_count = 0
    total_size = 0
    for item in path.rglob("*"):
        if item.is_file():
            file_count += 1
            try:
                total_size += item.stat().st_size
            except OSError:
                pass
    return {"path": str(path), "exists": True, "file_count": file_count, "size_bytes": total_size}


def _collect_disk_usage(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {"path": str(path), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
    except OSError:
        return {"path": str(path), "total_bytes": None, "used_bytes": None, "free_bytes": None}


def _check_db_access(db_session: Session) -> dict[str, Any]:
    try:
        db_session.execute(text("SELECT 1"))
        return {"ok": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _collect_last_sent_at() -> datetime | None:
    latest: datetime | None = None
    for mailbox_id in list_account_database_ids():
        db_session = open_account_session(mailbox_id)
        try:
            candidate = db_session.query(func.max(Email.last_reply_sent_at)).scalar()
        except Exception:  # noqa: BLE001
            candidate = None
        finally:
            db_session.close()

        if candidate is None:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def backend_paths(database_url: str) -> SimpleNamespace:
    database_path = _resolve_sqlite_path(database_url)
    return SimpleNamespace(
        backend_dir=BACKEND_DIR,
        data_dir=DATA_DIR,
        database_path=database_path,
        account_dbs_dir=database_path.parent / "account_dbs",
        attachments_dir=ATTACHMENTS_DIR,
        backups_dir=BACKUPS_DIR,
    )


def _resolve_sqlite_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///./"):
        return BACKEND_DIR / database_url.removeprefix("sqlite:///./")
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    return BACKEND_DIR / "data" / "mail_agent.db"
