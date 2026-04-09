from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.runtime_setting import RuntimeSetting
from app.models.user import User

logger = logging.getLogger(__name__)

SECRET_SETTING_KEYS = {
    "imap_password",
    "smtp_password",
    "openai_api_key",
    "deepseek_api_key",
    "bootstrap_admin_password",
}
RUNTIME_SETTING_ALIASES = {
    "auto_spam_enabled": "ai_auto_spam_enabled",
    "scan_interval_minutes": "scheduler_interval_minutes",
}
KEY_VALUE_SETTING_KEYS = {
    "preference_profile",
}


def get_runtime_settings_row(db: Session, *, create: bool = False) -> RuntimeSetting | None:
    try:
        row = (
            db.execute(
                select(RuntimeSetting)
                .where(RuntimeSetting.key.is_(None))
                .order_by(RuntimeSetting.id.asc())
            )
            .scalars()
            .first()
        )
    except OperationalError:
        logger.warning(
            "Runtime settings table is on a legacy schema; using base settings only",
            exc_info=True,
        )
        return None
    if row is None and create:
        row = RuntimeSetting()
        db.add(row)
        db.flush()
    return row


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    normalized_key = key.strip()
    if not normalized_key:
        return default
    try:
        row = (
            db.execute(select(RuntimeSetting).where(RuntimeSetting.key == normalized_key))
            .scalar_one_or_none()
        )
    except OperationalError:
        logger.warning(
            "Runtime settings key/value store is unavailable on the current schema",
            exc_info=True,
        )
        return default
    if row is None or row.value_json is None:
        return default
    try:
        return json.loads(row.value_json)
    except json.JSONDecodeError:
        logger.warning("Runtime setting value is not valid JSON: key=%s", normalized_key, exc_info=True)
        return default


def set_setting(db: Session, key: str, value: Any) -> None:
    normalized_key = key.strip()
    if not normalized_key:
        raise ValueError("Runtime setting key is required")
    try:
        row = (
            db.execute(select(RuntimeSetting).where(RuntimeSetting.key == normalized_key))
            .scalar_one_or_none()
        )
    except OperationalError as exc:
        logger.warning(
            "Runtime settings key/value store is unavailable on the current schema",
            exc_info=True,
        )
        raise RuntimeError("Runtime settings schema is outdated; run database migrations") from exc
    if row is None:
        row = RuntimeSetting(key=normalized_key)
        db.add(row)
    row.value_json = json.dumps(value, ensure_ascii=False)


def load_runtime_settings(db: Session) -> dict[str, Any]:
    row = get_runtime_settings_row(db)
    if row is None:
        if not _runtime_settings_supports_key_value_rows(db):
            return {}
        _backfill_legacy_runtime_settings_if_needed(db)
        row = get_runtime_settings_row(db)
    if row is None:
        return {}

    payload: dict[str, Any] = {
        "app_name": row.app_name,
        "app_env": row.app_env,
        "debug": row.debug,
        "imap_host": row.imap_host,
        "imap_port": row.imap_port,
        "imap_user": row.imap_user,
        "imap_password": row.imap_password,
        "smtp_host": row.smtp_host,
        "smtp_port": row.smtp_port,
        "smtp_user": row.smtp_user,
        "smtp_password": row.smtp_password,
        "smtp_use_tls": row.smtp_use_tls,
        "smtp_use_ssl": row.smtp_use_ssl,
        "deepseek_api_key": row.deepseek_api_key or row.openai_api_key,
        "openai_api_key": row.deepseek_api_key or row.openai_api_key,
        "deepseek_base_url": row.deepseek_base_url,
        "deepseek_model": row.deepseek_model,
        "ai_analysis_enabled": row.ai_analysis_enabled,
        "ai_auto_spam_enabled": row.ai_auto_spam_enabled,
        "auto_spam_enabled": row.ai_auto_spam_enabled,
        "ai_max_retries": row.ai_max_retries,
        "ai_timeout_seconds": row.ai_timeout_seconds,
        "redis_url": row.redis_url,
        "scheduler_interval_minutes": row.scheduler_interval_minutes,
        "scan_interval_minutes": row.scheduler_interval_minutes,
        "followup_overdue_days": row.followup_overdue_days,
        "catchup_absence_hours": row.catchup_absence_hours,
        "sent_review_batch_limit": row.sent_review_batch_limit,
        "run_background_jobs": row.run_background_jobs,
        "run_mail_watchers": row.run_mail_watchers,
        "interface_language": row.interface_language,
        "summary_language": row.summary_language,
        "scan_since_date": row.scan_since_date,
        "signature": row.signature,
        "max_emails_per_scan": row.max_emails_per_scan,
        "setup_completed": bool(row.setup_completed),
    }
    if row.cors_origins_json:
        try:
            payload["cors_origins"] = json.loads(row.cors_origins_json)
        except json.JSONDecodeError:
            logger.warning("Runtime setting cors_origins_json is not valid JSON", exc_info=True)
            payload["cors_origins"] = []
    return {key: value for key, value in payload.items() if value is not None}


