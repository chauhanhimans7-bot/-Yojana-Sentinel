# Yojana Sentinel — Architecture Overview (Slide Content)

## 5-Stage Autonomous Pipeline

```
  [ MONITOR ]  ──→  [ MATCH ]  ──→  [ DRAFT ]  ──→  [ APPROVE ]  ──→  [ TRACK ]
  Ingestion &       Rule-Based      Field Mapping    Human-in-the-    State Machine &
  Diff Engine       + LLM Review    & LLM Cover      Loop Dashboard   Staleness Nudge
```

---

### Stage 1: Continuous Monitoring
- **Module:** `monitoring/scheduler.py` & `monitoring/diff.py`
- **What it does:** Runs periodic ingestion against `myscheme.gov.in`, computes diffs against snapshot, emits `MonitoringEvent`s (`new_scheme`, `deadline_approaching`, `scheme_updated`, `scheme_closed`).

### Stage 2: Eligibility Matching Engine
- **Module:** `matching/rules_engine.py` & `matching/matcher.py`
- **What it does:** Evaluates 7 structured dimensions deterministically (zero hallucination). Uses Groq LLM (`other_conditions_reviewer.py`) only for unstructured free-text rules. Calculates match score (0-100) and status.

### Stage 3: Application Drafting Agent
- **Module:** `drafting/field_mapper.py` & `drafting/create_draft.py`
- **What it does:** Maps citizen profile attributes to scheme fields, checks document availability, flags inferable fields with `[DRAFT]`, and generates cover notes (`draft_writer.py`).

### Stage 4: Human-in-the-Loop Approval
- **Module:** `approval/app.py` & `approval/actions.py`
- **What it does:** Web dashboard displaying plain-language match rationale and pre-filled drafts. Explicit warning on missing fields. **Strict rule:** Action is "Mark Ready to Submit" — NEVER auto-submits.

### Stage 5: Post-Submission Tracking
- **Module:** `tracking/status_store.py` & `tracking/staleness_checker.py`
- **What it does:** Tracks state machine (`drafted → approved → submitted → pending → resolved`). Automatically fires follow-up nudges (`notifications.py`) when applications stall past threshold days.
