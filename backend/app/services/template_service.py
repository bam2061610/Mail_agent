import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

TEMPLATES_FILE_PATH = Path(__file__).resolve().parents[2] / "data" / "templates.json"
SUPPORTED_LANGUAGES = {"ru", "en", "tr"}


def list_templates(language: str | None = None) -> list[dict[str, Any]]:
    templates = _load_templates()
    if language:
        templates = [item for item in templates if item.get("language") == language]
    return sorted(templates, key=lambda item: (item.get("category", ""), item.get("name", "")))


def get_template(template_id: str) -> dict[str, Any] | None:
    for template in _load_templates():
        if template.get("id") == template_id:
            return template
    return None


def create_template(payload: dict[str, Any]) -> dict[str, Any]:
    templates = _load_templates()
    now = datetime.utcnow().isoformat()
    template = {
        "id": payload.get("id") or str(uuid4()),
        "name": str(payload.get("name") or "Untitled template").strip() or "Untitled template",
        "category": str(payload.get("category") or "general").strip() or "general",
        "language": _normalize_language(payload.get("language")) or "en",
        "subject_template": _normalize_text(payload.get("subject_template")),
        "body_template": str(payload.get("body_template") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
    }
    templates.append(template)
    _save_templates(templates)
    return template


def update_template(template_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    templates = _load_templates()
    for index, current in enumerate(templates):
        if current.get("id") != template_id:
            continue
        updated = current.copy()
        for key in ["name", "category", "body_template"]:
            if key in payload and payload[key] is not None:
                updated[key] = str(payload[key]).strip() or updated[key]
        if "subject_template" in payload:
            updated["subject_template"] = _normalize_text(payload.get("subject_template"))
        if "language" in payload and payload["language"] is not None:
            updated["language"] = _normalize_language(payload["language"]) or updated["language"]
        if "enabled" in payload and payload["enabled"] is not None:
            updated["enabled"] = bool(payload["enabled"])
        updated["updated_at"] = datetime.utcnow().isoformat()
        templates[index] = updated
        _save_templates(templates)
        return updated
    return None


def delete_template(template_id: str) -> bool:
    templates = _load_templates()
    filtered = [item for item in templates if item.get("id") != template_id]
    if len(filtered) == len(templates):
        return False
    _save_templates(filtered)
    return True


def render_template_context(template: dict[str, Any], email_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": template.get("id"),
        "template_name": template.get("name"),
        "template_language": template.get("language"),
        "template_subject": template.get("subject_template"),
        "template_body": template.get("body_template"),
        "email_context": email_context,
    }


def _load_templates() -> list[dict[str, Any]]:
    if not TEMPLATES_FILE_PATH.exists():
        defaults = _default_templates()
        _save_templates(defaults)
        return defaults
    try:
        raw = json.loads(TEMPLATES_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_templates()
    if not isinstance(raw, list):
        return _default_templates()
    return [item for item in raw if isinstance(item, dict)]


def _save_templates(templates: list[dict[str, Any]]) -> None:
    TEMPLATES_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_FILE_PATH.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")


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
    now = datetime.utcnow().isoformat()
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
