from contextlib import asynccontextmanager
import os
import logging
import socket
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes.actions import router as actions_router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.emails import router as emails_router
from app.api.routes.health import router as health_router
from app.api.routes.reports import router as reports_router
from app.api.routes.settings import router as settings_router
from app.api.routes.setup import router as setup_router
from app.api.routes.stats import router as stats_router
from app.api.routes.users import router as users_router
from app.config import DATA_DIR, get_effective_settings, settings
from app.core.logging import configure_logging
from app.core.api_errors import ApiError, api_error, infer_api_error_from_http_exception
from app.core.process_lock import ProcessLock, acquire_process_lock, release_process_lock
from app.core.rate_limiter import limiter
from app.db import (
    create_tables,
    open_global_session,
    reset_current_mailbox_id,
    resolve_mailbox_id_from_request,
    set_current_mailbox_id,
)
from app.scheduler import start_scheduler, stop_scheduler
from app.services.mail_watcher import start_mail_watchers, stop_mail_watchers
from app.services.settings_service import is_setup_completed
from app.services.user_service import ensure_default_admin

logger = logging.getLogger(__name__)
FRONTEND_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend_dist"
PUBLIC_API_PREFIXES = ("/api/setup", "/api/auth/login")
PUBLIC_PATHS = {"/health", "/api/system/status", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


def _build_startup_state() -> dict[str, object]:
    return {
        "process_started": False,
        "logging_initialized": False,
        "data_dir_exists": False,
        "data_dir_writable": False,
        "setup_completed": False,
        "startup_completed": False,
        "background_lock_path": str(DATA_DIR / "background-services.lock"),
        "background_lock_status": "unavailable",
        "background_lock_present": False,
        "background_lock_owned_by_current_process": False,
        "background_lock_owner_pid": None,
        "background_lock_owner_hostname": None,
        "background_lock_owner_instance_id": None,
        "scheduler_running": False,
        "watchers_running": False,
        "static_frontend_available": FRONTEND_DIST_DIR.exists(),
        "startup_error": None,
    }


def _ensure_data_dir_ready() -> tuple[bool, bool]:
    existed = DATA_DIR.exists()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("DATA_DIR unavailable: path=%s error=%s", DATA_DIR, exc, exc_info=True)
        raise RuntimeError("data_dir_unavailable") from exc

    probe = DATA_DIR / ".startup-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        if not existed:
            logger.info("Created DATA_DIR path=%s", DATA_DIR)
        return True, True
    except OSError as exc:
        logger.error("DATA_DIR not writable: path=%s error=%s", DATA_DIR, exc, exc_info=True)
        raise RuntimeError("data_dir_unavailable") from exc


def _startup_lock_summary(lock: ProcessLock) -> dict[str, object]:
    return {
        "background_lock_status": lock.status,
        "background_lock_present": lock.path.exists(),
        "background_lock_owned_by_current_process": bool(lock.acquired),
        "background_lock_owner_pid": lock.owner_pid,
        "background_lock_owner_hostname": lock.owner_hostname,
        "background_lock_owner_instance_id": lock.owner_instance_id,
    }


def _extract_request_mailbox_id(request: Request) -> str | None:
    mailbox_id = request.headers.get("X-Mailbox-Id") or request.query_params.get("mailbox_id")
    normalized = str(mailbox_id or "").strip()
    return normalized or None


def _structured_error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_payload())


