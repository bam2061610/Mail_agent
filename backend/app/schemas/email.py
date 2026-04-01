from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EmailListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    date_received: datetime | None = None
    status: str
    priority: str | None = None
    category: str | None = None
    ai_analyzed: bool
    requires_reply: bool
    is_spam: bool
    spam_source: str | None = None
    spam_reason: str | None = None
    applied_rules_json: str | None = None
    focus_flag: bool = False
    spam_action_at: datetime | None = None
    spam_action_actor: str | None = None
    waiting_state: str | None = None
    wait_days: int | None = None


class EmailDetail(EmailListItem):
    message_id: str | None = None
    thread_id: str | None = None
    recipients_json: str | None = None
    cc_json: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    folder: str
    direction: str
    ai_summary: str | None = None
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
