from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.email import Email
from app.services.language_service import choose_reply_language


def test_choose_reply_language_prefers_latest_thread_message():
    older = Email(
        subject="Hello",
        body_text="Здравствуйте, уточните, пожалуйста, сроки.",
        date_received=datetime.now(timezone.utc) - timedelta(minutes=10),
        detected_source_language="ru",
    )
    latest = Email(
        subject="Re: Hello",
        body_text="Please confirm the delivery window.",
        date_received=datetime.now(timezone.utc),
        detected_source_language="en",
    )
    current = Email(
        subject="Hello",
        body_text="Здравствуйте, уточните, пожалуйста, сроки.",
        date_received=datetime.now(timezone.utc) - timedelta(minutes=15),
        detected_source_language="ru",
    )

    language = choose_reply_language(current, thread_history=[older, latest], contact=SimpleNamespace(preferred_language=None))
    assert language == "en"
