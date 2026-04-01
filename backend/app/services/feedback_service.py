import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email


@dataclass(slots=True)
class DraftFeedbackResult:
    action_type: str
    inferred_tags: list[str]


def log_feedback_event(
    db_session: Session,
    action_type: str,
    email_id: int | None = None,
    actor: str = "user",
    task_id: int | None = None,
    details: dict | None = None,
) -> ActionLog:
    entry = ActionLog(
        email_id=email_id,
        task_id=task_id,
        action_type=action_type,
        actor=actor,
        details_json=json.dumps(details or {}, ensure_ascii=False),
    )
    db_session.add(entry)
    return entry


def record_decision_feedback(
    db_session: Session,
    email: Email,
    decision_type: str,
    verdict: str,
    details: dict | None = None,
    actor: str = "user",
) -> list[str]:
    payload = details.copy() if details else {}
    payload.update(
        {
            "decision_type": decision_type,
            "verdict": verdict,
            "current_priority": email.priority,
            "current_category": email.category,
            "current_spam": email.is_spam,
        }
    )
    created_events: list[str] = []

    if decision_type == "spam":
        if verdict in {"confirm_spam", "agree"}:
            email.is_spam = True
            email.status = "spam"
            created_events.append("ai_spam_confirmed")
        elif verdict in {"restore_spam", "disagree"}:
            email.is_spam = False
            if email.status == "spam":
                email.status = "read"
            created_events.append("ai_spam_restored")
    elif decision_type == "priority":
        old_priority = email.priority
        if verdict == "mark_important":
            email.priority = "high"
        elif verdict == "mark_not_important":
            email.priority = "low"
        elif payload.get("new_priority"):
            email.priority = str(payload["new_priority"])
        if email.priority != old_priority:
            payload["old_priority"] = old_priority
            payload["new_priority"] = email.priority
            created_events.append("ai_priority_changed")
    elif decision_type == "category" and payload.get("new_category"):
        old_category = email.category
        email.category = str(payload["new_category"])
        if email.category != old_category:
            payload["old_category"] = old_category
            payload["new_category"] = email.category
            created_events.append("ai_decision_rejected")

    if verdict in {"agree", "useful", "confirm_spam"}:
        created_events.append("ai_decision_approved")
    elif verdict in {"disagree", "bad", "restore_spam"}:
        created_events.append("ai_decision_rejected")

    if not created_events:
        created_events.append("ai_decision_approved" if verdict in {"agree", "useful"} else "ai_decision_rejected")

    for event_type in dict.fromkeys(created_events):
        log_feedback_event(
            db_session=db_session,
            action_type=event_type,
            email_id=email.id,
            actor=actor,
            details=payload,
        )

    db_session.add(email)
    return created_events


def record_draft_feedback(
    db_session: Session,
    email: Email,
    original_draft: str | None,
    final_draft: str | None,
    edit_type_tags: Iterable[str] | None = None,
    send_status: str | None = None,
    actor: str = "user",
) -> DraftFeedbackResult:
    original = (original_draft or "").strip()
    final = (final_draft or "").strip()
    inferred_tags = infer_edit_type_tags(original, final)
    if edit_type_tags:
        inferred_tags = list(dict.fromkeys([*inferred_tags, *[tag for tag in edit_type_tags if tag]]))

    changed = bool(original and final and original != final)
    if changed:
        log_feedback_event(
            db_session=db_session,
            action_type="draft_edited",
            email_id=email.id,
            actor=actor,
            details={
                "original_draft": original,
                "final_draft": final,
                "edit_type_tags": inferred_tags,
            },
        )
        if inferred_tags:
            log_feedback_event(
                db_session=db_session,
                action_type="rewrite_applied",
                email_id=email.id,
                actor=actor,
                details={"edit_type_tags": inferred_tags},
            )

    action_type = "draft_generated"
    if send_status == "sent":
        action_type = "draft_sent_after_edit" if changed else "draft_sent_as_is"
    elif changed:
        action_type = "draft_edited"

    log_feedback_event(
        db_session=db_session,
        action_type=action_type,
        email_id=email.id,
        actor=actor,
        details={
            "original_draft": original_draft,
            "final_draft": final_draft,
            "edit_type_tags": inferred_tags,
            "send_status": send_status,
        },
    )
    return DraftFeedbackResult(action_type=action_type, inferred_tags=inferred_tags)


def infer_edit_type_tags(original_draft: str | None, final_draft: str | None) -> list[str]:
    original = (original_draft or "").strip()
    final = (final_draft or "").strip()
    if not original or not final:
        return []

    tags: list[str] = []
    if len(final) < len(original) * 0.85:
        tags.append("shorter")
    if len(final) > len(original) * 1.15:
        tags.append("longer")

    original_cyrillic = _contains_cyrillic(original)
    final_cyrillic = _contains_cyrillic(final)
    if final_cyrillic and not original_cyrillic:
        tags.append("translated_russian")
    elif original_cyrillic and not final_cyrillic:
        tags.append("translated_english")
    if _contains_turkish_chars(final) and not _contains_turkish_chars(original):
        tags.append("translated_turkish")

    if _count_matches(final, FORMAL_PATTERNS) > _count_matches(original, FORMAL_PATTERNS):
        tags.append("more_formal")
    if _count_matches(final, SOFTENING_PATTERNS) > _count_matches(original, SOFTENING_PATTERNS):
        tags.append("softened_tone")
    if _count_matches(final, DEADLINE_PATTERNS) > _count_matches(original, DEADLINE_PATTERNS):
        tags.append("deadline_emphasis")
    if len(final.split("?")) > len(original.split("?")) or "please confirm" in final.lower() or "пожалуйста подтвердите" in final.lower():
        tags.append("clarified_request")

    return list(dict.fromkeys(tags))


FORMAL_PATTERNS = [
    r"\bplease\b",
    r"\bkindly\b",
    r"\bregards\b",
    r"\bуважаем",
    r"\bс уважением\b",
]
SOFTENING_PATTERNS = [
    r"\bthank you\b",
    r"\bappreciate\b",
    r"\bбудем признательны\b",
    r"\bспасибо\b",
]
DEADLINE_PATTERNS = [
    r"\bdeadline\b",
    r"\bdue\b",
    r"\burgent\b",
    r"\bсрок\b",
    r"\bсегодня\b",
    r"\bзавтра\b",
]


def _count_matches(text: str, patterns: list[str]) -> int:
    lowered = text.lower()
    return sum(len(re.findall(pattern, lowered)) for pattern in patterns)


def _contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04ff" for char in text)


def _contains_turkish_chars(text: str) -> bool:
    return any(char in "ğüşöçıİ" for char in text)
