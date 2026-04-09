# Deployment Guide

## Recommended Shape

The simplest production deployment is now a single container that serves:

- the FastAPI API
- the built React frontend
- the background scheduler and mailbox watchers

Runtime configuration is setup-first. After the container starts, open the app in a browser and complete the first-run wizard.

## Required Environment

Keep the runtime `.env` minimal:

```env
SECRET_KEY=<random 32-byte hex string>
DATABASE_URL=sqlite:///./data/mail_agent.db
PORT=8000
```

Mailbox credentials, AI keys, scheduler intervals, and workflow settings are stored in the database after setup completes.

## Docker Compose

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
```

The root `docker-compose.yml`:

- builds the root multi-stage `Dockerfile`
- persists SQLite data under `./data`
- exposes the app on port `8000`
- checks liveness through `GET /health`

## First Boot

1. Open `http://localhost:8000`.
2. Complete the setup wizard.
3. Sign in with the admin account you just created.

Until setup is complete:

- `GET /api/setup/status` stays public
- `POST /api/setup/complete` is allowed once
- other API routes return `503 {"error":"setup_required"}`

## Health Checks

`GET /health` returns:

```json
{
  "status": "ok",
  "setup_completed": true,
  "db": "ok",
  "scheduler": "ok"
}
```

Use this endpoint for Docker health checks, reverse proxies, or load balancers.

## Backups and Recovery

Admin backups include:

- the global SQLite database
- mailbox account databases
- exported config snapshots such as the preference profile and digest state
- optional attachments

Restore still requires the exact confirmation string:

```text
RESTORE <backup_name>
```

## Validation

Before shipping a build, run:

```bash
python -m compileall backend/app
pytest backend/tests -q
```

Frontend build validation is also recommended, but it requires a local Node.js toolchain or Docker build support.
