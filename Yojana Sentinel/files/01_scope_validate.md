# Phase 0 — Scope & Validate

**Load `00_master_context.md` first. This phase produces no application code — it produces the decision artifacts every later phase will read.**

## Goal
Freeze every ambiguous product decision into a written config/spec before any code is written, so later phases don't quietly redefine scope mid-build.

## Build the following files

### 1. `config/scope.json`
A single source of truth for MVP boundaries:
```json
{
  "target_state": "string, the one Indian state in scope",
  "included_categories": ["exactly 2-3 from: education, agriculture, health, housing, employment"],
  "strong_match_threshold": "number 0-100, e.g. 80",
  "partial_match_threshold": "number 0-100, e.g. 50",
  "deadline_approaching_window_days": "number, e.g. 14",
  "demo_channel": "enum: web_dashboard | whatsapp_mock"
}
```
Fill in real values — do not leave placeholders. Justify each value in a one-line comment (JSON5 or a companion `scope_notes.md`) explaining why that number/category was chosen (e.g. "education chosen because scholarship eligibility rules are the most cleanly structured of the three candidates").

### 2. `data/profiles_seed.json`
Exactly 2 fictional citizen personas conforming to the `CitizenProfile` schema in the master context. Requirements:
- Persona A should be a **strong match** candidate for at least one seed scheme you'll create in Phase 1.
- Persona B should be a **partial match / missing info** candidate — deliberately missing at least one document or field a scheme requires, to exercise the "missing_info" path later.
- Both personas need every field populated (no nulls except where the schema allows).
- Add a short one-paragraph backstory as a comment/companion field for use in demo narration (not part of the strict schema, store separately if needed).

### 3. `docs/demo_script_skeleton.md`
A skeleton (not the full script — that's Phase 8) capturing:
- Which persona is used in the live demo
- Which scheme category will be showcased
- What the "before" state looks like (nothing has fired yet)
- What triggers the "after" state (a monitoring event fires — decided in Phase 4)

## Edge cases to think through now (write answers into `scope_notes.md`)
- What happens if a citizen matches a scheme in a category NOT in `included_categories`? (Answer: out of scope for MVP, log it for future work, do not surface it.)
- What if `strong_match_threshold` and `partial_match_threshold` overlap or are set inconsistently? Add a validation check that `partial_match_threshold < strong_match_threshold`.
- What if the target state changes later (e.g. demo audience asks "does this work for my state")? Note in `scope_notes.md` that state is a config value, not hardcoded logic, so this is answerable honestly on stage.

## Explicitly out of scope for this phase
- No scraping, no matching logic, no UI. This phase only produces config and seed persona data.

## Acceptance criteria
- [ ] `config/scope.json` exists with real, justified values (no placeholders)
- [ ] `data/profiles_seed.json` has exactly 2 personas, schema-valid, one strong-match-shaped and one partial-match-shaped
- [ ] `scope_notes.md` answers all three edge-case questions above
- [ ] `docs/demo_script_skeleton.md` names the persona, category, before-state, and trigger for the eventual demo
