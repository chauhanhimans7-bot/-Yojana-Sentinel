"""
db/seed.py

Loads data/schemes_seed.json (and optionally data/scraped_normalized.json)
into the SQLite database.

Rules:
  - Upserts on scheme_id (INSERT OR REPLACE) — safe to re-run multiple times.
  - Nested fields (eligibility_rules, required_documents, etc.) are serialized
    to JSON strings for storage in TEXT columns.
  - Handles missing or malformed records with a warning rather than crashing.
  - Also seeds CitizenProfile records from data/profiles_seed.json.

Run:
    python -m db.seed
or:
    python -m db.seed --include-scraped   (also loads scraped_normalized.json)
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parent.parent
DB_PATH      = ROOT / "data" / "yojana_sentinel.db"
SCHEMA_PATH  = ROOT / "db" / "schema.sql"
SCHEMES_SEED = ROOT / "data" / "schemes_seed.json"
PROFILES_SEED = ROOT / "data" / "profiles_seed.json"
SCRAPED_NORM = ROOT / "data" / "scraped_normalized.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json(val) -> str:
    """Serialize a value to JSON string for SQLite TEXT column."""
    return json.dumps(val, ensure_ascii=False)


def connect() -> sqlite3.Connection:
    """Open (or create) the SQLite DB and apply the schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    log.info("Database ready: %s", DB_PATH)
    return conn


def upsert_schemes(conn: sqlite3.Connection, schemes: list[dict]) -> int:
    """
    Insert or replace scheme records. Returns the number of rows upserted.
    Skips records with missing scheme_id or name.
    """
    sql = """
        INSERT OR REPLACE INTO scheme (
            scheme_id, name, issuing_body, category, description,
            eligibility_rules, required_documents, application_fields,
            deadline, source_url, last_verified_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    skipped = 0
    for s in schemes:
        scheme_id = s.get("scheme_id")
        name      = s.get("name")

        if not scheme_id:
            log.warning("Scheme missing scheme_id — skipped: %s", name or "<no name>")
            skipped += 1
            continue
        if not name:
            log.warning("Scheme '%s' missing name — skipped.", scheme_id)
            skipped += 1
            continue

        try:
            conn.execute(sql, (
                scheme_id,
                name,
                s.get("issuing_body"),
                s.get("category", "other"),
                s.get("description"),
                _json(s.get("eligibility_rules", {})),
                _json(s.get("required_documents", [])),
                _json(s.get("application_fields", [])),
                s.get("deadline"),
                s.get("source_url", ""),
                s.get("last_verified_at", ""),
                s.get("status", "active"),
            ))
            count += 1
        except sqlite3.IntegrityError as exc:
            log.warning("IntegrityError inserting scheme '%s': %s", scheme_id, exc)
            skipped += 1

    conn.commit()
    log.info("Schemes: %d upserted, %d skipped.", count, skipped)
    return count


def upsert_profiles(conn: sqlite3.Connection, profiles: list[dict]) -> int:
    """
    Insert or replace CitizenProfile records.
    Skips internal fields prefixed with '_' (like _backstory).
    """
    sql = """
        INSERT OR REPLACE INTO citizen_profile (
            profile_id, display_name, age, gender, state, district,
            annual_income, category, occupation, owns_land, family_status,
            documents_available, language_preference, managed_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    skipped = 0
    for p in profiles:
        pid = p.get("profile_id")
        if not pid:
            log.warning("Profile missing profile_id — skipped.")
            skipped += 1
            continue

        try:
            conn.execute(sql, (
                pid,
                p.get("display_name", ""),
                p.get("age"),
                p.get("gender", "other"),
                p.get("state", ""),
                p.get("district"),
                p.get("annual_income"),
                p.get("category", "general"),
                p.get("occupation", ""),
                1 if p.get("owns_land") else 0,
                p.get("family_status"),
                _json(p.get("documents_available", [])),
                p.get("language_preference", "en"),
                p.get("managed_by"),
            ))
            count += 1
        except sqlite3.IntegrityError as exc:
            log.warning("IntegrityError inserting profile '%s': %s", pid, exc)
            skipped += 1

    conn.commit()
    log.info("Profiles: %d upserted, %d skipped.", count, skipped)
    return count


def load_json(path: Path) -> list[dict]:
    """Load a JSON array from a file. Returns [] and logs if unavailable."""
    if not path.exists():
        log.warning("File not found, skipping: %s", path)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            log.error("Expected a JSON array in %s — got %s.", path, type(data).__name__)
            return []
        return data
    except json.JSONDecodeError as exc:
        log.error("Failed to parse %s: %s", path, exc)
        return []


def run(include_scraped: bool = False) -> None:
    conn = connect()

    # ── Seed schemes ──────────────────────────────────────────────────────────
    seed_schemes = load_json(SCHEMES_SEED)
    if not seed_schemes:
        log.error("No seed schemes found. Aborting seed.")
        conn.close()
        return
    n_seed = upsert_schemes(conn, seed_schemes)

    # ── Optionally include scraped data ───────────────────────────────────────
    n_scraped = 0
    if include_scraped:
        scraped = load_json(SCRAPED_NORM)
        if scraped:
            n_scraped = upsert_schemes(conn, scraped)
        else:
            log.info("No scraped normalized data found — skipping.")

    # ── Seed profiles ──────────────────────────────────────────────────────────
    profiles = load_json(PROFILES_SEED)
    n_profiles = upsert_profiles(conn, profiles)

    conn.close()

    print("\n✅  Seed complete.")
    print(f"   Schemes from seed:    {n_seed}")
    if include_scraped:
        print(f"   Schemes from scraper: {n_scraped}")
    print(f"   Citizen profiles:     {n_profiles}")
    print(f"   Database:             {DB_PATH}")


if __name__ == "__main__":
    include_scraped = "--include-scraped" in sys.argv
    run(include_scraped=include_scraped)
