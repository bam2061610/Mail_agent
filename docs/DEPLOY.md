# Deployment Guide

## Admin Operations: Backup and Recovery

The deployment includes built-in admin backup/restore endpoints.

- Backups are stored at `backend/data/backups/`.
- Each backup is a timestamped folder with:
- SQLite DB snapshot.
- Operational JSON stores (`settings.local.json`, `rules.json`, `templates.json`, `mailboxes.json`, etc.).
- Optional attachments copy (`include_attachments=true`).

### Recommended baseline

1. Keep at least `keep_last=10` backups.
2. Run a backup before risky config/schema/manual maintenance changes.
3. For restore, verify confirmation string and backup name carefully.

### Restore safety

- Restore endpoint requires explicit confirmation format:
- `RESTORE <backup_name>`.
- System creates a safety backup before applying restore.
- Restore actions are audited (`restore_started`, `restore_completed`, `restore_failed`).

## Admin Diagnostics

Use admin diagnostics endpoints for production checks:

- `GET /api/admin/health`
- `GET /api/admin/diagnostics`
- `GET /api/admin/jobs`
- `GET /api/admin/mailboxes/status`
- `GET /api/admin/backups/status`

These endpoints expose:

- Scheduler running state and last job result.
- Last scan/analyze success/failure timestamps.
- Mailbox-level failure visibility.
- Backup/restore last-run status.
- Attachment/backups storage usage.

## Operational Tip

In small-team deployments, keep one admin account dedicated to weekly backup verification and periodic restore dry-runs on staging data.

## v1.0 Release Gate

Before tagging `v1.0.0`, run from repository root:

```bash
python -m compileall backend/app
pytest backend/tests -q
```

CI gate (`.github/workflows/tests.yml`) mirrors these checks on push/PR.

For final sign-off, complete `RELEASE_CHECKLIST.md` including manual UI smoke on target deployment environment.
