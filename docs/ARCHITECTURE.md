# Runtime Architecture (Canonical Paths)

This document defines the active runtime path to avoid ambiguity.

## Canonical entrypoint

- FastAPI app entrypoint: `backend/app/main.py`
- Startup/lifespan wiring: `backend/app/main.py` (includes table bootstrap, default admin bootstrap, scheduler start/stop)

## Canonical routing package

- Active routes live in: `backend/app/api/routes/*`
- `main.py` includes routers directly from `app.api.routes.*`
- Legacy `backend/app/api/routers/*` stubs were removed during stabilization cleanup.

## Canonical config source

- Active settings module: `backend/app/config.py`
- Runtime settings helpers:
  - `get_effective_settings()`
  - `get_safe_settings_view()`
  - `save_runtime_settings(...)`
- Legacy duplicate config module `backend/app/core/config.py` was removed.

## Canonical test gate

- Main validation command: `pytest backend/tests -q`
- Optional compile sanity check: `python -m compileall backend/app`

## Notes on scope

This cleanup pass intentionally did not refactor product behavior or service logic. It only removed dead paths and clarified runtime source-of-truth.
