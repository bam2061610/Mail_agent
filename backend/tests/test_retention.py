from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.attachment import Attachment
from app.models.email import Email
from app.services.attachment_service import ParsedAttachment, save_attachments
from app.services.imap_scanner import _imap_date_criterion, _is_older_than_cutoff
from app.services.retention_service import cleanup_email_retention


def test_imap_scan_window_uses_last_day(monkeypatch):
    fixed_now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    import app.services.imap_scanner as imap_scanner

    monkeypatch.setattr(imap_scanner, "datetime", FrozenDatetime)

    assert _imap_date_criterion() == "SINCE 01-Apr-2026"


def test_scan_window_boundary_helper_is_strict():
    cutoff = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc) - timedelta(days=1)
    exact = cutoff
    newer = cutoff + timedelta(seconds=1)
    older = cutoff - timedelta(seconds=1)

    assert _is_older_than_cutoff(exact, cutoff) is False
    assert _is_older_than_cutoff(newer, cutoff) is False
    assert _is_older_than_cutoff(older, cutoff) is True


def test_retention_cleanup_prunes_old_content_and_keeps_exact_boundary(db_session, isolated_paths):
    now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=10)

    exact_email = Email(
        message_id="<exact@test>",
        thread_id="<exact@test>",
        subject="Exactly one day old",
        sender_email="sender@example.com",
        sender_name="Sender",
        recipients_json='[{"email":"recipient@example.com","name":"Recipient"}]',
        cc_json="[]",
        body_text="Keep me",
        body_html="<p>Keep me</p>",
        ai_summary="Exact boundary summary",
        folder="inbox",
        direction="inbound",
        status="new",
        date_received=cutoff,
        has_attachments=True,
        mailbox_id="mb-default",
    )
    old_email = Email(
        message_id="<old@test>",
        thread_id="<old@test>",
        subject="Older than one day",
        sender_email="sender@example.com",
        sender_name="Sender",
        recipients_json='[{"email":"recipient@example.com","name":"Recipient"}]',
        cc_json="[]",
        body_text="Old text body",
        body_html="<p>Old html body</p>",
        ai_summary="Old summary text",
        folder="inbox",
        direction="inbound",
        status="new",
        date_received=now - timedelta(days=10, seconds=1),
        has_attachments=True,
        mailbox_id="mb-default",
    )
    db_session.add_all([exact_email, old_email])
    db_session.flush()

    exact_attachment = ParsedAttachment(
        filename="exact.pdf",
        content_type="application/pdf",
        size_bytes=5,
        content_id=None,
        is_inline=False,
        payload=b"exact",
    )
    old_attachment = ParsedAttachment(
        filename="old.pdf",
        content_type="application/pdf",
        size_bytes=3,
        content_id=None,
        is_inline=False,
        payload=b"old",
    )
    save_attachments(db_session, exact_email.id, "mb-default", [exact_attachment])
    save_attachments(db_session, old_email.id, "mb-default", [old_attachment])
    db_session.commit()

    exact_attachment_path = Path(isolated_paths["attachments_dir"]) / "mb-default" / str(exact_email.id)
    old_attachment_path = Path(isolated_paths["attachments_dir"]) / "mb-default" / str(old_email.id)
    exact_files_before = sorted(exact_attachment_path.glob("*"))
    old_files_before = sorted(old_attachment_path.glob("*"))
    assert exact_files_before
    assert old_files_before

    result = cleanup_email_retention(db_session, now=now, retention_days=10)
    assert result.pruned_count == 1
    assert result.attachment_count == 1
    assert result.email_ids == [old_email.id]

    db_session.refresh(exact_email)
    db_session.refresh(old_email)

    assert exact_email.body_text == "Keep me"
    assert exact_email.body_html == "<p>Keep me</p>"
    assert exact_email.ai_summary == "Exact boundary summary"
    assert exact_email.message_id == "<exact@test>"
    assert exact_email.thread_id == "<exact@test>"

    assert old_email.body_text is None
    assert old_email.body_html is None
    assert old_email.ai_summary == "Old summary text"
    assert old_email.message_id == "<old@test>"
    assert old_email.thread_id == "<old@test>"
    assert old_email.has_attachments is False

    assert db_session.query(Attachment).filter(Attachment.email_id == old_email.id).count() == 0
    assert db_session.query(Attachment).filter(Attachment.email_id == exact_email.id).count() == 1
    assert not old_attachment_path.exists() or not any(old_attachment_path.iterdir())
    assert any(exact_attachment_path.iterdir())

    second_run = cleanup_email_retention(db_session, now=now, retention_days=10)
    assert second_run.pruned_count == 0
    assert second_run.attachment_count == 0


def test_retention_cleanup_handles_missing_body_and_missing_attachment_files(db_session, isolated_paths):
    now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    email = Email(
        message_id="<missing@test>",
        thread_id="<missing@test>",
        subject="Missing content",
        sender_email="sender@example.com",
        recipients_json="[]",
        cc_json="[]",
        ai_summary="Summary survives",
        folder="sent",
        direction="outbound",
        status="replied",
        date_received=now - timedelta(days=11),
        has_attachments=True,
        mailbox_id="mb-missing",
    )
    db_session.add(email)
    db_session.flush()

    attachment_path = Path(isolated_paths["attachments_dir"]) / "mb-missing" / str(email.id) / "missing.pdf"
    db_session.add(
        Attachment(
            email_id=email.id,
            filename="missing.pdf",
            content_type="application/pdf",
            size_bytes=10,
            content_id=None,
            is_inline=False,
            local_storage_path=str(attachment_path),
        )
    )
    db_session.commit()

    result = cleanup_email_retention(db_session, now=now, retention_days=10)
    assert result.pruned_count == 1
    assert result.attachment_count == 1

    db_session.refresh(email)
    assert email.body_text is None
    assert email.body_html is None
    assert email.ai_summary == "Summary survives"
    assert db_session.query(Attachment).filter(Attachment.email_id == email.id).count() == 0
