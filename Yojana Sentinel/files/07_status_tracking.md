# Phase 6 — Post-Submission Status Tracking

**Load `00_master_context.md` and the outputs of Phases 0-5 first. Keep this phase deliberately shallow — a believable, honestly-scoped state machine beats a fragile fake integration with a real government status-tracking system.**

## Goal
Model what happens to an `ApplicationDraft` after a human approves it and (manually, outside the app) submits it — tracking status and nudging on staleness, without pretending to have a real-time feed from any government system.

## Build the following

### 1. `tracking/status_store.py`
- Implements the full `ApplicationDraft.status` state machine:
  `drafted → approved → submitted → pending → resolved` (with `rejected` as a terminal branch reachable from `drafted` or `approved`, per Phase 5).
- `mark_submitted(draft_id, submitted_at)` — the human confirms, inside the app, that they actually submitted the approved draft manually. This is a manual confirmation step, not an automatic transition — the app has no way to know submission happened unless told.
- `update_status(draft_id, new_status, note)` — for the MVP, this is a manual/mock update (the person operating the app, or a demo script, sets status changes by hand) since there is no real portal integration. Document this limitation explicitly in the code comments and in `docs/status_tracking_limitations.md` — do not let this look like a live integration in the demo if it isn't one.
- Every status transition is logged with a timestamp, for the same audit-trail reasons as Phase 5's approval log.

### 2. `tracking/staleness_checker.py`
- `find_stale_drafts(threshold_days)` — returns all `ApplicationDraft`s where `status` is `submitted` or `pending` and no status update has occurred in more than `threshold_days` (add this as a config value in `config/scope.json`, e.g. `status_stale_after_days`).
- This powers the "family member gets a nudge to follow up" story — the output of this function should be render-ready for a notification (draft id, scheme name, days since last update, suggested next action like "consider calling the local office").

### 3. `tracking/notifications.py`
- For the MVP, this can be a simple log/console output or a mock notification list rather than real SMS/push — but it must be triggered automatically by `staleness_checker.py`'s output, not manually invoked, so the "the agent follows up" story is real even if the delivery channel is mocked.

## Edge cases to handle
- A draft is marked `submitted` but the citizen later says they never actually submitted it (family member error) — provide an `unmark_submitted` or `correct_status` path so a wrong status isn't a dead end; log the correction.
- `find_stale_drafts` is called with no drafts in `submitted`/`pending` state — must return an empty list cleanly, not error.
- A draft reaches `resolved` (approved or rejected by the government) — this is a terminal state; no further staleness checks should fire for it. Verify this explicitly.

## Explicitly out of scope for this phase
- No real-time integration with any government portal's status system — this does not exist for most schemes and attempting to fake it would be dishonest to judges and to real users. State this limitation plainly in your demo (Phase 7).
- No automated re-submission or correction of a rejected application — that's a distinct, larger feature and out of MVP scope.

## Acceptance criteria
- [ ] The full status state machine transitions correctly in both the happy path and the rejected branch
- [ ] `find_stale_drafts` correctly identifies drafts past the configured threshold and correctly excludes `resolved`/`rejected` drafts
- [ ] A staleness event automatically produces a notification without manual triggering
- [ ] `docs/status_tracking_limitations.md` exists and honestly states this is manual/mock status tracking, not a live portal integration
