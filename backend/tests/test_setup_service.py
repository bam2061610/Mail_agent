from app.schemas.system import SetupCompleteRequest
from app.services import setup_service
from app.services.settings_service import is_setup_completed
from app.services.user_service import get_user_by_email


class _DummyImapConnection:
    def select(self, _folder: str, readonly: bool = True):
        return ("OK", [b"1"])

    def close(self) -> None:
        return None

    def logout(self) -> None:
        return None


def test_complete_setup_reuses_recent_successful_validations(
    db_session,
    monkeypatch,
):
    ai_calls = {"count": 0}
    imap_calls = {"count": 0}
    smtp_calls = {"count": 0}

    monkeypatch.setattr(setup_service, "create_mailbox_with_session", lambda *_args, **_kwargs: {})

    def fake_chat(**_kwargs) -> str:
        ai_calls["count"] += 1
        return '{"ok": true}'

    def fake_connect(_mailbox):
        imap_calls["count"] += 1
        return _DummyImapConnection()

    def fake_smtp(_mailbox) -> None:
        smtp_calls["count"] += 1

    monkeypatch.setattr(setup_service, "call_deepseek_chat", fake_chat)
    monkeypatch.setattr(setup_service, "connect_imap", fake_connect)
    monkeypatch.setattr(setup_service, "test_smtp_connection", fake_smtp)

    setup_service.clear_setup_validation_cache()
    payload = SetupCompleteRequest(
        admin={
            "email": "admin@example.com",
            "full_name": "Admin",
            "password": "strong-pass-123",
            "confirm_password": "strong-pass-123",
        },
        ai={
            "deepseek_api_key": "secret-key",
            "deepseek_model": "deepseek-chat",
            "deepseek_base_url": "https://api.deepseek.com",
        },
        mailbox={
            "name": "Primary",
            "email_address": "mailbox@example.com",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_username": "mailbox@example.com",
            "imap_password": "imap-secret",
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_username": "mailbox@example.com",
            "smtp_password": "smtp-secret",
            "smtp_use_tls": True,
            "smtp_use_ssl": True,
            "enabled": True,
            "is_default_outgoing": True,
        },
        scheduler_interval_minutes=7,
        followup_overdue_days=4,
        max_emails_per_scan=150,
        ai_analysis_enabled=True,
    )

    setup_service.test_ai_configuration(payload.ai)
    setup_service.test_mailbox_configuration(payload.mailbox)

    assert ai_calls["count"] == 1
    assert imap_calls["count"] == 1
    assert smtp_calls["count"] == 1

    setup_service.complete_setup(db_session, payload)

    assert ai_calls["count"] == 1
    assert imap_calls["count"] == 1
    assert smtp_calls["count"] == 1
    assert is_setup_completed(db_session) is True
    assert get_user_by_email(db_session, "admin@example.com") is not None
