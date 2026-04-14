from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from app.core.process_lock import ProcessLock


def test_worker_starts_and_stops_background_services(monkeypatch, tmp_path: Path):
    import app.worker as worker

    calls: list[str] = []
    stop_event = threading.Event()
    stop_event.set()

    monkeypatch.setattr(worker, "configure_logging", lambda *_args, **_kwargs: calls.append("configure_logging"))
    monkeypatch.setattr(worker, "create_tables", lambda: calls.append("create_tables"))
    monkeypatch.setattr(worker, "ensure_default_admin", lambda: calls.append("ensure_default_admin"))
    monkeypatch.setattr(
        worker,
        "acquire_process_lock",
        lambda _path: ProcessLock(path=tmp_path / "background-services.lock", handle=None, acquired=True),
    )
    monkeypatch.setattr(worker, "release_process_lock", lambda _lock: calls.append("release_process_lock"))
    monkeypatch.setattr(worker, "start_scheduler", lambda _config: calls.append("start_scheduler") or "scheduler")
    monkeypatch.setattr(worker, "stop_scheduler", lambda scheduler: calls.append(f"stop_scheduler:{scheduler}"))
    monkeypatch.setattr(worker, "start_mail_watchers", lambda: calls.append("start_mail_watchers") or "watchers")
    monkeypatch.setattr(worker, "stop_mail_watchers", lambda manager: calls.append(f"stop_mail_watchers:{manager}"))
    monkeypatch.setattr(worker, "is_setup_completed", lambda _db: True)
    monkeypatch.setattr(
        worker,
        "get_effective_settings",
        lambda: SimpleNamespace(run_background_jobs=True, run_mail_watchers=True, scan_interval_minutes=5),
    )

    result = worker.run_worker(stop_event=stop_event, install_signal_handlers=False)

    assert result == 0
    assert "start_scheduler" in calls
    assert "start_mail_watchers" in calls
    assert "stop_scheduler:scheduler" in calls
    assert "stop_mail_watchers:watchers" in calls
    assert "release_process_lock" in calls


def test_worker_exits_cleanly_when_lock_is_held(monkeypatch, tmp_path: Path):
    import app.worker as worker

    calls: list[str] = []
    monkeypatch.setattr(worker, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "create_tables", lambda: calls.append("create_tables"))
    monkeypatch.setattr(worker, "ensure_default_admin", lambda: calls.append("ensure_default_admin"))
    monkeypatch.setattr(
        worker,
        "acquire_process_lock",
        lambda _path: ProcessLock(path=tmp_path / "background-services.lock", handle=None, acquired=False),
    )
    monkeypatch.setattr(worker, "is_setup_completed", lambda _db: True)
    monkeypatch.setattr(worker, "start_scheduler", lambda _config: calls.append("start_scheduler"))
    monkeypatch.setattr(worker, "start_mail_watchers", lambda: calls.append("start_mail_watchers"))
    monkeypatch.setattr(
        worker,
        "get_effective_settings",
        lambda: SimpleNamespace(run_background_jobs=True, run_mail_watchers=True, scan_interval_minutes=5),
    )

    result = worker.run_worker(stop_event=threading.Event(), install_signal_handlers=False)

    assert result == 0
    assert calls == ["create_tables", "ensure_default_admin"]
