from contextlib import asynccontextmanager

from fastapi import FastAPI
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
from app.api.routes.users import router as users_router
from app.config import settings
from app.core.logging import configure_logging
from app.db import create_tables
from app.scheduler import start_scheduler, stop_scheduler
from app.services.user_service import ensure_default_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    create_tables()
    ensure_default_admin()
    scheduler = start_scheduler(app)
    try:
        yield
    finally:
        stop_scheduler(scheduler)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(emails_router)
app.include_router(contacts_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(actions_router)
app.include_router(admin_router)
app.include_router(reports_router)
