import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.action_log import ActionLog
from app.models.attachment import Attachment
from app.models.contact import Contact
from app.models.email import Email
from app.models.task import Task
from app.models.user import User
from app.schemas.email import (
    AttachmentItem,
    DraftGenerationResponse,
    EmailGenerateDraftRequest,
    EmailDetail,
    EmailFeedbackRequest,
    EmailSetReplyLanguageRequest,
    EmailRewriteDraftRequest,
    EmailAssignRequest,
    FeedbackResponse,
    FollowupDraftResponse,
    EmailListItem,
    EmailReplyRequest,
    EmailStatusUpdateRequest,
    EmailThreadResponse,
    DraftFeedbackRequest,
    WaitingCloseRequest,
    WaitingStartRequest,
)
from app.schemas.system import ErrorResponse
from app.services.ai_analyzer import generate_followup_draft, generate_personalized_draft, rewrite_draft
from app.services.attachment_service import get_attachment, get_attachment_file_path, list_email_attachments
from app.services.feedback_service import (
    infer_edit_type_tags,
    record_decision_feedback,
    record_draft_feedback,
)
from app.services.followup_tracker import (
    close_waiting,
    get_waiting_threads,
    get_thread_waiting_state,
    mark_thread_waiting,
)
from app.services.preference_profile import build_preference_prompt_block, get_preference_profile, rebuild_preference_profile
from app.services.spam_service import annotate_spam_review_metadata, confirm_email_spam, restore_email_from_spam
from app.services.smtp_sender import send_reply
from app.services.language_service import normalize_language
from app.services.mailbox_service import get_outgoing_mailbox_for_email
from app.services.permission_service import require_permission
from app.services.sent_review_service import (
    dismiss_sent_review,
    mark_sent_review_helpful,
    review_sent_email,
    save_sent_review,
)
from app.services.template_service import get_template

router = APIRouter(prefix="/api/emails", tags=["emails"])
ALLOWED_STATUSES = {"new", "read", "archived", "spam", "replied"}


