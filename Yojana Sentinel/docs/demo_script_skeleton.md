# Demo Script Skeleton — Yojana Sentinel

> **Note:** This is a skeleton only. The full narration and timing will be developed in Phase 8. Do not expand this until that phase.

---

## 1. Demo Persona

**Name:** Ramkali Devi (`profile-001`)
**Why chosen:** Strong-match candidate with a clear, emotionally resonant story (widow, small farmer, daughter studying for Class 11). All required documents are present, making the approval flow clean and satisfying to watch on stage.

---

## 2. Scheme Category Showcased

**Category:** `education` (scholarship)
**Specific scheme (tentative):** UP Scholarship Scheme for OBC students — well-structured eligibility rules (age, income, category, academic standing), real portal (`scholarship.up.gov.in`), and a deadline that creates urgency in the demo.

---

## 3. "Before" State (Nothing Has Fired Yet)

- Ramkali's profile is loaded in the dashboard.
- The schemes database has been seeded but no matching has run.
- No `MatchResult` or `ApplicationDraft` exists for `profile-001`.
- The monitoring scheduler has not yet triggered.
- The UI shows: *"No matches found yet. Monitoring is active."*

---

## 4. Trigger for the "After" State

**Trigger:** A `MonitoringEvent` of type `deadline_approaching` fires for the UP Scholarship scheme.
- The event is detected because the scheme's `deadline` is within the `deadline_approaching_window_days` (14 days) configured in `config/scope.json`.
- This triggers the matching pipeline → `MatchResult` is created with `match_status: strong_match`.
- The drafting agent runs → `ApplicationDraft` is created with `status: drafted`.
- The dashboard surfaces the draft with an **"Approve & Download"** button for one-tap approval.
- Ramkali's operator (son Vikram) reviews the pre-filled application and taps Approve.

---

## 5. What the Demo Audience Should Feel

- "It found her a scholarship automatically."
- "It already filled in all her details — she didn't have to type anything."
- "She still approves it before anything happens — she's in control."
- "This could work for my mother / grandmother / village."
