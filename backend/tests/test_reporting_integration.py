from datetime import datetime, timedelta, timezone

from app.models.email import Email
from app.models.task import Task


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

    db_session.add(
        Task(
            email_id=inbound.id,
            thread_id=inbound.thread_id,
            task_type="followup",
            title="Follow-up test",
            state="waiting_reply",
            followup_started_at=now - timedelta(days=1),
        )
    )
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

    pdf_export = client.get("/api/reports/followups/export?format=pdf", headers=admin_auth_headers)
    assert pdf_export.status_code == 200
    assert "application/pdf" in pdf_export.headers.get("content-type", "")
    assert "attachment;" in pdf_export.headers.get("content-disposition", "")


def test_team_activity_report_is_restricted_for_operator(client, operator_auth_headers):
    response = client.get("/api/reports/team-activity", headers=operator_auth_headers)
    assert response.status_code == 403
