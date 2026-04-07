from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(slots=True)
class ProcessLock:
    path: Path
    handle: TextIO | None
    acquired: bool


def acquire_process_lock(path: Path) -> ProcessLock:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        _ensure_lock_byte(handle)
        _lock_file(handle)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        return ProcessLock(path=path, handle=handle, acquired=True)
    except OSError:
        handle.close()
        return ProcessLock(path=path, handle=None, acquired=False)
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
