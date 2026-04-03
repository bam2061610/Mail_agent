from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.db import open_account_session
from app.services.imap_scanner import connect_imap, scan_inbox
from app.services.mailbox_service import get_enabled_mailbox_configs

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MailWatchResult:
    mailbox_id: str
    triggered_count: int = 0
    last_error: str | None = None
    started_at: float = field(default_factory=time.monotonic)


class MailWatcherManager:
    def __init__(
        self,
        mailbox_loader: Callable[[], Iterable[Any]] = get_enabled_mailbox_configs,
        connect_fn: Callable[[Any], Any] = connect_imap,
        scan_fn: Callable[[Any, Any], Any] = scan_inbox,
        *,
        idle_timeout_seconds: int = 55,
        fallback_probe_seconds: int = 30,
        reconnect_delay_seconds: int = 10,
    ) -> None:
        self._mailbox_loader = mailbox_loader
        self._connect_fn = connect_fn
        self._scan_fn = scan_fn
        self._idle_timeout_seconds = max(5, int(idle_timeout_seconds))
        self._fallback_probe_seconds = max(5, int(fallback_probe_seconds))
        self._reconnect_delay_seconds = max(1, int(reconnect_delay_seconds))
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started_mailboxes: list[str] = []

    @property
    def running(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def start(self) -> "MailWatcherManager":
        self._stop_event.clear()
        mailboxes = list(self._mailbox_loader() or [])
        self._started_mailboxes = [str(getattr(mailbox, "id", "")) for mailbox in mailboxes if getattr(mailbox, "id", None)]
        if not mailboxes:
            logger.info("Mail watcher not started: no enabled mailboxes found")
            return self

        for mailbox in mailboxes:
            mailbox_id = str(getattr(mailbox, "id", "") or "").strip() or "default"
            thread = threading.Thread(
                target=self._watch_mailbox_loop,
                args=(mailbox,),
                name=f"imap-watch-{mailbox_id}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
        logger.info("Mail watcher started for %s mailbox(es)", len(self._threads))
        return self

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()
        logger.info("Mail watcher stopped")

    def _watch_mailbox_loop(self, mailbox: Any) -> None:
        mailbox_id = str(getattr(mailbox, "id", "") or "").strip() or "default"
        mailbox_label = getattr(mailbox, "name", None) or getattr(mailbox, "email_address", None) or mailbox_id
        while not self._stop_event.is_set():
            connection = None
            try:
                connection = self._connect_fn(mailbox)
                if not _select_inbox(connection):
                    raise RuntimeError("Unable to select INBOX")
                logger.info("Mail watcher armed for mailbox=%s", mailbox_label)
                triggered = self._wait_for_message_signal(connection)
                if triggered:
                    self._trigger_scan(mailbox)
                if self._stop_event.is_set():
                    break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Mail watcher error for mailbox=%s: %s", mailbox_label, exc)
                if self._stop_event.wait(self._reconnect_delay_seconds):
                    break
            finally:
                _close_connection(connection)

    def _wait_for_message_signal(self, connection: Any) -> bool:
        if _supports_idle(connection):
            return _wait_using_idle(connection, self._stop_event, self._idle_timeout_seconds)
        return _wait_using_probe(connection, self._stop_event, self._fallback_probe_seconds)

    def _trigger_scan(self, mailbox: Any) -> None:
        mailbox_id = str(getattr(mailbox, "id", "") or "").strip() or "default"
        logger.info("Mail watcher detected activity for mailbox=%s; triggering sync", mailbox_id)
        db_session = open_account_session(mailbox_id)
        try:
            self._scan_fn(db_session, mailbox)
        finally:
            db_session.close()


def start_mail_watchers() -> MailWatcherManager:
    manager = MailWatcherManager()
    manager.start()
    return manager


def stop_mail_watchers(manager: MailWatcherManager | None) -> None:
    if manager is None:
        return
    manager.stop()


def _select_inbox(connection: Any) -> bool:
    try:
        status, _ = connection.select("INBOX", readonly=True)
        return status == "OK"
    except Exception:  # noqa: BLE001
        return False


def _supports_idle(connection: Any) -> bool:
    return callable(getattr(connection, "send", None)) and callable(getattr(connection, "readline", None))


def _wait_using_idle(connection: Any, stop_event: threading.Event, timeout_seconds: int) -> bool:
    sock = getattr(connection, "sock", None)
    previous_timeout = None
    if sock is not None and hasattr(sock, "gettimeout") and hasattr(sock, "settimeout"):
        previous_timeout = sock.gettimeout()
        sock.settimeout(timeout_seconds)

    saw_event = False
    try:
        connection.send(b"IDLE\r\n")
        greeting = connection.readline()
        if not greeting or not greeting.lstrip().startswith(b"+"):
            raise RuntimeError("Server did not accept IDLE command")
        while not stop_event.is_set():
            try:
                line = connection.readline()
            except socket.timeout:
                break
            if not line:
                break
            normalized = line.strip().upper()
            if b"EXISTS" in normalized or b"RECENT" in normalized:
                saw_event = True
                break
            if normalized.startswith(b"* BYE") or normalized.startswith(b"* BAD"):
                raise RuntimeError(normalized.decode("utf-8", errors="ignore") or "IMAP watcher disconnected")
    finally:
        try:
            connection.send(b"DONE\r\n")
            if hasattr(connection, "readline"):
                try:
                    connection.readline()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        if sock is not None and previous_timeout is not None:
            try:
                sock.settimeout(previous_timeout)
            except Exception:  # noqa: BLE001
                pass
    return saw_event


def _wait_using_probe(connection: Any, stop_event: threading.Event, probe_seconds: int) -> bool:
    last_known_count = _current_message_count(connection)
    while not stop_event.wait(probe_seconds):
        try:
            if callable(getattr(connection, "noop", None)):
                connection.noop()
            current_count = _current_message_count(connection)
        except Exception:  # noqa: BLE001
            return False
        if current_count is not None and (last_known_count is None or current_count > last_known_count):
            return True
        last_known_count = current_count
    return False


def _current_message_count(connection: Any) -> int | None:
    try:
        status, data = connection.select("INBOX", readonly=True)
        if status != "OK" or not data:
            return None
        raw_value = data[0]
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8", errors="ignore")
        return int(str(raw_value).split()[0])
    except Exception:  # noqa: BLE001
        return None


def _close_connection(connection: Any | None) -> None:
    if connection is None:
        return
    try:
        if callable(getattr(connection, "close", None)):
            connection.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        if callable(getattr(connection, "logout", None)):
            connection.logout()
    except Exception:  # noqa: BLE001
        pass
