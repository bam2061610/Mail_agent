from app.models.email import Email
from app.services.mailbox_service import create_mailbox, get_enabled_mailbox_configs, get_mailbox, get_outgoing_mailbox_for_email, update_mailbox
from app.services.imap_scanner import scan_inbox


def test_multi_mailbox_create_and_select_outgoing(db_session):
    first = create_mailbox(
        {
            "name": "Primary",
            "email_address": "primary@example.com",
            "imap_host": "imap.primary",
            "imap_password": "x",
            "smtp_host": "smtp.primary",
            "smtp_password": "x",
        }
    )
    second = create_mailbox(
        {
            "name": "Secondary",
            "email_address": "secondary@example.com",
            "imap_host": "imap.secondary",
            "imap_password": "x",
            "smtp_host": "smtp.secondary",
            "smtp_password": "x",
            "is_default_outgoing": True,
        }
    )
    enabled = get_enabled_mailbox_configs()
    assert len(enabled) >= 2

    updated = update_mailbox(first["id"], {"name": "Primary Updated", "smtp_use_tls": False})
    assert updated is not None
    assert updated["name"] == "Primary Updated"
    persisted = get_mailbox(first["id"])
    assert persisted is not None
    assert persisted["name"] == "Primary Updated"

    email = Email(
        message_id="<mb-1@test>",
        subject="Mailbox bound email",
        sender_email="client@example.com",
        folder="inbox",
        direction="inbound",
        status="new",
        mailbox_id=first["id"],
    )
    db_session.add(email)
    db_session.commit()
    selected = get_outgoing_mailbox_for_email(email)
    assert selected is not None
    assert selected.id == first["id"]
    assert second["id"] != first["id"]


def test_imap_scanner_with_mocked_imap(db_session, monkeypatch):
    from datetime import datetime, timezone

    class FakeIMAP:
        def __init__(self, *_args, **_kwargs):
            pass

        def login(self, *_args, **_kwargs):
            return "OK", []

        def select(self, *_args, **_kwargs):
            return "OK", [b""]

        def search(self, *_args, **_kwargs):
            return "OK", [b"1"]

        def fetch(self, uid, query):
            raw_query = query.encode() if isinstance(query, str) else query
            if b"HEADER.FIELDS" in raw_query:
                return "OK", [(b"header", b"Message-ID: <imap-test@test>\r\n\r\n")]
            return (
                "OK",
                [
                        (
                            b"body",
                            b"Message-ID: <imap-test@test>\r\nSubject: IMAP mocked\r\nFrom: ext@example.com\r\nTo: a@example.com\r\nDate: Thu, 02 Apr 2026 10:00:00 +0000\r\n\r\nBody",
                        )
                    ],
                )

        def close(self):
            return "OK", []

        def logout(self):
            return "BYE", []

    import app.services.imap_scanner as scanner

    fixed_now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(scanner, "datetime", FrozenDatetime)
    monkeypatch.setattr(scanner.imaplib, "IMAP4_SSL", FakeIMAP)
    settings = type(
        "S",
        (),
        {
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "u",
            "imap_password": "p",
                "id": "mb-1",
                "name": "Mailbox 1",
                "email_address": "mb1@example.com",
            },
    )()
    summary = scan_inbox(db_session, settings)
    assert summary.created_count == 1
