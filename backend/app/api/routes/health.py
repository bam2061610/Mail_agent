from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import open_global_session
from app.schemas.system import HealthResponse
from app.services.settings_service import is_setup_completed

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    db_state = "error"
    setup_completed = False
    db = open_global_session()
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
        setup_completed = is_setup_completed(db)
    except Exception:
        db_state = "error"
    finally:
        db.close()

    scheduler_state = "ok"
    background_lock = getattr(request.app.state, "background_lock", None)
    scheduler = getattr(request.app.state, "scheduler", None)
    if background_lock is not None and getattr(background_lock, "acquired", False):
        if scheduler is None:
            scheduler_state = "degraded"
        elif not getattr(scheduler, "running", False):
            scheduler_state = "degraded"

    return HealthResponse(
        status="ok" if db_state == "ok" else "degraded",
        setup_completed=setup_completed,
        db=db_state,
        scheduler=scheduler_state,
    )