@router.get("", response_model=list[EmailListItem])
def list_emails(
    status: str | None = None,
    mailbox_id: str | None = None,
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
    waiting_by_thread = {item.thread_id: item for item in get_waiting_threads(db)}
    for email in emails:
        waiting_state = waiting_by_thread.get(email.thread_id or email.message_id or "")
        setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
        setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
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
    waiting_state = get_thread_waiting_state(db, email.thread_id or email.message_id or "")
    setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
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

    thread_id = email.thread_id or email.message_id
    if not thread_id:
        return EmailThreadResponse(thread_id=f"email-{email.id}", emails=[email])

    thread_emails = (
        db.query(Email)
        .filter(or_(Email.thread_id == thread_id, Email.message_id == thread_id))
        .order_by(Email.date_received.asc().nullsfirst(), Email.id.asc())
        .all()
    )
    if not thread_emails:
        thread_emails = [email]

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
    thread_key = original_email.thread_id or original_email.message_id or f"email-{original_email.id}"
    previous_waiting_state = get_thread_waiting_state(db, thread_key)

    to_addresses = request.to or ([original_email.sender_email] if original_email.sender_email else [])
    if not to_addresses:
        raise HTTPException(status_code=400, detail="Reply recipient could not be determined")

    subject = request.subject or _build_reply_subject(original_email.subject)
    references = _build_references(original_email)
    runtime_settings = get_effective_settings()
    outgoing_mailbox = get_outgoing_mailbox_for_email(original_email) or runtime_settings
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

    original_email.status = "replied"
    original_email.requires_reply = False
    original_email.last_reply_sent_at = datetime.utcnow()
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
            date_received=datetime.utcnow(),
            body_text=request.body,
            folder="sent",
            direction="sent",
            status="replied",
            ai_analyzed=True,
            sent_review_status="pending",
        )
        db.add(sent_email)
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

    mark_thread_waiting(
        db_session=db,
        thread_id=thread_key,
        started_at=datetime.utcnow(),
        email_id=original_email.id,
        actor="api",
    )

    _upsert_contact(db, original_email.sender_email, original_email.sender_name, increment_sent=True)
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
    if previous_waiting_state is not None:
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=original_email.id,
                task_id=previous_waiting_state.task_id,
                action_type="followup_sent",
                actor=current_user.email,
                details_json=json.dumps({"thread_id": thread_key}, ensure_ascii=False),
            )
        )
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
    rebuild_preference_profile(db)
    db.refresh(original_email)
    waiting_state = get_thread_waiting_state(db, original_email.thread_id or original_email.message_id or "")
    setattr(original_email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(original_email, "wait_days", waiting_state.wait_days if waiting_state else None)
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
    if email.direction != "sent":
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

    previous_spam_state = email.is_spam
    email.status = request.status
    if request.status == "spam":
        email.is_spam = True
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="ai_spam_confirmed",
                actor=current_user.email,
                details_json=json.dumps({"source": "status_update"}, ensure_ascii=False),
            )
        )
    elif previous_spam_state and request.status != "spam":
        email.is_spam = False
        db.add(
            ActionLog(
                user_id=current_user.id,
                email_id=email.id,
                action_type="ai_spam_restored",
                actor=current_user.email,
                details_json=json.dumps({"source": "status_update", "new_status": request.status}, ensure_ascii=False),
            )
        )
    db.add(email)
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type=f"status_updated:{request.status}",
            actor=current_user.email,
            details_json=json.dumps({"status": request.status}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(email)
    waiting_state = get_thread_waiting_state(db, email.thread_id or email.message_id or "")
    setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
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

    restore_email_from_spam(db, email, actor=current_user.email)
    db.commit()
    rebuild_preference_profile(db)
    db.refresh(email)
    waiting_state = get_thread_waiting_state(db, email.thread_id or email.message_id or "")
    setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
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

    confirm_email_spam(db, email, actor=current_user.email)
    db.commit()
    rebuild_preference_profile(db)
    db.refresh(email)
    waiting_state = get_thread_waiting_state(db, email.thread_id or email.message_id or "")
    setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
    annotate_spam_review_metadata(db, [email])
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
    file_path = get_attachment_file_path(attachment)
    if not file_path.exists():
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
        filename=attachment.filename or file_path.name,
        media_type=attachment.content_type or "application/octet-stream",
    )


