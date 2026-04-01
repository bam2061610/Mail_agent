# ============================================================
# Orhun Mail Agent — Repository Structure Init (PowerShell)
# Based on: Единое ТЗ финал, раздел 8
# Usage: cd Mail_agent && .\init_repo.ps1
# ============================================================

Write-Host "🚀 Creating Orhun Mail Agent repository structure..." -ForegroundColor Cyan

# ── Directories ──────────────────────────────────────────────
$dirs = @(
    "backend/app/api/routers",
    "backend/app/core",
    "backend/app/db/models",
    "backend/app/repositories",
    "backend/app/services/mail",
    "backend/app/services/ai",
    "backend/app/services/followup",
    "backend/app/services/rules",
    "backend/app/workers",
    "backend/app/schemas",
    "backend/tests",
    "backend/alembic/versions",
    "frontend/src/app/pages",
    "frontend/src/features/inbox",
    "frontend/src/features/thread",
    "frontend/src/features/dashboard",
    "frontend/src/features/spam-log",
    "frontend/src/features/contacts",
    "frontend/src/features/settings",
    "frontend/src/shared/api",
    "frontend/src/shared/ui",
    "frontend/src/shared/utils",
    "infra/nginx",
    "infra/backup",
    "docs"
)

foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# ── __init__.py files ────────────────────────────────────────
$initDirs = @(
    "backend/app",
    "backend/app/api",
    "backend/app/api/routers",
    "backend/app/core",
    "backend/app/db",
    "backend/app/db/models",
    "backend/app/repositories",
    "backend/app/services",
    "backend/app/services/mail",
    "backend/app/services/ai",
    "backend/app/services/followup",
    "backend/app/services/rules",
    "backend/app/workers",
    "backend/app/schemas",
    "backend/tests"
)

foreach ($d in $initDirs) {
    New-Item -ItemType File -Path "$d/__init__.py" -Force | Out-Null
}