def save_runtime_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    row = get_runtime_settings_row(db, create=True)
    assert row is not None
    for key, value in updates.items():
        if value is None:
            continue
        _apply_runtime_setting_update(row, key, value)
    db.flush()
    return load_runtime_settings(db)


def build_effective_settings(base_settings: Any, db: Session) -> SimpleNamespace:
    merged = base_settings.model_dump()
    merged.update(load_runtime_settings(db))
    if "deepseek_api_key" not in merged and merged.get("openai_api_key"):
        merged["deepseek_api_key"] = merged["openai_api_key"]
    if "openai_api_key" not in merged and merged.get("deepseek_api_key"):
        merged["openai_api_key"] = merged["deepseek_api_key"]
    if "scheduler_interval_minutes" not in merged and merged.get("scan_interval_minutes") is not None:
        merged["scheduler_interval_minutes"] = merged["scan_interval_minutes"]
    if "scan_interval_minutes" not in merged and merged.get("scheduler_interval_minutes") is not None:
        merged["scan_interval_minutes"] = merged["scheduler_interval_minutes"]
    merged["auto_spam_enabled"] = bool(merged.get("ai_auto_spam_enabled", False))
    return SimpleNamespace(**merged)


def get_safe_settings_view(base_settings: Any, db: Session) -> dict[str, Any]:
    effective = vars(build_effective_settings(base_settings, db)).copy()
    for key in SECRET_SETTING_KEYS:
        effective.pop(key, None)

    effective["has_imap_password"] = bool(effective.get("imap_password"))
    effective["has_smtp_password"] = bool(effective.get("smtp_password"))
    effective["has_deepseek_api_key"] = bool(effective.get("deepseek_api_key") or effective.get("openai_api_key"))
    effective["has_openai_api_key"] = effective["has_deepseek_api_key"]
    effective["auto_spam_enabled"] = bool(effective.get("ai_auto_spam_enabled", False))
    effective["ai_auto_spam_enabled"] = effective["auto_spam_enabled"]
    return effective


def is_setup_completed(db: Session) -> bool:
    row = get_runtime_settings_row(db)
    if row is not None and row.setup_completed:
        return True
    existing_user = db.execute(select(User.id).limit(1)).scalar_one_or_none()
    return existing_user is not None


def mark_setup_completed(db: Session, *, completed: bool = True) -> None:
    row = get_runtime_settings_row(db, create=True)
    assert row is not None
    row.setup_completed = completed


def _apply_runtime_setting_update(row: RuntimeSetting, key: str, value: Any) -> None:
    normalized_key = RUNTIME_SETTING_ALIASES.get(key, key)
    if normalized_key in KEY_VALUE_SETTING_KEYS or normalized_key.startswith("digest_state_"):
        raise ValueError(f"Use get_setting/set_setting for key/value runtime setting '{normalized_key}'")
    if normalized_key == "cors_origins":
        row.cors_origins_json = json.dumps(value, ensure_ascii=False)
        return
    if normalized_key in {"interface_language", "summary_language"} and isinstance(value, str):
        setattr(row, normalized_key, value.strip().lower())
        return
    if normalized_key == "scan_since_date" and isinstance(value, str):
        setattr(row, normalized_key, value.strip() or None)
        return
    if normalized_key == "openai_api_key":
        row.deepseek_api_key = str(value).strip() or None
        row.openai_api_key = row.deepseek_api_key
        return
    if hasattr(row, normalized_key):
        setattr(row, normalized_key, value)


def _backfill_legacy_runtime_settings_if_needed(db: Session) -> None:
    from app.db import open_account_session

    legacy_session = open_account_session("default")
    try:
        try:
            legacy_row = (
                legacy_session.execute(
                    select(RuntimeSetting)
                    .where(RuntimeSetting.key.is_(None))
                    .order_by(RuntimeSetting.id.asc())
                )
                .scalars()
                .first()
            )
        except OperationalError:
            logger.warning(
                "Legacy account runtime settings are not readable on the current schema",
                exc_info=True,
            )
            return
        if legacy_row is None:
            return
        legacy_payload = {
            key: value
            for key, value in load_runtime_settings(legacy_session).items()
            if key not in {"setup_completed"}
        }
        if not legacy_payload:
            return
        save_runtime_settings(db, legacy_payload)
        db.commit()
    finally:
        legacy_session.close()


def _runtime_settings_supports_key_value_rows(db: Session) -> bool:
    try:
        columns = inspect(db.get_bind()).get_columns(RuntimeSetting.__tablename__)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to inspect runtime settings schema", exc_info=True)
        return False
    column_names = {str(column["name"]) for column in columns}
    return {"key", "value_json"}.issubset(column_names)
