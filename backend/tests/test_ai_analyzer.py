import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.email import Email
from app.services import ai_analyzer


def _cfg():
    return SimpleNamespace(
        deepseek_model="deepseek-chat",
        deepseek_base_url="https://api.deepseek.com",
        openai_api_key="x",
        ai_max_retries=1,
        ai_timeout_seconds=5,
        interface_language="ru",
        ai_auto_spam_enabled=False,
    )


def test_analyze_email_parses_structured_response(monkeypatch):
    payload = {
        "summary": "Important request from supplier.",
        "who_is_writing": "supplier sales",
        "to_whom": "Orhun procurement",
        "core_request": "share quote details",
        "required_action": "reply with pricing window",
        "priority": "high",
        "importance_score": 9,
        "category": "RFQ",
        "action_required": True,
        "action_description": "Reply with pricing window.",
        "key_dates": ["2026-04-05"],
        "key_amounts": ["$5000"],
        "draft_reply": "Thanks, we will respond shortly.",
    }
    monkeypatch.setattr(ai_analyzer, "_call_model_once", lambda **_kwargs: json.dumps(payload))
    email = Email(id=1, subject="RFQ", sender_email="sales@supplier.com", body_text="Need quote", recipients_json="[]", cc_json="[]")
    result = ai_analyzer.analyze_email(email, [], _cfg())
    assert result.priority == "high"
    assert result.importance_score == 9
    assert result.category == "RFQ"
    assert result.action_required is True


def test_save_analysis_result_propagates_thread_summary(db_session):
    current = Email(
        message_id="<thread-a@test>",
        thread_id="<thread-a@test>",
        subject="Need support",
        sender_email="x@example.com",
        body_text="Help please",
        folder="inbox",
        direction="inbound",
        status="new",
        ai_analyzed=False,
        date_received=datetime.now(timezone.utc),
    )
    followup = Email(
        message_id="<thread-b@test>",
        thread_id="<thread-a@test>",
        subject="Re: Need support",
        sender_email="x@example.com",
        body_text="Any update?",
        folder="inbox",
        direction="inbound",
        status="new",
        ai_analyzed=False,
        date_received=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add_all([current, followup])
    db_session.commit()

    ai_analyzer.save_analysis_result(
        db_session,
        current,
        ai_analyzer.AnalysisResult(
            summary="Кто пишет: поставщик. Кому: Orhun Medical. Суть: запрос на цену. Действие: ответить.",
            who_is_writing="supplier",
            to_whom="Orhun Medical",
            core_request="quote request",
            required_action="reply with pricing",
            priority="medium",
            importance_score=8,
            category="RFQ",
            action_required=True,
        ),
        config=_cfg(),
    )

    db_session.refresh(current)
    db_session.refresh(followup)
    assert current.ai_summary == followup.ai_summary
    assert current.importance_score == 8
    assert "Orhun Medical" in current.ai_summary


def test_save_analysis_result_respects_auto_spam_flag(db_session):
    email = Email(
        message_id="<spam@test>",
        subject="Suspicious offer",
        sender_email="spam@example.com",
        body_text="Buy now",
        folder="inbox",
        direction="inbound",
        status="new",
        ai_analyzed=False,
        date_received=datetime.now(timezone.utc),
    )
    db_session.add(email)
    db_session.commit()

    ai_analyzer.save_analysis_result(
        db_session,
        email,
        ai_analyzer.AnalysisResult(
            summary="Кто пишет: спам. Кому: пользователю. Суть: навязчивое предложение. Действие: удалить.",
            who_is_writing="spam sender",
            to_whom="user",
            core_request="sell something",
            required_action="ignore",
            priority="spam",
            category="Spam",
            action_required=False,
        ),
        config=SimpleNamespace(ai_auto_spam_enabled=False),
    )

    db_session.refresh(email)
    assert email.is_spam is False
    assert email.status == "new"


def test_generate_personalized_draft_defaults_to_latest_thread_language_and_custom_prompt(monkeypatch):
    latest = Email(
        id=2,
        subject="Re: Meeting",
        sender_email="partner@example.com",
        body_text="Please confirm the meeting.",
        recipients_json="[]",
        cc_json="[]",
        date_received=datetime.now(timezone.utc),
        detected_source_language="en",
    )
    current = Email(
        id=1,
        subject="Meeting",
        sender_email="partner@example.com",
        body_text="Здравствуйте, прошу подтвердить встречу.",
        recipients_json="[]",
        cc_json="[]",
        date_received=datetime.now(timezone.utc) - timedelta(minutes=5),
        detected_source_language="ru",
    )
    captured: dict[str, object] = {}

    def _fake_call(**kwargs):
        captured.update(kwargs)
        return json.dumps({"draft_reply": "Hello, confirmed.", "subject": "Re: Meeting", "target_language": "en"})

    monkeypatch.setattr(ai_analyzer, "_call_model_once", _fake_call)

    result = ai_analyzer.generate_personalized_draft(
        current,
        [current, latest],
        _cfg(),
        custom_prompt="Please keep it brief.",
    )
    payload = json.loads(captured["user_payload"])
    assert payload["custom_prompt"] == "Please keep it brief."
    assert payload["target_language"] == "en"
    assert result.target_language == "en"


def test_generate_personalized_draft_rejects_invalid_json(monkeypatch):
    email = Email(
        id=1,
        subject="Meeting",
        sender_email="partner@example.com",
        body_text="Please confirm the meeting.",
        recipients_json="[]",
        cc_json="[]",
        date_received=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(ai_analyzer, "_call_model_once", lambda **_kwargs: "not-json")

    try:
        ai_analyzer.generate_personalized_draft(email, [email], _cfg())
    except ValueError as exc:
        assert "JSON" in str(exc) or "draft_reply" in str(exc)
    else:
        raise AssertionError("Expected invalid AI response to raise ValueError")


def test_analyze_pending_updates_only_unanalyzed(db_session, monkeypatch):
    e1 = Email(
        message_id="<a1@test>",
        subject="Need support",
        sender_email="x@example.com",
        body_text="Help please",
        folder="inbox",
        direction="inbound",
        status="new",
        ai_analyzed=False,
    )
    e2 = Email(
        message_id="<a2@test>",
        subject="Already done",
        sender_email="y@example.com",
        body_text="Done",
        folder="inbox",
        direction="inbound",
        status="new",
        ai_analyzed=True,
    )
    db_session.add_all([e1, e2])
    db_session.commit()

    monkeypatch.setattr(
        ai_analyzer,
        "_call_model_once",
        lambda **_kwargs: json.dumps(
            {
                "summary": "Summary",
                "priority": "medium",
                "importance_score": 5,
                "category": "Support",
                "action_required": False,
                "action_description": "",
                "key_dates": [],
                "key_amounts": [],
                "draft_reply": None,
            }
        ),
    )

    summary = ai_analyzer.analyze_pending(db_session, _cfg())
    assert summary.analyzed_count == 1
    db_session.refresh(e1)
    db_session.refresh(e2)
    assert e1.ai_analyzed is True
    assert e1.importance_score == 5
    assert e2.ai_analyzed is True
