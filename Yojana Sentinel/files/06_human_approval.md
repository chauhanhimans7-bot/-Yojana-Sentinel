# Phase 5 — Human-in-the-Loop Approval

**Load `00_master_context.md` and the outputs of Phases 0-4 first. This is the trust surface of the whole product — a family member deciding whether to act on the agent's work. Every design choice here should make it obvious what the agent did versus what still needs a human decision.**

## Goal
Build the interface where a citizen or their family member reviews a drafted application and either approves it (moving it toward manual submission by them, outside the app), edits it, or rejects it — never an interface that submits anything automatically.

## Build the following

### 1. Approval surface — choose ONE per `config/scope.json`'s `demo_channel`:

**If `web_dashboard`:**
- `approval/app.py` (or equivalent) — a simple web page listing pending `ApplicationDraft`s with `status: "drafted"`.
- Each draft's view must show, in this order: scheme name and deadline, match reasoning (from `MatchResult.reasoning`), the rendered `draft_text`, the list of `unresolved_fields` if any, and three actions: Approve, Edit, Reject.

**If `whatsapp_mock`:**
- `approval/bot.py` (or equivalent) — a simulated chat interface (does not need real WhatsApp API integration for the MVP) presenting the same information as a conversational message, with quick-reply-style buttons for Approve / Edit / Reject.

### 2. `approval/actions.py`
- `approve_draft(draft_id, approver_name)` — sets `status: "approved"`, `approved_by`, `approved_at`. Must NOT trigger any submission — approval only marks the draft as ready for the human to physically/manually submit it themselves (by hand, via the real portal, in person, etc., all outside this app's scope).
- `reject_draft(draft_id, reason)` — sets `status: "rejected"`, logs the reason for later analysis (e.g. was it a bad match, wrong info, citizen changed their mind).
- `request_edit(draft_id, edited_fields)` — updates `filled_fields` with human-provided corrections, re-renders `draft_text`, keeps `status: "drafted"` until re-approved. Must revalidate that `unresolved_fields` is recomputed after an edit (a human filling in a previously-missing field should remove it from `unresolved_fields`).

### 3. `approval/approval_log.py`
- Every approve/reject/edit action is logged with a timestamp and actor name — this is your audit trail and also useful demo evidence ("here's the human decision, on the record").

## Content and copy requirements (do not skip — this determines whether the product is actually usable by the target user)
- All UI text in plain language, sentence case, no jargon like "eligibility predicate" or "match score" shown raw to the citizen — translate `match_status` into a plain sentence, e.g. "You likely qualify for this" rather than "strong_match."
- The "why" behind a match must be shown in plain language, sourced from `MatchResult.reasoning`, not hidden behind a technical label.
- If `language_preference` on the profile is not English, either render the approval surface in that language or clearly flag (in `docs/i18n_todo.md`) that translation is a known next step — do not silently ship English-only without acknowledging it.
- Never use an action label that doesn't match what happens: "Approve" must never actually submit; if your button says "Submit," you have violated the master context's non-negotiable rule #1 — rename it to something like "Mark ready to submit."

## Edge cases to handle
- Approver tries to approve a draft with non-empty `unresolved_fields` — must warn clearly and either block approval or require an explicit "approve anyway, I'll submit the rest myself" confirmation; document which choice you made and why.
- Two family members both viewing the same draft, one approves while the other is mid-edit — last-write-wins is acceptable for the MVP, but log both actions in `approval_log.py` so the conflict is visible after the fact, not silently lost.
- Draft is flagged `stale` (per Phase 4's staleness policy) — approval surface must show a clear warning and block approval until re-matched, not let a human approve outdated information.

## Explicitly out of scope for this phase
- No real submission to any government portal, API, or authority, under any circumstance.
- No post-submission status tracking yet (Phase 6) — this phase ends at `status: "approved"`.

## Acceptance criteria
- [ ] A drafted application with zero unresolved fields can be approved in the fewest possible taps/clicks appropriate to the chosen channel
- [ ] A drafted application with unresolved fields cannot be silently approved without the explicit warning path firing
- [ ] Every approve/reject/edit action appears in `approval_log.py` with actor and timestamp
- [ ] No button, label, or copy anywhere implies the app itself submits the application
