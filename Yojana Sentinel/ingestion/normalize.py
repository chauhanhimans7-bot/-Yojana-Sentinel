"""
ingestion/normalize.py

Converts raw records produced by scraper_myscheme.py into the exact `Scheme`
schema defined in 00_master_context.md.

Rules:
  - `last_verified_at` is always set to NOW (UTC) on each run.
  - `status` is derived from `deadline`:
      deadline is null             → "active"   (rolling / no deadline)
      deadline is in the future   → "active"
      deadline is in the past     → "closed"
  - Any field the scraper could NOT extract must be `null` — never an empty
    string — because all downstream phases check for `null` explicitly.
  - Empty string → null conversion is applied to every string field.

Run: python -m ingestion.normalize
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Optional

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RAW_INPUT = ROOT / "data" / "scraped_raw.json"
NORMALIZED_OUTPUT = ROOT / "data" / "scraped_normalized.json"

# ── Category mapping from API label back to schema enum ──────────────────────
CATEGORY_LABEL_TO_ENUM = {
    "education & learning": "education",
    "agriculture,rural & environment": "agriculture",
    "agriculture, rural & environment": "agriculture",
    "health & wellness": "health",
    "housing & shelter": "housing",
    "employment": "employment",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _empty_to_null(val: Any) -> Optional[str]:
    """Convert empty strings to None so downstream sees null, not ''."""
    if isinstance(val, str):
        val = val.strip()
        return val if val else None
    return val


def _parse_date(raw: Optional[str]) -> Optional[str]:
    """
    Try to parse a date string into ISO 'YYYY-MM-DD' format.
    Returns None if unparseable (rather than crashing).
    Handles common formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD Month YYYY.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # DD-MM-YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", raw)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass

    # Try datetime parsing for fuller strings
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue

    log.warning("Could not parse date string '%s' — setting to null.", raw)
    return None


def _derive_status(deadline: Optional[str]) -> str:
    """
    Derive Scheme status from deadline:
     - null  → "active"  (rolling / no deadline)
     - future → "active"
     - past  → "closed"
    """
    if deadline is None:
        return "active"
    today = date.today()
    try:
        dl = date.fromisoformat(deadline)
        return "active" if dl >= today else "closed"
    except ValueError:
        log.warning("Invalid deadline date '%s' for status derivation — defaulting to active.", deadline)
        return "active"


def _make_slug(name: Optional[str], issuing_body: Optional[str]) -> str:
    """Generate a stable slug for scheme_id from name + body."""
    parts = []
    for s in [name, issuing_body]:
        if s:
            parts.append(re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-"))
    slug = "-".join(parts)[:80] if parts else str(uuid.uuid4())
    return slug


def _map_category(raw_category: Optional[str], source_category_key: Optional[str]) -> str:
    """Resolve the Scheme.category enum from raw API label or our internal key."""
    if source_category_key and source_category_key in (
        "education", "agriculture", "health", "housing", "employment"
    ):
        return source_category_key

    if raw_category:
        mapped = CATEGORY_LABEL_TO_ENUM.get(raw_category.lower().strip())
        if mapped:
            return mapped

    return "other"


def normalize_record(raw: dict) -> dict:
    """
    Convert a single raw scraper record into a schema-valid Scheme dict.
    Null-safe: every field that can't be determined is explicitly null.
    """
    now_utc = datetime.now(timezone.utc).isoformat()

    name = _empty_to_null(raw.get("name"))
    issuing_body = _empty_to_null(raw.get("issuing_body"))
    raw_category = _empty_to_null(raw.get("category_raw"))
    source_category_key = _empty_to_null(raw.get("_source_category"))
    description_raw = _empty_to_null(raw.get("description"))
    deadline_raw = _parse_date(_empty_to_null(raw.get("deadline")))
    source_url = _empty_to_null(raw.get("source_url")) or "https://www.myscheme.gov.in"

    # Truncate description to ~400 chars as per schema note
    description = description_raw[:400] if description_raw else None

    category = _map_category(raw_category, source_category_key)
    status = _derive_status(deadline_raw)

    scheme_id = _empty_to_null(raw.get("_raw_id")) or _make_slug(name, issuing_body)

    return {
        "scheme_id": scheme_id,
        "name": name,
        "issuing_body": issuing_body,
        "category": category,
        "description": description,
        "eligibility_rules": {
            # Scraper cannot reliably extract structured rules from API summary.
            # All rules defaulted to null / empty arrays here; manual curation
            # or a future LLM extraction step (Phase 5) fills these in.
            "min_age": None,
            "max_age": None,
            "states": [],
            "max_annual_income": None,
            "categories": [],
            "occupation": [],
            "gender": "any",
            "land_ownership_required": None,
            "other_conditions": [
                "See source URL for full eligibility details — rules not yet extracted by scraper."
            ],
        },
        "required_documents": [],  # Not available from API summary
        "application_fields": [],  # Not available from API summary
        "deadline": deadline_raw,
        "source_url": source_url,
        "last_verified_at": now_utc,
        "status": status,
    }


def run(raw_path: Path = RAW_INPUT, output_path: Path = NORMALIZED_OUTPUT) -> list[dict]:
    """
    Read raw scraper output, normalize each record, and write results.
    Returns the list of normalized Scheme dicts.
    """
    if not raw_path.exists():
        log.error(
            "Raw input file not found: %s\n"
            "Run ingestion/scraper_myscheme.py first, or use schemes_seed.json directly.",
            raw_path,
        )
        return []

    with open(raw_path, "r", encoding="utf-8") as f:
        try:
            raw_records: list[dict] = json.load(f)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse raw input JSON: %s", exc)
            return []

    log.info("Normalizing %d raw records from %s", len(raw_records), raw_path)

    normalized = []
    skipped = 0
    for i, raw in enumerate(raw_records):
        # Skip records with no name — they're not usable
        if not raw.get("name"):
            log.warning("Record %d has no name — skipped.", i)
            skipped += 1
            continue
        scheme = normalize_record(raw)
        normalized.append(scheme)

    log.info(
        "Normalization complete: %d valid records, %d skipped.",
        len(normalized),
        skipped,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    log.info("Normalized output written to %s", output_path)
    return normalized


# ── Status derivation demo & self-test ───────────────────────────────────────

def _self_test() -> None:
    """Validate the three status derivation cases as required by acceptance criteria."""
    past_date = "2020-01-01"
    future_date = "2099-12-31"
    null_date = None

    assert _derive_status(null_date) == "active",   "null deadline must → active"
    assert _derive_status(future_date) == "active",  "future deadline must → active"
    assert _derive_status(past_date) == "closed",    "past deadline must → closed"

    log.info("Self-test PASSED: status derivation correct for all 3 deadline cases.")


if __name__ == "__main__":
    _self_test()
    results = run()
    if results:
        print(f"\n✅ Normalized {len(results)} scheme records.")
        print(f"   Output: {NORMALIZED_OUTPUT}")
    else:
        print(
            "\n⚠️  No records normalized. "
            "Run the scraper first, or check data/scraped_raw.json."
        )
