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
