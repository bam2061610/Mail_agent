import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db import open_global_session
from app.models.action_log import ActionLog
from app.models.email import Email
from app.models.rule import Rule

logger = logging.getLogger(__name__)

RULES_FILE_PATH = DATA_DIR / "rules.json"
RULES_MIGRATED_FILE_PATH = DATA_DIR / "rules.json.migrated"
SUPPORTED_CONDITIONS = {
    "sender_email",
    "sender_domain",
    "subject_contains",
    "has_auto_reply_headers",
    "category",
    "priority",
    "direction",
}
SUPPORTED_ACTIONS = {
    "set_priority",
    "set_category",
    "mark_spam",
    "archive",
    "trust_sender",
    "never_spam",
    "move_to_focus",
    "add_tag",
}


@dataclass(slots=True)
class RuleEvaluationResult:
    matched_rules: list[dict[str, Any]] = field(default_factory=list)
    applied_actions: list[str] = field(default_factory=list)
    spam_changed: bool = False
    archived: bool = False
    moved_to_focus: bool = False


def list_rules() -> list[dict[str, Any]]:
    _migrate_legacy_rules_if_needed()
    db = open_global_session()
    try:
        rows = db.execute(select(Rule).order_by(Rule.priority.asc(), Rule.created_at.asc())).scalars().all()
        return [_rule_to_dict(row) for row in rows]
    finally:
        db.close()


