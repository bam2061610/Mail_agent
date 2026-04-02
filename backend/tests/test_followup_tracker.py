from datetime import datetime, timedelta, timezone

from app.models.email import Email
from app.services.followup_tracker import (
    close_waiting,
    compute_wait_days,
    detect_overdue_threads,
    get_waiting_threads,
    mark_thread_waiting,
)


def test_mark_and_close_waiting(db_session):
    email = Email(
        message_id="<fup-1@test>",
        thread_id="<thread-fup@test>",
        subject="Need follow-up",
        sender_email="partner@example.com",
        folder="inbox",
        direction="inbound",
        status="new",
    )
    db_session.add(email)
    db_session.commit()

    mark_thread_waiting(db_session, thread_id=email.thread_id, email_id=email.id, actor="test")
    db_session.commit()
    snapshots = get_waiting_threads(db_session)
    assert snapshots
    assert snapshots[0].state in {"waiting_reply", "overdue_reply"}

    close_waiting(db_session, thread_id=email.thread_id, reason="done", actor="test")
    db_session.commit()
    snapshots_after = get_waiting_threads(db_session)
    assert snapshots_after == []


def test_detect_overdue_and_wait_days(db_session):
    email = Email(
        message_id="<fup-2@test>",
        thread_id="<thread-overdue@test>",
        subject="Overdue thread",
        sender_email="partner@example.com",
        folder="inbox",
        direction="inbound",
        status="new",
    )
    db_session.add(email)
    db_session.commit()
    started = datetime.now(timezone.utc) - timedelta(days=5)
    mark_thread_waiting(db_session, thread_id=email.thread_id, started_at=started, email_id=email.id, actor="test")
    db_session.commit()
    detect_overdue_threads(db_session, now=datetime.now(timezone.utc), threshold_days=3)
    db_session.commit()
    wait_days = compute_wait_days(db_session, email.thread_id, now=datetime.now(timezone.utc))
    assert wait_days >= 5
