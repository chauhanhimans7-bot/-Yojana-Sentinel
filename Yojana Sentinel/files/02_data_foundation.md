# Phase 1 — Data Foundation

**Load `00_master_context.md` and the outputs of `01_scope_validate.md` (specifically `config/scope.json`) first. This is the highest-risk phase in the whole build — government sources are inconsistent. Budget real time here.**

## Goal
Produce a reliable, normalized set of `Scheme` records — a mix of hand-curated seed data and at least one real, working scraper/parser — that every later phase can query without needing to know where the data originally came from.

## Build the following

### 1. `data/schemes_seed.json`
- 10–15 **real** government schemes, hand-curated, restricted to `config/scope.json`'s `target_state` + national schemes, within `included_categories`.
- Every record must conform exactly to the `Scheme` schema in the master context.
- For each scheme, `eligibility_rules` must be structured (not left as free text) wherever the real scheme's rules allow it — push anything genuinely ambiguous into `other_conditions` rather than forcing a bad structured fit.
- At least 2 schemes must have `deadline` within `deadline_approaching_window_days` of "today" (for demo purposes) — pick or adjust dates so the demo has something to trigger against.
- At least 1 scheme should be eligible for Persona A (strong match) and at least 1 should be a near-miss for Persona B (partial match / missing_info), from Phase 0's personas.

### 2. `ingestion/scraper_<source_name>.py`
- Pick exactly ONE real source (e.g. myscheme.gov.in, a specific state welfare department page, or PIB press release RSS for scheme announcements).
- Write a working parser that:
  - Fetches the source
  - Extracts at minimum: scheme name, a description, and (if present) a deadline and source URL
  - Handles the page/feed being unreachable or malformed without crashing (log and skip, don't throw)
  - Is idempotent — running it twice doesn't create duplicate scheme entries
- This does NOT need to cover every scheme category or be production-robust. It needs to prove the mechanism works end-to-end on real data, once.

### 3. `ingestion/normalize.py`
- Converts whatever raw shape the scraper produces into the exact `Scheme` schema.
- Must explicitly fill `last_verified_at` with the current timestamp on every run.
- Must set `status` based on whether `deadline` has passed (`closed`) or is in the future (`active`) or is null (`active`, rolling).
- Any field the scraper couldn't extract should be `null` (schema-valid), never an empty string standing in for missing data — later phases will check for `null` explicitly.

### 4. `db/schema.sql` and `db/seed.py`
- SQL table for `Scheme` matching the schema exactly (JSON columns are fine for nested fields like `eligibility_rules` if your DB supports it).
- `seed.py` loads `schemes_seed.json` into the table and is safe to re-run (upsert on `scheme_id`, not duplicate insert).

## Edge cases to handle
- Scheme with no deadline (rolling admission) — `deadline: null`, `status: "active"`, must not be treated as "closed" by any downstream logic.
- Scheme where `eligibility_rules.states` is empty — must be interpreted as "no state restriction," not "no state is eligible."
- Duplicate scheme detected across scraper run and seed file (same real scheme, different `scheme_id`) — write a short note in `docs/known_duplicates.md` on how you'd deduplicate in a real version; you don't need to solve it, just don't let it silently corrupt the demo data.
- Scraper source becomes unreachable at demo time — confirm `schemes_seed.json` alone is sufficient for the full demo to run with zero network dependency, and document this fallback explicitly.

## Explicitly out of scope for this phase
- No matching logic against citizen profiles (Phase 2).
- No monitoring/scheduling loop (Phase 3) — this phase produces static + one-shot-scraped data, not a running watcher.
- Do not attempt more than one scraper. One working end-to-end beats three brittle ones.

## Acceptance criteria
- [ ] `schemes_seed.json` has 10-15 real, schema-valid schemes within the fixed scope
- [ ] At least 2 schemes have a near-term deadline; at least 1 strong match and 1 partial match exist for the Phase 0 personas
- [ ] One scraper runs end-to-end against a live source and produces at least one schema-valid `Scheme` record
- [ ] The normalize step correctly derives `status` from `deadline` in all three cases (past/future/null)
- [ ] The demo can run entirely offline from `schemes_seed.json` if the live source is unavailable
