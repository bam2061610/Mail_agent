from dataclasses import dataclass
from types import SimpleNamespace

from app.models.action_log import ActionLog
from app.models.email import Email
from app.services.smtp_sender import SendReplyResult


@dataclass
class FakeScanSummary:
    total_created_count: int
    total_skipped_count: int
    mailbox_results: list
    errors: list[str]


@dataclass
class FakeAnalyzeSummary:
    selected_count: int
    analyzed_count: int
    failed_count: int
    skipped_count: int
    errors: list[str]


def test_happy_path_core_flow(client, db_session, admin_auth_headers, monkeypatch):
    import app.api.routes.actions as actions_route
    import app.api.routes.emails as emails_route

    def _fake_scan_all_mailboxes(db, _settings):
        email = Email(
            message_id="<smoke-1@test>",
            thread_id="<smoke-1@test>",
            subject="Supplier inquiry",
            sender_email="sales@supplier.com",
            sender_name="Sales Team",
            recipients_json='[{"email":"ops@orhun.local","name":"Ops"}]',
            cc_json="[]",
            body_text="Please review our quote options.",
            folder="inbox",
            direction="inbound",
            status="new",
            requires_reply=True,
            mailbox_id="mb-default",
            mailbox_name="Default",
            mailbox_address="ops@orhun.local",
            ai_analyzed=False,
        )
        db.add(email)
        db.commit()
        return FakeScanSummary(total_created_count=1, total_skipped_count=0, mailbox_results=[], errors=[])

    def _fake_analyze_pending(db, _settings):
        email = db.query(Email).filter(Email.message_id == "<smoke-1@test>").first()
        assert email is not None
        email.ai_analyzed = True
        email.ai_summary = "Supplier requests commercial response."
        email.priority = "high"
        email.category = "RFQ"
        email.ai_draft_reply = "Thank you, we will send details shortly."
        db.add(email)
        db.commit()
        return FakeAnalyzeSummary(selected_count=1, analyzed_count=1, failed_count=0, skipped_count=0, errors=[])

    monkeypatch.setattr(actions_route, "scan_all_mailboxes", _fake_scan_all_mailboxes)
    monkeypatch.setattr(actions_route, "analyze_pending", _fake_analyze_pending)
    monkeypatch.setattr(
        emails_route,
        "generate_personalized_draft",
        lambda **_kwargs: SimpleNamespace(draft_reply="Draft from AI", subject="Re: Supplier inquiry", target_language="en"),
    )
    monkeypatch.setattr(
        emails_route,
        "send_reply",
        lambda **_kwargs: SendReplyResult(status="sent", message_id="<sent-smoke@test>", recipients=["sales@supplier.com"], subject="Re: Supplier inquiry"),
    )

    scan = client.post("/api/scan", headers=admin_auth_headers)
    assert scan.status_code == 200
    assert scan.json()["imported_count"] == 1
    assert scan.json()["analyzed_count"] == 1

    email_list = client.get("/api/emails", headers=admin_auth_headers)
    assert email_list.status_code == 200
    imported = next(item for item in email_list.json() if item["subject"] == "Supplier inquiry")
    email_id = imported["id"]

    detail = client.get(f"/api/emails/{email_id}", headers=admin_auth_headers)
    assert detail.status_code == 200
    assert detail.json()["ai_analyzed"] is True

    draft = client.post(
        f"/api/emails/{email_id}/generate-draft",
        headers=admin_auth_headers,
        json={"target_language": "en"},
    )
    assert draft.status_code == 200
    assert draft.json()["draft_reply"] == "Draft from AI"

    send = client.post(
        f"/api/emails/{email_id}/reply",
        headers=admin_auth_headers,
        json={"body": "Sending final reply", "save_as_sent_record": True},
    )
    assert send.status_code == 200
    assert send.json()["status"] == "replied"

    actions = db_session.query(ActionLog).filter(ActionLog.email_id == email_id).all()
    action_types = {item.action_type for item in actions}
    assert "email_sent" in action_types
