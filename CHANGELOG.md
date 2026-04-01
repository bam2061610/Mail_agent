# Changelog

## [1.0.0] - 2026-04-02

### Added

- v1.0 release checklist (`RELEASE_CHECKLIST.md`)
- release version marker (`VERSION`)
- CI merge gate workflow (`.github/workflows/tests.yml`) with compile and test checks

### Changed

- Stabilization cleanup documented canonical runtime paths in docs
- Final freeze pass: role-aware UI safeguards for actions that are server-restricted:
- Viewer cannot trigger manual scan from UI
- Sent-review batch run button gated to manager/admin
- Report email action gated for non-viewer roles with clearer inline messaging

### Fixed

- Integration fixes from prior pass retained:
- startup default-admin bootstrap now honors active session factory
- catch-up digest includes overdue follow-ups even when older than `since`
- contact counters in reply flow safely handle nullable values

### Validation

- `python -m compileall backend/app` passed
- `pytest backend/tests -q` passed

### Known limitations (post-1.0 backlog)

- No live websocket sync yet (manual refresh/poll flows only)
- No SSO/OAuth identity integration (token/session auth only)
- Report export endpoints currently cover activity/followups directly (others via JSON)
- Local file-based stores are used for several operational datasets (rules/templates/mailboxes/preferences)
