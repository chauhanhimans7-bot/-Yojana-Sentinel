# Phase 2 — Citizen Profile & Matching Engine

**Load `00_master_context.md` and the outputs of Phases 0 and 1 (`config/scope.json`, `data/profiles_seed.json`, `data/schemes_seed.json`) first.**

## Goal
Build a deterministic, explainable matcher that scores every (profile, scheme) pair and produces a `MatchResult`. Eligibility must be rule-based; the LLM is only used where a scheme's `other_conditions` require judgment on ambiguous free text.

## Build the following

### 1. `matching/rules_engine.py`
Implement one pure function per eligibility dimension, each returning `pass | fail | not_applicable`:
- `check_age(profile, scheme)` — respects `min_age`/`max_age`, both may be null
- `check_state(profile, scheme)` — empty `states` array = pass for everyone
- `check_income(profile, scheme)` — respects `max_annual_income`, null = pass for everyone
- `check_category(profile, scheme)` — empty `categories` array = pass for everyone
- `check_occupation(profile, scheme)` — empty `occupation` array = pass for everyone
- `check_gender(profile, scheme)` — `any` = pass for everyone
- `check_land_ownership(profile, scheme)` — null = not applicable

Each function must be independently unit-testable and must not call the LLM.

### 2. `matching/other_conditions_reviewer.py`
- For any `other_conditions` entries on a scheme, use an LLM call to judge whether the profile plausibly satisfies each condition.
- This function must return a **confidence-qualified** verdict (`likely_pass | likely_fail | unclear`), never a bare `pass/fail` — unclear conditions should push the overall match toward `needs_review`, not silently toward `strong_match`.
- Log the LLM's stated reasoning for every call — this becomes part of `MatchResult.reasoning` and is your defense against "how do you know it's not hallucinating eligibility" from judges.

### 3. `matching/matcher.py`
- Combines `rules_engine.py` results + `other_conditions_reviewer.py` results into one `MatchResult` per (profile, scheme) pair.
- Scoring logic (adjust weights as needed, but keep it explicit and documented, not a black box):
  - Any hard rule `fail` → `match_status: not_eligible`, `match_score: 0`
  - All hard rules `pass`, no `other_conditions` issues → `match_status: strong_match`, score based on how many required documents the profile already has (`documents_available` vs `required_documents`)
  - All hard rules `pass`, but required documents/fields missing → `match_status: partial_match`, populate `missing_info`
  - All hard rules `pass`, but an `other_conditions` verdict is `unclear` → `match_status: needs_review`
- `reasoning` must name which specific rules passed/failed/were unclear — never a generic "profile matches this scheme."
- Compare against `config/scope.json`'s `strong_match_threshold` / `partial_match_threshold` to finalize `match_status` from `match_score`.

### 4. `matching/run_matching.py`
- CLI/script entrypoint: loads all schemes + all profiles, runs the matcher across the full cross-product, writes `MatchResult` records to the DB (or a `data/match_results.json` for the MVP).
- Must be safely re-runnable (overwrite previous results for the same profile+scheme pair, not append duplicates).

## Edge cases to handle
- A scheme with zero eligibility restrictions on every field (all nulls/empty arrays) — every profile should score as at least `partial_match`, driven purely by document completeness. Write a unit test for this.
- A profile missing a field a scheme's rule needs to check (e.g. profile has no `occupation` recorded but scheme restricts by occupation) — treat as `needs_review`, not a silent pass or fail.
- Two schemes are functionally identical except for `issuing_body` (a real risk with overlapping state/national schemes) — matcher should score both independently; do not attempt deduplication here (that's a data problem, flagged in Phase 1's `known_duplicates.md`).
- LLM call in `other_conditions_reviewer.py` fails or times out — must degrade to `unclear`, never silently skip the condition.

## Explicitly out of scope for this phase
- No monitoring/triggering (Phase 3) — this phase runs on-demand against static seed data.
- No application drafting (Phase 4) — `MatchResult` is the final output here, not a filled form.

## Acceptance criteria
- [ ] Each rule function in `rules_engine.py` has at least one passing and one failing unit test
- [ ] Persona A scores `strong_match` against at least one seed scheme; Persona B scores `partial_match` or `needs_review` against at least one seed scheme, matching the intent set in Phase 0
- [ ] Every `MatchResult.reasoning` names specific rules, not generic language
- [ ] Re-running `run_matching.py` does not duplicate results
