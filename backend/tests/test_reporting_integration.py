from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.email import Email


def test_activity_report_and_exports(client, db_session, admin_auth_headers):
    now = datetime.now(timezone.utc)
    inbound = Email(
        message_id="<report-in@test>",
        thread_id="<report-thread@test>",
        subject="Inbound for report",
        sender_email="supplier@example.com",
        folder="inbox",
        direction="inbound",
        status="new",
        priority="high",
        requires_reply=True,
        mailbox_id="mb-report",
        mailbox_name="Report mailbox",
        date_received=now - timedelta(hours=2),
    )
    sent = Email(
        message_id="<report-out@test>",
        thread_id="<report-thread@test>",
        subject="Sent for report",
        sender_email="ops@example.com",
        folder="sent",
        direction="sent",
        status="replied",
        mailbox_id="mb-report",
        mailbox_name="Report mailbox",
        sent_review_status="good",
        sent_reviewed_at=now - timedelta(hours=1),
        date_received=now - timedelta(hours=1),
    )
    db_session.add_all([inbound, sent])
    db_session.commit()

    report = client.get("/api/reports/activity", headers=admin_auth_headers)
    assert report.status_code == 200
    payload = report.json()
    assert payload["report_type"] == "activity"
    assert payload["summary"]["received_emails_count"] >= 1
    assert payload["summary"]["sent_emails_count"] >= 1
    assert isinstance(payload["rows"], list)

    csv_export = client.get("/api/reports/activity/export?format=csv", headers=admin_auth_headers)
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers.get("content-type", "")
    assert "attachment;" in csv_export.headers.get("content-disposition", "")

    pdf_export = client.get("/api/reports/sent-review/export?format=pdf", headers=admin_auth_headers)
    assert pdf_export.status_code == 200
    assert "application/pdf" in pdf_export.headers.get("content-type", "")
    assert "attachment;" in pdf_export.headers.get("content-disposition", "")


def test_obsolete_team_report_routes_are_gone(client, operator_auth_headers):
    response = client.get("/api/reports/team-activity", headers=operator_auth_headers)
    assert response.status_code == 404


def test_send_report_email_normalizes_recipients(client, admin_auth_headers, monkeypatch):
    import app.api.routes.reports as reports_route

    captured: dict[str, list[str]] = {}
    smtp_config = SimpleNamespace(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="bot@example.com",
        smtp_password="secret",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_address="bot@example.com",
    )

    def _fake_send_email(*, to, cc, bcc, subject, body, config):
        captured["to"] = to
        captured["cc"] = cc
        captured["bcc"] = bcc
        return SimpleNamespace(status="sent", message_id="<report@test>", recipients=[*to, *cc, *bcc], subject=subject)

    monkeypatch.setattr(reports_route, "get_default_runtime_mailbox_from_settings", lambda: smtp_config)
    monkeypatch.setattr(reports_route, "send_email", _fake_send_email)

    response = client.post(
        "/api/reports/send",
        headers=admin_auth_headers,
        json={
            "report_type": "activity",
            "to": ["  lead@example.com ", ""],
            "cc": [" manager@example.com  "],
            "bcc": ["   "],
        },
    )
    assert response.status_code == 200
    assert captured["to"] == ["lead@example.com"]
    assert captured["cc"] == ["manager@example.com"]
    assert captured["bcc"] == []


def test_send_report_email_returns_502_on_smtp_failure(client, admin_auth_headers, monkeypatch):
    import app.api.routes.reports as reports_route

    smtp_config = SimpleNamespace(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="bot@example.com",
        smtp_password="secret",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_address="bot@example.com",
    )

    def _raise_smtp(*, to, cc, bcc, subject, body, config):  # noqa: ARG001
        raise RuntimeError("SMTP send failed: auth error")

    monkeypatch.setattr(reports_route, "get_default_runtime_mailbox_from_settings", lambda: smtp_config)
    monkeypatch.setattr(reports_route, "send_email", _raise_smtp)

    response = client.post(
        "/api/reports/send",
        headers=admin_auth_headers,
        json={"report_type": "activity", "to": ["ops@example.com"]},
    )
    assert response.status_code == 502
    assert "Could not send report email" in response.json().get("detail", "")
