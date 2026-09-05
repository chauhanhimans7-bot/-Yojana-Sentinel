# Phase 4 — Application Drafting Agent

**Load `00_master_context.md` and the outputs of Phases 0-3 first. Read master context rule #1 again before starting this phase: the agent never submits anything. Every function here produces a draft, never a transmission.**

## Goal
Take a `strong_match` (or approved `partial_match`) `MatchResult` and produce a complete, human-reviewable `ApplicationDraft` — pre-filled wherever the citizen profile allows, explicitly flagged wherever it doesn't.

## Build the following

### 1. `drafting/field_mapper.py`
- For a given `(profile, scheme)` pair, map each entry in `scheme.application_fields` to a value:
  - If a direct field exists on `CitizenProfile` (e.g. `age`, `state`, `annual_income`), map it directly. Maintain an explicit mapping table (`field_id` → `CitizenProfile` attribute name) rather than fuzzy-matching field labels — fuzzy matching is exactly the kind of silent error that erodes trust in a govt-application tool.
  - If a field requires a document the citizen doesn't have (`documents_available` doesn't include a `required_documents` entry the field depends on), mark it `source: needs_input` and add it to `unresolved_fields`.
  - If a field genuinely can't be derived from any structured profile data (e.g. a free-text "reason for application" field), mark it `source: inferred` and let `draft_writer.py` (below) generate it — but only for fields explicitly allowed to be inferred (add an `inferable: true/false` flag to `Scheme.application_fields` in the schema if not already present, and default to `false`).
- Output: the `filled_fields` and `unresolved_fields` arrays of an `ApplicationDraft`.

### 2. `drafting/draft_writer.py`
- Takes the mapped fields and produces `ApplicationDraft.draft_text` — the human-readable rendered application or cover note.
- LLM prompt for this step must include: the scheme name and description, the filled field values, and an explicit instruction to never state a fact not present in the filled fields (no inventing employment history, no inventing family details beyond what's in `family_status`).
- For any `inferable: true` field, the LLM may draft plausible text but must mark it inline (e.g. wrap in `[DRAFT — please review: ...]`) so it's visually obvious to the human approver which parts are LLM-generated versus directly copied from profile data.
- Output must always include a rendered list of `unresolved_fields` at the top of `draft_text`, in plain language (e.g. "Before this can be submitted, you still need to provide: income certificate").

### 3. `drafting/create_draft.py`
- Orchestrates: takes a `MatchResult` with `match_status` in (`strong_match`, `partial_match`), calls `field_mapper.py` then `draft_writer.py`, writes a new `ApplicationDraft` with `status: "drafted"`.
- Must refuse to create a draft for a `MatchResult` with `match_status: not_eligible` — raise a clear error, this should never be reachable from the UI but must not silently succeed if called directly.
- Must refuse to create a draft if `MatchResult.match_status == "needs_review"` without an explicit human override flag passed in — document this clearly, since `needs_review` means the eligibility itself is uncertain, not just the paperwork.

## Edge cases to handle
- A scheme field has no corresponding profile attribute AND is not marked `inferable` — this must show up in `unresolved_fields`, never silently dropped from the draft.
- Two schemes with the same `field_id` naming convention but different meanings (e.g. `field_id: "amount"` means different things on two schemes) — the mapping table must be scoped per-scheme, not global, to avoid cross-scheme field bleed.
- Draft is created, then the underlying `Scheme` data changes (e.g. a `scheme_updated` event fires) before approval — document (in `docs/draft_staleness_policy.md`) what should happen: at minimum, flag the draft as stale and require re-matching before it can be approved. You don't need to fully implement the re-check loop, but the draft's `status` must have a way to represent "stale," and creating this doc is part of the deliverable.
- LLM call in `draft_writer.py` fails or times out — draft creation should fail cleanly with a retry path, never produce a draft with `draft_text: null` that a human might approve blind.

## Explicitly out of scope for this phase
- No approval UI (Phase 5) — this phase's output is a data object, not something a human sees yet.
- No actual submission mechanism of any kind — do not build a submit button, an API call to any portal, or anything that transmits the draft. This is a hard boundary, not a "later" item.

## Acceptance criteria
- [ ] A `strong_match` MatchResult for Persona A produces a complete draft with zero `unresolved_fields`
- [ ] A `partial_match` MatchResult for Persona B produces a draft where `unresolved_fields` correctly lists the missing document(s)
- [ ] `draft_text` clearly and visually distinguishes profile-sourced text from LLM-inferred text
- [ ] Attempting to draft a `not_eligible` match raises an error and creates no `ApplicationDraft`
