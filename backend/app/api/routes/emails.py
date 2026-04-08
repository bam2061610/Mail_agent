import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.exceptions import SmtpError
from app.models.action_log import ActionLog
from app.models.attachment import Attachment
from app.models.contact import Contact
from app.models.email import Email
from app.models.user import User
from app.schemas.email import (
    AttachmentItem,
    DraftGenerationResponse,
    EmailGenerateDraftRequest,
    EmailDetail,
    EmailFeedbackRequest,
    EmailSetReplyLanguageRequest,
    EmailRewriteDraftRequest,
    FeedbackResponse,
    EmailListItem,
    EmailReplyRequest,
    EmailReplyLaterRequest,
    EmailRegenerateSummaryRequest,
    EmailStatusUpdateRequest,
    EmailThreadResponse,
    DraftFeedbackRequest,
)
from app.schemas.system import ErrorResponse
from app.services.ai_analyzer import generate_personalized_draft, regenerate_email_summary, rewrite_draft
from app.services.deepseek_client import DeepSeekError, DeepSeekRateLimitError, DeepSeekResponseError, DeepSeekTimeoutError
from app.services.attachment_service import (
    build_attachment_download_payload,
    get_attachment,
    list_email_attachments,
)
from app.services.feedback_service import (
    infer_edit_type_tags,
    record_decision_feedback,
    record_draft_feedback,
)
from app.services.preference_profile import build_preference_prompt_block, get_preference_profile, rebuild_preference_profile
from app.services.spam_service import annotate_spam_review_metadata, confirm_email_spam, restore_email_from_spam
from app.services.mail.smtp_send import send_reply
from app.services.language_service import normalize_language
from app.services.imap_folder_service import move_email as move_email_on_server, move_to_inbox as move_email_to_inbox
from app.services.mailbox_service import (
    SENT_DIRECTION_VALUES,
    get_default_runtime_mailbox_from_settings,
    get_mailbox,
    get_outgoing_mailbox_for_email,
    get_thread_lookup_keys,
    is_outgoing_direction,
    is_sent_folder,
    to_runtime_mailbox,
)
from app.services.permission_service import require_permission
from app.services.sent_review_service import (
    dismiss_sent_review,
    mark_sent_review_helpful,
    review_sent_email,
    save_sent_review,
)
from app.services.template_service import get_template

router = APIRouter(prefix="/api/emails", tags=["emails"])
ALLOWED_STATUSES = {"new", "read", "archived", "spam", "replied", "reply_later", "processed"}
INBOUND_DIRECTION_VALUES = ("inbound", "incoming", "received")
logger = logging.getLogger(__name__)
STATUS_LOCAL_FOLDERS = {
    "archived": "Archive",
    "spam": "Spam",
    "processed": "Processed",
    "reply_later": "Reply Later",
    "new": "INBOX",
}


def _resolve_runtime_mailbox_for_email(email: Email):
    if getattr(email, "mailbox_id", None):
        mailbox = get_mailbox(str(email.mailbox_id), redact_secrets=False)
        if mailbox is not None:
            return to_runtime_mailbox(mailbox)
    return get_default_runtime_mailbox_from_settings()


def _move_email_on_server(mailbox_config, email: Email, target_kind: str, source_folder: str | None) -> None:
    if mailbox_config is None:
        logger.warning("Mailbox configuration missing; skipping IMAP move for email_id=%s", email.id)
        return

    try:
        if target_kind == "inbox":
            result = move_email_to_inbox(
                mailbox_config,
                email.imap_uid,
                source_folder=source_folder,
                message_id=email.message_id,
            )
        else:
            result = move_email_on_server(
                mailbox_config,
                email.imap_uid,
                target_kind,
                source_folder=source_folder,
                message_id=email.message_id,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"IMAP action failed: {exc}") from exc

    email.imap_uid = result.target_uid or result.source_uid or email.imap_uid


