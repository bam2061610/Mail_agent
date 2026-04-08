from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.process_lock import ProcessLock


def test_backend_startup_skips_background_lock_when_background_services_are_disabled(
    monkeypatch,
    tmp_path,
):
    import app.main as main_module

    calls: list[str] = []
    dummy_db = SimpleNamespace(close=lambda: calls.append("db.close"))

    monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main_module, "configure_logging", lambda *_args, **_kwargs: calls.append("configure_logging"))
    monkeypatch.setattr(main_module, "create_tables", lambda: calls.append("create_tables"))
    monkeypatch.setattr(main_module, "ensure_default_admin", lambda: calls.append("ensure_default_admin"))
    monkeypatch.setattr(main_module, "open_global_session", lambda: dummy_db)
    monkeypatch.setattr(main_module, "is_setup_completed", lambda _db: True)
    monkeypatch.setattr(
        main_module,
        "get_effective_settings",
        lambda: SimpleNamespace(run_background_jobs=False, run_mail_watchers=False),
    )
    monkeypatch.setattr(
        main_module,
        "acquire_process_lock",
        lambda _path: calls.append("acquire_process_lock") or ProcessLock(path=tmp_path / "background-services.lock", acquired=True),
    )
    monkeypatch.setattr(
        main_module,
        "release_process_lock",
        lambda lock: calls.append(f"release_process_lock:{getattr(lock, 'acquired', None)}"),
    )
    monkeypatch.setattr(main_module, "start_scheduler", lambda *_args, **_kwargs: calls.append("start_scheduler") or object())
    monkeypatch.setattr(main_module, "stop_scheduler", lambda scheduler: calls.append(f"stop_scheduler:{scheduler is not None}"))
    monkeypatch.setattr(main_module, "start_mail_watchers", lambda: calls.append("start_mail_watchers") or object())
    monkeypatch.setattr(main_module, "stop_mail_watchers", lambda watchers: calls.append(f"stop_mail_watchers:{watchers is not None}"))
    main_module.app.dependency_overrides.clear()

    with TestClient(main_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "acquire_process_lock" not in calls
    assert "start_scheduler" not in calls
    assert "start_mail_watchers" not in calls
    assert "release_process_lock:False" in calls

    background_lock = main_module.app.state.background_lock
    assert isinstance(background_lock, ProcessLock)
    assert background_lock.path == tmp_path / "background-services.lock"
    assert background_lock.handle is None
    assert background_lock.acquired is False
