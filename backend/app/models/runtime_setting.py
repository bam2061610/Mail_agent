from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_env: Mapped[str | None] = mapped_column(String(50), nullable=True)
    debug: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imap_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_use_tls: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    smtp_use_ssl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    openai_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    deepseek_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    deepseek_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deepseek_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_analysis_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_auto_spam_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redis_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scheduler_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_overdue_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catchup_absence_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_review_batch_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_emails_per_scan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_background_jobs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    run_mail_watchers: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    interface_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scan_since_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    cors_origins_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
