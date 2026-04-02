from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mailbox_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    mailbox_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mailbox_address: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipients_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_received: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder: Mapped[str] = mapped_column(String(100), default="inbox", nullable=False)
    direction: Mapped[str] = mapped_column(String(50), default="inbound", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_dates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_amounts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_draft_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spam_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    spam_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detected_source_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preferred_reply_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_reply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_to_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    last_reply_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_review_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sent_review_issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sent_review_suggested_improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
