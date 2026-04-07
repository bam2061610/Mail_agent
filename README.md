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

For a dedicated background worker in a second terminal:

```bash
cd backend
python -m app.worker
```

The API and worker share a process lock, so only one process owns scheduler/watchers at a time. In Docker Compose the API has background jobs disabled and the dedicated `worker` service owns them.

## What You Get

- `GET /health` returns service status, app name, environment, and server time.
- `GET /api/emails` returns the current email list from SQLite.
- `GET /api/emails/{id}` returns one email or `404`.
- Schema migrations are applied automatically on startup for the global DB and mailbox account DBs.

Manual schema upgrade:

```bash
cd backend
alembic upgrade head
```

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
- `GET /api/emails/{id}/attachments`
- `GET /api/emails/attachments/{id}/download`
- `GET /api/attachments/{id}/download`
- `POST /api/emails/{id}/status`
- `POST /api/emails/{id}/reply`
- `POST /api/emails/{id}/waiting/start`
- `POST /api/emails/{id}/waiting/close`
- `POST /api/emails/{id}/followup-draft`
- `GET /api/contacts`
- `GET /api/stats`
- `GET /api/digest`
- `GET /api/digest/catchup`
- `POST /api/digest/mark-seen`
- `POST /api/digest/rebuild`
- `GET /api/settings`
- `POST /api/settings`
- `GET /api/mailboxes`
- `POST /api/mailboxes`
- `PUT /api/mailboxes/{id}`
- `DELETE /api/mailboxes/{id}`
- `POST /api/mailboxes/{id}/test-connection`
- `POST /api/mailboxes/{id}/scan`
- `POST /api/scan`
- `GET /api/followups`
- `GET /api/sent/reviews`
- `POST /api/sent/review/run`
- `POST /api/emails/{id}/sent-review/review`
- `POST /api/emails/{id}/sent-review/dismiss`
- `POST /api/emails/{id}/sent-review/helpful`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/users`
- `POST /api/users`
- `PUT /api/users/{id}`
- `POST /api/users/{id}/disable`
- `POST /api/users/{id}/reset-password`
- `POST /api/emails/{id}/assign`
- `POST /api/emails/{id}/unassign`
- `GET /api/admin/health`
- `GET /api/admin/diagnostics`
- `GET /api/admin/jobs`
- `GET /api/admin/mailboxes/status`
- `GET /api/admin/backups`
- `GET /api/admin/backups/status`
- `POST /api/admin/backups/create`
- `POST /api/admin/backups/restore`

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

### Frontend API base URL in built deployments

- The production frontend keeps `/api/*` as the default path (same-origin).
- The frontend container image now includes nginx proxying from `/api/*` to `backend:8000`, so login and API calls work in Docker Compose without cross-origin setup.
- If you deploy built static assets behind a different topology, set `VITE_API_BASE_URL` (see `frontend/.env.example`) to the backend origin at build time.

## Authentication, Roles, and Team Mode

The app now supports practical multi-user team access with role checks enforced on the backend.

- Passwords are hashed with PBKDF2 (`sha256`) and never stored in plain text.
- Login is token-based (`Authorization: Bearer <token>`).
- Audit actions now include acting `user_id` in `action_log` for key operations.
- Assignment is available for thread/email ownership (`assigned_to_user_id`, `assigned_by_user_id`, `assigned_at`).

First admin bootstrap is now explicit instead of automatic by default.

- Set `BOOTSTRAP_DEFAULT_ADMIN=true` in `backend/.env` for the first run only.
- Set `BOOTSTRAP_ADMIN_PASSWORD=<your-password>` to choose the initial admin password.
- If `BOOTSTRAP_ADMIN_PASSWORD` is left blank, the backend generates a random password and prints it once in the startup logs.
- After the first admin is created, set `BOOTSTRAP_DEFAULT_ADMIN=false` again.

Roles:

- `admin`: full access (users, settings, mailboxes, assignment, send/workflow actions)
- `manager`: operational control (assignment, rules, review, send/workflow actions)
- `operator`: daily operations (send/status/spam/scan/read)
- `viewer`: read-only dashboards and queue visibility

The frontend includes:

- login screen
- current-user role indicator
- logout action
- role-aware control disabling/hiding
- assignment controls in thread detail
- admin-only user management section in Settings

## Backup, Restore, and Admin Diagnostics

Admin-only operations are available through `/api/admin/*` and surfaced in the Settings diagnostics panel.

Backup behavior:

- Creates timestamped backup folders under `backend/data/backups/backup_YYYYMMDD_HHMMSS`
- Backs up the global SQLite DB, mailbox-scoped account DBs under `backend/data/account_dbs/`, and operational JSON config stores
- Optional attachment-folder backup via `include_attachments=true`
- Applies simple retention (`keep_last`, default 10)

Restore behavior:

- Requires explicit confirmation text: `RESTORE <backup_name>`
- Creates an automatic safety backup before restore
- Restores global DB + mailbox account DBs + config files; attachments restore is optional
- All backup/restore actions are audited in `action_log`

Diagnostics behavior:

- `GET /api/admin/health` and `GET /api/admin/diagnostics` report:
  - API/DB status
  - scheduler status and last job outcome
  - scan/analyze last success/failure
  - SMTP and AI config readiness
  - mailbox-by-mailbox last success/failure
  - storage usage for attachments/backups and disk space
- `GET /api/admin/jobs` returns persisted last-run operational state
- `GET /api/admin/mailboxes/status` shows mailbox status summary (optional live IMAP check)

Example backup create:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/backups/create \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"include_attachments\":false,\"keep_last\":10}"
```

Example restore:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/backups/restore \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"backup_name\":\"backup_20260401_180000\",\"confirmation\":\"RESTORE backup_20260401_180000\",\"restore_attachments\":false}"
```

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
- `GET /api/templates`
- `POST /api/templates`
- `PUT /api/templates/{id}`
- `DELETE /api/templates/{id}`
- `POST /api/emails/{id}/generate-draft`
- `POST /api/emails/{id}/rewrite-draft`
- `POST /api/emails/{id}/set-reply-language`

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

## Multilingual Drafts + Templates

The product now supports practical multilingual drafting for daily business communication:

- incoming email language is detected heuristically and stored on the email record
- supported languages are `ru`, `en`, and `tr`
- reply generation defaults to the detected source language unless the user overrides it
- reusable templates are stored in `backend/data/templates.json`
- AI can personalize a selected template to the current thread while preserving the chosen language

Quick rewrite actions are also supported:

- `shorter`
- `more formal`
- `softer`
- `stronger deadline emphasis`
- `translate to Russian`
- `translate to English`
- `translate to Turkish`

### Draft generation example

```bash
curl -X POST http://127.0.0.1:8000/api/emails/1/generate-draft \
  -H "Content-Type: application/json" \
  -d "{\"target_language\":\"ru\",\"template_id\":\"followup-ru\"}"
```

### Draft rewrite example

```bash
curl -X POST http://127.0.0.1:8000/api/emails/1/rewrite-draft \
  -H "Content-Type: application/json" \
  -d "{\"current_draft\":\"Hello, thank you for your email.\",\"instruction\":\"translate to Turkish\",\"target_language\":\"tr\"}"
```

## Offline Catch-Up + Sent Review

This step adds a practical situational-awareness layer:

- Catch-up digest detects return-after-absence and summarizes what changed while you were away
- Sent review analyzes recently sent replies for tone, completeness, action clarity, and unanswered questions

Catch-up behavior:

- User activity state is stored in `backend/data/digest_state.json`
- `CATCHUP_ABSENCE_HOURS` (default `8`) defines when catch-up mode is shown
- Digest includes:
  - important new inbound threads
  - waiting/overdue follow-ups
  - new spam worth review
  - recent sent replies
  - follow-ups due now
  - top action list

Sent review behavior:

- Sent emails are marked with `sent_review_status="pending"` when saved as sent records
- Review is non-blocking for send flow (send succeeds even if review is not run yet)
- Run review manually (or from dashboard action) with:

```bash
curl -X POST http://127.0.0.1:8000/api/sent/review/run
```

- Recent reviewed sent mail:

```bash
curl "http://127.0.0.1:8000/api/sent/reviews?limit=20"
```

Digest endpoints:

```bash
curl http://127.0.0.1:8000/api/digest/catchup
curl -X POST http://127.0.0.1:8000/api/digest/mark-seen
```

## Multi-Mailbox + Attachments

The app now supports multiple mailbox accounts and attachment metadata/storage.

- Mailboxes are stored in `backend/data/mailboxes.json`
- Scanner loops through all enabled mailboxes via `scan_all_mailboxes(...)`
- Every imported email is linked to `mailbox_id`, `mailbox_name`, `mailbox_address`
- Replies are sent through the mailbox linked to the email (or the default outgoing mailbox)

Attachment handling:

- Attachment metadata is saved in the `attachments` table
- Files are stored locally under `backend/data/attachments/<mailbox_id>/<email_id>/`
- Duplicate attachment saves for the same email are skipped
- Search now supports attachment name/type through `GET /api/emails?search=...`
- You can filter by mailbox and attachment presence:
  - `GET /api/emails?mailbox_id=<id>&has_attachments=true`

### Manual multi-mailbox scan

```bash
cd backend
python -c "from app.config import settings; from app.db import SessionLocal; from app.services.imap_scanner import scan_all_mailboxes; db = SessionLocal(); print(scan_all_mailboxes(db, settings)); db.close()"
```

### Attachment endpoints

- `GET /api/emails/{id}/attachments`
- `GET /api/emails/attachments/{id}/download`
- `GET /api/attachments/{id}/download`

## Health Check

Default local URL: `http://127.0.0.1:8000/health`

## Automated Tests and QA Harness

The backend now includes a practical `pytest` suite with unit/service/API/smoke coverage and mocked external integrations (IMAP/SMTP/AI/scheduler).

### Test structure

- `backend/tests/` for unit/service/API tests
- `backend/tests/smoke/` for happy-path smoke checks

### Run all tests

```bash
cd backend
pytest -q
```

### Run one test file

```bash
cd backend
pytest -q tests/test_api_emails.py
```

### Run smoke checks

```bash
cd backend
pytest -q tests/smoke/test_core_flow.py
```

### What is mocked

- IMAP transport (`imaplib.IMAP4_SSL`) in scanner tests
- SMTP transport (`smtplib.SMTP`) in sender/reply tests
- AI model calls (DeepSeek/OpenAI client call path)
- scheduler side effects in API tests

No real external mailbox/API is required to execute tests.

## Demo Seed / Reset

For manual QA, seed realistic demo records:

```bash
cd backend
python -m app.services.dev_seed
```

This dev-only seed also creates demo users with fixed local passwords for QA convenience.

Programmatic usage:

```bash
cd backend
python -c "from app.services.dev_seed import seed_demo_data, reset_demo_data; print(reset_demo_data()); print(seed_demo_data())"
```

## Export and Reporting

Reporting endpoints:

- `GET /api/reports/activity`
- `GET /api/reports/followups`
- `GET /api/reports/sent-review`
- `GET /api/reports/team-activity` (manager/admin)
- `GET /api/reports/activity/export?format=csv|pdf`
- `GET /api/reports/followups/export?format=csv|pdf`
- `POST /api/reports/send`

Filters:

- `date_from`, `date_to`
- `mailbox_id`
- `user_id`
- `status`, `priority`, `category`

Export formats:

- JSON via report endpoints
- CSV via export endpoints
- PDF via export endpoints

Reporting audit actions:

- `report_generated`
- `report_exported_csv`
- `report_exported_pdf`
- `report_emailed`

Example:

```bash
curl "http://127.0.0.1:8000/api/reports/activity?date_from=2026-04-01&date_to=2026-04-30" -H "Authorization: Bearer <TOKEN>"
```

## v1.0 Freeze Notes

This repository is in v1.0 freeze mode:

- scope is frozen (bugfix/polish only)
- no new modules or architecture changes are included in freeze patches
- canonical runtime path is documented in `docs/ARCHITECTURE.md`

Release artifacts:

- `VERSION`
- `CHANGELOG.md`
- `RELEASE_CHECKLIST.md`

## Release Validation Commands

From repository root:

```bash
python -m compileall backend/app
pytest backend/tests -q
```

Optional focused smoke:

```bash
pytest backend/tests/smoke/test_core_flow.py -q
```

## Canonical Runtime Paths

To keep runtime behavior unambiguous, this repository now uses one canonical path for each core area:

- App entrypoint: `backend/app/main.py`
- Routing package: `backend/app/api/routes/*`
- Settings/config source: `backend/app/config.py`

Reference note: `docs/ARCHITECTURE.md`

## CI Merge Gate

A minimal GitHub Actions merge gate is included at:

- `.github/workflows/tests.yml`

It runs on push and pull requests and executes:

1. dependency install from `backend/requirements.txt`
2. `python -m compileall backend/app`
3. `pytest backend/tests -q`
