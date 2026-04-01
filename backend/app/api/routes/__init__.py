from app.api.routes.actions import router as actions_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.emails import router as emails_router
from app.api.routes.health import router as health_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stats import router as stats_router

__all__ = [
    "actions_router",
    "contacts_router",
    "emails_router",
    "health_router",
    "settings_router",
    "stats_router",
]
