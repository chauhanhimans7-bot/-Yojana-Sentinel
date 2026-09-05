# docs/known_duplicates.md

## Known Duplicate Scheme Risk — Yojana Sentinel MVP

### The Problem

The demo data pipeline has two sources for `Scheme` records:
1. **`data/schemes_seed.json`** — hand-curated, authoritative for the demo.
2. **`data/scraped_normalized.json`** — produced by `ingestion/scraper_myscheme.py`.

It is possible (and in practice likely) that the same real government scheme
appears in **both** sources with different `scheme_id` slugs. For example:

| Source | scheme_id generated | Real scheme |
|---|---|---|
| Seed (hand-curated) | `up-scholarship-obc-2026` | UP OBC Scholarship |
| Scraper (myscheme API) | `up-obc-scholarship-2026-uttar-pradesh-social-welfare` | UP OBC Scholarship |

These would be treated as **two distinct schemes** by the DB, causing:
- Duplicate MatchResults for the same citizen
- Double-counting in the approval UI
- Confusing demo output ("you matched 6 schemes" when only 3 are unique)

---

### Current MVP Decision

For the MVP / hackathon demo:

> **`schemes_seed.json` is the authoritative source. Scraped data is supplementary and used only for "new scheme discovery" — it is NOT merged with existing seed records.**

`db/seed.py` uses `INSERT OR REPLACE` keyed on `scheme_id`. As long as the
seed file's `scheme_id` values are the canonical ones, a separately scraped
record with a different slug will simply add a new row — not overwrite the
seed record. The demo runs entirely from the seed, so this creates no visible
duplication in the demo flow.

---

### How to Deduplicate in a Production Version

1. **Content Fingerprinting:** Generate a canonical fingerprint for each scheme
   as `sha256(normalize(name) + normalize(issuing_body))`. On ingestion, check
   if a record with the same fingerprint already exists regardless of `scheme_id`.
   If yes, update `last_verified_at` on the existing record rather than inserting a new row.

2. **Exact Name + Issuing Body Match:** Prior to insert, query:
   ```sql
   SELECT scheme_id FROM scheme
   WHERE lower(trim(name)) = lower(trim(?))
     AND lower(trim(issuing_body)) = lower(trim(?))
   ```
   If a match is found, treat the incoming record as an update, not a new insert.

3. **Source URL Deduplication:** Many duplicate scheme entries share the same
   `source_url`. An index on `source_url` + a pre-insert check can catch these.

4. **LLM-Assisted Deduplication (future):** For near-duplicate names (e.g.
   "PM Kisan" vs. "Pradhan Mantri Kisan Samman Nidhi"), a lightweight embedding
   similarity check (cosine similarity > 0.92) can flag potential duplicates
   for human review before committing to the DB.

---

### Fallback Guarantee at Demo Time

`schemes_seed.json` alone is **sufficient for the full demo with zero network
dependency**. The scraper is optional / additive. If the live source is
unreachable at demo time, `db/seed.py` (without `--include-scraped`) loads
only the seed and the entire demo runs offline. This is the documented default.
