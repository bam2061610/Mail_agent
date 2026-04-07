from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EmailListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    mailbox_id: str | None = None
    mailbox_name: str | None = None
    mailbox_address: str | None = None
    imap_uid: str | None = None
    date_received: datetime | None = None
    status: str
    priority: str | None = None
    importance_score: int | None = None
    category: str | None = None
    ai_analyzed: bool
    requires_reply: bool
    is_spam: bool
    spam_source: str | None = None
    spam_reason: str | None = None
    applied_rules_json: str | None = None
    focus_flag: bool = False
    ai_summary: str | None = None
    body_text: str | None = None
    spam_action_at: datetime | None = None
    spam_action_actor: str | None = None
    detected_source_language: str | None = None
    preferred_reply_language: str | None = None
    has_attachments: bool = False
    attachment_count: int = 0
    waiting_state: str | None = None
    wait_days: int | None = None
    assigned_to_user_id: int | None = None
    assigned_by_user_id: int | None = None
    assigned_at: datetime | None = None
    sent_by_user_id: int | None = None
    sent_review_summary: str | None = None
    sent_review_status: str | None = None
    sent_review_issues_json: str | None = None
    sent_review_score: float | None = None
    sent_review_suggested_improvement: str | None = None
    sent_reviewed_at: datetime | None = None


class EmailDetail(EmailListItem):
    message_id: str | None = None
    thread_id: str | None = None
    recipients_json: str | None = None
    cc_json: str | None = None
    imap_uid: str | None = None
    body_html: str | None = None
    folder: str
    direction: str
    action_description: str | None = None
    key_dates_json: str | None = None
    key_amounts_json: str | None = None
    ai_draft_reply: str | None = None
    ai_confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class EmailCreateDraftRequest(BaseModel):
    instructions: str | None = None


class EmailUpdateStatusRequest(BaseModel):
    status: str


class EmailStatusUpdateRequest(BaseModel):
    status: str


class EmailReplyLaterRequest(BaseModel):
    snooze_until: datetime | None = None
    interval_minutes: int | None = None


class EmailReplyRequest(BaseModel):
    body: str
    to: list[str] | None = None
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str | None = None
    save_as_sent_record: bool = True


class EmailThreadResponse(BaseModel):
    thread_id: str
    emails: list[EmailDetail]


class WaitingStartRequest(BaseModel):
    expected_reply_by: datetime | None = None


class WaitingCloseRequest(BaseModel):
    reason: str | None = None


class FollowupDraftResponse(BaseModel):
    thread_id: str
    draft_reply: str


class WaitingThreadItem(BaseModel):
    task_id: int
    email_id: int | None = None
    thread_id: str
    state: str
    title: str
    subtitle: str | None = None
    started_at: datetime | None = None
    expected_reply_by: datetime | None = None
    wait_days: int
    latest_email_id: int | None = None
    latest_subject: str | None = None
    latest_sender_email: str | None = None
    latest_sender_name: str | None = None
    latest_ai_summary: str | None = None
    latest_date_received: datetime | None = None
    followup_draft: str | None = None


class EmailFeedbackRequest(BaseModel):
    decision_type: str
    verdict: str
    details: dict[str, Any] | None = None


class DraftFeedbackRequest(BaseModel):
    original_draft: str | None = None
    final_draft: str | None = None
    edit_type_tags: list[str] = Field(default_factory=list)
    send_status: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    action_types: list[str] = Field(default_factory=list)
    inferred_tags: list[str] = Field(default_factory=list)


class EmailGenerateDraftRequest(BaseModel):
    target_language: str | None = None
    template_id: str | None = None
    tone: str | None = None
    length: str | None = None
    custom_prompt: str | None = None


class EmailRewriteDraftRequest(BaseModel):
    current_draft: str
    instruction: str
    target_language: str | None = None


class EmailSetReplyLanguageRequest(BaseModel):
    language: str


class EmailRegenerateSummaryRequest(BaseModel):
    target_language: str


class DraftGenerationResponse(BaseModel):
    draft_reply: str
    subject: str | None = None
    target_language: str
    template_id: str | None = None


class AttachmentItem(BaseModel):
    id: int
    email_id: int
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int
    content_id: str | None = None
    is_inline: bool = False
    created_at: datetime


class EmailAssignRequest(BaseModel):
    user_id: int