@router.post("/{email_id}/waiting/start", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def start_waiting(
    email_id: int,
    request: WaitingStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("assign_items")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    mark_thread_waiting(
        db_session=db,
        thread_id=email.thread_id or email.message_id or f"email-{email.id}",
        started_at=datetime.utcnow(),
        expected_reply_by=request.expected_reply_by,
        email_id=email.id,
        actor=current_user.email,
    )
    db.commit()
    db.refresh(email)
    waiting_state = get_thread_waiting_state(db, email.thread_id or email.message_id or "")
    setattr(email, "waiting_state", waiting_state.state if waiting_state else None)
    setattr(email, "wait_days", waiting_state.wait_days if waiting_state else None)
    return email


@router.post("/{email_id}/waiting/close", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def stop_waiting(
    email_id: int,
    request: WaitingCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("assign_items")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    close_waiting(
        db_session=db,
        thread_id=email.thread_id or email.message_id or f"email-{email.id}",
        reason=request.reason or "closed_by_user",
        actor=current_user.email,
    )
    db.commit()
    db.refresh(email)
    setattr(email, "waiting_state", None)
    setattr(email, "wait_days", None)
    return email


@router.post("/{email_id}/followup-draft", response_model=FollowupDraftResponse, responses={404: {"model": ErrorResponse}})
def create_followup_draft(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("send_email")),
) -> FollowupDraftResponse:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    thread_key = email.thread_id or email.message_id or f"email-{email.id}"
    waiting_state = get_thread_waiting_state(db, thread_key)
    if waiting_state is None:
        raise HTTPException(status_code=400, detail="Thread is not currently waiting for reply")

    thread_history = (
        db.query(Email)
        .filter(or_(Email.thread_id == thread_key, Email.message_id == thread_key))
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(5)
        .all()
    )
    preference_block = build_preference_prompt_block(get_preference_profile(db))
    draft = generate_followup_draft(email, thread_history, waiting_state.wait_days, get_effective_settings(), preference_block=preference_block)
    task = db.query(Task).filter(Task.id == waiting_state.task_id).first()
    if task is not None:
        task.followup_draft = draft
        db.add(task)
    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            task_id=waiting_state.task_id,
            action_type="followup_generated",
            actor=current_user.email,
            details_json=json.dumps({"thread_id": thread_key}, ensure_ascii=False),
        )
    )
    db.commit()
    return FollowupDraftResponse(thread_id=thread_key, draft_reply=draft)


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
    result = generate_personalized_draft(
        email_record=email,
        thread_history=thread_history,
        config=get_effective_settings(),
        target_language=request.target_language,
        template_id=request.template_id,
        tone=request.tone,
        length=request.length,
        preference_block=preference_block,
    )
    email.ai_draft_reply = result.draft_reply
    email.preferred_reply_language = result.target_language
    db.add(email)
    details = {
        "target_language": result.target_language,
        "subject": result.subject,
        "template_id": request.template_id,
        "tone": request.tone,
        "length": request.length,
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
    result = rewrite_draft(
        email_record=email,
        current_draft=request.current_draft,
        instruction=request.instruction,
        config=get_effective_settings(),
        target_language=request.target_language,
        preference_block=preference_block,
    )
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


@router.post("/{email_id}/assign", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def assign_email(
    email_id: int,
    request: EmailAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("assign_items")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    target_user = db.query(User).filter(User.id == request.user_id, User.is_active.is_(True)).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found")

    email.assigned_to_user_id = target_user.id
    email.assigned_by_user_id = current_user.id
    email.assigned_at = datetime.utcnow()
    db.add(email)

    thread_key = email.thread_id or email.message_id
    if thread_key:
        tasks = db.query(Task).filter(Task.thread_id == thread_key).all()
        for task in tasks:
            task.assigned_to_user_id = target_user.id
            task.assigned_by_user_id = current_user.id
            task.assigned_at = datetime.utcnow()
            task.assigned_to = target_user.email
            db.add(task)

    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type="email_assigned",
            actor=current_user.email,
            details_json=json.dumps(
                {
                    "assigned_to_user_id": target_user.id,
                    "assigned_to_email": target_user.email,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


@router.post("/{email_id}/unassign", response_model=EmailDetail, responses={404: {"model": ErrorResponse}})
def unassign_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("assign_items")),
) -> Email:
    email = db.query(Email).filter(Email.id == email_id).first()
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    email.assigned_to_user_id = None
    email.assigned_by_user_id = current_user.id
    email.assigned_at = datetime.utcnow()
    db.add(email)

    thread_key = email.thread_id or email.message_id
    if thread_key:
        tasks = db.query(Task).filter(Task.thread_id == thread_key).all()
        for task in tasks:
            task.assigned_to_user_id = None
            task.assigned_by_user_id = current_user.id
            task.assigned_at = datetime.utcnow()
            task.assigned_to = None
            db.add(task)

    db.add(
        ActionLog(
            user_id=current_user.id,
            email_id=email.id,
            action_type="email_unassigned",
            actor=current_user.email,
            details_json=json.dumps({}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(email)
    _attach_attachment_counts(db, [email])
    return email


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
        contact.last_contact_at = datetime.utcnow()
    if increment_sent:
        contact.emails_sent_count = int(contact.emails_sent_count or 0) + 1
        contact.last_contact_at = datetime.utcnow()
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
