# Yojana Sentinel — Master Context

**Paste this file into your agent's context (or reference it) before running any of the numbered phase prompts. It defines the shared vocabulary, data schemas, and non-negotiable rules every other file assumes exist. If a phase prompt conflicts with this file, this file wins.**

---

## 1. One-line product definition

Yojana Sentinel is an agent that monitors Indian government welfare scheme sources for new or changing schemes, matches them against a citizen's profile, drafts the application when there's a strong match approaching its deadline, and hands it to a human for one-tap approval before anything is ever submitted.

## 2. Who this is for

- Primary user: a rural/semi-urban Indian citizen with limited internet access, literacy, or time to monitor scheme portals themselves.
- Realistic operator: a more digitally fluent family member (child, relative, local volunteer) who manages the app on the citizen's behalf.
- Design every UI string and flow assuming the person reading it may not be technical, and may be reading it in a regional language.

## 3. Non-negotiable product rules

These apply across every phase. Any phase prompt that seems to imply otherwise should be interpreted through these rules:

1. **The agent never submits anything on its own.** It drafts, it never transmits to a government portal or authority. Every submission requires an explicit human tap.
2. **Eligibility decisions are rule-based, not vibes-based.** Encode scheme eligibility as structured logical predicates (age ranges, income thresholds, state, category, occupation, land ownership, etc.). The LLM's job is extracting those rules from messy scheme text and drafting prose — not deciding eligibility from free reasoning alone.
3. **Every claim the agent makes about a match or a deadline must carry a source** — the URL/document it came from and the timestamp it was last verified.
4. **Missing information is surfaced, not guessed.** If a required field can't be filled from the citizen profile, the agent flags it explicitly rather than inventing a plausible value.
5. **MVP scope is fixed:** one state + national-level schemes only, 2–3 scheme categories (recommended: education/scholarship, agriculture/farmer subsidy, maternity/health benefit). Do not let scope creep into "all schemes, all states" during any phase.

## 4. Core data schemas

Every phase must read and write these exact shapes. Use these field names verbatim across all modules so phases compose without translation layers.

### 4.1 `Scheme`
```json
{
  "scheme_id": "string, stable slug e.g. 'up-scholarship-2026'",
  "name": "string, official scheme name",
  "issuing_body": "string, e.g. 'Ministry of Rural Development' or state dept name",
  "category": "enum: education | agriculture | health | housing | employment | other",
  "description": "string, plain-language summary, max ~400 chars",
  "eligibility_rules": {
    "min_age": "number | null",
    "max_age": "number | null",
    "states": ["array of state names, empty array = all-India"],
    "max_annual_income": "number | null (INR)",
    "categories": ["array from: general | obc | sc | st | ews | other, empty = no restriction"],
    "occupation": ["array of allowed occupations, empty = no restriction"],
    "gender": "enum: any | male | female | other",
    "land_ownership_required": "boolean | null",
    "other_conditions": ["array of free-text conditions the rule-engine can't structure yet — flagged for LLM-assisted review"]
  },
  "required_documents": ["array of document names, e.g. 'Aadhaar card', 'income certificate'"],
  "application_fields": [
    {"field_id": "string", "label": "string", "type": "enum: text | number | date | select | document_upload", "required": "boolean"}
  ],
  "deadline": "ISO date string | null (null = rolling/no deadline)",
  "source_url": "string, canonical source page",
  "last_verified_at": "ISO datetime string",
  "status": "enum: active | closed | upcoming"
}
```

### 4.2 `CitizenProfile`
```json
{
  "profile_id": "string",
  "display_name": "string",
  "age": "number",
  "gender": "enum: male | female | other",
  "state": "string",
  "district": "string | null",
  "annual_income": "number (INR)",
  "category": "enum: general | obc | sc | st | ews",
  "occupation": "string",
  "owns_land": "boolean",
  "family_status": "string, free text, e.g. 'single mother, 2 children'",
  "documents_available": ["array of document names the citizen already has on file"],
  "language_preference": "string, e.g. 'hi', 'mr', 'en'",
  "managed_by": "string | null, name/contact of the family member operating the account on their behalf"
}
```

