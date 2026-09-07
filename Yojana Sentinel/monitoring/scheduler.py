"""
monitoring/scheduler.py

Interval-based monitoring loop for Yojana Sentinel.

On each tick:
  1. Re-runs ingestion (scraper + normalize) OR reads seed data in offline/demo mode.
  2. Compares new vs previous scheme snapshot via diff.py → emits MonitoringEvents.
  3. For each new_scheme or deadline_approaching event, re-runs the matcher against
     all stored profiles for that scheme and saves fresh MatchResults.

Design decisions:
  - Single-threaded, tick-skipping model: if a previous tick is still running
    (detected via a lock file), the new tick is SKIPPED and logged, not queued.
    Rationale: Government scheme data changes slowly; missing one 30-min tick is
    harmless. Queuing risks memory growth and hides scraper hanging.
  - Offline/demo mode flag: controlled by config/scope.json "demo_mode": true,
    or the --demo CLI flag. In demo mode, reads schemes_seed.json rather than
    calling the live scraper. This ensures the demo runs without network dependency.

Usage:
  python -m monitoring.scheduler           # live mode
  python -m monitoring.scheduler --demo    # offline/seed mode
  python -m monitoring.scheduler --once    # run one tick and exit (for testing)
"""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from monitoring.diff import compute_diff
from monitoring.event_log import all_events, append

log = logging.getLogger(__name__)

ROOT          = Path(__file__).resolve().parent.parent
SCOPE_PATH    = ROOT / "config" / "scope.json"
DB_PATH       = ROOT / "data" / "yojana_sentinel.db"
SCHEMES_SEED  = ROOT / "data" / "schemes_seed.json"
PROFILES_SEED = ROOT / "data" / "profiles_seed.json"
LOCK_FILE     = ROOT / "data" / ".scheduler_lock"
SNAPSHOT_PATH = ROOT / "data" / "scheme_snapshot.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Config ─────────────────────────────────────────────────────────────────────

