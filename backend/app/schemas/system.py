from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    server_time: datetime


class ErrorResponse(BaseModel):
    detail: str


class StatsResponse(BaseModel):
    new_count: int
    waiting_reply_count: int
    analyzed_today_count: int
    total_inbox_count: int
    spam_count: int
    waiting_count: int = 0
    overdue_count: int = 0
    followup_due_today_count: int = 0


class DigestResponse(BaseModel):
    date: str
    emails_received_today: int
    important_emails: int
    unanswered_emails: int
    analyzed_count: int


class SettingsResponse(BaseModel):
    app_name: str
    app_env: str
    debug: bool
    database_url: str
    imap_host: str
    imap_port: int
    imap_user: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    deepseek_base_url: str
    deepseek_model: str
    scan_interval_minutes: int
    followup_overdue_days: int
    cors_origins: list[str]
    has_imap_password: bool
    has_smtp_password: bool
    has_openai_api_key: bool


class SettingsUpdateRequest(BaseModel):
    app_name: str | None = None
    app_env: str | None = None
    debug: bool | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_user: str | None = None
    imap_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    openai_api_key: str | None = None
    scan_interval_minutes: int | None = None
    followup_overdue_days: int | None = None
    cors_origins: list[str] | None = None


class ManualScanResponse(BaseModel):
    imported_count: int
    analyzed_count: int
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] | None = None


class PreferenceProfileResponse(BaseModel):
    version: int
    generated_at: str | None = None
    draft_preferences: dict[str, Any] = Field(default_factory=dict)
    decision_preferences: dict[str, Any] = Field(default_factory=dict)
    summary_lines: list[str] = Field(default_factory=list)


class OperationStatusResponse(BaseModel):
    status: str = "ok"


class AutomationRule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    order: int = 0
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class AutomationRuleCreateRequest(BaseModel):
    name: str
    enabled: bool = True
    order: int | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: dict[str, Any] = Field(default_factory=dict)


class AutomationRuleUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    order: int | None = None
    conditions: dict[str, Any] | None = None
    actions: dict[str, Any] | None = None


class AutomationRuleReorderItem(BaseModel):
    id: str
    order: int


class AutomationRuleReorderRequest(BaseModel):
    items: list[AutomationRuleReorderItem] = Field(default_factory=list)