def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    _migrate_legacy_rules_if_needed()
    db = open_global_session()
    try:
        now = datetime.now(timezone.utc)
        current_priority = payload.get("order")
        if current_priority is None:
            current_priority = (
                db.execute(select(Rule.priority).order_by(Rule.priority.desc()).limit(1)).scalar_one_or_none() or -1
            ) + 1
        rule = Rule(
            id=str(payload.get("id") or uuid4()),
            name=str(payload.get("name") or "Untitled rule").strip() or "Untitled rule",
            enabled=bool(payload.get("enabled", True)),
            priority=int(current_priority),
            conditions_json=json.dumps(_sanitize_conditions(payload.get("conditions")), ensure_ascii=False),
            actions_json=json.dumps(_sanitize_actions(payload.get("actions")), ensure_ascii=False),
            created_at=payload.get("created_at") or now,
            updated_at=now,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return _rule_to_dict(rule)
    finally:
        db.close()


def update_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    _migrate_legacy_rules_if_needed()
    db = open_global_session()
    try:
        rule = db.get(Rule, rule_id)
        if rule is None:
            return None
        if "name" in payload and payload["name"] is not None:
            rule.name = str(payload["name"]).strip() or rule.name
        if "enabled" in payload and payload["enabled"] is not None:
            rule.enabled = bool(payload["enabled"])
        if "order" in payload and payload["order"] is not None:
            rule.priority = int(payload["order"])
        if "conditions" in payload and payload["conditions"] is not None:
            rule.conditions_json = json.dumps(_sanitize_conditions(payload["conditions"]), ensure_ascii=False)
        if "actions" in payload and payload["actions"] is not None:
            rule.actions_json = json.dumps(_sanitize_actions(payload["actions"]), ensure_ascii=False)
        rule.updated_at = datetime.now(timezone.utc)
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return _rule_to_dict(rule)
    finally:
        db.close()


def delete_rule(rule_id: str) -> bool:
    _migrate_legacy_rules_if_needed()
    db = open_global_session()
    try:
        rule = db.get(Rule, rule_id)
        if rule is None:
            return False
        db.delete(rule)
        db.commit()
        return True
    finally:
        db.close()


def reorder_rules(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _migrate_legacy_rules_if_needed()
    order_map = {str(item.get("id")): int(item.get("order", 0)) for item in items if item.get("id")}
    db = open_global_session()
    try:
        rows = db.execute(select(Rule).where(Rule.id.in_(tuple(order_map.keys())))).scalars().all()
        for row in rows:
            row.priority = order_map[row.id]
            row.updated_at = datetime.now(timezone.utc)
            db.add(row)
        db.commit()
    finally:
        db.close()
    return list_rules()


def apply_rules_to_email(
    db_session: Session,
    email: Email,
    source: str = "system",
) -> RuleEvaluationResult:
    result = RuleEvaluationResult()
    matched_rule_records: list[dict[str, Any]] = []
    spam_protected = False

    for rule in list_rules():
        if not rule.get("enabled", True):
            continue
        matched_fields = _match_rule(rule, email)
        if matched_fields is None:
            continue

        matched_rule_records.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "order": rule["order"],
                "matched_fields": matched_fields,
                "actions": rule["actions"],
            }
        )
        result.matched_rules.append(rule)
        _log_rule_applied(db_session, email, rule, matched_fields, source)
        actions = rule.get("actions", {})

        if actions.get("trust_sender") or actions.get("never_spam"):
            spam_protected = True
            if email.is_spam or email.status == "spam":
                result.spam_changed = True
            email.is_spam = False
            if email.status == "spam":
                email.status = "read"
            email.spam_source = None
            email.spam_reason = None
            result.applied_actions.extend(
                action_name
                for action_name in ("trust_sender", "never_spam")
                if actions.get(action_name)
            )

        if actions.get("set_priority"):
            email.priority = str(actions["set_priority"]).lower()
            result.applied_actions.append("set_priority")

        if actions.get("set_category"):
            email.category = str(actions["set_category"])
            result.applied_actions.append("set_category")

        if actions.get("move_to_focus"):
            email.focus_flag = True
            result.moved_to_focus = True
            result.applied_actions.append("move_to_focus")

        if actions.get("archive"):
            email.status = "archived"
            result.archived = True
            result.applied_actions.append("archive")

        if actions.get("mark_spam") and not spam_protected:
            email.is_spam = True
            email.status = "spam"
            email.spam_source = "rule"
            email.spam_reason = f"Matched rule: {rule['name']}"
            result.spam_changed = True
            result.applied_actions.append("mark_spam")
            db_session.add(
                ActionLog(
                    email_id=email.id,
                    action_type="email_marked_spam",
                    actor="rule_engine",
                    details_json=json.dumps(
                        {
                            "source": "rule",
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    email.applied_rules_json = json.dumps(matched_rule_records, ensure_ascii=False) if matched_rule_records else None
    if not result.matched_rules:
        if email.applied_rules_json:
            email.applied_rules_json = None
        return result

    if not email.focus_flag and any(_is_sender_trusted(rule) for rule in result.matched_rules):
        email.focus_flag = True

    db_session.add(email)
    result.applied_actions = list(dict.fromkeys(result.applied_actions))
    return result


def is_trusted_sender(email: Email) -> bool:
    for rule in list_rules():
        if not rule.get("enabled", True):
            continue
        if not (rule.get("actions", {}).get("trust_sender") or rule.get("actions", {}).get("never_spam")):
            continue
        if _match_rule(rule, email) is not None:
            return True
    return False


def _migrate_legacy_rules_if_needed() -> None:
    if not RULES_FILE_PATH.exists():
        return
    db = open_global_session()
    try:
        existing_rule = db.execute(select(Rule.id).limit(1)).scalar_one_or_none()
        if existing_rule is not None:
            if not RULES_MIGRATED_FILE_PATH.exists():
                RULES_FILE_PATH.rename(RULES_MIGRATED_FILE_PATH)
            return

        raw = json.loads(RULES_FILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raw = []
        now = datetime.now(timezone.utc)
        for item in raw:
            if not isinstance(item, dict):
                continue
            db.add(
                Rule(
                    id=str(item.get("id") or uuid4()),
                    name=str(item.get("name") or "Untitled rule"),
                    enabled=bool(item.get("enabled", True)),
                    priority=int(item.get("order", 0)),
                    conditions_json=json.dumps(_sanitize_conditions(item.get("conditions")), ensure_ascii=False),
                    actions_json=json.dumps(_sanitize_actions(item.get("actions")), ensure_ascii=False),
                    created_at=_parse_iso(item.get("created_at")) or now,
                    updated_at=_parse_iso(item.get("updated_at")) or now,
                )
            )
        db.commit()
        RULES_FILE_PATH.rename(RULES_MIGRATED_FILE_PATH)
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not migrate automation rules from %s", RULES_FILE_PATH, exc_info=True)
    finally:
        db.close()


def _rule_to_dict(rule: Rule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "enabled": bool(rule.enabled),
        "order": int(rule.priority),
        "conditions": _loads_json_object(rule.conditions_json),
        "actions": _loads_json_object(rule.actions_json),
        "created_at": rule.created_at.isoformat() if rule.created_at else "",
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    }


def _loads_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Rule payload is not valid JSON", exc_info=True)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_conditions(raw_conditions: Any) -> dict[str, Any]:
    if not isinstance(raw_conditions, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in raw_conditions.items():
        if key not in SUPPORTED_CONDITIONS or value in (None, "", []):
            continue
        if key == "has_auto_reply_headers":
            sanitized[key] = bool(value)
        else:
            sanitized[key] = str(value).strip()
    return sanitized


def _sanitize_actions(raw_actions: Any) -> dict[str, Any]:
    if not isinstance(raw_actions, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in raw_actions.items():
        if key not in SUPPORTED_ACTIONS or value in (None, "", []):
            continue
        if key in {"mark_spam", "archive", "trust_sender", "never_spam", "move_to_focus"}:
            sanitized[key] = bool(value)
        else:
            sanitized[key] = value if key == "add_tag" else str(value).strip()
    return sanitized


def _match_rule(rule: dict[str, Any], email: Email) -> dict[str, Any] | None:
    conditions = rule.get("conditions", {})
    if not conditions:
        return None

    matched_fields: dict[str, Any] = {}
    sender_email = (email.sender_email or "").strip().lower()
    sender_domain = sender_email.split("@", 1)[1] if "@" in sender_email else ""
    subject = (email.subject or "").lower()
    auto_reply = _looks_like_auto_reply(email)

    for key, expected in conditions.items():
        if key == "sender_email":
            if sender_email != str(expected).strip().lower():
                return None
            matched_fields[key] = sender_email
        elif key == "sender_domain":
            if sender_domain != str(expected).strip().lower():
                return None
            matched_fields[key] = sender_domain
        elif key == "subject_contains":
            if str(expected).strip().lower() not in subject:
                return None
            matched_fields[key] = expected
        elif key == "has_auto_reply_headers":
            if bool(expected) != auto_reply:
                return None
            matched_fields[key] = auto_reply
        elif key == "category":
            if (email.category or "").lower() != str(expected).strip().lower():
                return None
            matched_fields[key] = email.category
        elif key == "priority":
            if (email.priority or "").lower() != str(expected).strip().lower():
                return None
            matched_fields[key] = email.priority
        elif key == "direction":
            if (email.direction or "").lower() != str(expected).strip().lower():
                return None
            matched_fields[key] = email.direction
    return matched_fields


def _looks_like_auto_reply(email: Email) -> bool:
    haystack = " ".join(part for part in [email.subject or "", email.body_text or ""] if part).lower()
    patterns = [
        r"\bautomatic reply\b",
        r"\bauto(?:matic)? response\b",
        r"\bout of office\b",
        r"\bvacation reply\b",
        r"\bавтоответ\b",
        r"\bавтоматическ",
    ]
    return any(re.search(pattern, haystack) for pattern in patterns)


def _is_sender_trusted(rule: dict[str, Any]) -> bool:
    actions = rule.get("actions", {})
    return bool(actions.get("trust_sender") or actions.get("never_spam") or actions.get("move_to_focus"))


def _log_rule_applied(
    db_session: Session,
    email: Email,
    rule: dict[str, Any],
    matched_fields: dict[str, Any],
    source: str,
) -> None:
    db_session.add(
        ActionLog(
            email_id=email.id,
            action_type="rule_applied",
            actor="rule_engine",
            details_json=json.dumps(
                {
                    "source": source,
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "matched_fields": matched_fields,
                    "actions": rule.get("actions", {}),
                },
                ensure_ascii=False,
            ),
        )
    )


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
