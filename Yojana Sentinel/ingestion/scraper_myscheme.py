"""
ingestion/scraper_myscheme.py

Fetches scheme listings from the myscheme.gov.in public API.
Targets the search endpoint to get schemes for UP + national scope
within the configured categories.

Output: list of raw dicts saved to data/scraped_raw.json
Run: python -m ingestion.scraper_myscheme

Design principles:
- Handles unreachable / malformed source silently (log + skip, no crash)
- Idempotent: deduplicates by (name, issuing_body) before writing output
- Returns an empty list if the source is unavailable (offline-safe)
"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import requests

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RAW_OUTPUT = ROOT / "data" / "scraped_raw.json"

# ── Config ──────────────────────────────────────────────────────────────────
SCOPE_PATH = ROOT / "config" / "scope.json"

# myscheme.gov.in public search API (no auth required)
# Docs: https://www.myscheme.gov.in (public portal, uses REST-like endpoints)
BASE_URL = "https://api.myscheme.gov.in/search/v4/schemes"

CATEGORY_MAP = {
    "education": "Education & Learning",
    "agriculture": "Agriculture,Rural & Environment",
    "health": "Health & Wellness",
}

REQUEST_TIMEOUT = 15  # seconds
MAX_RESULTS_PER_CATEGORY = 20
RETRY_ATTEMPTS = 2
RETRY_DELAY = 3  # seconds between retries


def load_scope() -> dict:
    """Load scope.json to get target_state and included_categories."""
    with open(SCOPE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_schemes_for_category(
    category_label: str,
    state: str,
    page: int = 1,
    page_size: int = 20,
) -> Optional[list[dict]]:
    """
    Call the myscheme.gov.in API for a specific category and state.
    Returns a list of raw scheme dicts, or None if the request fails.
    """
    params = {
        "keyword": "",
        "schemeCategory": category_label,
        "state": state,
        "page": page,
        "limit": page_size,
        "lang": "en",
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "YojanaSentinel/1.0 (hackathon-demo; educational project)",
    }

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            log.info(
                "Fetching from myscheme API | category=%s state=%s attempt=%d",
                category_label,
                state,
                attempt,
            )
            resp = requests.get(
                BASE_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            # The API wraps results under different keys depending on version.
            # Try common locations gracefully.
            schemes = (
                data.get("data", {}).get("schemes")
                or data.get("schemes")
                or data.get("data")
                or []
            )
            if not isinstance(schemes, list):
                log.warning(
                    "Unexpected API response shape for category=%s. Got type=%s",
                    category_label,
                    type(schemes).__name__,
                )
                return []

            log.info(
                "Fetched %d raw scheme records for category=%s",
                len(schemes),
                category_label,
            )
            return schemes

        except requests.exceptions.ConnectionError:
            log.warning(
                "Connection error reaching myscheme API (attempt %d/%d). "
                "Will retry after %ds.",
                attempt,
                RETRY_ATTEMPTS,
                RETRY_DELAY,
            )
        except requests.exceptions.Timeout:
            log.warning(
                "Request timed out for category=%s (attempt %d/%d).",
                category_label,
                attempt,
                RETRY_ATTEMPTS,
            )
        except requests.exceptions.HTTPError as exc:
            log.warning("HTTP error for category=%s: %s", category_label, exc)
            return []  # Non-transient HTTP errors → no retry
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Malformed JSON from API for category=%s: %s", category_label, exc)
            return []

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY)

    log.error(
        "All %d attempts failed for category=%s. Returning empty list.",
        RETRY_ATTEMPTS,
        category_label,
    )
    return []


def extract_fields(raw: dict) -> dict:
    """
    Extract the minimal fields required by normalize.py from a raw API record.
    Uses liberal key-checking to handle API version drift.
    Returns None for fields that genuinely can't be extracted.
    """
    name = (
        raw.get("name")
        or raw.get("schemeName")
        or raw.get("title")
        or None
    )
    description = (
        raw.get("description")
        or raw.get("shortDescription")
        or raw.get("about")
        or None
    )
    # Deadline — many schemes won't have one; that's fine (null = rolling)
    deadline = (
        raw.get("deadline")
        or raw.get("lastDateToApply")
        or raw.get("closingDate")
        or None
    )
    source_url = (
        raw.get("sourceUrl")
        or raw.get("schemeUrl")
        or raw.get("url")
        or raw.get("officialWebsite")
        or "https://www.myscheme.gov.in"
    )
    issuing_body = (
        raw.get("issuedBy")
        or raw.get("ministry")
        or raw.get("department")
        or raw.get("nodal_ministry")
        or None
    )
    category = raw.get("schemeCategory") or raw.get("category") or None

    return {
        "_raw_id": raw.get("id") or raw.get("schemeId") or raw.get("slug") or None,
        "name": name,
        "issuing_body": issuing_body,
        "category_raw": category,
        "description": description,
        "deadline": deadline,
        "source_url": source_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def deduplicate(records: list[dict]) -> list[dict]:
    """
    Idempotency guard: ensure no two records share the same (_raw_id or name + issuing_body).
    If _raw_id is present, use it; otherwise fall back to name.
    Later records in the list are discarded in favour of earlier ones.
    """
    seen_ids: set = set()
    seen_names: set = set()
    unique = []
    for rec in records:
        raw_id = rec.get("_raw_id")
        name = (rec.get("name") or "").strip().lower()

        if raw_id and raw_id in seen_ids:
            log.debug("Duplicate _raw_id=%s — skipped.", raw_id)
            continue
        if name and name in seen_names:
            log.debug("Duplicate name='%s' — skipped.", name)
            continue

        if raw_id:
            seen_ids.add(raw_id)
        if name:
            seen_names.add(name)
        unique.append(rec)

    removed = len(records) - len(unique)
    if removed:
        log.info("Removed %d duplicate raw records.", removed)
    return unique


def run() -> list[dict]:
    """
    Main entry point. Returns the list of extracted raw scheme dicts.
    Safe to call repeatedly (idempotent output).
    """
    scope = load_scope()
    state = scope.get("target_state", "Uttar Pradesh")
    categories = scope.get("included_categories", [])

    all_raw: list[dict] = []

    for cat_key in categories:
        cat_label = CATEGORY_MAP.get(cat_key)
        if not cat_label:
            log.warning("No API category label mapping for '%s' — skipping.", cat_key)
            continue

        raw_records = fetch_schemes_for_category(
            category_label=cat_label,
            state=state,
            page_size=MAX_RESULTS_PER_CATEGORY,
        )
        if not raw_records:
            log.info(
                "No records returned for category=%s — source may be unavailable.",
                cat_key,
            )
            continue

        for raw in raw_records:
            extracted = extract_fields(raw)
            extracted["_source_category"] = cat_key  # preserve our category key
            all_raw.append(extracted)

    all_raw = deduplicate(all_raw)

    # Persist raw output so normalize.py can consume it
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_raw, f, ensure_ascii=False, indent=2)

    log.info(
        "Scrape complete. %d unique raw records written to %s",
        len(all_raw),
        RAW_OUTPUT,
    )
    return all_raw


if __name__ == "__main__":
    results = run()
    if results:
        print(f"\n✅ Scraped {len(results)} unique raw scheme records.")
        print(f"   Saved to: {RAW_OUTPUT}")
    else:
        print(
            "\n⚠️  Scraper returned 0 records. "
            "Source may be unreachable. Demo will use schemes_seed.json."
        )
