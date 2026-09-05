# Hard Questions & Honest Answers (Judge QA Guide)

### Q1: "How reliable is scraping at scale across all Indian states and schemes?"
> **Answer:** For the MVP, we built a functional scraper targeting `myscheme.gov.in` for Uttar Pradesh across Education, Agriculture, and Health, backed by hand-curated seed data for offline reliability. In a production build, relying solely on web scraping is fragile due to portal DOM changes. Production deployment would combine official API integrations (such as India Stack / MyScheme APIs), RSS/portal change feeds, and fallback web scraping with schema-validation guards.

---

### Q2: "How do you know the eligibility matching engine isn't hallucinating?"
> **Answer:** Eligibility evaluation is 100% deterministic for structured criteria. Age, state, caste category, family income, land ownership, gender, and occupation are calculated via pure predicate logic functions (`matching/rules_engine.py`) without LLM involvement. The LLM (Groq `llama-3.1-8b-instant`) is strictly restricted to reviewing ambiguous free-text conditions, and any failure defaults safely to `needs_review` rather than a silent pass.

---

### Q3: "What stops this agent from submitting incorrect applications on someone's behalf?"
> **Answer:** Non-negotiable architectural rule #1: **The agent NEVER submits anything automatically.** The system only produces pre-filled drafts (`ApplicationDraft`) and surfaces them to a family member via a human-in-the-loop dashboard. The approval action is explicitly labeled "Mark Ready to Submit," meaning the human must physically inspect, complete missing fields, and manually submit the form on the official portal.

---

### Q4: "Why would a family member trust a pre-filled government form from an AI?"
> **Answer:** Complete transparency and provenance. Every single field in the pre-filled form displays its source (`profile`, `inferred`, or `needs_input`). Fields inferred by the LLM are explicitly wrapped in `[DRAFT — please review: ...]` markers, and unresolved required fields are highlighted with prominent yellow warning banners before approval is permitted.

---

### Q5: "What is your real integration story with government status-tracking portals?"
> **Answer:** Most Indian government schemes currently lack public open REST APIs for real-time status tracking. Rather than creating a deceptive fake integration, Yojana Sentinel uses an honest manual confirmation model (`mark_submitted`) paired with automated staleness nudging (`staleness_checker.py`). When an application stays pending past 14 days, the agent alerts the family member to follow up.
