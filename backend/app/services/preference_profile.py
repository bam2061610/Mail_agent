import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.action_log import ActionLog

PREFERENCE_PROFILE_PATH = DATA_DIR / "preference_profile.json"


def rebuild_preference_profile(db_session: Session) -> dict[str, Any]:
    logs = db_session.query(ActionLog).order_by(ActionLog.created_at.asc()).all()
    draft_tag_counter: Counter[str] = Counter()
    decision_counter: Counter[str] = Counter()
    language_counter: Counter[str] = Counter()
    spam_counter: Counter[str] = Counter()
    priority_counter: Counter[str] = Counter()

    for log in logs:
        details = _parse_details(log.details_json)
        if log.action_type in {"draft_edited", "draft_sent_after_edit", "rewrite_applied"}:
            for tag in details.get("edit_type_tags", []) or []:
                draft_tag_counter[str(tag)] += 1
                if str(tag).startswith("translated_"):
                    language_counter[str(tag).replace("translated_", "")] += 1
        if log.action_type in {"ai_decision_approved", "ai_decision_rejected"}:
            decision_type = str(details.get("decision_type") or "unknown")
            decision_counter[f"{decision_type}:{'approved' if log.action_type.endswith('approved') else 'rejected'}"] += 1
        if log.action_type in {"ai_spam_confirmed", "ai_spam_restored"}:
            spam_counter[log.action_type] += 1
        if log.action_type == "ai_priority_changed":
            new_priority = str(details.get("new_priority") or "unknown")
            priority_counter[new_priority] += 1

    summary_lines = _build_summary_lines(draft_tag_counter, language_counter, spam_counter, priority_counter)
    profile = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft_preferences": {
            "prefers_shorter_drafts": draft_tag_counter["shorter"] > draft_tag_counter["longer"],
            "prefers_formal_tone": draft_tag_counter["more_formal"] >= max(1, draft_tag_counter["softened_tone"]),
            "common_rewrite_tags": [tag for tag, _ in draft_tag_counter.most_common(6)],
            "preferred_languages": [language for language, _ in language_counter.most_common(3)],
        },
        "decision_preferences": {
            "priority_adjustments": dict(priority_counter),
            "spam_confirmed_count": spam_counter["ai_spam_confirmed"],
            "spam_restored_count": spam_counter["ai_spam_restored"],
            "decision_feedback": dict(decision_counter),
        },
        "summary_lines": summary_lines,
    }
    _save_profile(profile)
    return profile


def load_preference_profile() -> dict[str, Any] | None:
    if not PREFERENCE_PROFILE_PATH.exists():
        return None
    try:
        return json.loads(PREFERENCE_PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_preference_profile(db_session: Session) -> dict[str, Any]:
    stored = load_preference_profile()
    if stored:
        return stored
    return rebuild_preference_profile(db_session)


def build_preference_prompt_block(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    lines = profile.get("summary_lines") or []
    if not lines:
        return ""
    return "User preference signals:\n- " + "\n- ".join(lines[:4])


def _save_profile(profile: dict[str, Any]) -> None:
    PREFERENCE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCE_PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_details(raw_details: str | None) -> dict[str, Any]:
    if not raw_details:
        return {}
    try:
        parsed = json.loads(raw_details)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_summary_lines(
    draft_tags: Counter[str],
    languages: Counter[str],
    spam_counter: Counter[str],
    priority_counter: Counter[str],
) -> list[str]:
    lines: list[str] = []
    if draft_tags["shorter"] > draft_tags["longer"]:
        lines.append("User often shortens drafts before sending.")
    if draft_tags["more_formal"] > 0:
        lines.append("User prefers more formal email tone.")
    if languages:
        top_language = languages.most_common(1)[0][0]
        lines.append(f"User frequently rewrites drafts into {top_language}.")
    if spam_counter["ai_spam_restored"] > spam_counter["ai_spam_confirmed"]:
        lines.append("User restores spam decisions relatively often; be conservative with spam labels.")
    if priority_counter:
        top_priority = priority_counter.most_common(1)[0][0]
        lines.append(f"User often changes priority to {top_priority}.")
    return lines
