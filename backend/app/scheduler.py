import logging
import os
from dataclasses import dataclass

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_effective_settings
from app.db import SessionLocal
from app.services.ai_analyzer import analyze_pending
from app.services.imap_scanner import scan_inbox

logger = logging.getLogger(__name__)

SCHEDULER_JOB_ID = "scan_and_analyze"


@dataclass(slots=True)
class ScheduledRunResult:
    imported_count: int
    analyzed_count: int
    errors_count: int
    errors: list[str]


def run_scan_and_analyze() -> ScheduledRunResult:
    logger.info("Scheduled scan/analyze job started")
    db_session = SessionLocal()
    settings = get_effective_settings()
    imported_count = 0
    analyzed_count = 0
    errors: list[str] = []

    try:
        try:
            scan_result = scan_inbox(db_session, settings)
            imported_count = scan_result.created_count
            errors.extend(scan_result.errors)
            logger.info(
                "Scheduled inbox scan finished: imported=%s fetched=%s skipped=%s errors=%s",
                scan_result.created_count,
                scan_result.fetched_messages,
                scan_result.skipped_count,
                len(scan_result.errors),
            )
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            error_message = f"scan_failed: {exc}"
            errors.append(error_message)
            logger.exception("Scheduled inbox scan failed")

        try:
            analysis_result = analyze_pending(db_session, settings)
            analyzed_count = analysis_result.analyzed_count
            errors.extend(analysis_result.errors)
            logger.info(
                "Scheduled email analysis finished: analyzed=%s failed=%s skipped=%s errors=%s",
                analysis_result.analyzed_count,
                analysis_result.failed_count,
                analysis_result.skipped_count,
                len(analysis_result.errors),
            )
        except Exception as exc:  # noqa: BLE001
            db_session.rollback()
            error_message = f"analysis_failed: {exc}"
            errors.append(error_message)
            logger.exception("Scheduled email analysis failed")
    finally:
        db_session.close()

    result = ScheduledRunResult(
        imported_count=imported_count,
        analyzed_count=analyzed_count,
        errors_count=len(errors),
        errors=errors,
    )
    logger.info(
        "Scheduled scan/analyze job completed: imported=%s analyzed=%s errors=%s",
        result.imported_count,
        result.analyzed_count,
        result.errors_count,
    )
    return result


def create_scheduler(config) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        },
        timezone="UTC",
    )
    scheduler.add_job(
        run_scan_and_analyze,
        trigger="interval",
        minutes=max(1, int(config.scan_interval_minutes)),
        id=SCHEDULER_JOB_ID,
        replace_existing=True,
    )
    return scheduler


def start_scheduler(app_or_config) -> BackgroundScheduler | None:
    config = getattr(app_or_config, "state", None)
    if config is not None:
        app = app_or_config
        existing_scheduler = getattr(app.state, "scheduler", None)
        if existing_scheduler is not None and existing_scheduler.running:
            logger.info("Scheduler already running; skipping duplicate start")
            return existing_scheduler

        if _should_skip_scheduler_start():
            logger.info("Scheduler start skipped in watcher/reload parent process")
            return None

        scheduler = create_scheduler(get_effective_settings())
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info(
            "Scheduler started with interval=%s minutes",
            max(1, int(get_effective_settings().scan_interval_minutes)),
        )
        return scheduler

    scheduler = create_scheduler(app_or_config)
    scheduler.start()
    logger.info(
        "Scheduler started with interval=%s minutes",
        max(1, int(app_or_config.scan_interval_minutes)),
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler | None) -> None:
    if scheduler is None:
        return
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _should_skip_scheduler_start() -> bool:
    # In some reload/watch setups the parent supervisor process should not run jobs.
    if os.environ.get("RUN_MAIN") == "false":
        return True
    return False
