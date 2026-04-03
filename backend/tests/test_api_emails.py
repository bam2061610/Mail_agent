from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.attachment import Attachment
from app.models.email import Email
from app.services.deepseek_client import DeepSeekRateLimitError, DeepSeekResponseError, DeepSeekTimeoutError
from app.services.smtp_sender import SendReplyResult


def test_health_and_email_list(client, admin_auth_headers, sample_email):
    health = client.get("/health")
    assert health.status_code == 200
    listing = client.get("/api/emails", headers=admin_auth_headers)
    assert listing.status_code == 200
    items = listing.json()
    assert any(item["id"] == sample_email.id for item in items)


def test_get_email_detail(client, admin_auth_headers, sample_email):
    response = client.get(f"/api/emails/{sample_email.id}", headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.json()["subject"] == sample_email.subject


def test_update_email_status(client, admin_auth_headers, sample_email):
    response = client.post(
        f"/api/emails/{sample_email.id}/status",
        headers=admin_auth_headers,
        json={"status": "archived"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"


def test_reply_email_with_mocked_smtp(client, admin_auth_headers, admin_user, sample_email, db_session, monkeypatch):
    import app.api.routes.emails as emails_route

    monkeypatch.setattr(
        emails_route,
        "send_reply",
        lambda **_kwargs: SendReplyResult(
            status="sent",
            message_id="<sent@test>",
            recipients=["sales@supplier.com"],
            subject="Re: ok",
        ),
    )
    response = client.post(
        f"/api/emails/{sample_email.id}/reply",
        headers=admin_auth_headers,
        json={"body": "Thanks, received.", "save_as_sent_record": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "replied"
    sent_rows = db_session.query(Email).filter(Email.id != sample_email.id).all()
    assert len(sent_rows) == 1
    sent_email = sent_rows[0]
    assert sent_email.direction == "outbound"
    assert sent_email.folder.lower() == "sent"
    assert sent_email.sent_by_user_id == admin_user.id


def test_generate_draft_with_mocked_ai(client, admin_auth_headers, sample_email, monkeypatch):
    import app.api.routes.emails as emails_route

    captured = {}

    monkeypatch.setattr(
        emails_route,
        "generate_personalized_draft",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(draft_reply="Generated draft", subject="Re: x", target_language="en"),
    )
    response = client.post(
        f"/api/emails/{sample_email.id}/generate-draft",
        headers=admin_auth_headers,
        json={"target_language": "en", "custom_prompt": "Keep it short."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["draft_reply"] == "Generated draft"
    assert payload["target_language"] == "en"
    assert captured["custom_prompt"] == "Keep it short."


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_fragment"),
    [
        (DeepSeekTimeoutError("timed out"), 504, "timed out"),
        (DeepSeekRateLimitError("slow down"), 429, "rate limit"),
        (DeepSeekResponseError("invalid"), 502, "Unexpected AI response"),
    ],
)
def test_generate_draft_returns_controlled_ai_errors(client, admin_auth_headers, sample_email, monkeypatch, exc, expected_status, expected_fragment):
    import app.api.routes.emails as emails_route

    monkeypatch.setattr(emails_route, "generate_personalized_draft", lambda **_kwargs: (_ for _ in ()).throw(exc))
    response = client.post(
        f"/api/emails/{sample_email.id}/generate-draft",
        headers=admin_auth_headers,
        json={"target_language": "en"},
    )
    assert response.status_code == expected_status
    assert expected_fragment in response.json().get("detail", "")


def test_reply_email_returns_specific_smtp_failure(client, admin_auth_headers, sample_email, monkeypatch):
    import app.api.routes.emails as emails_route

    monkeypatch.setattr(emails_route, "send_reply", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("SMTP auth failed")))
    response = client.post(
        f"/api/emails/{sample_email.id}/reply",
        headers=admin_auth_headers,
        json={"body": "Thanks, received.", "save_as_sent_record": True},
    )
    assert response.status_code == 502
    assert "SMTP delivery failed" in response.json().get("detail", "")


def test_rules_spam_and_mailboxes_endpoints(client, admin_auth_headers, sample_email):
    rule_resp = client.post(
        "/api/rules",
        headers=admin_auth_headers,
        json={"name": "Always focus", "conditions": {"sender_email": sample_email.sender_email}, "actions": {"move_to_focus": True}},
    )
    assert rule_resp.status_code == 200

    spam_list = client.get("/api/spam", headers=admin_auth_headers)
    assert spam_list.status_code == 200

    mailbox_create = client.post(
        "/api/mailboxes",
        headers=admin_auth_headers,
        json={
            "name": "Ops mailbox",
            "email_address": "ops@example.com",
            "imap_host": "imap.example.com",
            "imap_password": "secret",
            "smtp_host": "smtp.example.com",
            "smtp_password": "secret",
        },
    )
    assert mailbox_create.status_code == 200
    mailbox_list = client.get("/api/mailboxes", headers=admin_auth_headers)
    assert mailbox_list.status_code == 200
    assert len(mailbox_list.json()) >= 1


def test_list_emails_supports_sent_filters(client, admin_auth_headers, db_session, sample_email):
    sent_email = Email(
        message_id="<sent-filter@test>",
        thread_id="<sent-filter@test>",
        subject="Outbound update",
        sender_email="admin@orhun.local",
        sender_name="Admin User",
        recipients_json='[{"email":"client@example.com","name":"Client"}]',
        cc_json="[]",
        body_text="Quick status update from the team.",
        folder="sent",
        direction="sent",
        status="replied",
        requires_reply=False,
        ai_analyzed=True,
        date_received=datetime.now(timezone.utc),
    )
    db_session.add(sent_email)
    db_session.commit()

    sent_by_direction = client.get("/api/emails?direction=sent", headers=admin_auth_headers)
    assert sent_by_direction.status_code == 200
    sent_by_direction_ids = [item["id"] for item in sent_by_direction.json()]
    assert sent_email.id in sent_by_direction_ids
    assert sample_email.id not in sent_by_direction_ids

    sent_by_folder = client.get("/api/emails?folder=sent", headers=admin_auth_headers)
    assert sent_by_folder.status_code == 200
    sent_by_folder_ids = [item["id"] for item in sent_by_folder.json()]
    assert sent_email.id in sent_by_folder_ids
    assert sample_email.id not in sent_by_folder_ids


def test_attachment_download_uses_utf8_content_disposition(
    client,
    admin_auth_headers,
    db_session,
    sample_email,
    isolated_paths,
):
    attachment_file = Path(isolated_paths["attachments_dir"]) / "mb-default" / str(sample_email.id) / "invoice.pdf"
    attachment_file.parent.mkdir(parents=True, exist_ok=True)
    attachment_file.write_bytes(b"%PDF-1.4\nfake\n")

    attachment = Attachment(
        email_id=sample_email.id,
        filename="счет-фактура.pdf",
        content_type="application/pdf",
        size_bytes=attachment_file.stat().st_size,
        is_inline=False,
        local_storage_path=str(attachment_file),
    )
    db_session.add(attachment)
    db_session.commit()
    db_session.refresh(attachment)

    response = client.get(f"/api/emails/attachments/{attachment.id}/download", headers=admin_auth_headers)
    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment;" in disposition.lower()
    assert "filename*=" in disposition
    assert "UTF-8''" in disposition


def test_thread_endpoint_includes_outbound_messages(client, admin_auth_headers, sample_email, db_session):
    sent_email = Email(
        message_id="<thread-sent@test>",
        thread_id=sample_email.message_id,
        subject=f"Re: {sample_email.subject}",
        sender_email="admin@orhun.local",
        sender_name="Admin User",
        recipients_json='[{"email":"sales@supplier.com","name":null}]',
        cc_json="[]",
        body_text="Following up on your quotation request.",
        folder="Sent",
        direction="outbound",
        status="replied",
        requires_reply=False,
        ai_analyzed=True,
        date_received=datetime.now(timezone.utc),
    )
    db_session.add(sent_email)
    db_session.commit()

    response = client.get(f"/api/emails/{sample_email.id}/thread", headers=admin_auth_headers)
    assert response.status_code == 200
    payload = response.json()
    directions = [item.get("direction") for item in payload.get("emails", [])]
    assert "outbound" in directions
