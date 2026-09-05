"""
matching/run_matching.py

CLI entrypoint for the matching pipeline.

Loads:
  - All Scheme records from the database (or schemes_seed.json as fallback)
  - All CitizenProfile records from the database (or profiles_seed.json as fallback)

Runs matcher.match() for every (profile, scheme) cross-product,
filtered to schemes in included_categories per config/scope.json.

Writes MatchResult records to:
  - The SQLite database (match_result table) — upserted on (profile_id, scheme_id)
  - data/match_results.json — flat file fallback for demos without DB

Re-runnable: existing results for the same (profile_id, scheme_id) are overwritten.

Usage:
  python -m matching.run_matching              # with LLM
  python -m matching.run_matching --no-llm     # skip LLM for fast offline run
  python -m matching.run_matching --json-only  # write to JSON only, skip DB
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from matching.matcher import match

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parent.parent
DB_PATH       = ROOT / "data" / "yojana_sentinel.db"
SCHEMES_SEED  = ROOT / "data" / "schemes_seed.json"
PROFILES_SEED = ROOT / "data" / "profiles_seed.json"
RESULTS_JSON  = ROOT / "data" / "match_results.json"
SCOPE_PATH    = ROOT / "config" / "scope.json"


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_scope() -> dict:
    with open(SCOPE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_from_db() -> tuple[list[dict], list[dict]]:
    """Load schemes and profiles from SQLite. Returns (schemes, profiles)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    def _parse_json_fields(row: sqlite3.Row, json_fields: list[str]) -> dict:
        d = dict(row)
        for field in json_fields:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    d[field] = []
        return d

    scheme_json_fields = [
        "eligibility_rules", "required_documents", "application_fields"
    ]
    profile_json_fields = ["documents_available"]

    schemes_raw = conn.execute("SELECT * FROM scheme").fetchall()
    schemes = [_parse_json_fields(r, scheme_json_fields) for r in schemes_raw]

    profiles_raw = conn.execute("SELECT * FROM citizen_profile").fetchall()
    profiles = [_parse_json_fields(r, profile_json_fields) for r in profiles_raw]

    # Normalize owns_land: 0/1 → False/True
    for p in profiles:
        p["owns_land"] = bool(p.get("owns_land", 0))

    conn.close()
    log.info("Loaded %d schemes, %d profiles from DB.", len(schemes), len(profiles))
    return schemes, profiles


def load_from_json() -> tuple[list[dict], list[dict]]:
    """Load from seed JSON files (fallback when DB is unavailable)."""
    with open(SCHEMES_SEED, "r", encoding="utf-8") as f:
        schemes = json.load(f)
    with open(PROFILES_SEED, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    log.info("Loaded %d schemes, %d profiles from seed JSON.", len(schemes), len(profiles))
    return schemes, profiles


# ── DB upsert ─────────────────────────────────────────────────────────────────

def upsert_result(conn: sqlite3.Connection, result: dict) -> None:
    """Upsert a single MatchResult into the DB."""
    sql = """
        INSERT OR REPLACE INTO match_result (
            profile_id, scheme_id, match_score, match_status,
            missing_info, reasoning, evaluated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (
        result["profile_id"],
        result["scheme_id"],
        result["match_score"],
        result["match_status"],
        json.dumps(result["missing_info"], ensure_ascii=False),
        result["reasoning"],
        result["evaluated_at"],
    ))


# ── Main ──────────────────────────────────────────────────────────────────────

def run(use_llm: bool = True, json_only: bool = False) -> list[dict]:
    """
    Run the full matching pipeline.
    Returns the list of all MatchResult dicts produced.
    """
    scope = load_scope()
    included_cats = set(scope.get("included_categories", []))

    # Load data
    try:
        if not json_only and DB_PATH.exists():
            schemes, profiles = load_from_db()
        else:
            log.info("DB not found or json-only mode. Loading from seed JSON.")
            schemes, profiles = load_from_json()
    except Exception as exc:
        log.warning("DB load failed (%s). Falling back to seed JSON.", exc)
        schemes, profiles = load_from_json()

    # Filter schemes to included_categories only
    filtered_schemes = [s for s in schemes if s.get("category") in included_cats]
    log.info(
        "Matching %d profile(s) × %d scheme(s) in categories %s.",
        len(profiles), len(filtered_schemes), included_cats,
    )

    all_results: list[dict] = []

    # Open DB connection (if needed)
    conn: sqlite3.Connection | None = None
    if not json_only and DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys=ON")

    try:
        for profile in profiles:
            pid = profile.get("profile_id", "unknown")
            log.info("── Matching profile: %s (%s)", pid, profile.get("display_name", ""))

            for scheme in filtered_schemes:
                sid = scheme.get("scheme_id", "unknown")
                log.info(" → Scheme: %s", sid)

                result = match(profile, scheme, run_llm=use_llm)
                all_results.append(result)

                if conn is not None:
                    upsert_result(conn, result)

        if conn is not None:
            conn.commit()

    finally:
        if conn is not None:
            conn.close()

    # Write JSON output (always — useful for demo/dashboards)
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    log.info("Matching complete. %d results written.", len(all_results))
    return all_results


def _print_summary(results: list[dict]) -> None:
    from collections import Counter
    status_counts = Counter(r["match_status"] for r in results)
    print("\n📊 Matching Summary")
    print("─" * 40)
    for status, count in sorted(status_counts.items()):
        print(f"  {status:20s}: {count}")
    print(f"  {'TOTAL':20s}: {len(results)}")
    print(f"\n Results saved to: {RESULTS_JSON}")
    if DB_PATH.exists():
        print(f" Database updated:  {DB_PATH}")

    # Show strong matches
    strong = [r for r in results if r["match_status"] == "strong_match"]
    if strong:
        print("\n✅ Strong Matches:")
        for r in strong:
            print(f"  profile={r['profile_id']}  scheme={r['scheme_id']}  score={r['match_score']}")

    partial = [r for r in results if r["match_status"] == "partial_match"]
    if partial:
        print("\n⚠️  Partial Matches:")
        for r in partial:
            mi = r.get("missing_info", [])[:2]
            print(f"  profile={r['profile_id']}  scheme={r['scheme_id']}  score={r['match_score']}  missing={mi}")


if __name__ == "__main__":
    use_llm   = "--no-llm"    not in sys.argv
    json_only = "--json-only" in sys.argv

    if not use_llm:
        log.info("LLM disabled (--no-llm). other_conditions will not be reviewed.")

    results = run(use_llm=use_llm, json_only=json_only)
    _print_summary(results)
