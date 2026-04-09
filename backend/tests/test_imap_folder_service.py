from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.imap_folder_service as imap_folder_service


class FakeImapConnection:
    def __init__(
        self,
        *,
        supports_move: bool,
        source_uid: str = "77",
        source_message_id: str = "<move@test>",
        fail_copy: bool = False,
        fail_store: bool = False,
        fail_expunge: bool = False,
        fail_move: bool = False,
        verify_target: bool = True,
    ) -> None:
        self.capabilities = {b"MOVE"} if supports_move else set()
        self.fail_copy = fail_copy
        self.fail_store = fail_store
        self.fail_expunge = fail_expunge
        self.fail_move = fail_move
        self.verify_target = verify_target
        self.selected_folder: str | None = None
        self.created_folders: list[str] = []
        self.search_log: list[tuple[str | None, str | None]] = []
        self.copy_calls: list[tuple[str, str]] = []
        self.move_calls: list[tuple[str, str]] = []
        self.store_calls: list[tuple[str, str, str]] = []
        self.fetch_calls: list[tuple[str | None, str | None]] = []
        self.closed = False
        self.logged_out = False
        self._next_uid = 100
        self._deleted_uids: set[str] = set()
        self._selected_readonly = False
        self.folders: dict[str, list[dict[str, object]]] = {
            "INBOX": [{"uid": source_uid, "message_id": source_message_id, "deleted": False}],
            "OMA": [],
            "OMA/Archive": [],
            "OMA/Spam": [],
            "OMA/Processed": [],
            "OMA/ReplyLater": [],
        }

    def list(self):
        payload = [f'(\\HasNoChildren) "/" "{folder}"'.encode("utf-8") for folder in self.folders]
        return "OK", payload

    def create(self, folder: str):
        normalized = folder.strip('"')
        self.folders.setdefault(normalized, [])
        self.created_folders.append(normalized)
        return "OK", [b"created"]

    def select(self, folder: str, readonly: bool = True):
        if folder not in self.folders:
            return "NO", [b"missing"]
        self.selected_folder = folder
        self._selected_readonly = readonly
        return "OK", [str(len([item for item in self.folders[folder] if not item.get("deleted")])).encode("utf-8")]

    def uid(self, command: str, *args):
        if command == "search":
            header_value = args[-1]
            if isinstance(header_value, bytes):
                header_value = header_value.decode("utf-8", errors="ignore")
            header_value = str(header_value)
            self.search_log.append((self.selected_folder, header_value))
            matches = [
                str(item["uid"])
                for item in self.folders.get(self.selected_folder or "", [])
                if not item.get("deleted") and item.get("message_id") == header_value
            ]
            if self.selected_folder == "INBOX" and header_value == "<retry@test>":
                matches = ["88"]
                self.folders["INBOX"].append({"uid": "88", "message_id": header_value, "deleted": False})
            if matches:
                return "OK", [" ".join(matches).encode("utf-8")]
            return "OK", [b""]

        if command == "fetch":
            uid = str(args[0])
            self.fetch_calls.append((self.selected_folder, uid))
            exists = any(
                str(item["uid"]) == uid and not item.get("deleted")
                for item in self.folders.get(self.selected_folder or "", [])
            )
            if exists:
                return "OK", [(b"data", f"{uid} (UID {uid})".encode("utf-8"))]
            return "OK", [b""]

        if command == "move":
            uid = str(args[0])
            target_folder = str(args[1])
            self.move_calls.append((uid, target_folder))
            if self.fail_move:
                return "NO", [b"move failed"]
            if self._selected_readonly:
                return "NO", [b"[READ-ONLY] move not allowed in read-only mode"]
            source_items = self.folders.get(self.selected_folder or "", [])
            source_item = next((item for item in source_items if str(item["uid"]) == uid and not item.get("deleted")), None)
            if source_item is None:
                return "NO", [b"missing"]
            new_uid = str(self._next_uid)
            self._next_uid += 1
            self.folders.setdefault(target_folder, []).append(
                {"uid": new_uid, "message_id": source_item["message_id"], "deleted": False}
            )
            source_items.remove(source_item)
            return "OK", [f"COPYUID 1 {uid} {new_uid}".encode("utf-8")]

        if command == "copy":
            uid = str(args[0])
            target_folder = str(args[1])
            self.copy_calls.append((uid, target_folder))
            if self.fail_copy:
                return "NO", [b"copy failed"]
            source_items = self.folders.get(self.selected_folder or "", [])
            source_item = next((item for item in source_items if str(item["uid"]) == uid and not item.get("deleted")), None)
            if source_item is None:
                return "NO", [b"missing"]
            new_uid = str(self._next_uid)
            self._next_uid += 1
            self.folders.setdefault(target_folder, []).append(
                {"uid": new_uid, "message_id": source_item["message_id"], "deleted": False}
            )
            return "OK", [f"COPYUID 1 {uid} {new_uid}".encode("utf-8")]

        if command == "store":
            uid = str(args[0])
            flags = str(args[1])
            value = str(args[2])
            self.store_calls.append((uid, flags, value))
            if self.fail_store:
                return "NO", [b"store failed"]
            if self._selected_readonly:
                return "NO", [b"[READ-ONLY] store not allowed in read-only mode"]
            source_items = self.folders.get(self.selected_folder or "", [])
            source_item = next((item for item in source_items if str(item["uid"]) == uid), None)
            if source_item is None:
                return "NO", [b"missing"]
            source_item["deleted"] = True
            self._deleted_uids.add(uid)
            return "OK", [b"stored"]

        return "NO", [b"unsupported"]

    def expunge(self):
        if self.fail_expunge:
            return "NO", [b"expunge failed"]
        source_items = self.folders.get(self.selected_folder or "", [])
        self.folders[self.selected_folder or ""] = [item for item in source_items if not item.get("deleted")]
        return "OK", [b"expunged"]

    def close(self):
        self.closed = True
        return "OK", []

    def logout(self):
        self.logged_out = True
        return "BYE", []