### 4.3 `MatchResult`
```json
{
  "profile_id": "string",
  "scheme_id": "string",
  "match_score": "number, 0-100",
  "match_status": "enum: strong_match | partial_match | not_eligible | needs_review",
  "missing_info": ["array of CitizenProfile or document fields that block a confident match"],
  "reasoning": "string, short explanation of why this score, referencing which rules passed/failed",
  "evaluated_at": "ISO datetime string"
}
```

### 4.4 `ApplicationDraft`
```json
{
  "draft_id": "string",
  "profile_id": "string",
  "scheme_id": "string",
  "filled_fields": [
    {"field_id": "string", "value": "string", "source": "enum: profile | inferred | needs_input"}
  ],
  "unresolved_fields": ["array of field_ids the citizen must still supply"],
  "draft_text": "string, the human-readable rendered application/cover note",
  "status": "enum: drafted | approved | rejected | submitted | pending | resolved",
  "created_at": "ISO datetime string",
  "approved_by": "string | null",
  "approved_at": "ISO datetime string | null"
}
```

### 4.5 `MonitoringEvent`
```json
{
  "event_id": "string",
  "event_type": "enum: new_scheme | deadline_approaching | scheme_closed | scheme_updated",
  "scheme_id": "string",
  "detected_at": "ISO datetime string",
  "detail": "string, what changed"
}
```

## 5. Suggested tech stack (adjust to what your agent/environment supports)

- **Orchestration:** LangGraph or an equivalent agent-graph framework for the monitor → match → draft → approve loop.
- **LLM:** Groq-hosted model (or whatever low-latency inference the environment provides) for rule extraction and draft-text generation only — not for eligibility decisions.
- **Storage:** SQLite for the hackathon MVP (Scheme, CitizenProfile, MatchResult, ApplicationDraft, MonitoringEvent tables mapped directly from the schemas above).
- **Scraping/ingestion:** a single well-tested parser for one real source (e.g. myscheme.gov.in or one state welfare portal), plus hand-curated JSON seed data for the remaining schemes used in the demo.
- **Scheduler:** a simple interval loop or cron-style job; does not need to be production-grade for the MVP.
- **Frontend:** a single web page (or WhatsApp-style chat mock) for profile input, match review, and one-tap approval.

## 6. Repository layout to establish before Phase 1

```
yojana-sentinel/
  data/
    schemes_seed.json          # hand-curated schemes matching the Scheme schema
    profiles_seed.json         # 2 test personas matching CitizenProfile schema
  ingestion/
    scraper_<source_name>.py   # one proof-of-concept scraper
    normalize.py               # raw source data -> Scheme schema
  matching/
    rules_engine.py            # eligibility predicate evaluation
    matcher.py                 # profile x scheme -> MatchResult
  monitoring/
    scheduler.py
    diff.py                    # detects new/changed/closed schemes -> MonitoringEvent
  drafting/
    field_mapper.py            # CitizenProfile -> ApplicationDraft.filled_fields
    draft_writer.py            # LLM call producing draft_text
  approval/
    app.py or bot.py           # approval UI/mock
  tracking/
    status_store.py            # ApplicationDraft.status transitions
  db/
    schema.sql
    seed.py
  README.md
```

## 7. How to use the phase prompt files

Each numbered file (`01_...md` through `08_...md`) is a standalone prompt you can hand to your coding agent one at a time, in order. Each one:
- Assumes this master context is already loaded/known.
- States exactly what to build, the inputs/outputs, the edge cases to handle, and what NOT to build yet.
- Ends with acceptance criteria your agent should self-check against before you move to the next file.

Do not skip ahead — later phases assume earlier phases' schemas and files exist unchanged.
