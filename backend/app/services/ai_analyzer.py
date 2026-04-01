import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.action_log import ActionLog
from app.models.email import Email
from app.services.language_service import choose_reply_language, normalize_language, update_email_languages
from app.services.preference_profile import build_preference_prompt_block, get_preference_profile
from app.services.rule_engine import apply_rules_to_email, is_trusted_sender
from app.services.template_service import get_template, render_template_context

logger = logging.getLogger(__name__)

VALID_PRIORITIES = {"critical", "high", "medium", "low", "spam"}
VALID_CATEGORIES = {"RFQ", "Invoice", "Logistics", "Support", "Spam", "Other"}


class AnalysisResult(BaseModel):
    summary: str
    priority: str = "medium"
    category: str = "Other"
    action_required: bool = False
    action_description: str | None = None
    key_dates: list[str] = []
    key_amounts: list[str] = []
    draft_reply: str | None = None
    confidence: float | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def validate_priority(cls, value: object) -> str:
        if isinstance(value, str) and value.lower() in VALID_PRIORITIES:
            return value.lower()
        return "medium"

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, value: object) -> str:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lower() == "spam":
                return "Spam"
            if normalized in VALID_CATEGORIES:
                return normalized
        return "Other"

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "No summary generated."

    @field_validator("action_description", "draft_reply", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value)

    @field_validator("key_dates", "key_amounts", mode="before")
    @classmethod
    def normalize_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, confidence))


@dataclass(slots=True)
class AnalyzePendingSummary:
    selected_count: int
    analyzed_count: int
    failed_count: int
    skipped_count: int
    errors: list[str]


class DraftResponse(BaseModel):
    draft_reply: str
    subject: str | None = None
    target_language: str

    @field_validator("draft_reply", mode="before")
    @classmethod
    def validate_draft_reply(cls, value: object) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise ValueError("draft_reply is required")

    @field_validator("subject", mode="before")
    @classmethod
    def normalize_subject(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value)

    @field_validator("target_language", mode="before")
    @classmethod
    def validate_language(cls, value: object) -> str:
        normalized = normalize_language(str(value) if value is not None else None)
        return normalized or "ru"


def build_system_prompt(config, preference_block: str | None = None) -> str:
    base_prompt = (
        "You are an email assistant for Orhun Medical, a network of medical centers "
        "in Kazakhstan. You analyze incoming emails and provide structured analysis. "
        "The company receives emails from medical equipment suppliers, logistics "
        "companies, and partners. The primary language of correspondence is Russian "
        "and English. Always respond in JSON format only, no markdown, no preamble."
    )
    if preference_block:
        return f"{base_prompt}\n\n{preference_block}"
    return base_prompt