@router.get("", response_model=list[EmailListItem])
def list_emails(
    status: str | None = None,
    mailbox_id: str | None = None,
    direction: str | None = None,
    folder: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    has_attachments: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> list[Email]:
    query = db.query(Email)

    if status:
        query = query.filter(Email.status == status)
    if mailbox_id:
        query = query.filter(Email.mailbox_id == mailbox_id)
    if direction:
        normalized_direction = direction.strip().lower()
        if normalized_direction in SENT_DIRECTION_VALUES:
            query = query.filter(Email.direction.in_(SENT_DIRECTION_VALUES))
        elif normalized_direction in INBOUND_DIRECTION_VALUES:
            query = query.filter(Email.direction == "inbound")
        else:
            query = query.filter(Email.direction == normalized_direction)
    if folder:
        normalized_folder = folder.strip().lower()
        if is_sent_folder(normalized_folder):
            query = query.filter(
                or_(
                    Email.folder.ilike("%sent%"),
                    Email.folder.ilike("%outbox%"),
                    Email.direction.in_(SENT_DIRECTION_VALUES),
                )
            )
        elif normalized_folder == "inbox":
            query = query.filter(or_(Email.folder.ilike("%inbox%"), Email.direction == "inbound"))
        else:
            query = query.filter(Email.folder.ilike(normalized_folder))
    if priority:
        query = query.filter(Email.priority == priority)
    if category:
        query = query.filter(Email.category == category)
    if has_attachments is not None:
        query = query.filter(Email.has_attachments.is_(has_attachments))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Attachment, Attachment.email_id == Email.id).filter(
            or_(
                Email.subject.ilike(pattern),
                Email.sender_email.ilike(pattern),
                Email.sender_name.ilike(pattern),
                Email.ai_summary.ilike(pattern),
                Attachment.filename.ilike(pattern),
                Attachment.content_type.ilike(pattern),
            )
        ).distinct(Email.id)

    emails = (
        query.order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    annotate_spam_review_metadata(db, emails)
    _attach_attachment_counts(db, emails)
    return emails


@router.get("/{email_id}", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def get_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    annotate_spam_review_metadata(db, [email])
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/regenerate-summary", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def regenerate_email_summary_route(
    email_id: int,
    request: EmailRegenerateSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update_status")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    thread_history = _load_thread_history_for_summary(db, email)
    summary_language = normalize_language(request.target_language) or "ru"
    preference_block = build_preference_prompt_block(get_preference_profile(db))
    try:
        summary = regenerate_email_summary(
            email_record=email,
            thread_history=thread_history,
            config=get_effective_settings(),
            summary_language=summary_language,
            preference_block=preference_block,
        )
        email.ai_summary = summary
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="summary_regenerated",
                actor=current_user.email,
                details_json=json.dumps({"target_language": summary_language}, ensure_ascii=False),
            )
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unable to regenerate summary: {exc}") from exc

    db.refresh(email)
    annotate_spam_review_metadata(db, [email])
    _attach_attachment_counts(db, [email])
    return email


@router.get("/{email_id}/thread", response_model=EmailThreadResponse, responses={404: {"model": ErrorResponse}})
def get_email_thread(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> EmailThreadResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    thread_keys = get_thread_lookup_keys(email)
    if not thread_keys:
        return EmailThreadResponse(thread_id=f"email-{email.id}", emails=[email])

    conditions = [Email.thread_id == key for key in thread_keys] + [Email.message_id == key for key in thread_keys]
    thread_emails = db.query(Email).filter(or_(*conditions)).order_by(Email.date_received.asc().nullsfirst(), Email.id.asc()).all()
    if not thread_emails:
        thread_emails = [email]

    thread_id = thread_keys[0]
    return EmailThreadResponse(thread_id=thread_id, emails=thread_emails)


@router.post("/{email_id}/reply", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def reply_to_email(
    email_id: int,
    request: EmailReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> Email:
    original_email = db.query(Email).filter(Email.id == email_id).first()
    if original_email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    to_addresses = request.to or ([original_email.sender_email] if original_email.sender_email else [])
    if not to_addresses:
        raise HTTPException(status_code=400, detail="Reply recipient could not be determined")

    subject = request.subject or _build_reply_subject(original_email.subject)
    references = _build_references(original_email)
    runtime_settings = get_effective_settings()
    outgoing_mailbox = get_outgoing_mailbox_for_email(original_email) or runtime_settings
    try:
        send_result = send_reply(
            to=to_addresses,
            subject=subject,
            body=request.body,
            reply_to_message_id=original_email.message_id,
            config=outgoing_mailbox,
            cc=request.cc,
            bcc=request.bcc,
            references=references,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SmtpError as exc:
        raise HTTPException(status_code=502, detail=f"SMTP delivery failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP delivery failed for email_id=%s", email_id, exc_info=True)
        raise HTTPException(status_code=502, detail=f"SMTP delivery failed: {exc}") from exc

    original_email.status = "replied"
    original_email.requires_reply = False
    original_email.last_reply_sent_at = datetime.now(timezone.utc)
    db.add(original_email)

    sent_email: Email | None = None
    if request.save_as_sent_record:
        sent_email = Email(
            message_id=send_result.message_id,
            thread_id=original_email.thread_id or original_email.message_id or send_result.message_id,
            mailbox_id=getattr(outgoing_mailbox, "id", None),
            mailbox_name=getattr(outgoing_mailbox, "name", None),
            mailbox_address=getattr(outgoing_mailbox, "email_address", None),
            subject=subject,
            sender_email=getattr(outgoing_mailbox, "email_address", None) or getattr(outgoing_mailbox, "smtp_username", None),
            sender_name=getattr(outgoing_mailbox, "name", None),
            recipients_json=json.dumps([{"email": address, "name": None} for address in to_addresses], ensure_ascii=False),
            cc_json=json.dumps([{"email": address, "name": None} for address in request.cc], ensure_ascii=False),
            date_received=datetime.now(timezone.utc),
            body_text=request.body,
            folder="Sent",
            direction="outbound",
            status="replied",
            ai_analyzed=True,
            sent_by_user_id=current_user.id,
            sent_review_status="pending",
        )
        db.add(sent_email)
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=original_email.id,
            action_type="email_sent",
            actor=current_user.email,
            details_json=json.dumps(
                {
                    "reply_message_id": send_result.message_id,
                    "subject": subject,
                    "to": to_addresses,
                    "cc": request.cc,
                    "bcc_count": len(request.bcc),
                    "mailbox_id": getattr(outgoing_mailbox, "id", None),
                },
                ensure_ascii=False,
            ),
        )
    )
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Email was sent but DB commit failed for email_id=%s", email_id)
        raise HTTPException(
            status_code=500,
            detail="Email was sent via SMTP but local database update failed. Please refresh and verify Sent mailbox.",
        ) from exc

    if sent_email is not None:
        try:
            effective_settings = get_effective_settings()
            summary_thread_history = _load_thread_history_for_summary(db, sent_email)
            summary_language = (
                normalize_language(getattr(effective_settings, "summary_language", None))
                or normalize_language(getattr(original_email, "preferred_reply_language", None))
                or normalize_language(getattr(original_email, "detected_source_language", None))
            )
            preference_block = build_preference_prompt_block(get_preference_profile(db))
            sent_summary = regenerate_email_summary(
                email_record=sent_email,
                thread_history=summary_thread_history,
                config=effective_settings,
                summary_language=summary_language or effective_settings.summary_language,
                preference_block=preference_block,
            )
            sent_email.ai_summary = sent_summary
            db.add(
                ActionLog(
                    user_id=current_user.id,
                    email_id=sent_email.id,
                    action_type="summary_regenerated",
                    actor="ai",
                    details_json=json.dumps(
                        {
                            "source": "post_send",
                            "direction": sent_email.direction,
                            "thread_id": sent_email.thread_id,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Post-send summary generation failed for email_id=%s", email_id)

    try:
        original_draft = original_email.ai_draft_reply
        draft_feedback = record_draft_feedback(
            db_session=db,
            email=original_email,
            original_draft=original_draft,
            final_draft=request.body,
            edit_type_tags=infer_edit_type_tags(original_draft, request.body),
            send_status="sent",
            actor="user",
        )

        _upsert_contact(db, original_email.sender_email, original_email.sender_name, increment_sent=True)
        if draft_feedback.action_type == "draft_sent_after_edit":
            db.add(
                ActionLog(
                    user_id=current_user.id,
                    email_id=original_email.id,
                    action_type="rewrite_requested",
                    actor=current_user.email,
                    details_json=json.dumps({"edit_type_tags": draft_feedback.inferred_tags}, ensure_ascii=False),
                )
            )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Post-send side effects failed for email_id=%s", email_id)

    try:
        rebuild_preference_profile(db)
    except Exception:  # noqa: BLE001
        logger.exception("Preference profile rebuild failed after reply for email_id=%s", email_id)

    db.refresh(original_email)
    return original_email


@router.post("/{email_id}/sent-review/review", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def review_single_sent_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("run_sent_review")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if not is_outgoing_direction(email.direction):
        raise HTTPException(status_code=400, detail="Only sent emails can be reviewed")
    thread_history = (
        db.query(Email)
        .filter(or_(Email.thread_id == (email.thread_id or email.message_id), Email.message_id == (email.thread_id or email.message_id)))
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(8)
        .all()
    )
    result = review_sent_email(
        email_record=email,
        thread_history=thread_history,
        config=get_effective_settings(),
    )
    save_sent_review(db, email, result)
    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/sent-review/dismiss", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def dismiss_single_sent_review(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    dismiss_sent_review(db, email, actor=current_user.email)
    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/sent-review/helpful", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def mark_single_sent_review_helpful(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    mark_sent_review_helpful(db, email, actor=current_user.email)
    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/status", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def update_email_status(
    email_id: int,
    request: EmailStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update_status")),
) -> Email:
    if request.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported status")

    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    mailbox_config = _resolve_runtime_mailbox_for_email(email)
    previous_spam_state = email.is_spam
    previous_folder = email.folder
    status = request.status

    try:
        if status == "spam":
            email.status = "spam"
            email.is_spam = True
            email.spam_source = "user"
            email.spam_reason = "Moved to spam folder"
            email.folder = STATUS_LOCAL_FOLDERS["spam"]
            email.requires_reply = False
            db.add(email)
            _move_email_on_server(mailbox_config, email, "spam", previous_folder)
            db.add(
                ActionLog(
                    user_id=current_user.id,
                    email_id=email.id,
                    action_type="ai_spam_confirmed",
                    actor=current_user.email,
                    details_json=json.dumps({"source": "status_update"}, ensure_ascii=False),
                )
            )
        elif status == "archived":
            email.status = "archived"
            email.folder = STATUS_LOCAL_FOLDERS["archived"]
            email.requires_reply = False
            db.add(email)
            _move_email_on_server(mailbox_config, email, "archive", previous_folder)
        elif status == "processed":
            email.status = "processed"
            email.folder = STATUS_LOCAL_FOLDERS["processed"]
            email.requires_reply = False
            db.add(email)
            _move_email_on_server(mailbox_config, email, "processed", previous_folder)
        elif status == "reply_later":
            email.status = "reply_later"
            email.folder = STATUS_LOCAL_FOLDERS["reply_later"]
            db.add(email)
            _move_email_on_server(mailbox_config, email, "reply_later", previous_folder)
        elif status == "new":
            email.status = "new"
            email.folder = STATUS_LOCAL_FOLDERS["new"]
            if previous_spam_state:
                email.is_spam = False
            db.add(email)
            _move_email_on_server(mailbox_config, email, "inbox", previous_folder)
        else:
            email.status = status
            db.add(email)
        if previous_spam_state and status != "spam":
            email.is_spam = False
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected status update failure: {exc}") from exc

    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type=f"status_updated:{status}",
            actor=current_user.email,
            details_json=json.dumps({"status": status}, ensure_ascii=False),
        )
    )
    if status == "spam" and previous_spam_state:
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="ai_spam_restored",
                actor=current_user.email,
                details_json=json.dumps({"source": "status_update", "new_status": status}, ensure_ascii=False),
            )
        )
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unable to persist status update: {exc}") from exc
    db.refresh(email)
    annotate_spam_review_metadata(db, [email])
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/restore", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def restore_spam_message(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("spam_review")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    mailbox_config = _resolve_runtime_mailbox_for_email(email)
    previous_folder = email.folder
    try:
        restore_email_from_spam(db, email, actor=current_user.email)
        email.folder = STATUS_LOCAL_FOLDERS["new"]
        db.add(email)
        _move_email_on_server(mailbox_config, email, "inbox", previous_folder)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unable to restore message: {exc}") from exc

    rebuild_preference_profile(db)
    db.refresh(email)
    annotate_spam_review_metadata(db, [email])
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/confirm-spam", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def confirm_spam_message(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("spam_review")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    mailbox_config = _resolve_runtime_mailbox_for_email(email)
    previous_folder = email.folder
    try:
        confirm_email_spam(db, email, actor=current_user.email)
        email.folder = STATUS_LOCAL_FOLDERS["spam"]
        email.requires_reply = False
        db.add(email)
        _move_email_on_server(mailbox_config, email, "spam", previous_folder)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unable to confirm spam: {exc}") from exc

    rebuild_preference_profile(db)
    db.refresh(email)
    annotate_spam_review_metadata(db, [email])
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/reply-later", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def move_email_reply_later(
    email_id: int,
    request: EmailReplyLaterRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update_status")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    mailbox_config = _resolve_runtime_mailbox_for_email(email)
    previous_folder = email.folder
    email.status = "reply_later"
    email.folder = STATUS_LOCAL_FOLDERS["reply_later"]
    db.add(email)

    try:
        _move_email_on_server(mailbox_config, email, "reply_later", previous_folder)
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="status_updated:reply_later",
                actor=current_user.email,
                details_json=json.dumps(
                    {
                        "status": "reply_later",
                        "snooze_until": request.snooze_until.isoformat() if request and request.snooze_until else None,
                        "interval_minutes": request.interval_minutes if request else None,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unable to move message later: {exc}") from exc

    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


@router.get("/{email_id}/attachments", response_model=list[AttachmentItem], responses={404: {"model": ErrorResponse}})
def get_email_attachments(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> list[Attachment]:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return list_email_attachments(db, email_id)


@router.get("/attachments/{attachment_id}/download", responses={404: {"model": ErrorResponse}})
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
):
    attachment = get_attachment(db, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        file_path, _, media_type, headers = build_attachment_download_payload(attachment)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment file missing")
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=attachment.email_id,
            action_type="attachment_downloaded",
            actor=current_user.email,
            details_json=json.dumps({"attachment_id": attachment.id, "filename": attachment.filename}, ensure_ascii=False),
        )
    )
    db.commit()
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers=headers,
    )
@router.post("/{email_id}/set-reply-language", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def set_reply_language(
    email_id: int,
    request: EmailSetReplyLanguageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    language = normalize_language(request.language)
    if not language:
        raise HTTPException(status_code=400, detail="Unsupported language")

    email.preferred_reply_language = language
    db.add(email)
    if email.sender_email:
        contact = db.query(Contact).filter(Contact.email == email.sender_email).first()
        if contact is not None:
            contact.preferred_language = language
            db.add(contact)
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type="reply_language_changed",
            actor=current_user.email,
            details_json=json.dumps({"language": language}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(email)
    return email


@router.post("/{email_id}/generate-draft", response_model=DraftGenerationResponse, responses={404: {"model": ErrorResponse}})
def create_ai_draft(
    email_id: int,
    request: EmailGenerateDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> DraftGenerationResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    thread_key = email.thread_id or email.message_id or f"email-{email.id}"
    thread_history = (
        db.query(Email)
        .filter(or_(Email.thread_id == thread_key, Email.message_id == thread_key))
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(5)
        .all()
    )
    preference_block = build_preference_prompt_block(get_preference_profile(db))
    try:
        result = generate_personalized_draft(
            email_record=email,
            thread_history=thread_history,
            config=get_effective_settings(),
            target_language=request.target_language,
            template_id=request.template_id,
            tone=request.tone,
            length=request.length,
            custom_prompt=request.custom_prompt,
            preference_block=preference_block,
        )
    except DeepSeekTimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"AI draft timed out: {exc}") from exc
    except DeepSeekRateLimitError as exc:
        raise HTTPException(status_code=429, detail=f"AI rate limit reached: {exc}") from exc
    except (DeepSeekResponseError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected AI response: {exc}") from exc
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=f"AI draft generation failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected AI draft failure for email_id=%s", email_id)
        raise HTTPException(status_code=500, detail=f"Unexpected AI draft failure: {exc}") from exc
    email.ai_draft_reply = result.draft_reply
    email.preferred_reply_language = result.target_language
    db.add(email)
    details = {
        "target_language": result.target_language,
        "subject": result.subject,
        "template_id": request.template_id,
        "tone": request.tone,
        "length": request.length,
        "custom_prompt_used": bool(request.custom_prompt),
    }
    if request.template_id and get_template(request.template_id):
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="template_applied",
                actor=current_user.email,
                details_json=json.dumps(details, ensure_ascii=False),
            )
        )
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type="draft_generated",
            actor=current_user.email,
            details_json=json.dumps(details | {"draft_reply": result.draft_reply}, ensure_ascii=False),
        )
    )
    db.commit()
    return DraftGenerationResponse(
        draft_reply=result.draft_reply,
        subject=result.subject,
        target_language=result.target_language,
        template_id=request.template_id,
    )


@router.post("/{email_id}/rewrite-draft", response_model=DraftGenerationResponse, responses={404: {"model": ErrorResponse}})
def rewrite_existing_draft(
    email_id: int,
    request: EmailRewriteDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> DraftGenerationResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    preference_block = build_preference_prompt_block(get_preference_profile(db))
    thread_key = email.thread_id or email.message_id or f"email-{email.id}"
    thread_history = (
        db.query(Email)
        .filter(or_(Email.thread_id == thread_key, Email.message_id == thread_key))
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(5)
        .all()
    )
    try:
        result = rewrite_draft(
            email_record=email,
            current_draft=request.current_draft,
            instruction=request.instruction,
            config=get_effective_settings(),
            thread_history=thread_history,
            target_language=request.target_language,
            preference_block=preference_block,
        )
    except DeepSeekTimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"AI rewrite timed out: {exc}") from exc
    except DeepSeekRateLimitError as exc:
        raise HTTPException(status_code=429, detail=f"AI rate limit reached: {exc}") from exc
    except (DeepSeekResponseError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected AI response: {exc}") from exc
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=f"AI rewrite failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected AI rewrite failure for email_id=%s", email_id)
        raise HTTPException(status_code=500, detail=f"Unexpected AI rewrite failure: {exc}") from exc
    previous_draft = email.ai_draft_reply
    email.ai_draft_reply = result.draft_reply
    email.preferred_reply_language = result.target_language
    db.add(email)
    action_type = "draft_translated" if "translate" in request.instruction.lower() else "draft_rewritten"
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type=action_type,
            actor=current_user.email,
            details_json=json.dumps(
                {
                    "instruction": request.instruction,
                    "target_language": result.target_language,
                    "original_draft": previous_draft or request.current_draft,
                    "rewritten_draft": result.draft_reply,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return DraftGenerationResponse(
        draft_reply=result.draft_reply,
        subject=result.subject,
        target_language=result.target_language,
    )


@router.post("/{email_id}/feedback", response_model=FeedbackResponse, responses={404: {"model": ErrorResponse}})
def submit_email_feedback(
    email_id: int,
    request: EmailFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> FeedbackResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    created_actions = record_decision_feedback(
        db_session=db,
        email=email,
        decision_type=request.decision_type,
        verdict=request.verdict,
        details=request.details,
        actor=current_user.email,
    )
    db.commit()
    rebuild_preference_profile(db)
    return FeedbackResponse(status="ok", action_types=created_actions)


@router.post("/{email_id}/draft-feedback", response_model=FeedbackResponse, responses={404: {"model": ErrorResponse}})
def submit_draft_feedback(
    email_id: int,
    request: DraftFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> FeedbackResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    result = record_draft_feedback(
        db_session=db,
        email=email,
        original_draft=request.original_draft or email.ai_draft_reply,
        final_draft=request.final_draft,
        edit_type_tags=request.edit_type_tags,
        send_status=request.send_status,
        actor=current_user.email,
    )
    if result.inferred_tags:
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="rewrite_requested",
                actor=current_user.email,
                details_json=json.dumps({"edit_type_tags": result.inferred_tags}, ensure_ascii=False),
            )
        )
    db.commit()
    rebuild_preference_profile(db)
    return FeedbackResponse(status="ok", action_types=[result.action_type], inferred_tags=result.inferred_tags)


def _build_reply_subject(subject: str | None) -> str:
    if not subject:
        return "Re: No subject"
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}"


def _build_references(email: Email) -> list[str]:
    references: list[str] = []
    if email.thread_id and email.thread_id != email.message_id:
        references.append(email.thread_id)
    if email.message_id:
        references.append(email.message_id)
    return references


def _upsert_contact(
    db: Session,
    email_address: str | None,
    name: str | None,
    increment_received: bool = False,
    increment_sent: bool = False,
) -> None:
    if not email_address:
        return

    contact = db.query(Contact).filter(Contact.email == email_address).first()
    if contact is None:
        contact = Contact(email=email_address, name=name)
    if name and not contact.name:
        contact.name = name
    if increment_received:
        contact.emails_received_count = int(contact.emails_received_count or 0) + 1
        contact.last_contact_at = datetime.now(timezone.utc)
    if increment_sent:
        contact.emails_sent_count = int(contact.emails_sent_count or 0) + 1
        contact.last_contact_at = datetime.now(timezone.utc)
    db.add(contact)


def _attach_attachment_counts(db: Session, emails: list[Email]) -> None:
    if not emails:
        return
    email_ids = [email.id for email in emails]
    rows = db.query(Attachment.email_id).filter(Attachment.email_id.in_(email_ids)).all()
    counts: dict[int, int] = {}
    for (email_id,) in rows:
        counts[email_id] = counts.get(email_id, 0) + 1
    for email in emails:
        setattr(email, "attachment_count", counts.get(email.id, 0))


def _load_thread_history_for_summary(db: Session, email: Email) -> list[Email]:
    if not email.thread_id:
        return []
    return (
        db.query(Email)
        .filter(Email.thread_id == email.thread_id, Email.id != email.id)
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(5)
        .all()
    )
