from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


@dataclass(slots=True)
class ProcessLock:
    path: Path
    handle: TextIO | None = None
    acquired: bool = False
    status: str = "unavailable"
    owner_pid: int | None = None
    owner_hostname: str | None = None
    owner_instance_id: str | None = None
    acquired_at: str | None = None
    stale: bool = False
    diagnostic: str | None = None


@dataclass(slots=True)
class ProcessLockMetadata:
    pid: int | None = None
    hostname: str | None = None
    instance_id: str | None = None
    acquired_at: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


def read_process_lock_metadata(path: Path) -> ProcessLockMetadata:
    if not path.exists():
        return ProcessLockMetadata()
    try:
        raw_text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ProcessLockMetadata()
    if not raw_text:
        return ProcessLockMetadata()
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            pid = int(raw_text)
        except ValueError:
            pid = None
        return ProcessLockMetadata(pid=pid, raw={"legacy": raw_text})
    if not isinstance(payload, dict):
        return ProcessLockMetadata(raw={"payload": payload})
    pid = payload.get("pid")
    try:
        pid_value = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_value = None
    hostname = str(payload.get("hostname") or "").strip() or None
    instance_id = str(payload.get("instance_id") or "").strip() or None
    acquired_at = str(payload.get("acquired_at") or "").strip() or None
    return ProcessLockMetadata(pid=pid_value, hostname=hostname, instance_id=instance_id, acquired_at=acquired_at, raw=payload)


def acquire_process_lock(path: Path) -> ProcessLock:
    path.parent.mkdir(parents=True, exist_ok=True)
    current_metadata = _build_current_lock_metadata()
    stale_metadata = read_process_lock_metadata(path)
    attempt = 0
    while True:
        attempt += 1
        handle = path.open("a+", encoding="utf-8")
        try:
            _ensure_lock_byte(handle)
            _lock_file(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps(current_metadata, ensure_ascii=False))
            handle.flush()
            stale = bool(stale_metadata.pid and stale_metadata.pid != os.getpid() and not _is_process_alive(stale_metadata.pid))
            return ProcessLock(
                path=path,
                handle=handle,
                acquired=True,
                status="acquired",
                owner_pid=current_metadata["pid"],
                owner_hostname=current_metadata["hostname"],
                owner_instance_id=current_metadata["instance_id"],
                acquired_at=current_metadata["acquired_at"],
                stale=stale,
            )
        except OSError:
            handle.close()
            metadata = read_process_lock_metadata(path)
            stale = bool(metadata.pid and metadata.pid != os.getpid() and not _is_process_alive(metadata.pid))
            status = "stale" if stale else "held"
            diagnostic = "stale_lock_detected" if stale else "lock_held_by_live_process"
            if stale and attempt == 1:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    return ProcessLock(
                        path=path,
                        handle=None,
                        acquired=False,
                        status=status,
                        owner_pid=metadata.pid,
                        owner_hostname=metadata.hostname,
                        owner_instance_id=metadata.instance_id,
                        acquired_at=metadata.acquired_at,
                        stale=stale,
                        diagnostic="stale_lock_cleanup_failed",
                    )
                continue
            return ProcessLock(
                path=path,
                handle=None,
                acquired=False,
                status=status,
                owner_pid=metadata.pid,
                owner_hostname=metadata.hostname,
                owner_instance_id=metadata.instance_id,
                acquired_at=metadata.acquired_at,
                stale=stale,
                diagnostic=diagnostic,
            )
        except Exception:
            handle.close()
            raise


def release_process_lock(lock: ProcessLock | None) -> None:
    if lock is None or lock.handle is None:
        return

    handle = lock.handle
    try:
        _unlock_file(handle)
    except OSError:
        pass
    finally:
        try:
            handle.close()
        except OSError:
            pass

    try:
        if lock.path.exists():
            lock.path.unlink()
    except OSError:
        pass


def inspect_process_lock(path: Path) -> ProcessLock:
    metadata = read_process_lock_metadata(path)
    stale = bool(metadata.pid and metadata.pid != os.getpid() and not _is_process_alive(metadata.pid))
    return ProcessLock(
        path=path,
        handle=None,
        acquired=False,
        status="stale" if stale else ("held" if metadata.pid else "unavailable"),
        owner_pid=metadata.pid,
        owner_hostname=metadata.hostname,
        owner_instance_id=metadata.instance_id,
        acquired_at=metadata.acquired_at,
        stale=stale,
        diagnostic="stale_lock_detected" if stale else None,
    )


def _ensure_lock_byte(handle: TextIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() > 0:
        handle.seek(0)
        return
    handle.write("0")
    handle.flush()
    handle.seek(0)


def _lock_file(handle: TextIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: TextIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _build_current_lock_metadata() -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "instance_id": os.getenv("HOSTNAME") or socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }


def _is_process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception:  # noqa: BLE001
            return False
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
