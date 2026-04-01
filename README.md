# Orhun Mail Agent

AI-powered email management system for Orhun Medical.
Intelligent layer on top of existing email — not a new mail server.

## Stack
- Backend: FastAPI + SQLAlchemy 2.x + PostgreSQL + Redis
- AI: DeepSeek API (pluggable LLM adapter)
- Frontend: React + Vite + TypeScript
- Deploy: Docker Compose

## Quick Start
cp .env.example .env
cd infra && docker compose up -d db redis
cd ../backend && pip install -r requirements.txt
uvicorn app.main:app --reload

## License
Proprietary — Orhun Medical LLP
