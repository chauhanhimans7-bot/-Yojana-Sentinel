# Yojana Sentinel — Final Fix & Completion Prompt

Paste this entire file to Antigravity as one message. It is based on a full audit of your actual code and actual data (not assumptions) — every item below was either read directly in your files or confirmed by actually running your code.

---

## Context

The Yojana Sentinel MVP is largely built and working. All 8 phases have real code, and the following have been verified by actually executing them against real project data: the monitoring scheduler (event detection + idempotency), the approval actions, the full status-tracking lifecycle (drafted → approved → submitted → pending → resolved with staleness nudges), and the rules engine (41/41 test assertions passed). This is not a rebuild — it's a fix-and-finish pass. Do not rewrite working modules. Only touch what's listed below.

---

## PRIORITY 1 — Real bugs, must fix before demo

### Bug 1: `matching/matcher.py` — docstring contradicts its own code
The docstring says:
```
score >= strong_match_threshold           → strong_match
score >= partial_match_threshold          → partial_match
score <  partial_match_threshold          → not_eligible
```
But the actual `match()` function's final `else` branch always returns `partial_match` regardless of how low the score is — there is no code path that produces `not_eligible` from a low document score. Confirmed in real data: `profile-001` × `up-kisan-karj-rahat-2026` scored 25/100 and is labeled `partial_match`, contradicting the documented threshold rule.

**Fix:** Decide the intended behavior and make the code and docstring agree. Recommended: keep the current code behavior (low doc-completeness is still `partial_match` because the person IS eligible, just missing paperwork) and rewrite the docstring to state this explicitly, rather than changing the scoring logic. If you instead want strict compliance with the original docstring, add an `else` branch that returns `not_eligible` when `doc_score < PARTIAL_THRESHOLD`. Pick one and make both match.

### Bug 2: `docs/demo_script.md` — factually wrong about your own data
- Claims match score is "92%" and status "`strong_match`" for the scholarship demo. Actual `match_results.json` shows `profile-001` × `up-scholarship-obc-2026` = **66.7%, `partial_match`**, missing `marksheet of previous qualifying exam` and `institution enrollment certificate`.
- Refers to the persona as "Ramesh" and "Ramesh's daughter" throughout. The actual persona in `profiles_seed.json` is **Ramkali Devi** (widow, farmer), managed by her son **Vikram**. There is no Ramesh anywhere in the data.

**Fix:** Rewrite `demo_script.md`'s narration to use the real name (Ramkali Devi / son Vikram) and the real match outcome (66.7%, partial match, two missing documents). The partial-match story is still compelling — pivot the narration to: "the agent tells her exactly what's missing before she wastes a trip." Do not fabricate a new persona or inflate the score to fit the old script — fix the script to fit the real data.

### Bug 3: `monitoring/demo_trigger.py` — its own usage example is broken
The docstring's example command uses `--scheme up-scholarship-2026`, which does not exist. The real scheme ID is `up-scholarship-obc-2026`. Running the exact command from the file's own docstring fails with a "scheme not found" error.

**Fix:** Correct the docstring example to use the real scheme ID `up-scholarship-obc-2026`. Grep the whole codebase and all `docs/*.md` files for any other occurrence of the incorrect ID `up-scholarship-2026` and fix those too.

---

## PRIORITY 2 — Structural gaps, fix if time allows

### Gap 4: `config/scope.json` does not exist in the repository
Multiple modules (`matching/matcher.py`, `matching/run_matching.py`, `ingestion/scraper_myscheme.py`, `monitoring/scheduler.py`, `monitoring/diff.py`, `tracking/staleness_checker.py`) all read from `config/scope.json`, and the project clearly has been run successfully before (real match results and event logs exist) — but the file itself was never found in the repo during this audit.

**Fix:** Create `config/scope.json` at the project root (not in `data/`) with these exact values, which are consistent with every other file in the project:
```json
{
  "target_state": "Uttar Pradesh",
  "included_categories": ["education", "agriculture", "health"],
  "strong_match_threshold": 80,
  "partial_match_threshold": 50,
  "deadline_approaching_window_days": 14,
  "demo_channel": "web_dashboard",
  "monitoring_interval_minutes": 30,
  "status_stale_after_days": 14,
  "demo_mode": true
}
```
Confirm this file is NOT in `.gitignore` and is actually committed — its absence suggests it may have been accidentally excluded.

