from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    app_name: str = Field(default="Orhun Mail Agent", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    secret_key: str = Field(default="", alias="SECRET_KEY")
    database_url: str = Field(default=f"sqlite:///{(DATA_DIR / 'mail_agent.db').as_posix()}", alias="DATABASE_URL")
    port: int = Field(default=8000, alias="PORT")
    bootstrap_default_admin: bool = Field(default=False, alias="BOOTSTRAP_DEFAULT_ADMIN")
    bootstrap_admin_email: str = Field(default="admin@orhun.local", alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: str = Field(default="", alias="BOOTSTRAP_ADMIN_PASSWORD")
    bootstrap_admin_full_name: str = Field(default="Bootstrap Admin", alias="BOOTSTRAP_ADMIN_FULL_NAME")
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
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    interface_language: str = Field(default="ru", alias="INTERFACE_LANGUAGE")
    summary_language: str = Field(default="ru", alias="SUMMARY_LANGUAGE")
    scan_since_date: str | None = Field(default=None, alias="SCAN_SINCE_DATE")
    signature: str = Field(default="", alias="SIGNATURE")
    ai_analysis_enabled: bool = Field(default=True, alias="AI_ANALYSIS_ENABLED")
    ai_auto_spam_enabled: bool = Field(default=True, alias="AI_AUTO_SPAM_ENABLED")
    ai_max_retries: int = Field(default=3, alias="AI_MAX_RETRIES")
    ai_timeout_seconds: int = Field(default=60, alias="AI_TIMEOUT_SECONDS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    scheduler_interval_minutes: int = Field(default=5, alias="SCHEDULER_INTERVAL_MINUTES")
    max_emails_per_scan: int = Field(default=200, alias="MAX_EMAILS_PER_SCAN")
    followup_overdue_days: int = Field(default=3, alias="FOLLOWUP_OVERDUE_DAYS")
    catchup_absence_hours: int = Field(default=8, alias="CATCHUP_ABSENCE_HOURS")
    sent_review_batch_limit: int = Field(default=20, alias="SENT_REVIEW_BATCH_LIMIT")
    run_background_jobs: bool = Field(default=True, alias="RUN_BACKGROUND_JOBS")
    run_mail_watchers: bool = Field(default=True, alias="RUN_MAIL_WATCHERS")
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
    from app.db import open_global_session
    from app.services.settings_service import load_runtime_settings as load_runtime_settings_from_db

    db = open_global_session()
    try:
        return load_runtime_settings_from_db(db)
    finally:
        db.close()


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    from app.db import open_global_session
    from app.services.settings_service import save_runtime_settings as save_runtime_settings_to_db

    db = open_global_session()
    try:
        payload = save_runtime_settings_to_db(db, updates)
        db.commit()
        return payload
    finally:
        db.close()


def get_effective_settings() -> SimpleNamespace:
    from app.db import open_global_session
    from app.services.settings_service import build_effective_settings

    db = open_global_session()
    try:
        return build_effective_settings(settings, db)
    finally:
        db.close()


def get_safe_settings_view() -> dict[str, Any]:
    from app.db import open_global_session
    from app.services.settings_service import get_safe_settings_view as build_safe_settings_view

    db = open_global_session()
    try:
        return build_safe_settings_view(settings, db)
    finally:
        db.close()