def _mailbox() -> SimpleNamespace:
    return SimpleNamespace(
        id="mailbox-1",
        name="Mailbox 1",
        email_address="mb1@example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="mb1@example.com",
        imap_password="secret",
    )


@pytest.fixture(autouse=True)
def clear_folder_cache():
    imap_folder_service._FOLDER_STATE_CACHE.clear()
    yield
    imap_folder_service._FOLDER_STATE_CACHE.clear()


def test_successful_move_path_verifies_target_and_resolves_backslash_hint(monkeypatch):
    connection = FakeImapConnection(supports_move=True)
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    result = imap_folder_service.move_email(
        _mailbox(),
        "77",
        "OMA\\Spam",
        source_folder="INBOX",
        message_id="<move@test>",
    )

    assert result.status == "moved"
    assert result.source_uid == "77"
    assert result.target_uid == "100"
    assert result.target_folder == "OMA/Spam"
    assert connection.move_calls == [("77", "OMA/Spam")]


def test_successful_copy_delete_path_verifies_target(monkeypatch):
    connection = FakeImapConnection(supports_move=False)
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    result = imap_folder_service.move_email(
        _mailbox(),
        "77",
        "archive",
        source_folder="INBOX",
        message_id="<move@test>",
    )

    assert result.status == "moved"
    assert result.source_uid == "77"
    assert result.target_uid == "100"
    assert result.target_folder == "OMA/Archive"
    assert connection.copy_calls == [("77", "OMA/Archive")]
    assert connection.store_calls == [("77", "+FLAGS.SILENT", r"(\Deleted)")]
    assert connection.folders["INBOX"] == []


def test_copy_failure_raises(monkeypatch):
    connection = FakeImapConnection(supports_move=False, fail_copy=True)
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    with pytest.raises(RuntimeError, match="IMAP move failed"):
        imap_folder_service.move_email(
            _mailbox(),
            "77",
            "spam",
            source_folder="INBOX",
            message_id="<move@test>",
        )


@pytest.mark.parametrize("fail_stage", ["store", "expunge"])
def test_copy_delete_failure_on_store_or_expunge(monkeypatch, fail_stage):
    connection = FakeImapConnection(
        supports_move=False,
        fail_store=fail_stage == "store",
        fail_expunge=fail_stage == "expunge",
    )
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    with pytest.raises(RuntimeError, match="IMAP move failed"):
        imap_folder_service.move_email(
            _mailbox(),
            "77",
            "processed",
            source_folder="INBOX",
            message_id="<move@test>",
        )


def test_stale_uid_retries_via_message_id(monkeypatch):
    connection = FakeImapConnection(supports_move=True)
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    result = imap_folder_service.move_email(
        _mailbox(),
        "999",
        "spam",
        source_folder="INBOX",
        message_id="<retry@test>",
    )

    assert result.source_uid == "88"
    assert result.target_uid == "100"
    assert connection.search_log[0] == ("INBOX", "<retry@test>")
    assert connection.move_calls == [("999", "OMA/Spam"), ("88", "OMA/Spam")]


def test_scoped_message_id_uses_raw_message_id_for_search(monkeypatch):
    connection = FakeImapConnection(supports_move=True, source_message_id="<raw@test>")
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    imap_folder_service.move_email(
        _mailbox(),
        None,
        "spam",
        source_folder="INBOX",
        message_id="<raw@test>::mailbox-1",
    )

    assert connection.search_log[0] == ("INBOX", "<raw@test>")


def test_stale_uid_retry_reselects_folder_as_writable(monkeypatch):
    """Regression: after _find_message_uid selects folder readonly, the retry must
    re-select it writable before calling _try_move_or_copy (COPY+DELETE path)."""
    connection = FakeImapConnection(supports_move=False, source_uid="88", source_message_id="<retry-write@test>")
    # Add a stale uid that doesn't exist so the first attempt fails
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    result = imap_folder_service.move_email(
        _mailbox(),
        "999",  # stale uid — not present in INBOX
        "spam",
        source_folder="INBOX",
        message_id="<retry-write@test>",
    )

    assert result.status == "moved"
    assert result.source_uid == "88"
    # INBOX must be empty — message was deleted from source
    assert connection.folders["INBOX"] == []
    assert any(item["message_id"] == "<retry-write@test>" for item in connection.folders.get("OMA/Spam", []))


def test_move_verification_fails_when_target_folder_is_empty(monkeypatch):
    connection = FakeImapConnection(supports_move=True, verify_target=False)
    original_uid = connection.uid

    def broken_move(command: str, *args):
        if command == "move":
            uid = str(args[0])
            target_folder = str(args[1])
            connection.move_calls.append((uid, target_folder))
            return "OK", [f"COPYUID 1 {uid} 100".encode("utf-8")]
        return original_uid(command, *args)

    monkeypatch.setattr(connection, "uid", broken_move)
    monkeypatch.setattr(imap_folder_service, "connect_imap", lambda _mailbox: connection)

    with pytest.raises(RuntimeError, match="verification failed"):
        imap_folder_service.move_email(
            _mailbox(),
            "77",
            "spam",
            source_folder="INBOX",
            message_id="<move@test>",
        )
