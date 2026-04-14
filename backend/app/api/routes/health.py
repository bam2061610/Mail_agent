import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import open_global_session
from app.schemas.system import HealthResponse, SystemStatusResponse
from app.services.diagnostics_service import collect_system_status
from app.services.settings_service import is_setup_completed

router = APIRouter(tags=["system"])


def _read_build_info() -> dict[str, str]:
    info: dict[str, str] = {}
    env_commit = os.environ.get("GIT_COMMIT") or os.environ.get("BUILD_COMMIT")
    if env_commit:
        info["commit"] = env_commit.strip()
    build_time = os.environ.get("BUILD_TIME")
    if build_time:
        info["build_time"] = build_time.strip()
    build_file = Path("/app/BUILD_INFO")
    if build_file.exists():
        try:
            for line in build_file.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    info.setdefault(key.strip().lower(), value.strip())
        except OSError:
            pass
    if "commit" not in info:
        try:
            commit = subprocess.check_output(
                ["git", "-C", "/app", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).decode("ascii").strip()
            if commit:
                info["commit"] = commit
        except Exception:  # noqa: BLE001
            pass
    return info


@router.get("/api/version", include_in_schema=False)
def get_version() -> JSONResponse:
    payload = {"app": "mail_agent", **_read_build_info()}
    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


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


@router.get("/api/system/status", response_model=SystemStatusResponse)
def get_system_status(request: Request) -> SystemStatusResponse:
    startup_state = getattr(request.app.state, "startup_state", {}) or {}
    return SystemStatusResponse(
        **collect_system_status(
            setup_completed=bool(startup_state.get("setup_completed", False)),
            startup_completed=bool(startup_state.get("startup_completed", False)),
            scheduler_running=bool(getattr(request.app.state, "scheduler", None) and getattr(request.app.state.scheduler, "running", False)),
            watchers_running=bool(getattr(request.app.state, "mail_watchers", None)),
        )
    )
