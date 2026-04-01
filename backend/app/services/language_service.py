import re
from dataclasses import dataclass

from app.models.contact import Contact
from app.models.email import Email

SUPPORTED_LANGUAGES = {"ru", "en", "tr"}
DEFAULT_REPLY_LANGUAGE = "ru"

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
TURKISH_RE = re.compile(r"[ğüşöçıİĞÜŞÖÇ]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

RUSSIAN_HINTS = {
    "здравствуйте", "добрый", "спасибо", "пожалуйста", "счет", "договор", "срок", "поставка", "подтвердите",
}
ENGLISH_HINTS = {
    "hello", "regards", "thank", "please", "invoice", "quotation", "delivery", "confirm", "follow-up",
}
TURKISH_HINTS = {
    "merhaba", "teşekkür", "tesekkur", "lütfen", "fatura", "teklif", "tedarik", "gün", "bugün", "yarın",
}


@dataclass(slots=True)
class LanguageDecision:
    detected_language: str
    confidence: float
    reason: str


def detect_language(text: str | None, subject: str | None = None) -> LanguageDecision:
    content = " ".join(part for part in [subject or "", text or ""] if part).strip()
    if not content:
        return LanguageDecision(detected_language=DEFAULT_REPLY_LANGUAGE, confidence=0.0, reason="empty")

    lowered = content.lower()
    cyrillic_count = len(CYRILLIC_RE.findall(content))
    turkish_char_count = len(TURKISH_RE.findall(content))
    latin_words = LATIN_WORD_RE.findall(content)

    russian_hits = sum(1 for hint in RUSSIAN_HINTS if hint in lowered)
    english_hits = sum(1 for hint in ENGLISH_HINTS if hint in lowered)
    turkish_hits = sum(1 for hint in TURKISH_HINTS if hint in lowered)

    if cyrillic_count >= 6 or russian_hits >= 2:
        return LanguageDecision("ru", min(0.98, 0.55 + russian_hits * 0.1 + cyrillic_count / 200), "cyrillic_or_ru_keywords")
    if turkish_char_count >= 2 or turkish_hits >= 2:
        return LanguageDecision("tr", min(0.95, 0.55 + turkish_hits * 0.12 + turkish_char_count * 0.08), "turkish_chars_or_keywords")
    if english_hits >= 1 or len(latin_words) >= 6:
        return LanguageDecision("en", min(0.9, 0.45 + english_hits * 0.12 + len(latin_words) / 60), "latin_text_or_en_keywords")
    return LanguageDecision(DEFAULT_REPLY_LANGUAGE, 0.3, "fallback_default")


def normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    aliases = {
        "russian": "ru",
        "русский": "ru",
        "english": "en",
        "английский": "en",
        "turkish": "tr",
        "турецкий": "tr",
    }
    return aliases.get(normalized)


def choose_reply_language(
    email: Email,
    explicit_language: str | None = None,
    contact: Contact | None = None,
) -> str:
    for candidate in [
        normalize_language(explicit_language),
        normalize_language(email.preferred_reply_language),
        normalize_language(contact.preferred_language if contact else None),
        normalize_language(email.detected_source_language),
    ]:
        if candidate:
            return candidate
    return DEFAULT_REPLY_LANGUAGE


def update_email_languages(
    email: Email,
    contact: Contact | None = None,
    explicit_reply_language: str | None = None,
) -> LanguageDecision:
    decision = detect_language(email.body_text or email.body_html, email.subject)
    email.detected_source_language = decision.detected_language
    email.preferred_reply_language = choose_reply_language(email, explicit_reply_language, contact)
    return decision
