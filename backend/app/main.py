from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.actions import router as actions_router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.emails import router as emails_router
from app.api.routes.health import router as health_router
from app.api.routes.reports import router as reports_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stats import router as stats_router
from app.config import settings
from app.core.logging import configure_logging
from app.db import create_tables, reset_current_mailbox_id, resolve_mailbox_id_from_request, set_current_mailbox_id
from app.scheduler import start_scheduler, stop_scheduler
from app.services.mail_watcher import start_mail_watchers, stop_mail_watchers
from app.services.user_service import ensure_default_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    create_tables()
    ensure_default_admin()
    scheduler = start_scheduler(app)
    mail_watchers = start_mail_watchers()
    app.state.mail_watchers = mail_watchers
    try:
        yield
    finally:
        stop_mail_watchers(getattr(app.state, "mail_watchers", None))
        stop_scheduler(scheduler)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)


@app.middleware("http")
async def mailbox_context_middleware(request: Request, call_next):
    token = set_current_mailbox_id(resolve_mailbox_id_from_request(request))
    try:
        response = await call_next(request)
        return response
    finally:
        reset_current_mailbox_id(token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(emails_router)
app.include_router(contacts_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(actions_router)
app.include_router(admin_router)
app.include_router(reports_router)
