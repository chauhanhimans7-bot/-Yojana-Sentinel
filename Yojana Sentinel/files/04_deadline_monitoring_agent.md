# Phase 3 — Deadline & Monitoring Agent

**Load `00_master_context.md` and the outputs of Phases 0-2 first. This is the phase that makes the product an agent rather than a search tool — it must be visibly, demonstrably continuous, not a one-shot query.**

## Goal
Build the watcher that periodically re-checks scheme sources, detects meaningful changes, and fires `MonitoringEvent`s that trigger downstream matching + drafting — including a way to simulate this live for a demo without waiting on a real government portal to actually change.

## Build the following

### 1. `monitoring/scheduler.py`
- An interval-based loop (or cron-equivalent) that, on each tick:
  1. Re-runs the Phase 1 scraper/ingestion against the live source (or re-reads `schemes_seed.json` if running in offline/demo mode — make this a config flag, not two separate codepaths)
  2. Passes old vs new scheme data to `diff.py`
  3. Writes any resulting `MonitoringEvent`s to the DB/event log
  4. For each `deadline_approaching` or `new_scheme` event, triggers the Phase 2 matcher against all stored profiles for that scheme
- Interval should be configurable (e.g. `monitoring_interval_minutes` in `config/scope.json` — add this field now if not already present).

### 2. `monitoring/diff.py`
Implement detection for exactly these four `MonitoringEvent.event_type` values:
- `new_scheme` — a `scheme_id` present now that wasn't in the previous snapshot
- `deadline_approaching` — a scheme's `deadline` falls within `deadline_approaching_window_days` of "now" for the first time this check (must not re-fire every tick once already flagged — track a `deadline_alert_sent` flag or equivalent)
- `scheme_closed` — a scheme's `deadline` has now passed, or its `status` field changed to `closed` at the source
- `scheme_updated` — any of `eligibility_rules`, `required_documents`, or `deadline` changed value for an existing `scheme_id`

Each detected event must populate `detail` with a specific, human-readable description of what changed (e.g. "deadline moved from 2026-09-10 to 2026-09-20"), not just the event type.

### 3. `monitoring/demo_trigger.py`
- A standalone script/function that lets you manually inject a fake `MonitoringEvent` (e.g. "simulate scheme X's deadline entering the approaching window right now") without needing the real source to change.
- This is what you'll actually run on stage — document this clearly in a comment at the top of the file.
- Must go through the exact same downstream path (`scheduler.py`'s trigger-matcher step) as a real detected event, so the demo is proving the real pipeline, not a separate mock.

### 4. `monitoring/event_log.py`
- Append-only log/table of every `MonitoringEvent` ever fired, queryable by `scheme_id` and `event_type`.
- This is what Phase 8's demo will visually display as "the agent noticed this."

## Edge cases to handle
- Scheduler tick runs while a previous tick's ingestion is still in progress (e.g. slow scraper) — must not overlap; skip or queue, document which you chose and why.
- A scheme flickers status (source briefly reports it closed, then active again due to a scraping glitch) — do not fire `scheme_closed` and then immediately `new_scheme`-equivalent noise; consider a minimum-confidence or debounce window and document the tradeoff.
- `deadline_approaching` firing repeatedly for the same scheme on every tick — must fire once per scheme per approach into the window, not once per tick (see `deadline_alert_sent` flag above).
- Demo trigger fires for a `scheme_id` that doesn't exist in current data — should fail loudly with a clear error, not silently no-op, since this will burn you live on stage if the ID is wrong.

## Explicitly out of scope for this phase
- No application drafting yet (Phase 4) — this phase's job ends at firing the matcher and logging the event.
- No UI (Phase 5) — event log can be a raw table/JSON for now.

## Acceptance criteria
- [ ] Running the scheduler twice in a row with unchanged source data produces zero new events
- [ ] `demo_trigger.py` reliably fires a `deadline_approaching` event on command and it flows through to a fresh `MatchResult`
- [ ] Deadline alerts do not repeat once already fired for a given scheme
- [ ] Every `MonitoringEvent.detail` is specific enough to read aloud in a demo without further editing
