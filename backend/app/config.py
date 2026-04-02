import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE_PATH = DATA_DIR / "settings.local.json"
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
    if not SETTINGS_FILE_PATH.exists():
        return {}

    try:
        return json.loads(SETTINGS_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_runtime_settings()
    for key, value in updates.items():
        if value is None:
            continue
        current[key] = value

    SETTINGS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


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
    return payload
