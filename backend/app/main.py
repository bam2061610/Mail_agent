from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
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
PUBLIC_PATHS = {"/health", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to reset in-memory rate limiter state on startup", exc_info=True)
    create_tables()
    ensure_default_admin()
    runtime_settings = get_effective_settings()
    db = open_global_session()
    try:
        setup_completed = is_setup_completed(db)
    finally:
        db.close()
    needs_lock = setup_completed and (
        runtime_settings.run_background_jobs or runtime_settings.run_mail_watchers
    )
    background_lock = (
        acquire_process_lock(DATA_DIR / "background-services.lock")
        if needs_lock
        else ProcessLock(path=DATA_DIR / "background-services.lock", acquired=False)
    )
    app.state.background_lock = background_lock

    scheduler = None
    mail_watchers = None
    if not setup_completed:
        logger.info("Setup is not complete; skipping background scheduler and mail watcher startup")
    elif background_lock.acquired:
        if runtime_settings.run_background_jobs:
            scheduler = start_scheduler(app)
        if runtime_settings.run_mail_watchers:
            mail_watchers = start_mail_watchers()
    else:
        logger.info("Background services already owned by another process; skipping local scheduler/watchers start")

    app.state.mail_watchers = mail_watchers
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        stop_mail_watchers(getattr(app.state, "mail_watchers", None))
        stop_scheduler(getattr(app.state, "scheduler", None))
        release_process_lock(getattr(app.state, "background_lock", None))


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def mailbox_context_middleware(request: Request, call_next):
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
                return JSONResponse(status_code=503, content={"error": "setup_required"})
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
