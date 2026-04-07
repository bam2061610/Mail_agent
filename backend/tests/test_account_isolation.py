from pathlib import Path

from app.config import load_runtime_settings, save_runtime_settings
from app.db import get_account_database_url, open_account_session, reset_current_mailbox_id, set_current_mailbox_id
from app.models.email import Email


def test_mailbox_accounts_use_isolated_sqlite_databases(db_session, isolated_paths):
    mailbox_a = "mailbox-a"
    mailbox_b = "mailbox-b"

    db_url_a = get_account_database_url(mailbox_a)
    db_url_b = get_account_database_url(mailbox_b)
    assert db_url_a != db_url_b

    token_a = set_current_mailbox_id(mailbox_a)
    try:
        save_runtime_settings({"signature": "Signature A", "interface_language": "en", "summary_language": "en", "scan_since_date": "2026-04-01T00:00:00Z"})
        settings_a = load_runtime_settings()
        assert settings_a["signature"] == "Signature A"
        assert settings_a["interface_language"] == "en"
        assert settings_a["summary_language"] == "en"
        assert settings_a["scan_since_date"] == "2026-04-01T00:00:00Z"
    finally:
        reset_current_mailbox_id(token_a)

    token_b = set_current_mailbox_id(mailbox_b)
    try:
        save_runtime_settings({"signature": "Signature B", "interface_language": "ru", "summary_language": "ru", "scan_since_date": "2026-04-02T00:00:00Z"})
        settings_b = load_runtime_settings()
        assert settings_b["signature"] == "Signature B"
        assert settings_b["interface_language"] == "ru"
        assert settings_b["summary_language"] == "ru"
        assert settings_b["scan_since_date"] == "2026-04-02T00:00:00Z"
    finally:
        reset_current_mailbox_id(token_b)

    account_a = open_account_session(mailbox_a)
    account_b = open_account_session(mailbox_b)
    try:
        account_a.add(
            Email(
                message_id="<a@test>",
                thread_id="thread-a",
                subject="Account A",
                sender_email="a@example.com",
                body_text="A body",
                folder="inbox",
                direction="inbound",
                status="new",
            )
        )
        account_a.commit()

        account_b.add(
            Email(
                message_id="<b@test>",
                thread_id="thread-b",
                subject="Account B",
                sender_email="b@example.com",
                body_text="B body",
                folder="inbox",
                direction="inbound",
                status="new",
            )
        )
        account_b.commit()

        count_a = account_a.query(Email).count()
        count_b = account_b.query(Email).count()
        assert count_a == 1
        assert count_b == 1

        assert account_a.query(Email).filter(Email.thread_id == "thread-b").count() == 0
        assert account_b.query(Email).filter(Email.thread_id == "thread-a").count() == 0
    finally:
        account_a.close()
        account_b.close()

    assert Path(db_url_a.removeprefix("sqlite:///")).exists()
    assert Path(db_url_b.removeprefix("sqlite:///")).exists()
