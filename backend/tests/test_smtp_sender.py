from types import SimpleNamespace

from app.services import smtp_sender


class DummySMTP:
    sent = False

    def __init__(self, *_args, **_kwargs):
        self.logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        return None

    def starttls(self, **_kwargs):
        return None

    def login(self, *_args, **_kwargs):
        self.logged_in = True

    def send_message(self, *_args, **_kwargs):
        DummySMTP.sent = True


def _config():
    return SimpleNamespace(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="bot@example.com",
        smtp_password="secret",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_address="bot@example.com",
    )


def test_send_reply_uses_smtp_transport(monkeypatch):
    monkeypatch.setattr(smtp_sender.smtplib, "SMTP", DummySMTP)
    sent_copy_calls = []
    monkeypatch.setattr(
        smtp_sender,
        "append_sent_copy_to_imap",
        lambda config, message, folder_kind="sent", save_copy_as_seen=True: sent_copy_calls.append((config, message["Subject"], folder_kind)),
    )
    result = smtp_sender.send_reply(
        to=["client@example.com"],
        subject="Re: Test",
        body="Hello",
        reply_to_message_id="<old@test>",
        config=_config(),
    )
    assert result.status == "sent"
    assert DummySMTP.sent is True
    assert "client@example.com" in result.recipients
    assert sent_copy_calls and sent_copy_calls[0][2] == "sent"


def test_send_email_appends_sent_copy(monkeypatch):
    monkeypatch.setattr(smtp_sender.smtplib, "SMTP", DummySMTP)
    sent_copy_calls = []
    monkeypatch.setattr(
        smtp_sender,
        "append_sent_copy_to_imap",
        lambda config, message, folder_kind="sent", save_copy_as_seen=True: sent_copy_calls.append((config, message["Subject"], folder_kind)),
    )
    result = smtp_sender.send_email(
        to=["client@example.com"],
        subject="Status update",
        body="Hello",
        config=_config(),
    )
    assert result.status == "sent"
    assert sent_copy_calls and sent_copy_calls[0][1] == "Status update"