def load_scope() -> dict:
    with open(SCOPE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Lock helpers (tick-skipping overlap prevention) ────────────────────────────

def _acquire_lock() -> bool:
    """Return True if lock was acquired; False if another tick is running."""
    if LOCK_FILE.exists():
        log.warning(
            "Scheduler lock exists — previous tick still running or crashed. "
            "Skipping this tick. If this is a crash remnant, delete: %s",
            LOCK_FILE,
        )
        return False
    LOCK_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return True


def _release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception as exc:
        log.warning("Could not remove scheduler lock: %s", exc)


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_current_schemes(demo_mode: bool) -> list[dict]:
    """
    Returns the current list of Scheme dicts.
    In demo/offline mode: reads schemes_seed.json.
    In live mode: runs the scraper + normalizer pipeline.
    """
    if demo_mode:
        log.info("Demo mode — loading schemes from seed file.")
        with open(SCHEMES_SEED, "r", encoding="utf-8") as f:
            return json.load(f)

    # Live mode: run ingestion pipeline
    try:
        from ingestion.scraper_myscheme import run as scrape
        from ingestion.normalize import run as normalize
        raw_path = ROOT / "data" / "scraped_raw.json"
        normalized_path = ROOT / "data" / "scraped_normalized.json"

        log.info("Live mode — running scraper...")
        scraped = scrape()

        if not scraped:
            log.warning("Scraper returned 0 records. Falling back to seed data.")
            with open(SCHEMES_SEED, "r", encoding="utf-8") as f:
                return json.load(f)

        log.info("Running normalizer on %d raw records...", len(scraped))
        normalized = normalize(raw_path=raw_path, output_path=normalized_path)
        return normalized if normalized else _load_seed_schemes()

    except Exception as exc:
        log.error("Ingestion pipeline failed: %s — falling back to seed data.", exc)
        return _load_seed_schemes()


def _load_seed_schemes() -> list[dict]:
    with open(SCHEMES_SEED, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_previous_snapshot() -> list[dict]:
    """Load last tick's scheme list from snapshot file."""
    if not SNAPSHOT_PATH.exists():
        log.info("No previous snapshot found — first run. All schemes will be 'new'.")
        return []
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not load snapshot: %s. Treating as first run.", exc)
        return []


def _save_snapshot(schemes: list[dict]) -> None:
    """Persist current scheme list as snapshot for next tick's diff."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(schemes, f, ensure_ascii=False, indent=2)
    log.debug("Snapshot saved: %d schemes.", len(schemes))


# ── Profile loading ────────────────────────────────────────────────────────────

def _load_profiles() -> list[dict]:
    """Load all CitizenProfile records from DB or seed JSON."""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM citizen_profile").fetchall()
            conn.close()
            profiles = []
            for row in rows:
                p = dict(row)
                if isinstance(p.get("documents_available"), str):
                    try:
                        p["documents_available"] = json.loads(p["documents_available"])
                    except Exception:
                        p["documents_available"] = []
                p["owns_land"] = bool(p.get("owns_land", 0))
                profiles.append(p)
            log.info("Loaded %d profile(s) from DB.", len(profiles))
            return profiles
        except Exception as exc:
            log.warning("DB profile load failed: %s — using seed JSON.", exc)

    with open(PROFILES_SEED, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    log.info("Loaded %d profile(s) from seed JSON.", len(profiles))
    return profiles


# ── Trigger matcher for a specific scheme ─────────────────────────────────────

def trigger_matching_for_scheme(scheme_id: str, schemes: list[dict]) -> None:
    """
    Run matcher.match() for all profiles against a specific scheme.
    Called after new_scheme or deadline_approaching events.
    """
    from matching.matcher import match as do_match

    target = next((s for s in schemes if s.get("scheme_id") == scheme_id), None)
    if not target:
        log.error(
            "trigger_matching_for_scheme: scheme_id='%s' not found in current snapshot. "
            "Ensure the scheme exists in schemes_seed.json or the DB.",
            scheme_id,
        )
        return

    profiles = _load_profiles()
    if not profiles:
        log.warning("No profiles found. Skipping matching for scheme '%s'.", scheme_id)
        return

    scope = load_scope()
    included_cats = set(scope.get("included_categories", []))
    if target.get("category") not in included_cats:
        log.info(
            "Scheme '%s' category '%s' not in included_categories — skipping trigger match.",
            scheme_id,
            target.get("category"),
        )
        return

    log.info("Trigger matching: scheme='%s' against %d profile(s).", scheme_id, len(profiles))

    results = []
    for profile in profiles:
        result = do_match(profile, target, run_llm=True)
        results.append(result)
        log.info(
            "  → profile=%s status=%s score=%.0f",
            profile.get("profile_id"), result["match_status"], result["match_score"],
        )

    # Upsert results to DB
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA foreign_keys=ON")
            for res in results:
                conn.execute(
                    """INSERT OR REPLACE INTO match_result
                       (profile_id, scheme_id, match_score, match_status,
                        missing_info, reasoning, evaluated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        res["profile_id"], res["scheme_id"], res["match_score"],
                        res["match_status"],
                        json.dumps(res["missing_info"], ensure_ascii=False),
                        res["reasoning"], res["evaluated_at"],
                    ),
                )
            conn.commit()
            conn.close()
            log.info("Match results for scheme '%s' saved to DB.", scheme_id)
        except Exception as exc:
            log.error("Failed to save match results to DB: %s", exc)


# ── Single tick ────────────────────────────────────────────────────────────────

def run_tick(demo_mode: bool = False) -> list[dict]:
    """
    Execute one monitoring tick.
    Returns list of MonitoringEvent dicts emitted this tick.
    """
    log.info("═" * 60)
    log.info("Scheduler tick started | demo_mode=%s", demo_mode)
    log.info("═" * 60)

    previous = _load_previous_snapshot()
    current  = _load_current_schemes(demo_mode)

    if not current:
        log.warning("No current scheme data available. Tick aborted — snapshot unchanged.")
        return []

    # Run diff
    events = compute_diff(previous, current)
    log.info("Tick diff complete: %d event(s) emitted.", len(events))

    # Save snapshot for next tick
    _save_snapshot(current)

    # Trigger matcher for actionable events
    trigger_event_types = {"new_scheme", "deadline_approaching"}
    triggered_schemes = set()

    for evt in events:
        if evt.get("event_type") in trigger_event_types:
            sid = evt.get("scheme_id", "")
            if sid and sid not in triggered_schemes:
                log.info(
                    "Event '%s' for scheme '%s' → triggering matcher.",
                    evt["event_type"], sid,
                )
                trigger_matching_for_scheme(sid, current)
                triggered_schemes.add(sid)

    log.info("Tick complete. %d event(s), %d scheme(s) re-matched.", len(events), len(triggered_schemes))
    return events


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_loop(demo_mode: bool = False, run_once: bool = False) -> None:
    """
    Run the scheduler in a continuous interval loop.
    Set run_once=True to execute exactly one tick and exit.
    """
    scope = load_scope()
    interval_minutes = int(scope.get("monitoring_interval_minutes", 30))
    interval_seconds = interval_minutes * 60

    log.info("Yojana Sentinel Scheduler starting.")
    log.info("  Interval     : %d minutes", interval_minutes)
    log.info("  Demo mode    : %s", demo_mode)
    log.info("  Run once     : %s", run_once)
    log.info("  DB path      : %s", DB_PATH)

    while True:
        if not _acquire_lock():
            log.warning("Tick skipped (lock held). Sleeping for %d minutes...", interval_minutes)
            if run_once:
                break
            time.sleep(interval_seconds)
            continue

        try:
            run_tick(demo_mode=demo_mode)
        except Exception as exc:
            log.error("Unhandled error during scheduler tick: %s", exc, exc_info=True)
        finally:
            _release_lock()

        if run_once:
            log.info("--once flag set. Exiting after single tick.")
            break

        log.info("Next tick in %d minute(s). Press Ctrl+C to stop.", interval_minutes)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    demo_mode = "--demo" in sys.argv
    run_once  = "--once" in sys.argv
    run_loop(demo_mode=demo_mode, run_once=run_once)
