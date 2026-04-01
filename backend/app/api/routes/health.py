from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        server_time=datetime.now(timezone.utc),
    )
