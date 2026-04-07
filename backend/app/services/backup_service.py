import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_effective_settings
from app.db import dispose_database_engines
from app.services.diagnostics_service import backend_paths

BACKUP_KEEP_DEFAULT = 10
BACKUP_CONFIG_FILES = [
    "rules.json",
    "templates.json",
    "preference_profile.json",
    "digest_state.json",
]


@dataclass(slots=True)
class BackupCreateResult:
    backup_name: str
    backup_path: str
    include_attachments: bool
    size_bytes: int
    manifest: dict[str, Any]
    pruned_backups: list[str]


@dataclass(slots=True)
class BackupRestoreResult:
    backup_name: str
    restored_database: bool
    restored_config_files: list[str]
    restored_attachments: bool
    safety_backup_name: str | None


def list_backups() -> list[dict[str, Any]]:
    paths = backend_paths(get_effective_settings().database_url)
    backups_dir = paths.backups_dir
    if not backups_dir.exists():
        return []

    result: list[dict[str, Any]] = []
    for item in sorted(backups_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not item.is_dir():
            continue
        manifest_path = item / "manifest.json"
        manifest = _read_manifest(manifest_path)
        size_bytes = _dir_size_bytes(item)
        result.append(
            {
                "backup_name": item.name,
                "created_at": manifest.get("created_at"),
                "include_attachments": bool(manifest.get("include_attachments", False)),
                "size_bytes": size_bytes,
                "path": str(item),
                "manifest": manifest,
            }
        )
    return result


def create_backup(
    *,
    include_attachments: bool = False,
    keep_last: int = BACKUP_KEEP_DEFAULT,
    reason: str = "manual",
) -> BackupCreateResult:
    settings = get_effective_settings()
    paths = backend_paths(settings.database_url)
    paths.backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_dir = paths.backups_dir / backup_name
    backup_dir.mkdir(parents=True, exist_ok=False)

    db_source = paths.database_path
    db_target = backup_dir / "mail_agent.db"
    if db_source.exists():
        shutil.copy2(db_source, db_target)

    config_target = backup_dir / "config"
    config_target.mkdir(parents=True, exist_ok=True)
    restored_files: list[str] = []
    for filename in BACKUP_CONFIG_FILES:
        source_path = paths.data_dir / filename
        if source_path.exists():
            shutil.copy2(source_path, config_target / filename)
            restored_files.append(filename)

    account_db_ids: list[str] = []
    if paths.account_dbs_dir.exists():
        account_db_ids = sorted(
            item.name
            for item in paths.account_dbs_dir.iterdir()
            if item.is_dir() and (item / "mail_agent.db").exists()
        )
        if account_db_ids:
            shutil.copytree(paths.account_dbs_dir, backup_dir / "account_dbs")

    attachments_copied = False
    if include_attachments and paths.attachments_dir.exists():
        shutil.copytree(paths.attachments_dir, backup_dir / "attachments")
        attachments_copied = True

    manifest = {
        "backup_name": backup_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "database_file": db_target.name if db_target.exists() else None,
        "account_db_ids": account_db_ids,
        "config_files": restored_files,
        "include_attachments": attachments_copied,
        "app_env": getattr(settings, "app_env", "development"),
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    size_bytes = _dir_size_bytes(backup_dir)
    pruned = _apply_retention(paths.backups_dir, keep_last=max(1, int(keep_last)))
    return BackupCreateResult(
        backup_name=backup_name,
        backup_path=str(backup_dir),
        include_attachments=attachments_copied,
        size_bytes=size_bytes,
        manifest=manifest,
        pruned_backups=pruned,
    )


def restore_backup(
    *,
    backup_name: str,
    confirmation: str,
    restore_attachments: bool = False,
    create_safety_backup: bool = True,
) -> BackupRestoreResult:
    settings = get_effective_settings()
    paths = backend_paths(settings.database_url)
    backup_dir = paths.backups_dir / backup_name
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise ValueError("Backup not found")

    expected_confirmation = f"RESTORE {backup_name}"
    if confirmation.strip() != expected_confirmation:
        raise ValueError(f"Confirmation mismatch. Use exactly: {expected_confirmation}")

    safety_backup_name: str | None = None
    if create_safety_backup:
        safety = create_backup(include_attachments=False, keep_last=BACKUP_KEEP_DEFAULT, reason=f"pre_restore:{backup_name}")
        safety_backup_name = safety.backup_name

    dispose_database_engines()

    db_source = backup_dir / "mail_agent.db"
    restored_db = False
    if db_source.exists():
        paths.database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_source, paths.database_path)
        restored_db = True

    account_dbs_source = backup_dir / "account_dbs"
    if account_dbs_source.exists():
        if paths.account_dbs_dir.exists():
            shutil.rmtree(paths.account_dbs_dir)
        shutil.copytree(account_dbs_source, paths.account_dbs_dir)
        restored_db = True

    restored_configs: list[str] = []
    config_source = backup_dir / "config"
    if config_source.exists():
        for item in config_source.iterdir():
            if item.is_file():
                shutil.copy2(item, paths.data_dir / item.name)
                restored_configs.append(item.name)

    restored_attachments = False
    attachments_source = backup_dir / "attachments"
    if restore_attachments and attachments_source.exists():
        if paths.attachments_dir.exists():
            shutil.rmtree(paths.attachments_dir)
        shutil.copytree(attachments_source, paths.attachments_dir)
        restored_attachments = True

    return BackupRestoreResult(
        backup_name=backup_name,
        restored_database=restored_db,
        restored_config_files=sorted(restored_configs),
        restored_attachments=restored_attachments,
        safety_backup_name=safety_backup_name,
    )


def get_backup_status() -> dict[str, Any]:
    backups = list_backups()
    latest = backups[0] if backups else None
    return {
        "backups_count": len(backups),
        "latest_backup": latest,
        "backup_dir": str(backend_paths(get_effective_settings().database_url).backups_dir),
    }


def _apply_retention(backups_dir: Path, keep_last: int) -> list[str]:
    removed: list[str] = []
    candidates = [item for item in sorted(backups_dir.iterdir(), key=lambda p: p.name, reverse=True) if item.is_dir()]
    for stale in candidates[keep_last:]:
        shutil.rmtree(stale, ignore_errors=True)
        removed.append(stale.name)
    return removed


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
