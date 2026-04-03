import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SECRET_SETTING_KEYS = {
    "imap_password",
    "smtp_password",
    "openai_api_key",
}


class Settings(BaseSettings):
    app_name: str = Field(default="Orhun Mail Agent", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    database_url: str = Field(default=f"sqlite:///{(DATA_DIR / 'mail_agent.db').as_posix()}", alias="DATABASE_URL")
    dev_auth_bypass: bool = Field(default=False, alias="DEV_AUTH_BYPASS")
    imap_host: str = Field(default="", alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    imap_user: str = Field(default="", alias="IMAP_USER")
    imap_password: str = Field(default="", alias="IMAP_PASSWORD")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=True, alias="SMTP_USE_SSL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    interface_language: str = Field(default="ru", alias="INTERFACE_LANGUAGE")
    signature: str = Field(default="", alias="SIGNATURE")
    ai_auto_spam_enabled: bool = Field(default=False, alias="AI_AUTO_SPAM_ENABLED")
    ai_max_retries: int = Field(default=3, alias="AI_MAX_RETRIES")
    ai_timeout_seconds: int = Field(default=60, alias="AI_TIMEOUT_SECONDS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    scan_interval_minutes: int = Field(default=5, alias="SCAN_INTERVAL_MINUTES")
    followup_overdue_days: int = Field(default=3, alias="FOLLOWUP_OVERDUE_DAYS")
    catchup_absence_hours: int = Field(default=8, alias="CATCHUP_ABSENCE_HOURS")
    sent_review_batch_limit: int = Field(default=20, alias="SENT_REVIEW_BATCH_LIMIT")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        alias="CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return bool(value)


settings = Settings()


def load_runtime_settings() -> dict[str, Any]:
    from app.db import open_account_session
    from app.models.runtime_setting import RuntimeSetting

    db = open_account_session()
    try:
        row = db.query(RuntimeSetting).order_by(RuntimeSetting.id.desc()).first()
        if row is None:
            return {}
        return _runtime_setting_to_dict(row)
    finally:
        db.close()


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    from app.db import open_account_session
    from app.models.runtime_setting import RuntimeSetting

    db = open_account_session()
    try:
        row = db.query(RuntimeSetting).order_by(RuntimeSetting.id.desc()).first()
        if row is None:
            row = RuntimeSetting()
            db.add(row)

        for key, value in updates.items():
            if value is None:
                continue
            _apply_runtime_setting_update(row, key, value)

        db.commit()
        db.refresh(row)
        return _runtime_setting_to_dict(row)
    finally:
        db.close()


def get_effective_settings() -> SimpleNamespace:
    merged = settings.model_dump()
    merged.update(load_runtime_settings())
    return SimpleNamespace(**merged)


def get_safe_settings_view() -> dict[str, Any]:
    effective = get_effective_settings()
    payload = vars(effective).copy()
    for key in SECRET_SETTING_KEYS:
        payload.pop(key, None)

    payload["has_imap_password"] = bool(getattr(effective, "imap_password", None))
    payload["has_smtp_password"] = bool(getattr(effective, "smtp_password", None))
    payload["has_openai_api_key"] = bool(getattr(effective, "openai_api_key", None))
    payload["ai_auto_spam_enabled"] = bool(getattr(effective, "ai_auto_spam_enabled", False))
    return payload


def _runtime_setting_to_dict(row: Any) -> dict[str, Any]:
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
        "openai_api_key": row.openai_api_key,
        "deepseek_base_url": row.deepseek_base_url,
        "deepseek_model": row.deepseek_model,
        "interface_language": row.interface_language,
        "signature": row.signature,
        "ai_auto_spam_enabled": row.ai_auto_spam_enabled,
        "ai_max_retries": row.ai_max_retries,
        "ai_timeout_seconds": row.ai_timeout_seconds,
        "redis_url": row.redis_url,
        "scan_interval_minutes": row.scan_interval_minutes,
        "followup_overdue_days": row.followup_overdue_days,
        "catchup_absence_hours": row.catchup_absence_hours,
        "sent_review_batch_limit": row.sent_review_batch_limit,
    }
    cors_value = row.cors_origins_json
    if cors_value:
        try:
            payload["cors_origins"] = json.loads(cors_value)
        except Exception:  # noqa: BLE001
            payload["cors_origins"] = []
    return {key: value for key, value in payload.items() if value is not None}


def _apply_runtime_setting_update(row: Any, key: str, value: Any) -> None:
    if key == "cors_origins":
        row.cors_origins_json = json.dumps(value, ensure_ascii=False)
        return
    if hasattr(row, key):
        setattr(row, key, value)
