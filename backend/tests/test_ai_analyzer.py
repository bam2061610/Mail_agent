import json
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
    )


def test_analyze_email_parses_structured_response(monkeypatch):
    payload = {
        "summary": "Important request from supplier.",
        "priority": "high",
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
    assert result.category == "RFQ"
    assert result.action_required is True


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
    assert e2.ai_analyzed is True
