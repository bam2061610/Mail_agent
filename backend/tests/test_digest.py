from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.email import Email
from app.models.task import Task
from app.services.digest_service import generate_catchup_digest, mark_digest_seen


def test_generate_catchup_digest(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Email(
                message_id="<d1@test>",
                thread_id="<d1@test>",
                subject="Critical supplier email",
                sender_email="sales@supplier.com",
                folder="inbox",
                direction="inbound",
                status="new",
                priority="high",
                requires_reply=True,
                date_received=now - timedelta(hours=1),
            ),
            Email(
                message_id="<d2@test>",
                thread_id="<d2@test>",
                subject="Sent reply",
                sender_email="team@orhun.local",
                folder="sent",
                direction="sent",
                status="replied",
                date_received=now - timedelta(hours=2),
            ),
            Task(
                email_id=None,
                thread_id="<d1@test>",
                task_type="followup",
                title="Follow-up",
                state="overdue_reply",
                followup_started_at=now - timedelta(days=4),
            ),
        ]
    )
    db_session.commit()

    digest = generate_catchup_digest(db_session, SimpleNamespace(catchup_absence_hours=1), now=now)
    assert digest.important_new
    assert digest.waiting_or_overdue
    assert isinstance(digest.top_actions, list)


def test_mark_digest_seen(db_session):
    payload = mark_digest_seen(db_session)
    assert payload["last_seen_at"]
    assert payload["last_digest_viewed_at"]
