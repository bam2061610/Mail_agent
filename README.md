# Orhun Mail Agent

Minimal backend skeleton for the Orhun Mail Agent project. This step focuses on a clean FastAPI foundation with configuration, database models, and basic API routes.

## Backend Setup

### Linux/macOS

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload
```

### Windows

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload
```

## What You Get

- `GET /health` returns service status, app name, environment, and server time.
- `GET /api/emails` returns the current email list from SQLite.
- `GET /api/emails/{id}` returns one email or `404`.
- Database tables are created automatically on startup.

## Manual IMAP Scan

After filling in IMAP settings in `backend/.env`, you can run a one-off inbox import:

```bash
cd backend
python -c "from app.config import settings; from app.db import SessionLocal; from app.services.imap_scanner import scan_inbox; db = SessionLocal(); print(scan_inbox(db, settings)); db.close()"
```

The scanner reads `INBOX` via IMAP SSL, fetches only messages not already stored by `message_id`, and saves parsed emails into the existing `emails` table without marking them as read.

## Manual AI Analysis

After setting `OPENAI_API_KEY` in `backend/.env`, you can analyze pending imported emails through DeepSeek:

```bash
cd backend
python -c "from app.config import settings; from app.db import SessionLocal; from app.services.ai_analyzer import analyze_pending; db = SessionLocal(); print(analyze_pending(db, settings, limit=10)); db.close()"
```

The analyzer sends the current email plus a compact recent thread history to DeepSeek at `https://api.deepseek.com`, expects JSON-only output, validates the result, and stores the analysis back into the `emails` table.

## API Endpoints

- `GET /api/emails` with filters: `status`, `priority`, `category`, `search`, `limit`, `offset`
- `GET /api/emails/{id}`
- `GET /api/emails/{id}/thread`
- `POST /api/emails/{id}/status`
- `POST /api/emails/{id}/reply`
- `POST /api/emails/{id}/waiting/start`
- `POST /api/emails/{id}/waiting/close`
- `POST /api/emails/{id}/followup-draft`
- `GET /api/contacts`
- `GET /api/stats`
- `GET /api/digest`
- `GET /api/settings`
- `POST /api/settings`
- `POST /api/scan`
- `GET /api/followups`

## Web UI

The first working dashboard lives in `frontend/` as a React + Vite app. It is desktop-first and organized around:

- Focus dashboard
- Active queue
- Thread detail + draft workflow
- Spam review log
- Settings panel

### Run frontend locally

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the backend on `http://localhost:8000`.

### Main UI flows

- Open the focus dashboard to review counters and daily summary
- Move into Active Queue to inspect reply-needed items
- Open Waiting Queue to track conversations waiting on the other side
- Open a thread, review AI summary, edit the draft, and send via the existing reply endpoint
- Mark a thread as waiting for reply, close waiting manually, or generate a suggested follow-up draft
- Archive or mark spam from the detail actions
- Use "Scan now" to manually trigger inbox import + analysis
- Open Settings to update safe runtime configuration

## Follow-up Tracking

Outgoing conversations can now be tracked in a waiting state:

- Sending a reply through the app automatically starts waiting-for-reply tracking for that thread
- You can also start or close waiting manually from the API or dashboard
- Waiting threads automatically move to overdue when they exceed `FOLLOWUP_OVERDUE_DAYS`
- If an inbound reply arrives in a tracked thread, waiting is closed automatically during inbox import
- Overdue threads can generate a suggested follow-up draft through the existing AI integration

## Feedback / Learning Loop

The app now learns from operator behavior without model fine-tuning:

- AI summary, priority, spam, and draft feedback can be submitted through the API and UI
- When a draft is sent unchanged, that is logged as a positive signal
- When a draft is edited before sending, the original and final versions are both preserved in `action_log`
- Lightweight heuristics infer tags such as `shorter`, `more_formal`, `translated_russian`, `deadline_emphasis`, and `clarified_request`
- Aggregated preferences are rebuilt into a compact profile and injected into future AI prompts

Feedback-related endpoints:

- `POST /api/emails/{id}/feedback`
- `POST /api/emails/{id}/draft-feedback`
- `GET /api/preferences`
- `POST /api/preferences/rebuild`
- `GET /api/rules`
- `POST /api/rules`
- `PUT /api/rules/{id}`
- `DELETE /api/rules/{id}`
- `GET /api/spam`
- `POST /api/emails/{id}/restore`
- `POST /api/emails/{id}/confirm-spam`

## Manual Reply Test

After setting SMTP values in `backend/.env` or through `POST /api/settings`, you can send a reply through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/emails/1/reply ^
  -H "Content-Type: application/json" ^
  -d "{\"body\":\"Thank you, we will review and reply shortly.\",\"save_as_sent_record\":true}"
```

## Manual Scan + Analyze

Trigger IMAP import followed by AI analysis:

```bash
curl -X POST http://127.0.0.1:8000/api/scan
```

## Automatic Scheduler

On FastAPI startup, APScheduler now starts a background job that runs inbox scan plus pending AI analysis every `SCAN_INTERVAL_MINUTES`.

- The scheduler reuses the existing scan/analyze services.
- Overlapping runs are prevented with `max_instances=1`.
- Missed ticks are coalesced so reloads or temporary pauses do not queue many duplicate runs.
- The manual `POST /api/scan` endpoint still works independently.

## Automation Rules + Spam Review

The product now supports lightweight explicit rules on top of AI analysis:

- Rules are stored in `backend/data/rules.json`
- Matching is deterministic and ordered by `order`
- Supported match fields include `sender_email`, `sender_domain`, `subject_contains`, `has_auto_reply_headers`, `category`, `priority`, and `direction`
- Supported actions include `set_priority`, `set_category`, `mark_spam`, `archive`, `trust_sender`, `never_spam`, and `move_to_focus`
- Rules are applied once on import and again after AI analysis so sender/domain rules can work immediately while category/priority rules can refine AI output

Spam review is now a first-class workflow:

- `GET /api/spam` returns the spam log with source and reason when available
- `POST /api/emails/{id}/restore` restores a message back to active workflow and records the restore in `action_log`
- `POST /api/emails/{id}/confirm-spam` confirms the spam decision and feeds that signal back into the learning loop
- The dashboard Spam view shows source, timing, and review actions

### Rule examples

```bash
curl -X POST http://127.0.0.1:8000/api/rules \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Medcon always high\",\"conditions\":{\"sender_domain\":\"medcon.com.tr\"},\"actions\":{\"set_priority\":\"high\",\"move_to_focus\":true}}"
```

```bash
curl -X POST http://127.0.0.1:8000/api/rules \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Newsletter archive\",\"conditions\":{\"sender_email\":\"newsletter@example.com\"},\"actions\":{\"archive\":true,\"set_priority\":\"low\"}}"
```

## Health Check

Default local URL: `http://127.0.0.1:8000/health`
