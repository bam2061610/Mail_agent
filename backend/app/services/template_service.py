import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.config import DATA_DIR
from app.db import open_global_session
from app.models.template import Template

logger = logging.getLogger(__name__)

TEMPLATES_FILE_PATH = DATA_DIR / "templates.json"
TEMPLATES_MIGRATED_FILE_PATH = DATA_DIR / "templates.json.migrated"
SUPPORTED_LANGUAGES = {"ru", "en", "tr"}


def list_templates(language: str | None = None) -> list[dict[str, Any]]:
    _ensure_templates_seeded()
    db = open_global_session()
    try:
        query = select(Template)
        if language:
            query = query.where(Template.language == language)
        rows = db.execute(query.order_by(Template.category.asc(), Template.name.asc())).scalars().all()
        return [_template_to_dict(row) for row in rows]
    finally:
        db.close()


def get_template(template_id: str) -> dict[str, Any] | None:
    _ensure_templates_seeded()
    db = open_global_session()
    try:
        row = db.get(Template, template_id)
        return _template_to_dict(row) if row is not None else None
    finally:
        db.close()


def create_template(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_templates_seeded()
    db = open_global_session()
    try:
        now = datetime.now(timezone.utc)
        row = Template(
            id=str(payload.get("id") or uuid4()),
            name=str(payload.get("name") or "Untitled template").strip() or "Untitled template",
            category=str(payload.get("category") or "general").strip() or "general",
            language=_normalize_language(payload.get("language")) or "en",
            subject=_normalize_text(payload.get("subject_template")),
            body=str(payload.get("body_template") or "").strip(),
            enabled=bool(payload.get("enabled", True)),
            created_at=_parse_iso(payload.get("created_at")) or now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _template_to_dict(row)
    finally:
        db.close()


def update_template(template_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    _ensure_templates_seeded()
    db = open_global_session()
    try:
        row = db.get(Template, template_id)
        if row is None:
            return None
        for key, attr_name in [("name", "name"), ("category", "category")]:
            if key in payload and payload[key] is not None:
                setattr(row, attr_name, str(payload[key]).strip() or getattr(row, attr_name))
        if "body_template" in payload and payload["body_template"] is not None:
            row.body = str(payload["body_template"]).strip() or row.body
        if "subject_template" in payload:
            row.subject = _normalize_text(payload.get("subject_template"))
        if "language" in payload and payload["language"] is not None:
            row.language = _normalize_language(payload["language"]) or row.language
        if "enabled" in payload and payload["enabled"] is not None:
            row.enabled = bool(payload["enabled"])
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        db.refresh(row)
        return _template_to_dict(row)
    finally:
        db.close()


def delete_template(template_id: str) -> bool:
    _ensure_templates_seeded()
    db = open_global_session()
    try:
        row = db.get(Template, template_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def render_template_context(template: dict[str, Any], email_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": template.get("id"),
        "template_name": template.get("name"),
        "template_language": template.get("language"),
        "template_subject": template.get("subject_template"),
        "template_body": template.get("body_template"),
        "email_context": email_context,
    }


def _ensure_templates_seeded() -> None:
    db = open_global_session()
    try:
        existing = db.execute(select(Template.id).limit(1)).scalar_one_or_none()
        if existing is not None:
            _rename_legacy_templates_file_if_present()
            return

        seeded = False
        if TEMPLATES_FILE_PATH.exists():
            try:
                raw = json.loads(TEMPLATES_FILE_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Could not load templates from %s", TEMPLATES_FILE_PATH, exc_info=True)
                raw = []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    db.add(
                        Template(
                            id=str(item.get("id") or uuid4()),
                            name=str(item.get("name") or "Untitled template").strip() or "Untitled template",
                            category=str(item.get("category") or "general").strip() or "general",
                            language=_normalize_language(item.get("language")) or "en",
                            subject=_normalize_text(item.get("subject_template")),
                            body=str(item.get("body_template") or "").strip(),
                            enabled=bool(item.get("enabled", True)),
                            created_at=_parse_iso(item.get("created_at")) or datetime.now(timezone.utc),
                            updated_at=_parse_iso(item.get("updated_at")) or datetime.now(timezone.utc),
                        )
                    )
                    seeded = True
        if not seeded:
            for item in _default_templates():
                db.add(
                    Template(
                        id=item["id"],
                        name=item["name"],
                        category=item["category"],
                        language=item["language"],
                        subject=item["subject_template"],
                        body=item["body_template"],
                        enabled=bool(item["enabled"]),
                        created_at=_parse_iso(item["created_at"]) or datetime.now(timezone.utc),
                        updated_at=_parse_iso(item["updated_at"]) or datetime.now(timezone.utc),
                    )
                )
        db.commit()
        _rename_legacy_templates_file_if_present()
    finally:
        db.close()


def _rename_legacy_templates_file_if_present() -> None:
    if TEMPLATES_FILE_PATH.exists() and not TEMPLATES_MIGRATED_FILE_PATH.exists():
        TEMPLATES_FILE_PATH.rename(TEMPLATES_MIGRATED_FILE_PATH)


def _template_to_dict(row: Template) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "category": row.category,
        "language": row.language,
        "subject_template": row.subject,
        "body_template": row.body,
        "enabled": bool(row.enabled),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _normalize_language(value: Any) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in SUPPORTED_LANGUAGES else None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _default_templates() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    defaults = [
        ("ack", "Acknowledgment / thanks", "general", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nThank you for your email. We have received your message and will review the details shortly.\n\nBest regards,\nOrhun Medical"),
        ("clarify", "Request for clarification", "clarification", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nThank you for your message. Could you please clarify the requested details so we can proceed quickly?\n\nBest regards,\nOrhun Medical"),
        ("followup", "Polite follow-up", "followup", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nJust following up on the message below. We would appreciate your update when convenient.\n\nBest regards,\nOrhun Medical"),
        ("meeting", "Meeting confirmation", "meeting", "en", "Meeting confirmation", "Hello {{recipient_name}},\n\nThank you. We confirm the meeting and will be ready at the agreed time.\n\nBest regards,\nOrhun Medical"),
        ("decline", "Decline politely", "decline", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nThank you for your message. Unfortunately, we cannot proceed with this request at the moment.\n\nBest regards,\nOrhun Medical"),
        ("docs", "Request for documents", "documents", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nCould you please send the required documents so we can continue the review?\n\nBest regards,\nOrhun Medical"),
        ("quote", "Pricing / quote follow-up", "pricing", "en", "Re: {{subject}}", "Hello {{recipient_name}},\n\nWe are following up regarding the quotation and would appreciate your updated pricing details.\n\nBest regards,\nOrhun Medical"),
        ("approval", "Internal approval clarification", "internal", "en", "Re: {{subject}}", "Hello,\n\nPlease clarify the approval status and any remaining items before we proceed.\n\nBest regards,\nOrhun Medical"),
        ("ack-ru", "Подтверждение / благодарность", "general", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nСпасибо за ваше письмо. Мы получили сообщение и скоро вернемся с ответом.\n\nС уважением,\nOrhun Medical"),
        ("clarify-ru", "Запрос уточнений", "clarification", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nСпасибо за письмо. Пожалуйста, уточните детали запроса, чтобы мы могли быстрее продолжить работу.\n\nС уважением,\nOrhun Medical"),
        ("followup-ru", "Вежливый follow-up", "followup", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nНапоминаем по письму ниже. Будем признательны за обновление, когда вам будет удобно.\n\nС уважением,\nOrhun Medical"),
        ("meeting-ru", "Подтверждение встречи", "meeting", "ru", "Подтверждение встречи", "Здравствуйте, {{recipient_name}}.\n\nПодтверждаем встречу и будем готовы в согласованное время.\n\nС уважением,\nOrhun Medical"),
        ("decline-ru", "Вежливый отказ", "decline", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nСпасибо за сообщение. К сожалению, сейчас мы не можем продолжить по этому запросу.\n\nС уважением,\nOrhun Medical"),
        ("docs-ru", "Запрос документов", "documents", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nПожалуйста, отправьте необходимые документы, чтобы мы могли продолжить рассмотрение.\n\nС уважением,\nOrhun Medical"),
        ("quote-ru", "Уточнение по цене / КП", "pricing", "ru", "Re: {{subject}}", "Здравствуйте, {{recipient_name}}.\n\nПросим уточнить актуальные цены и условия по вашему предложению.\n\nС уважением,\nOrhun Medical"),
        ("approval-ru", "Уточнение по внутреннему согласованию", "internal", "ru", "Re: {{subject}}", "Здравствуйте.\n\nПожалуйста, уточните статус согласования и оставшиеся шаги перед продолжением.\n\nС уважением,\nOrhun Medical"),
        ("ack-tr", "Tesekkur / alindi", "general", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nE-postaniz icin tesekkur ederiz. Mesajinizi aldik ve kisa sure icinde inceleyecegiz.\n\nSaygilarimizla,\nOrhun Medical"),
        ("clarify-tr", "Aciklama talebi", "clarification", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nMesajiniz icin tesekkur ederiz. Devam edebilmemiz icin rica etsek ilgili detaylari netlestirebilir misiniz?\n\nSaygilarimizla,\nOrhun Medical"),
        ("followup-tr", "Nazik hatirlatma", "followup", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nAsagidaki konu hakkinda nazik bir hatirlatma yapmak isteriz. Uygun oldugunuzda guncellemenizi rica ederiz.\n\nSaygilarimizla,\nOrhun Medical"),
        ("meeting-tr", "Toplanti teyidi", "meeting", "tr", "Toplanti teyidi", "Merhaba {{recipient_name}},\n\nToplantiyi teyit ediyoruz ve belirlenen saatte hazir olacagiz.\n\nSaygilarimizla,\nOrhun Medical"),
        ("decline-tr", "Nazik reddetme", "decline", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nMesajiniz icin tesekkur ederiz. Ne yazik ki bu talep ile su anda ilerleyemiyoruz.\n\nSaygilarimizla,\nOrhun Medical"),
        ("docs-tr", "Evrak talebi", "documents", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nDegerlendirmeye devam edebilmemiz icin gerekli belgeleri paylasabilir misiniz?\n\nSaygilarimizla,\nOrhun Medical"),
        ("quote-tr", "Fiyat / teklif takibi", "pricing", "tr", "Re: {{subject}}", "Merhaba {{recipient_name}},\n\nTeklif ve fiyat detaylari hakkinda guncel bilgi paylasmanizi rica ederiz.\n\nSaygilarimizla,\nOrhun Medical"),
        ("approval-tr", "Ic onay durumu", "internal", "tr", "Re: {{subject}}", "Merhaba,\n\nDevam etmeden once onay durumunu ve kalan adimlari netlestirebilir misiniz?\n\nSaygilarimizla,\nOrhun Medical"),
    ]
    return [
        {
            "id": item_id,
            "name": name,
            "category": category,
            "language": language,
            "subject_template": subject_template,
            "body_template": body_template,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
        for item_id, name, category, language, subject_template, body_template in defaults
    ]


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