def build_user_payload(email_record: Email, thread_history: list[Email]) -> str:
    payload = {
        "current_email": {
            "id": email_record.id,
            "subject": email_record.subject,
            "from": {
                "name": email_record.sender_name,
                "email": email_record.sender_email,
            },
            "to": email_record.recipients_json,
            "cc": email_record.cc_json,
            "date_received": email_record.date_received.isoformat() if email_record.date_received else None,
            "body_text": _truncate(email_record.body_text, 8000),
            "body_html": _truncate(email_record.body_html, 4000),
        },
        "thread_history": [
            {
                "id": item.id,
                "subject": item.subject,
                "from": item.sender_email,
                "date_received": item.date_received.isoformat() if item.date_received else None,
                "summary_hint": _truncate(item.ai_summary or item.body_text, 1500),
            }
            for item in thread_history
        ],
        "expected_json_schema": {
            "summary": "2-3 sentence summary",
            "priority": "critical|high|medium|low|spam",
            "category": "RFQ|Invoice|Logistics|Support|Spam|Other",
            "action_required": True,
            "action_description": "what needs to be done",
            "key_dates": ["2026-04-03"],
            "key_amounts": ["$5000"],
            "draft_reply": "reply draft text or null",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def analyze_email(
    email_record: Email,
    thread_history: list[Email],
    config,
    preference_block: str | None = None,
) -> AnalysisResult:
    system_prompt = build_system_prompt(config, preference_block=preference_block)
    user_payload = build_user_payload(email_record, thread_history)
    last_error: Exception | None = None

    for attempt in range(1, max(1, config.ai_max_retries) + 1):
        try:
            response_text = _call_model_once(
                system_prompt=system_prompt,
                user_payload=user_payload,
                config=config,
            )
            parsed_json = _extract_json_object(response_text)
            return AnalysisResult.model_validate(parsed_json)
        except (ValueError, ValidationError) as exc:
            last_error = exc
            logger.warning("AI analysis parse/validation failed on attempt %s: %s", attempt, exc)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("AI analysis request failed on attempt %s: %s", attempt, exc)

        if attempt < max(1, config.ai_max_retries):
            time.sleep(min(2 * attempt, 5))

    raise RuntimeError(f"DeepSeek analysis failed after retries: {last_error}")


def generate_followup_draft(
    email_record: Email,
    thread_history: list[Email],
    wait_days: int,
    config,
    preference_block: str | None = None,
) -> str:
    system_prompt = (
        "You are an email assistant for Orhun Medical in Kazakhstan. "
        "Write a concise professional follow-up email in the same language as the thread "
        "when possible. Return JSON only."
    )
    if preference_block:
        system_prompt = f"{system_prompt}\n\n{preference_block}"
    payload = {
        "task": "generate_followup_draft",
        "wait_days": wait_days,
        "current_email": {
            "subject": email_record.subject,
            "sender_email": email_record.sender_email,
            "sender_name": email_record.sender_name,
            "body_text": _truncate(email_record.body_text, 5000),
            "ai_summary": email_record.ai_summary,
        },
        "thread_history": [
            {
                "subject": item.subject,
                "sender_email": item.sender_email,
                "date_received": item.date_received.isoformat() if item.date_received else None,
                "body_text": _truncate(item.body_text, 1400),
                "ai_summary": item.ai_summary,
            }
            for item in thread_history[:5]
        ],
        "expected_json_schema": {
            "draft_reply": "short professional follow-up email"
        },
    }
    response_text = _call_model_once(
        system_prompt=system_prompt,
        user_payload=json.dumps(payload, ensure_ascii=False),
        config=config,
    )
    parsed_json = _extract_json_object(response_text)
    draft = parsed_json.get("draft_reply")
    if not isinstance(draft, str) or not draft.strip():
        raise ValueError("Model did not return a valid follow-up draft")
    return draft.strip()


def analyze_pending(db_session: Session, config, limit: int | None = None) -> AnalyzePendingSummary:
    preference_block = build_preference_prompt_block(get_preference_profile(db_session))
    query = (
        db_session.query(Email)
        .filter(or_(Email.ai_analyzed.is_(False), Email.ai_analyzed.is_(None)))
        .order_by(Email.date_received.asc().nullsfirst(), Email.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)

    pending_emails = query.all()
    analyzed_count = 0
    failed_count = 0
    skipped_count = 0
    errors: list[str] = []

    for email_record in pending_emails:
        if not (email_record.body_text or email_record.body_html or email_record.subject):
            skipped_count += 1
            continue

        thread_history = _load_thread_history(db_session, email_record)
        try:
            result = analyze_email(email_record, thread_history, config, preference_block=preference_block)
            save_analysis_result(db_session, email_record, result)
            analyzed_count += 1
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            failed_count += 1
            error_message = f"Email {email_record.id} analysis failed: {exc}"
            errors.append(error_message)
            logger.exception(error_message)

    return AnalyzePendingSummary(
        selected_count=len(pending_emails),
        analyzed_count=analyzed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        errors=errors,
    )


def save_analysis_result(db_session: Session, email_record: Email, analysis_result: AnalysisResult) -> None:
    contact = None
    if email_record.sender_email:
        contact = db_session.query(Contact).filter(Contact.email == email_record.sender_email).first()
    update_email_languages(email_record, contact=contact)
    email_record.ai_summary = analysis_result.summary
    email_record.priority = analysis_result.priority
    email_record.category = analysis_result.category
    email_record.requires_reply = analysis_result.action_required
    email_record.action_description = analysis_result.action_description
    email_record.key_dates_json = json.dumps(analysis_result.key_dates, ensure_ascii=False)
    email_record.key_amounts_json = json.dumps(analysis_result.key_amounts, ensure_ascii=False)
    if not email_record.ai_draft_reply:
        email_record.ai_draft_reply = analysis_result.draft_reply
        if analysis_result.draft_reply:
            db_session.add(
                ActionLog(
                    email_id=email_record.id,
                    action_type="draft_generated",
                    actor="ai",
                    details_json=json.dumps(
                        {
                            "draft_reply": analysis_result.draft_reply,
                            "source": "email_analysis",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
    ai_marked_spam = analysis_result.category == "Spam" or analysis_result.priority == "spam"
    if ai_marked_spam and not is_trusted_sender(email_record):
        email_record.is_spam = True
        email_record.status = "spam"
        email_record.spam_source = "ai"
        email_record.spam_reason = f"AI classified as {analysis_result.category or analysis_result.priority}"
    elif email_record.spam_source == "ai":
        email_record.is_spam = False
        email_record.spam_source = None
        email_record.spam_reason = None
    email_record.ai_analyzed = True
    if analysis_result.confidence is not None:
        email_record.ai_confidence = analysis_result.confidence
    db_session.add(email_record)
    db_session.flush()
    apply_rules_to_email(db_session, email_record, source="ai")
    db_session.commit()
    db_session.refresh(email_record)


def generate_personalized_draft(
    email_record: Email,
    thread_history: list[Email],
    config,
    target_language: str | None = None,
    template_id: str | None = None,
    tone: str | None = None,
    length: str | None = None,
    preference_block: str | None = None,
) -> DraftResponse:
    language = choose_reply_language(email_record, explicit_language=target_language)
    template = get_template(template_id) if template_id else None
    system_prompt = (
        "You are an email assistant for Orhun Medical in Kazakhstan. "
        "Generate a professional business email draft in the requested target language. "
        "If a template is provided, preserve its intention and structure while personalizing it to the thread. "
        "Always return JSON only."
    )
    if preference_block:
        system_prompt = f"{system_prompt}\n\n{preference_block}"

    payload = {
        "task": "generate_personalized_draft",
        "target_language": language,
        "tone": tone or "professional",
        "length": length or "medium",
        "current_email": {
            "subject": email_record.subject,
            "sender_name": email_record.sender_name,
            "sender_email": email_record.sender_email,
            "body_text": _truncate(email_record.body_text, 5000),
            "ai_summary": email_record.ai_summary,
            "detected_source_language": email_record.detected_source_language,
        },
        "thread_history": [
            {
                "subject": item.subject,
                "sender_email": item.sender_email,
                "body_text": _truncate(item.body_text, 1400),
                "date_received": item.date_received.isoformat() if item.date_received else None,
            }
            for item in thread_history[:5]
        ],
        "template_context": render_template_context(
            template,
            {
                "subject": email_record.subject,
                "recipient_name": email_record.sender_name or email_record.sender_email or "colleague",
            },
        ) if template else None,
        "expected_json_schema": {
            "draft_reply": "personalized business email draft",
            "subject": "reply subject or null",
            "target_language": language,
        },
    }
    response_text = _call_model_once(
        system_prompt=system_prompt,
        user_payload=json.dumps(payload, ensure_ascii=False),
        config=config,
    )
    return DraftResponse.model_validate(_extract_json_object(response_text))


def rewrite_draft(
    email_record: Email,
    current_draft: str,
    instruction: str,
    config,
    target_language: str | None = None,
    preference_block: str | None = None,
) -> DraftResponse:
    language = choose_reply_language(email_record, explicit_language=target_language)
    system_prompt = (
        "You are an email assistant for Orhun Medical in Kazakhstan. "
        "Rewrite the provided draft according to the user instruction. "
        "Keep the business intent intact, preserve important facts, and return JSON only."
    )
    if preference_block:
        system_prompt = f"{system_prompt}\n\n{preference_block}"
    payload = {
        "task": "rewrite_draft",
        "target_language": language,
        "instruction": instruction,
        "current_email": {
            "subject": email_record.subject,
            "sender_name": email_record.sender_name,
            "sender_email": email_record.sender_email,
            "ai_summary": email_record.ai_summary,
        },
        "draft": current_draft,
        "expected_json_schema": {
            "draft_reply": "rewritten business email draft",
            "subject": "updated subject or null",
            "target_language": language,
        },
    }
    response_text = _call_model_once(
        system_prompt=system_prompt,
        user_payload=json.dumps(payload, ensure_ascii=False),
        config=config,
    )
    return DraftResponse.model_validate(_extract_json_object(response_text))


def _call_model_once(system_prompt: str, user_payload: str, config) -> str:
    client = _create_openai_client(config)
    response = client.chat.completions.create(
        model=config.deepseek_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty model response")
    return content


def _create_openai_client(config):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai package is required for AI analysis") from exc

    if not config.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    return OpenAI(
        api_key=config.openai_api_key,
        base_url=config.deepseek_base_url,
        timeout=config.ai_timeout_seconds,
    )


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    candidate = raw_response.strip()
    if candidate.startswith("```"):
        lines = [line for line in candidate.splitlines() if not line.strip().startswith("```")]
        candidate = "\n".join(lines).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response does not contain a JSON object")

    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Model JSON response must be an object")
    return parsed


def _load_thread_history(db_session: Session, email_record: Email) -> list[Email]:
    if not email_record.thread_id:
        return []

    return (
        db_session.query(Email)
        .filter(Email.thread_id == email_record.thread_id, Email.id != email_record.id)
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(5)
        .all()
    )


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
