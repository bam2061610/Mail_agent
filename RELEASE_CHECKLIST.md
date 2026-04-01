# Orhun Mail Agent v1.0 Release Checklist

## Scope freeze

- [x] Feature scope frozen (bugfix/polish only)
- [x] No new product modules introduced
- [x] Runtime path remains canonical (`app.main` + `api/routes` + `app/config.py`)

## Validation

- [x] `python -m compileall backend/app`
- [x] `pytest backend/tests -q`
- [x] Critical smoke flow covered by `backend/tests/smoke/test_core_flow.py`
- [ ] Manual UI sanity pass in browser on target environment

## Critical flows to verify manually

- [ ] Login/logout
- [ ] Dashboard/focus load
- [ ] Email list + detail
- [ ] Reply send
- [ ] Waiting start/close + follow-up draft
- [ ] Spam restore/confirm
- [ ] Multilingual draft generate/rewrite
- [ ] Mailbox filter + attachment download
- [ ] Reports load/export/email (role-aware)
- [ ] Admin diagnostics + backup/restore guard

## Deployment/readiness

- [x] README startup/test commands match current repo
- [x] CI merge gate exists (`.github/workflows/tests.yml`)
- [x] DEPLOY docs include operational admin endpoints
- [x] CHANGELOG prepared for v1.0
- [x] VERSION file present

## Tag decision

- If all manual checks pass: tag `v1.0.0`
- If any environment-specific blocker appears: cut `v1.0.0-rc1` and patch
