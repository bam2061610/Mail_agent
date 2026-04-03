from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from app.services.mail_watcher import MailWatcherManager


class FakeIdleConnection:
    def __init__(self) -> None:
        self.commands: list[bytes] = []
        self.select_calls = 0
        self.readline_calls = 0
        self.closed = False
        self.logged_out = False
        self.sock = SimpleNamespace(gettimeout=lambda: None, settimeout=lambda *_args, **_kwargs: None)

    def select(self, folder: str, readonly: bool = True):
        self.select_calls += 1
        return "OK", [b"1"]

    def send(self, payload: bytes):
        self.commands.append(payload)

    def readline(self):
        self.readline_calls += 1
        if self.readline_calls == 1:
            return b"+ idling\r\n"
        if self.readline_calls == 2:
            return b"* 1 EXISTS\r\n"
        return b"OK\r\n"

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True


def test_mail_watcher_initializes_and_triggers_scan(monkeypatch):
    mailbox = SimpleNamespace(id="mb-real", name="Real mailbox", email_address="real@example.com")
    triggered = threading.Event()
    stopped = threading.Event()

    fake_connection = FakeIdleConnection()

    def fake_connect(_mailbox):
        return fake_connection

    def fake_scan(db_session, runtime_mailbox):
        assert runtime_mailbox.id == mailbox.id
        assert db_session is not None
        triggered.set()
        stopped.set()

    manager = MailWatcherManager(
        mailbox_loader=lambda: [mailbox],
        connect_fn=fake_connect,
        scan_fn=fake_scan,
        idle_timeout_seconds=1,
        fallback_probe_seconds=1,
        reconnect_delay_seconds=1,
    )
    manager.start()
    assert manager.running is True

    assert triggered.wait(timeout=5)
    stopped.set()
    manager.stop()
    assert fake_connection.closed is True or fake_connection.logged_out is True

