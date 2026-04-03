from __future__ import annotations

from email.message import EmailMessage
from types import SimpleNamespace

from app.models.email import Email
from app.services.imap_mailbox_actions import append_sent_copy_to_imap, reply_later_email_via_imap


class FakeIMAPConnection:
    def __init__(self, *, message_id: str) -> None:
        self.message_id = message_id
        self.folders = ["INBOX"]
        self.created_folders: list[str] = []
        self.selected_folder: str | None = None
        self.copy_targets: list[str] = []
        self.appended_folders: list[str] = []
        self.store_calls: list[tuple[bytes, str, str]] = []
        self.closed = False
        self.logged_out = False

    def list(self):
        payload = [f'(\\HasNoChildren) "/" "{folder}"'.encode("utf-8") for folder in self.folders]
        return "OK", payload

    def create(self, folder: str):
        if folder not in self.folders:
            self.folders.append(folder)
            self.created_folders.append(folder)
        return "OK", [b"created"]

    def select(self, folder: str, readonly: bool = True):
        self.selected_folder = folder
        if folder.lower() == "inbox":
            return "OK", [b"1"]
        if folder in self.folders:
            return "OK", [b"1"]
        return "NO", [b"missing"]

    def uid(self, command: str, *args):
        if command == "search":
            _, header_name, header_value = args[1:]
            if self.selected_folder and self.selected_folder.lower() == "inbox" and header_name == "Message-ID" and header_value == self.message_id:
                return "OK", [b"1"]
            return "OK", [b""]
        if command == "store":
            uid = args[0]
            flags = args[1]
            value = args[2]
            self.store_calls.append((uid, flags, value))
            return "OK", [b"stored"]
        if command == "copy":
            uid = args[0]
            target = args[1]
            self.copy_targets.append(target)
            return "OK", [b"copied"]
        return "NO", [b"unsupported"]

    def append(self, folder, flags, date_time, raw_bytes):
        self.appended_folders.append(folder)
        self.folders.append(folder)
        return "OK", [b"appended"]

    def expunge(self):
        return "OK", [b"expunged"]

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True


def _mailbox_config():
    return SimpleNamespace(
        id="mb-default",
        name="Default",
        email_address="sender@example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="sender@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="sender@example.com",
        smtp_password="secret",
        smtp_use_tls=False,
        smtp_use_ssl=True,
    )


def test_reply_later_moves_message_and_creates_folder(db_session, monkeypatch):
    email = Email(
        message_id="<reply-later@test>",
        thread_id="<reply-later@test>",
        subject="Reply later",
        sender_email="sender@example.com",
        recipients_json="[]",
        cc_json="[]",
        folder="INBOX",
        direction="inbound",
        status="read",
        requires_reply=True,
        mailbox_id="mb-default",
    )
    db_session.add(email)
    db_session.commit()
    db_session.refresh(email)

    fake_connection = FakeIMAPConnection(message_id=email.message_id)
    monkeypatch.setattr("app.services.imap_mailbox_actions.connect_imap", lambda _config: fake_connection)

    result = reply_later_email_via_imap(db_session, email, _mailbox_config())

    assert result.status == "moved"
    assert "Reply Later" in fake_connection.created_folders
    assert fake_connection.copy_targets == ["Reply Later"]
    db_session.refresh(email)
    assert email.folder == "Reply Later"
    assert email.status == "archived"
    assert email.requires_reply is False


def test_append_sent_copy_uses_sent_folder(db_session, monkeypatch):
    fake_connection = FakeIMAPConnection(message_id="<sent-copy@test>")
    monkeypatch.setattr("app.services.imap_mailbox_actions.connect_imap", lambda _config: fake_connection)

    message = EmailMessage()
    message["Subject"] = "Sent copy"
    message["From"] = "sender@example.com"
    message["To"] = "client@example.com"
    message.set_content("Hello from sent copy")

    folder = append_sent_copy_to_imap(_mailbox_config(), message)

    assert folder == "Sent"
    assert "Sent" in fake_connection.created_folders
    assert fake_connection.appended_folders == ["Sent"]