### Gap 5: Document-tracking mismatch between matching and drafting
`matching/matcher.py` scores document completeness against `Scheme.required_documents` (e.g. the OBC scholarship scheme lists 6 required documents). `drafting/field_mapper.py` only resolves documents that appear as `document_upload` type entries in `Scheme.application_fields` — and only 2 of the scholarship's 6 required documents exist as `application_fields` entries. Result: `MatchResult.missing_info` can say "2 documents missing" while the resulting `ApplicationDraft.unresolved_fields` doesn't reflect those same 2 documents, because nothing in `application_fields` represents them.

**Fix:** For every scheme in `data/schemes_seed.json`, ensure every entry in `required_documents` has a corresponding `document_upload`-type entry in `application_fields`, OR add a reconciliation step in `field_mapper.map_fields()` that also checks `scheme.required_documents` directly (not just `application_fields`) and adds any missing required document to `unresolved_fields` even if it isn't modeled as a form field. Prefer the first approach (fixing the seed data) since it's simpler and doesn't touch working code.

### Gap 6: `seed_drafts.py` is a stale duplicate of `drafting/create_draft.py`
`seed_drafts.py` (at the project root) manually re-implements draft creation with a hardcoded, non-LLM cover-note template — it does not call `drafting/draft_writer.py` at all, so it bypasses the LLM generation logic and the `[DRAFT — please review: ...]` marker convention entirely. The real pipeline (`drafting/create_draft.py` + `drafting/draft_writer.py`) is correctly LLM-backed and spec-compliant.

**Fix:** Delete `seed_drafts.py`, or if it's still needed as a quick offline fallback for demo safety, rename it clearly (e.g. `seed_drafts_offline_fallback.py`) and add a comment explaining it is NOT the production drafting path and exists only as a network-independent backup.

---

## PRIORITY 3 — Demo-day risk mitigation

### Risk 7: LLM dependency at demo time
`matching/other_conditions_reviewer.py` and `drafting/draft_writer.py` both require a live `GROQ_API_KEY` with quota. Confirmed live: without it, several matches that are currently saved as `strong_match`/`partial_match` in `match_results.json` shift to `needs_review` instead (safe degradation, but changes what the demo shows).

**Fix:** Before the demo, verify the API key works and has quota. As a safety net, also confirm `data/match_results.json` and the pre-generated `ApplicationDraft` records already in the database are NOT regenerated live during the demo unless intentional — i.e., the demo trigger script should be tested once beforehand in the exact environment/network conditions it will run in on stage.

### Risk 8: Decide the demo's approval moment now, not on stage
Real drafts in the database include both zero-unresolved-field drafts and drafts with several unresolved fields (requiring `confirm_anyway=True` to approve, per `approval/actions.py`'s correct blocking behavior). Both are valid demo beats but tell different stories.

**Fix:** No code change — just decide and note in `docs/demo_script.md` which specific `draft_id` will be approved live, and whether the unresolved-fields warning path will be shown deliberately as a trust-building moment.

---

## PRIORITY 4 — Test coverage gap

`tests/test_rules_engine.py` exists and all 41 assertions pass against the real `rules_engine.py`. There is no equivalent test file for `matching/matcher.py`, `drafting/field_mapper.py`, or `monitoring/diff.py` — this is exactly why Bug 1 above went undetected.

**Fix (if time allows):** Add `tests/test_matcher.py` with at minimum: a test asserting the documented threshold behavior at the boundary (score just above/below `partial_match_threshold`), a test for the `needs_review` path when `other_conditions_reviewer` returns `unclear`, and a test for the `not_eligible` short-circuit on hard rule failure. This is lower priority than Priority 1–3 but will prevent the next version of this exact bug class.

---

## What NOT to touch

Do not modify: `monitoring/scheduler.py`, `monitoring/diff.py`, `monitoring/event_log.py`, `approval/actions.py`, `approval/approval_log.py`, `tracking/status_store.py`, `tracking/staleness_checker.py`, `tracking/notifications.py`, `matching/rules_engine.py`. These have all been verified working end-to-end against real data and real test assertions. Any change to these should be treated as high-risk and re-tested against the same verification steps used to confirm them (re-run the scheduler tick, re-run the status lifecycle, re-run the rules engine test assertions).

## When done

Report back with: which of the above items were fixed, the diff for each, and confirmation that re-running `python -m matching.run_matching`, `python -m monitoring.scheduler --demo --once`, and the rules engine tests still produce the same verified-good results as before your changes.
