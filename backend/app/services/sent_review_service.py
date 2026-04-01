import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email
from app.services.preference_profile import get_preference_profile

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"good", "needs_attention", "problematic"}


class SentReviewResult(BaseModel):
    summary: str
    verdict: str = "good"
    issues: list[str] = []
    suggested_improvement: str | None = None
    score: float | None = None

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "No sent-review summary generated."

    @field_validator("verdict", mode="before")
    @classmethod
    def validate_verdict(cls, value: object) -> str:
        if isinstance(value, str) and value.strip().lower() in VALID_VERDICTS:
            return value.strip().lower()
        return "needs_attention"

    @field_validator("issues", mode="before")
    @classmethod
    def validate_issues(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @field_validator("suggested_improvement", mode="before")
    @classmethod
    def normalize_suggestion(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value)

    @field_validator("score", mode="before")
    @classmethod
    def validate_score(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(100.0, parsed))


@dataclass(slots=True)
class SentReviewBatchSummary:
    selected_count: int
    reviewed_count: int
    failed_count: int
    errors: list[str]


def review_pending_sent(db_session: Session, config, limit: int | None = None) -> SentReviewBatchSummary:
    query = (
        db_session.query(Email)
        .filter(
            Email.direction == "sent",
            or_(Email.sent_review_status.is_(None), Email.sent_review_status.in_(["pending"])),
        )
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
    )
    effective_limit = limit or int(getattr(config, "sent_review_batch_limit", 20) or 20)
    query = query.limit(max(1, effective_limit))
    pending = query.all()

    reviewed_count = 0
    failed_count = 0
    errors: list[str] = []
    preference_profile = get_preference_profile(db_session)
    for email_record in pending:
        thread_history = _load_thread_history(db_session, email_record)
        try:
            result = review_sent_email(
                email_record=email_record,
                thread_history=thread_history,
                preference_profile=preference_profile,
                config=config,
            )
            save_sent_review(db_session, email_record, result)
            reviewed_count += 1
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            failed_count += 1
            message = f"Sent review failed for email {email_record.id}: {exc}"
            errors.append(message)
            logger.warning(message)

    return SentReviewBatchSummary(
        selected_count=len(pending),
        reviewed_count=reviewed_count,
        failed_count=failed_count,
        errors=errors,
    )


def review_sent_email(
    email_record: Email,
    thread_history: list[Email],
    config,
    preference_profile: dict[str, Any] | None = None,
) -> SentReviewResult:
    payload = {
        "task": "review_sent_email_quality",
        "business_context": "Orhun Medical, Kazakhstan",
        "current_sent_email": {
            "id": email_record.id,
            "subject": email_record.subject,
            "body_text": _truncate(email_record.body_text, 7000),
            "sender_email": email_record.sender_email,
            "mailbox_name": email_record.mailbox_name,
            "language_hint": email_record.preferred_reply_language or email_record.detected_source_language,
        },
        "recent_thread_history": [
            {
                "id": item.id,
                "direction": item.direction,
                "subject": item.subject,
                "body_text": _truncate(item.body_text, 1800),
                "ai_summary": item.ai_summary,
                "date_received": item.date_received.isoformat() if item.date_received else None,
            }
            for item in thread_history[:6]
        ],
        "preferences_hint": {
            "summary_lines": (preference_profile or {}).get("summary_lines", [])[:4],
            "draft_preferences": (preference_profile or {}).get("draft_preferences", {}),
        },
        "evaluation_dimensions": [
            "tone_style_appropriateness",
            "response_completeness",
            "unanswered_questions",
            "deadline_commitment_clarity",
            "length_fit",
            "language_match",
        ],
        "expected_json_schema": {
            "summary": "short quality note",
            "verdict": "good|needs_attention|problematic",
            "issues": ["list of concrete issues"],
            "suggested_improvement": "optional fix suggestion",
            "score": 0,
        },
    }
    response_text = _call_model(
        system_prompt=(
            "You are an outgoing email quality reviewer for Orhun Medical. "
            "Review sent business emails for tone, completeness, clarity, and actionability. "
            "Respond in JSON only."
        ),
        user_payload=json.dumps(payload, ensure_ascii=False),
        config=config,
    )
    raw_json = _extract_json(response_text)
    return SentReviewResult.model_validate(raw_json)


def save_sent_review(db_session: Session, email_record: Email, review: SentReviewResult) -> None:
    now = datetime.utcnow()
    email_record.sent_review_summary = review.summary
    email_record.sent_review_status = review.verdict
    email_record.sent_review_issues_json = json.dumps(review.issues, ensure_ascii=False)
    email_record.sent_review_suggested_improvement = review.suggested_improvement
    email_record.sent_review_score = review.score
    email_record.sent_reviewed_at = now
    db_session.add(email_record)
    db_session.add(
        ActionLog(
            email_id=email_record.id,
            action_type="sent_review_generated",
            actor="ai",
            details_json=json.dumps(
                {
                    "verdict": review.verdict,
                    "issues": review.issues,
                    "score": review.score,
                },
                ensure_ascii=False,
            ),
        )
    )
    db_session.commit()
    db_session.refresh(email_record)


def dismiss_sent_review(db_session: Session, email_record: Email, actor: str = "user") -> None:
    email_record.sent_review_status = "dismissed"
    db_session.add(email_record)
    db_session.add(
        ActionLog(
            email_id=email_record.id,
            action_type="sent_review_dismissed",
            actor=actor,
            details_json=json.dumps({"email_id": email_record.id}, ensure_ascii=False),
        )
    )
    db_session.commit()


def mark_sent_review_helpful(db_session: Session, email_record: Email, actor: str = "user") -> None:
    db_session.add(
        ActionLog(
            email_id=email_record.id,
            action_type="sent_review_marked_helpful",
            actor=actor,
            details_json=json.dumps({"email_id": email_record.id}, ensure_ascii=False),
        )
    )
    db_session.commit()


def _load_thread_history(db_session: Session, email_record: Email) -> list[Email]:
    thread_id = email_record.thread_id or email_record.message_id
    if not thread_id:
        return []
    return (
        db_session.query(Email)
        .filter(or_(Email.thread_id == thread_id, Email.message_id == thread_id), Email.id != email_record.id)
        .order_by(Email.date_received.desc().nullslast(), Email.id.desc())
        .limit(8)
        .all()
    )


def _call_model(system_prompt: str, user_payload: str, config) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai package is required for sent review") from exc

    if not getattr(config, "openai_api_key", None):
        raise ValueError("OPENAI_API_KEY is not configured")

    client = OpenAI(
        api_key=config.openai_api_key,
        base_url=getattr(config, "deepseek_base_url", "https://api.deepseek.com"),
        timeout=getattr(config, "ai_timeout_seconds", 60),
    )

    retries = max(1, int(getattr(config, "ai_max_retries", 3) or 3))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=getattr(config, "deepseek_model", "deepseek-chat"),
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
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 * attempt, 5))
    raise RuntimeError(f"sent-review model call failed: {last_error}")


def _extract_json(raw: str) -> dict[str, Any]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = [line for line in candidate.splitlines() if not line.strip().startswith("```")]
        candidate = "\n".join(lines).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response does not contain JSON object")
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON response must be object")
    return parsed


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
