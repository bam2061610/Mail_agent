from types import SimpleNamespace

from app.models.email import Email
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


def test_reply_email_with_mocked_smtp(client, admin_auth_headers, sample_email, monkeypatch):
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


def test_generate_draft_with_mocked_ai(client, admin_auth_headers, sample_email, monkeypatch):
    import app.api.routes.emails as emails_route

    monkeypatch.setattr(
        emails_route,
        "generate_personalized_draft",
        lambda **_kwargs: SimpleNamespace(draft_reply="Generated draft", subject="Re: x", target_language="en"),
    )
    response = client.post(
        f"/api/emails/{sample_email.id}/generate-draft",
        headers=admin_auth_headers,
        json={"target_language": "en"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["draft_reply"] == "Generated draft"
    assert payload["target_language"] == "en"


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