def _log_startup_stage(message: str, **fields: object) -> None:
    extras = ", ".join(f"{key}={value}" for key, value in fields.items())
    if extras:
        logger.info("%s | %s", message, extras)
    else:
        logger.info(message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    app.state.startup_state = _build_startup_state()
    app.state.startup_state["process_started"] = True
    _log_startup_stage("Process start", pid=os.getpid(), hostname=socket.gethostname(), data_dir=DATA_DIR)
    _log_startup_stage("Entering lifespan")
    app.state.startup_state["logging_initialized"] = True
    _log_startup_stage("Logging initialization complete")
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to reset in-memory rate limiter state on startup", exc_info=True)
    _log_startup_stage("Table creation/check starting")
    _ensure_data_dir_ready_state = _ensure_data_dir_ready()
    app.state.startup_state["data_dir_exists"], app.state.startup_state["data_dir_writable"] = _ensure_data_dir_ready_state
    _log_startup_stage(
        "DATA_DIR verified",
        path=DATA_DIR,
        exists=app.state.startup_state["data_dir_exists"],
        writable=app.state.startup_state["data_dir_writable"],
    )
    create_tables()
    _log_startup_stage("Table creation/check complete")
    ensure_default_admin()
    _log_startup_stage("Default admin ensured")
    runtime_settings = get_effective_settings()
    db = open_global_session()
    try:
        setup_completed = is_setup_completed(db)
    finally:
        db.close()
    app.state.startup_state["setup_completed"] = setup_completed
    _log_startup_stage("Setup state check result", setup_completed=setup_completed)
    needs_lock = setup_completed and (
        runtime_settings.run_background_jobs or runtime_settings.run_mail_watchers
    )
    lock_path = DATA_DIR / "background-services.lock"
    _log_startup_stage("Attempting background lock acquisition", path=lock_path, needed=needs_lock)
    background_lock = (
        acquire_process_lock(lock_path)
        if needs_lock
        else ProcessLock(path=lock_path, acquired=False, status="skipped")
    )
    app.state.background_lock = background_lock
    app.state.startup_state.update(_startup_lock_summary(background_lock))
    if background_lock.acquired:
        _log_startup_stage(
            "Background lock acquired",
            path=lock_path,
            owner_pid=background_lock.owner_pid,
            owner_hostname=background_lock.owner_hostname,
            owner_instance_id=background_lock.owner_instance_id,
            stale=background_lock.stale,
        )
    elif background_lock.status == "stale":
        logger.error(
            "Stale background lock detected and not recovered: path=%s owner_pid=%s owner_hostname=%s owner_instance_id=%s diagnostic=%s",
            lock_path,
            background_lock.owner_pid,
            background_lock.owner_hostname,
            background_lock.owner_instance_id,
            background_lock.diagnostic,
        )
    else:
        _log_startup_stage(
            "Background lock not acquired",
            path=lock_path,
            status=background_lock.status,
            owner_pid=background_lock.owner_pid,
            owner_hostname=background_lock.owner_hostname,
            owner_instance_id=background_lock.owner_instance_id,
        )

    scheduler = None
    mail_watchers = None
    if not setup_completed:
        _log_startup_stage("Setup is not complete; skipping background scheduler and mail watcher startup")
    elif background_lock.acquired:
        if runtime_settings.run_background_jobs:
            _log_startup_stage("Scheduler startup requested")
            scheduler = start_scheduler(app)
            _log_startup_stage("Scheduler startup complete", running=bool(getattr(scheduler, "running", False)))
        if runtime_settings.run_mail_watchers:
            _log_startup_stage("Mail watcher startup requested")
            mail_watchers = start_mail_watchers()
            _log_startup_stage("Mail watcher startup complete", running=bool(mail_watchers))
    else:
        _log_startup_stage(
            "Background services already owned by another process; skipping local scheduler/watchers start",
            status=background_lock.status,
        )

    app.state.mail_watchers = mail_watchers
    app.state.scheduler = scheduler
    app.state.startup_state["scheduler_running"] = bool(scheduler and getattr(scheduler, "running", False))
    app.state.startup_state["watchers_running"] = bool(mail_watchers)
    app.state.startup_state["startup_completed"] = True
    _log_startup_stage(
        "Startup complete",
        scheduler_running=app.state.startup_state["scheduler_running"],
        watchers_running=app.state.startup_state["watchers_running"],
    )
    try:
        yield
    finally:
        _log_startup_stage("Shutdown starting")
        stop_mail_watchers(getattr(app.state, "mail_watchers", None))
        stop_scheduler(getattr(app.state, "scheduler", None))
        release_process_lock(getattr(app.state, "background_lock", None))
        _log_startup_stage("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(ApiError)
async def _handle_api_error(_request: Request, exc: ApiError):
    return _structured_error_response(exc)


@app.exception_handler(HTTPException)
async def _handle_http_exception(request: Request, exc: HTTPException):
    api_exc = infer_api_error_from_http_exception(exc)
    if api_exc.error_code == "not_found" and request.url.path.startswith("/api"):
        api_exc.error_code = "diagnostics_unavailable" if "diagnostic" in request.url.path else api_exc.error_code
    return _structured_error_response(api_exc)


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(_request: Request, exc: RequestValidationError):
    return _structured_error_response(
        api_error(
            "validation_error",
            "Request validation failed",
            status_code=422,
            details={"errors": exc.errors()},
        )
    )


@app.exception_handler(Exception)
async def _handle_unexpected_error(request: Request, exc: Exception):
    logger.exception("Unexpected backend error path=%s", request.url.path)
    return _structured_error_response(
        api_error(
            "diagnostics_unavailable",
            "An unexpected server error occurred",
            status_code=500,
            details={"path": request.url.path},
        )
    )


@app.middleware("http")
async def mailbox_context_middleware(request: Request, call_next):
    request.state.request_mailbox_id = _extract_request_mailbox_id(request)
    token = set_current_mailbox_id(resolve_mailbox_id_from_request(request))
    try:
        response = await call_next(request)
        return response
    finally:
        reset_current_mailbox_id(token)


@app.middleware("http")
async def setup_required_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api") and path not in PUBLIC_PATHS and not any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES):
        db = open_global_session()
        try:
            if not is_setup_completed(db):
                return _structured_error_response(
                    api_error(
                        "setup_required",
                        "Setup is required before this request can be processed",
                        status_code=503,
                    )
                )
        finally:
            db.close()
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(setup_router)
app.include_router(auth_router)
app.include_router(emails_router)
app.include_router(contacts_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(actions_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(users_router)


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend_root():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend_app(full_path: str):
        if full_path.startswith("api") or full_path in {"health", "docs", "redoc", "openapi.json"}:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        target = FRONTEND_DIST_DIR / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
