from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class CatchupItem(BaseModel):
    email_id: int | None = None
    task_id: int | None = None
    thread_id: str | None = None
    subject: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    mailbox_name: str | None = None
    state: str | None = None
    priority: str | None = None
    status: str | None = None
    date_received: str | None = None
    expected_reply_by: str | None = None


class CatchupDigestResponse(BaseModel):
    generated_at: str
    since: str
    away_hours: int
    should_show: bool
    important_new: list[CatchupItem] = Field(default_factory=list)
    waiting_or_overdue: list[CatchupItem] = Field(default_factory=list)
    spam_review: list[CatchupItem] = Field(default_factory=list)
    recent_sent: list[CatchupItem] = Field(default_factory=list)
    followups_due: list[CatchupItem] = Field(default_factory=list)
    top_actions: list[str] = Field(default_factory=list)


class DigestSeenResponse(BaseModel):
    status: str = "ok"
    last_seen_at: str
    last_digest_viewed_at: str


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
    catchup_absence_hours: int
    sent_review_batch_limit: int
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
    catchup_absence_hours: int | None = None
    sent_review_batch_limit: int | None = None
    cors_origins: list[str] | None = None


class ManualScanResponse(BaseModel):
    imported_count: int
    analyzed_count: int
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] | None = None


class SentReviewRunResponse(BaseModel):
    selected_count: int
    reviewed_count: int
    failed_count: int
    errors: list[str] = Field(default_factory=list)


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


class MessageTemplate(BaseModel):
    id: str
    name: str
    category: str
    language: str
    subject_template: str | None = None
    body_template: str
    enabled: bool = True
    created_at: str
    updated_at: str


class MessageTemplateCreateRequest(BaseModel):
    name: str
    category: str
    language: str
    subject_template: str | None = None
    body_template: str
    enabled: bool = True


class MessageTemplateUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    language: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    enabled: bool | None = None


class MailboxResponse(BaseModel):
    id: str
    name: str
    email_address: str
    imap_host: str
    imap_port: int
    imap_username: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = True
    enabled: bool = True
    is_default_outgoing: bool = False
    created_at: str
    updated_at: str
    has_imap_password: bool = False
    has_smtp_password: bool = False


class MailboxCreateRequest(BaseModel):
    name: str
    email_address: str
    imap_host: str
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str
    smtp_host: str
    smtp_port: int = 465
    smtp_username: str | None = None
    smtp_password: str
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = True
    enabled: bool = True
    is_default_outgoing: bool = False


class MailboxUpdateRequest(BaseModel):
    name: str | None = None
    email_address: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None
    enabled: bool | None = None
    is_default_outgoing: bool | None = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class AuthMeResponse(BaseModel):
    user: "UserResponse"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    timezone: str | None = None
    language: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserCreateRequest(BaseModel):
    email: str
    full_name: str
    password: str
    role: str = "operator"
    timezone: str | None = None
    language: str | None = None


class UserUpdateRequest(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    timezone: str | None = None
    language: str | None = None


class UserResetPasswordRequest(BaseModel):
    new_password: str


class BackupItem(BaseModel):
    backup_name: str
    created_at: str | None = None
    include_attachments: bool = False
    size_bytes: int = 0
    path: str
    manifest: dict[str, Any] = Field(default_factory=dict)


class BackupCreateRequest(BaseModel):
    include_attachments: bool = False
    keep_last: int = 10


class BackupCreateResponse(BaseModel):
    backup_name: str
    backup_path: str
    include_attachments: bool
    size_bytes: int
    pruned_backups: list[str] = Field(default_factory=list)


class BackupRestoreRequest(BaseModel):
    backup_name: str
    confirmation: str
    restore_attachments: bool = False


class BackupRestoreResponse(BaseModel):
    backup_name: str
    restored_database: bool
    restored_config_files: list[str] = Field(default_factory=list)
    restored_attachments: bool = False
    safety_backup_name: str | None = None


class BackupStatusResponse(BaseModel):
    backups_count: int
    latest_backup: BackupItem | None = None
    backup_dir: str


class AdminMailboxStatusResponse(BaseModel):
    mailbox_id: str
    mailbox_name: str
    email_address: str | None = None
    enabled: bool
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
    connection_ok: bool | None = None
    connection_error: str | None = None


class AdminHealthResponse(BaseModel):
    overall_status: str
    server_time: str
    app_env: str
    components: dict[str, Any] = Field(default_factory=dict)
    mailboxes: list[AdminMailboxStatusResponse] = Field(default_factory=list)
    storage: dict[str, Any] = Field(default_factory=dict)
    jobs: dict[str, Any] = Field(default_factory=dict)


class AdminJobsResponse(BaseModel):
    scheduler: dict[str, Any] = Field(default_factory=dict)
    scan: dict[str, Any] = Field(default_factory=dict)
    analyze: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    restore: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    report_type: str
    generated_at: str
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ReportSendRequest(BaseModel):
    report_type: str
    to: list[str]
    date_from: str | None = None
    date_to: str | None = None
    mailbox_id: str | None = None
    user_id: int | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)


class ReportSendResponse(BaseModel):
    status: str = "sent"
    report_type: str
    recipients: list[str] = Field(default_factory=list)
    subject: str
