"""
db/seed.py — Unified Database Seeder

Loads data/schemes_seed.json and data/profiles_seed.json into the target DB
(Supabase PostgreSQL or local SQLite) using ANSI-compliant ON CONFLICT queries.

Run:
    python -m db.seed
or:
    python -m db.seed --include-scraped   (also loads scraped_normalized.json)
"""

import json
import logging
import sys
from pathlib import Path

from db.database import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT          = Path(__file__).resolve().parent.parent
SCHEMA_PATH   = ROOT / "db" / "schema.sql"
SCHEMES_SEED  = ROOT / "data" / "schemes_seed.json"
PROFILES_SEED = ROOT / "data" / "profiles_seed.json"
SCRAPED_NORM  = ROOT / "data" / "scraped_normalized.json"


def _json(val) -> str:
    """Serialize a value to JSON string for TEXT columns."""
    return json.dumps(val, ensure_ascii=False)


def upsert_schemes(db, schemes: list[dict]) -> int:
    """
    Insert or update scheme records using ANSI ON CONFLICT.
    """
    sql = """
        INSERT INTO scheme (
            scheme_id, name, issuing_body, category, description,
            eligibility_rules, required_documents, application_fields,
            deadline, source_url, last_verified_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (scheme_id) DO UPDATE SET
            name = EXCLUDED.name,
            issuing_body = EXCLUDED.issuing_body,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            eligibility_rules = EXCLUDED.eligibility_rules,
            required_documents = EXCLUDED.required_documents,
            application_fields = EXCLUDED.application_fields,
            deadline = EXCLUDED.deadline,
            source_url = EXCLUDED.source_url,
            last_verified_at = EXCLUDED.last_verified_at,
            status = EXCLUDED.status
    """
    count = 0
    skipped = 0
    for s in schemes:
        scheme_id = s.get("scheme_id")
        name      = s.get("name")

        if not scheme_id or not name:
            skipped += 1
            continue

        try:
            db.execute(sql, (
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
        except Exception as exc:
            log.warning("Error inserting scheme '%s': %s", scheme_id, exc)
            skipped += 1

    log.info("Schemes: %d upserted, %d skipped.", count, skipped)
    return count


def upsert_profiles(db, profiles: list[dict]) -> int:
    """
    Insert or update CitizenProfile records using ANSI ON CONFLICT.
    """
    sql = """
        INSERT INTO citizen_profile (
            profile_id, display_name, age, gender, state, district,
            annual_income, category, occupation, owns_land, family_status,
            documents_available, language_preference, managed_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (profile_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            age = EXCLUDED.age,
            gender = EXCLUDED.gender,
            state = EXCLUDED.state,
            district = EXCLUDED.district,
            annual_income = EXCLUDED.annual_income,
            category = EXCLUDED.category,
            occupation = EXCLUDED.occupation,
            owns_land = EXCLUDED.owns_land,
            family_status = EXCLUDED.family_status,
            documents_available = EXCLUDED.documents_available,
            language_preference = EXCLUDED.language_preference,
            managed_by = EXCLUDED.managed_by
    """
    count = 0
    skipped = 0
    for p in profiles:
        pid = p.get("profile_id")
        if not pid:
            skipped += 1
            continue

        try:
            db.execute(sql, (
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
        except Exception as exc:
            log.warning("Error inserting profile '%s': %s", pid, exc)
            skipped += 1

    log.info("Profiles: %d upserted, %d skipped.", count, skipped)
    return count


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def run(include_scraped: bool = False) -> None:
    with get_db() as db:
        # Initialize schema if local SQLite
        if not db.is_postgres and SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                db.conn.executescript(f.read())

        seed_schemes = load_json(SCHEMES_SEED)
        n_seed = upsert_schemes(db, seed_schemes)

        n_scraped = 0
        if include_scraped:
            scraped = load_json(SCRAPED_NORM)
            if scraped:
                n_scraped = upsert_schemes(db, scraped)

        profiles = load_json(PROFILES_SEED)
        n_profiles = upsert_profiles(db, profiles)

        db.commit()

    print("\n✅  Seed complete.")
    print(f"   Schemes from seed:    {n_seed}")
    if include_scraped:
        print(f"   Schemes from scraper: {n_scraped}")
    print(f"   Citizen profiles:     {n_profiles}")


if __name__ == "__main__":
    include_scraped = "--include-scraped" in sys.argv
    run(include_scraped=include_scraped)
