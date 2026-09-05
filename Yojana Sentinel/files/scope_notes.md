# Scope Notes — Yojana Sentinel MVP

## Justifications for `config/scope.json` values

| Field | Value | Justification |
|---|---|---|
| `target_state` | `Uttar Pradesh` | UP has the largest rural population in India and a rich ecosystem of both national + state welfare schemes. Many national schemes have UP-specific portals (e.g., UP Scholarship), making it ideal for a demo that feels real and relatable. |
| `included_categories` | `education, agriculture, health` | Education (scholarship) rules are the most cleanly structured with defined age/income/caste cutoffs. Agriculture (PM-KISAN, Kisan Credit Card) is simple and rule-based. Health/maternity (PMMVY) is a high-impact, time-bound scheme — together the three exercise all major schema fields. |
| `strong_match_threshold` | `80` | A score of 80+ signals all mandatory eligibility predicates pass (age, income, state, category). Below this, at least one hard constraint is uncertain or failed. This gives confident language in draft text. |
| `partial_match_threshold` | `50` | Scores 50–79 indicate most predicates pass but one or more optional/soft conditions are unverified. The citizen should still be shown the scheme with a "check required" flag. Scores below 50 indicate unlikely eligibility and are suppressed from the UI to avoid noise. |
| `deadline_approaching_window_days` | `14` | A 14-day window gives the citizen's operator enough time to gather documents, get income certificates, and complete the draft approval cycle — realistic for rural contexts with limited daily internet access. |
| `demo_channel` | `web_dashboard` | A web dashboard is easier to demo on stage than a WhatsApp mock (no phone dependency, works on any screen, scrollable history). WhatsApp channel remains a future enhancement. |

---

## Edge Case Answers

### Edge Case 1: Citizen matches a scheme NOT in `included_categories`
**Answer:** Out of scope for MVP. The matcher will evaluate schemes only from the categories listed in `config/scope.json → included_categories`. Any scheme with a category not in that list will be silently skipped during matching. The skip event should be logged at DEBUG level (e.g., `"Skipping scheme {scheme_id}: category '{category}' not in included_categories"`) so the behaviour is auditable. This will be surfaced as a "coming soon" capability note at Phase 8 demo time.

### Edge Case 2: `strong_match_threshold` and `partial_match_threshold` are inconsistent
**Answer:** A startup validation check must be added (in `matching/matcher.py` or a dedicated `config_validator.py`) that asserts:
```python
assert config["partial_match_threshold"] < config["strong_match_threshold"], \
    "Config error: partial_match_threshold must be strictly less than strong_match_threshold"
```
If this check fails, the application must raise a `ValueError` and refuse to start. This prevents silent mis-classification of MatchResults.

### Edge Case 3: Target state changes at demo time
**Answer:** `target_state` is a config value in `config/scope.json`, not a hardcoded string inside any matching or ingestion logic. All modules must read state from the config at runtime. This means the honest answer on stage is: *"Yes, the system can be pointed at any state — you change one line in the config and re-run the ingestion. Today we're scoped to UP for the demo."* This must be a stated design principle during Phase 2 when the scraper and seed data are built — no state name must be hardcoded inside business logic.

---

## Notes on Persona Design

- **Ramkali Devi (profile-001):** Designed as a strong-match candidate for the UP Scholarship scheme (daughter is 16, in school, family is OBC with income well below the scholarship threshold). Also likely a match for PM-KISAN (owns land, farmer). All documents present.
- **Suresh Kumar (profile-002):** Designed as a partial-match / missing-info candidate for the PM Matru Vandana Yojana (PMMVY) — a maternity health benefit. He is eligible on income and category, but is missing an income certificate and his wife lacks a personal bank account — both required fields. This exercises the `missing_info` and `unresolved_fields` paths in the matching and drafting pipeline.