# ── backend/app/main.py ─────────────────────────────────────
@'
"""Orhun Mail Agent — FastAPI entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
'@ | Set-Content -Path "backend/app/main.py" -Encoding utf8

# ── backend/app/core/config.py ──────────────────────────────
@'
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Orhun Mail Agent"
    environment: str = "dev"

    database_url: str = "postgresql+asyncpg://oma:oma@localhost:5432/oma"
    redis_url: str | None = None

    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
'@ | Set-Content -Path "backend/app/core/config.py" -Encoding utf8

# ── backend/app/core/security.py ────────────────────────────
'"""Authentication & session helpers."""' | Set-Content -Path "backend/app/core/security.py" -Encoding utf8

# ── backend/app/core/logging.py ─────────────────────────────
@'
"""Structured logging configuration."""
import logging
import sys


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
'@ | Set-Content -Path "backend/app/core/logging.py" -Encoding utf8

# ── backend/app/db/base.py ──────────────────────────────────
@'
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
'@ | Set-Content -Path "backend/app/db/base.py" -Encoding utf8

# ── backend/app/db/session.py ───────────────────────────────
@'
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
'@ | Set-Content -Path "backend/app/db/session.py" -Encoding utf8

# ── db/models stubs ─────────────────────────────────────────
$models = @("account","folder","thread","message","attachment","analysis","task","contact","preference","audit")
foreach ($m in $models) {
    """""$m model."""""
from app.db.base import Base
" | Set-Content -Path "backend/app/db/models/$m.py" -Encoding utf8
}

# ── api/routers stubs ───────────────────────────────────────
$routers = @("auth","accounts","threads","drafts","contacts","rules","stats","settings")
foreach ($r in $routers) {
    @"
"""$r router."""
from fastapi import APIRouter

router = APIRouter()
"@ | Set-Content -Path "backend/app/api/routers/$r.py" -Encoding utf8
}

# ── services stubs ──────────────────────────────────────────
$mailSvc = @("imap_sync","smtp_send","mime_parser","thread_builder")
foreach ($s in $mailSvc) { "" | Set-Content -Path "backend/app/services/mail/$s.py" -Encoding utf8 }

$aiSvc = @("llm_client","prompts","classifiers","drafting","spam","summarizer")
foreach ($s in $aiSvc) { "" | Set-Content -Path "backend/app/services/ai/$s.py" -Encoding utf8 }

$fuSvc = @("tracker","digest")
foreach ($s in $fuSvc) { "" | Set-Content -Path "backend/app/services/followup/$s.py" -Encoding utf8 }

"" | Set-Content -Path "backend/app/services/rules/engine.py" -Encoding utf8

# ── workers stubs ───────────────────────────────────────────
"" | Set-Content -Path "backend/app/workers/jobs.py" -Encoding utf8
"" | Set-Content -Path "backend/app/workers/scheduler.py" -Encoding utf8

# ── backend/requirements.txt ────────────────────────────────
@'
fastapi>=0.115
uvicorn[standard]>=0.30
sqlalchemy>=2.0
alembic>=1.14
pydantic>=2.0
pydantic-settings>=2.0
asyncpg
httpx
apscheduler>=3.10
redis>=5.0
rq
beautifulsoup4
lxml
orjson
python-multipart
pytest
pytest-asyncio
'@ | Set-Content -Path "backend/requirements.txt" -Encoding utf8

# ── backend/Dockerfile ──────────────────────────────────────
@'
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'@ | Set-Content -Path "backend/Dockerfile" -Encoding utf8

# ── frontend files ──────────────────────────────────────────
@'
import React from "react";
import ReactDOM from "react-dom/client";

function App() {
  return <div>Orhun Mail Agent</div>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
'@ | Set-Content -Path "frontend/src/main.tsx" -Encoding utf8

@'
{
  "name": "orhun-mail-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3"
  },
  "devDependencies": {
    "@types/react": "^18.3",
    "@types/react-dom": "^18.3",
    "@vitejs/plugin-react": "^4.3",
    "typescript": "^5.5",
    "vite": "^5.4"
  }
}
'@ | Set-Content -Path "frontend/package.json" -Encoding utf8

@'
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
'@ | Set-Content -Path "frontend/vite.config.ts" -Encoding utf8

@'
FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
'@ | Set-Content -Path "frontend/Dockerfile" -Encoding utf8

# ── infra ───────────────────────────────────────────────────
@'
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: oma
      POSTGRES_PASSWORD: oma
      POSTGRES_DB: oma
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build: ../backend
    env_file: ../.env
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis

  frontend:
    build: ../frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  pgdata:
'@ | Set-Content -Path "infra/docker-compose.yml" -Encoding utf8

@'
server {
    listen 80;
    location / {
        proxy_pass http://frontend:80;
    }
    location /api/ {
        proxy_pass http://backend:8000;
    }
}
'@ | Set-Content -Path "infra/nginx/default.conf" -Encoding utf8

# ── Root files ──────────────────────────────────────────────
@'
# === Database ===
DATABASE_URL=postgresql+asyncpg://oma:oma@localhost:5432/oma
REDIS_URL=redis://localhost:6379/0

# === IMAP ===
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=user@example.com
IMAP_PASSWORD=

# === SMTP ===
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASSWORD=

# === AI ===
LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com

# === App ===
ENVIRONMENT=dev
'@ | Set-Content -Path ".env.example" -Encoding utf8

@'
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
node_modules/
frontend/dist/
.env
.env.local
.env.*.local
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db
*.sqlite3
*.db
pgdata/
*.log
'@ | Set-Content -Path ".gitignore" -Encoding utf8

@'
# Orhun Mail Agent

AI-powered email management system for Orhun Medical.

> Intelligent layer on top of existing email — not a new mail server.

## Architecture

- **Backend**: FastAPI + SQLAlchemy 2.x + PostgreSQL + Redis
- **AI**: DeepSeek API (pluggable LLM adapter)
- **Frontend**: React + Vite + TypeScript
- **Deploy**: Docker Compose

## Quick Start

```bash
cp .env.example .env
# edit .env with your credentials

cd infra && docker compose up -d db redis
cd ../backend && pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Project Structure

```
backend/          — FastAPI application
  app/
    api/routers/  — HTTP endpoints
    core/         — config, security, logging
    db/models/    — SQLAlchemy models
    services/     — mail, ai, followup, rules
    workers/      — background jobs & scheduler
    schemas/      — Pydantic schemas
frontend/         — React + Vite application
infra/            — Docker Compose, nginx, backups
docs/             — specs, API doc, deploy guide, roadmap
```

## License

Proprietary — Orhun Medical LLP
'@ | Set-Content -Path "README.md" -Encoding utf8

# ── Docs stubs ──────────────────────────────────────────────
"# API Reference`n`nSee section 14 of the unified spec." | Set-Content -Path "docs/API.md" -Encoding utf8
"# Deployment Guide`n`nTODO" | Set-Content -Path "docs/DEPLOY.md" -Encoding utf8
"# Roadmap`n`nSee section 15 of the unified spec." | Set-Content -Path "docs/ROADMAP.md" -Encoding utf8

Write-Host ""
Write-Host "✅ Structure created! 68 files ready." -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  git add -A"
Write-Host '  git commit -m "feat: initialize project structure per unified spec"'
Write-Host "  git push -u origin main"
