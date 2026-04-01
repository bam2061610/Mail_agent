import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.email import Email

logger = logging.getLogger(__name__)

RULES_FILE_PATH = Path(__file__).resolve().parents[2] / "data" / "rules.json"
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
    rules = _load_rules()
    return sorted(rules, key=lambda item: (int(item.get("order", 0)), str(item.get("created_at", ""))))


def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    rules = _load_rules()
    now = datetime.utcnow().isoformat()
    order = payload.get("order")
    if order is None:
        order = max([int(rule.get("order", 0)) for rule in rules], default=-1) + 1

    rule = {
        "id": payload.get("id") or str(uuid4()),
        "name": str(payload.get("name") or "Untitled rule").strip() or "Untitled rule",
        "enabled": bool(payload.get("enabled", True)),
        "order": int(order),
        "conditions": _sanitize_conditions(payload.get("conditions")),
        "actions": _sanitize_actions(payload.get("actions")),
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
    }
    rules.append(rule)
    _save_rules(rules)
    return rule


def update_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    rules = _load_rules()
    for index, current in enumerate(rules):
        if current.get("id") != rule_id:
            continue

        updated = current.copy()
        if "name" in payload:
            updated["name"] = str(payload["name"]).strip() or updated["name"]
        if "enabled" in payload and payload["enabled"] is not None:
            updated["enabled"] = bool(payload["enabled"])
        if "order" in payload and payload["order"] is not None:
            updated["order"] = int(payload["order"])
        if "conditions" in payload and payload["conditions"] is not None:
            updated["conditions"] = _sanitize_conditions(payload["conditions"])
        if "actions" in payload and payload["actions"] is not None:
            updated["actions"] = _sanitize_actions(payload["actions"])
        updated["updated_at"] = datetime.utcnow().isoformat()
        rules[index] = updated
        _save_rules(rules)
        return updated
    return None


def delete_rule(rule_id: str) -> bool:
    rules = _load_rules()
    filtered = [rule for rule in rules if rule.get("id") != rule_id]
    if len(filtered) == len(rules):
        return False
    _save_rules(filtered)
    return True


def reorder_rules(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_map = {str(item.get("id")): int(item.get("order", 0)) for item in items if item.get("id")}
    rules = _load_rules()
    for rule in rules:
        if rule.get("id") in order_map:
            rule["order"] = order_map[rule["id"]]
            rule["updated_at"] = datetime.utcnow().isoformat()
    _save_rules(rules)
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


def _load_rules() -> list[dict[str, Any]]:
    if not RULES_FILE_PATH.exists():
        return []
    try:
        raw = json.loads(RULES_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not load automation rules from %s", RULES_FILE_PATH)
        return []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id") or uuid4()),
                "name": str(item.get("name") or "Untitled rule"),
                "enabled": bool(item.get("enabled", True)),
                "order": int(item.get("order", 0)),
                "conditions": _sanitize_conditions(item.get("conditions")),
                "actions": _sanitize_actions(item.get("actions")),
                "created_at": str(item.get("created_at") or datetime.utcnow().isoformat()),
                "updated_at": str(item.get("updated_at") or datetime.utcnow().isoformat()),
            }
        )
    return normalized


def _save_rules(rules: list[dict[str, Any]]) -> None:
    RULES_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_FILE_PATH.write_text(json.dumps(list_rules_payload(rules), ensure_ascii=False, indent=2), encoding="utf-8")


def list_rules_payload(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rules, key=lambda item: (int(item.get("order", 0)), str(item.get("created_at", ""))))


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
