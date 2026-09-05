# Internationalization (i18n) Roadmap & Implementation Notes

## Current State
- `CitizenProfile` schema includes `language_preference` (default: `"en"`, supports `"hi"`, `"bn"`, `"ta"`, `"te"`, etc.).
- The core rules engine and field mapper process data in English.
- The approval interface (`approval/app.py`) displays an informational badge when a citizen's profile specifies a non-English language preference (e.g., `hi`).

---

## Planned Regional Language Pipeline (Post-MVP Roadmap)

1. **Cover Note Translation (`drafting/draft_writer.py`)**
   - Prompt modification to generate cover notes directly in `language_preference` (e.g., Hindi for UP/Bihar citizens).
   - Dynamic prompt instruction: `Language: {profile.language_preference}`.

2. **UI Component Localization (`approval/app.py`)**
   - Gettext or JSON dictionary mapping for UI labels:
     - `Mark Ready to Submit` → `जमा करने के लिए तैयार चिह्नित करें`
     - `Reject` → `अस्वीकार करें`
     - `Edit Fields` → `विवरण संपादित करें`

3. **Plain-Language Match Rationale Translation**
   - Translate match status descriptions (`strong_match`, `partial_match`) into regional dialects to maximize accessibility for rural citizens.
