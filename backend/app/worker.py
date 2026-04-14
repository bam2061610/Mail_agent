from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable

from app.config import DATA_DIR, get_effective_settings, settings
from app.core.logging import configure_logging
from app.core.process_lock import ProcessLock, acquire_process_lock, release_process_lock
from app.db import create_tables
from app.scheduler import start_scheduler, stop_scheduler
from app.services.mail_watcher import start_mail_watchers, stop_mail_watchers
from app.services.settings_service import is_setup_completed
from app.services.user_service import ensure_default_admin

logger = logging.getLogger(__name__)
BACKGROUND_LOCK_PATH = DATA_DIR / "background-services.lock"


def run_worker(
    *,
    stop_event: threading.Event | None = None,
    install_signal_handlers: bool = True,
) -> int:
    configure_logging(settings.debug)
    create_tables()
    ensure_default_admin()
    runtime_settings = get_effective_settings()
    from app.db import open_global_session

    db = open_global_session()
    try:
        setup_completed = is_setup_completed(db)
    finally:
        db.close()

    if not setup_completed:
        logger.info("Worker startup skipped because setup is not complete")
        return 0

    if not runtime_settings.run_background_jobs and not runtime_settings.run_mail_watchers:
        logger.info("Worker startup skipped because background jobs and mail watchers are disabled")
        return 0

    lock = acquire_process_lock(BACKGROUND_LOCK_PATH)
    if not lock.acquired:
        logger.warning("Background worker lock is already held by another process; worker will exit")
        return 0

    local_stop_event = stop_event or threading.Event()
    restore_handlers = (
        _install_signal_handlers(local_stop_event)
        if install_signal_handlers and threading.current_thread() is threading.main_thread()
        else []
    )
    scheduler = None
    mail_watchers = None

    try:
        if runtime_settings.run_background_jobs:
            scheduler = start_scheduler(runtime_settings)
            logger.info("Background worker started scheduler")

        if runtime_settings.run_mail_watchers:
            mail_watchers = start_mail_watchers()
            logger.info("Background worker started mail watchers")

        while not local_stop_event.wait(0.5):
            pass
        logger.info("Background worker received stop signal")
        return 0
    finally:
        stop_mail_watchers(mail_watchers)
        stop_scheduler(scheduler)
        release_process_lock(lock)
        for signum, handler in restore_handlers:
            signal.signal(signum, handler)


def main() -> int:
    return run_worker()


def _install_signal_handlers(stop_event: threading.Event) -> list[tuple[int, Callable]]:
    previous_handlers: list[tuple[int, Callable]] = []

    def _handle_signal(_signum, _frame) -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers.append((signum, signal.getsignal(signum)))
        signal.signal(signum, _handle_signal)
    return previous_handlers


if __name__ == "__main__":
    raise SystemExit(main())
