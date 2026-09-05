# Phase 7 — Demo Prep & Storytelling

**Load `00_master_context.md` and the outputs of all previous phases first. This phase produces no new product functionality — it produces the artifacts and script needed to present the working system convincingly and honestly in under 3 minutes.**

## Goal
Turn the working pipeline (monitor → match → draft → approve → track) into a tight live demo that shows the agent noticing something a human would have missed, and prepare honest answers to the hardest questions judges will ask.

## Build the following

### 1. `docs/demo_script.md`
Expand Phase 0's `demo_script_skeleton.md` into a full, timed script:
- **0:00–0:20** — Set up the persona and the pain point in one sentence each (use Phase 0's persona backstory). State plainly what existing tools (Yojana Matcher, Am I Eligible, etc.) do NOT do: monitor, act, or follow up.
- **0:20–1:00** — Trigger `monitoring/demo_trigger.py` live, on stage, to fire a real `deadline_approaching` or `new_scheme` event against real seed data. Narrate what's happening as the event log updates.
- **1:00–1:40** — Show the event automatically flowing into a fresh `MatchResult` and then an `ApplicationDraft` — emphasize that this happened without a human initiating a search.
- **1:40–2:20** — Show the approval surface: the plain-language match reasoning, the pre-filled draft, the clearly-flagged unresolved fields, and the one-tap approve action. Make the "the agent never submits, a human always does" point explicit here.
- **2:20–2:50** — Show a stale-status nudge firing (Phase 6) to close the loop: monitor → match → draft → approve → track.
- **2:50–3:00** — One sentence on what's next (multi-state expansion, more scheme categories, real portal status integration) — framed as roadmap, not as a gap you're hiding.

### 2. `docs/architecture_slide.md`
A one-slide-worth of content (bullet form, ready to drop into slides) showing the five-stage pipeline as a simple flow: Monitor → Match → Draft → Approve → Track, with one line under each stage naming the real module that implements it (reference actual file paths from earlier phases, e.g. `monitoring/scheduler.py`) so it's clear this is a working system, not a mockup.

### 3. `docs/why_agent_not_chatbot_slide.md`
Bullet content contrasting Yojana Sentinel against one-shot Q&A tools (Yojana Matcher, Am I Eligible), organized around three axes: **monitors continuously** vs. one-shot lookup, **acts** (drafts) vs. only informs, **follows up** (status tracking) vs. forgets after the answer. Keep each bullet to one line — this slide should be readable at a glance from the back of the room.

### 4. `docs/hard_questions.md`
Write honest, specific answers (2-4 sentences each) to the questions this project will draw, since your own risk assessment already flagged the first one:
- "How reliable is the scraping at scale across all states and schemes?" — be honest that Phase 1 built one proof-of-concept scraper plus hand-curated seed data, and describe what production-grade ingestion would require.
- "How do you know the eligibility matching isn't hallucinating?" — point to the rule-based engine (Phase 2) and explain the LLM's role is scoped to ambiguous free-text conditions only, always surfaced as `needs_review` rather than a silent pass.
- "What stops this from submitting something wrong on someone's behalf?" — point to the hard no-auto-submit rule and the approval flow (Phase 5).
- "Why would a family member trust a pre-filled government form from an AI?" — point to the visible sourcing (every field marked profile/inferred/needs_input) and the plain-language match reasoning.
- "What's your real integration story with government portals?" — be candid that most Indian government schemes have no public status API; this is a known, structural limitation, not something the product pretends to solve.

## Edge cases to handle for the live demo specifically
- Network/scraper dependency at demo time — confirm (per Phase 1's acceptance criteria) the full script runs entirely from seed data with zero live network calls, and rehearse it that way at least once.
- Timing overrun — mark in the script which section can be cut first if running long (recommend: shorten the stale-status nudge section, since it's the least visually novel part).
- A judge asks to see a scheme category or state not in scope — have the honest one-line answer ready from `config/scope.json`'s justification notes (Phase 0), rather than improvising scope on the spot.

## Explicitly out of scope for this phase
- No new features. If you find yourself wanting to add something to make the demo "more impressive," write it into the roadmap line of the script instead of building it now.

## Acceptance criteria
- [ ] Full demo script runs end-to-end offline, timed at or under 3 minutes, rehearsed at least once
- [ ] Architecture slide references real file paths, not aspirational ones
- [ ] All five `hard_questions.md` answers are specific to this build, not generic AI-safety boilerplate
- [ ] The team has agreed on which section to cut first if running long
