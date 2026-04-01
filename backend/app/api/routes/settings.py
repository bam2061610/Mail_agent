from fastapi import APIRouter

from app.config import get_safe_settings_view, save_runtime_settings
from app.schemas.system import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return SettingsResponse(**get_safe_settings_view())


@router.post("", response_model=SettingsResponse)
def update_settings(request: SettingsUpdateRequest) -> SettingsResponse:
    save_runtime_settings(request.model_dump(exclude_none=True))
    return SettingsResponse(**get_safe_settings_view())
