"""
tracking/staleness_checker.py

Finds applications in 'submitted' or 'pending' state that have not had a status update
in longer than threshold_days (configured in config/scope.json: status_stale_after_days).

Powers the "family member gets a nudge to follow up" story.

Excludes terminal states ('resolved', 'rejected') and 'drafted' / 'approved' states.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from db.database import get_db

log = logging.getLogger(__name__)

ROOT       = Path(__file__).resolve().parent.parent
DB_PATH    = ROOT / "data" / "yojana_sentinel.db"
SCOPE_PATH = ROOT / "config" / "scope.json"
LOG_PATH   = ROOT / "data" / "status_transition_log.json"


def _load_threshold_days() -> int:
    if SCOPE_PATH.exists():
        try:
            with open(SCOPE_PATH, "r", encoding="utf-8") as f:
                scope = json.load(f)
                return int(scope.get("status_stale_after_days", 14))
        except Exception:
            pass
    return 14


def _get_last_updated_map() -> dict[str, datetime]:
    """Map draft_id -> datetime of last status transition from transition log."""
    last_map = {}
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
                for entry in reversed(logs):
                    did = entry.get("draft_id")
                    ts_str = entry.get("timestamp")
                    if did and ts_str:
                        try:
                            last_map[did] = datetime.fromisoformat(ts_str)
                        except Exception:
                            pass
        except Exception:
            pass
    return last_map


def find_stale_drafts(threshold_days: int | None = None) -> list[dict]:
    """
    Returns list of render-ready nudge dicts for drafts in 'submitted' or 'pending'
    that have been inactive for more than threshold_days.
    """
    if threshold_days is None:
        threshold_days = _load_threshold_days()

    if not DB_PATH.exists():
        return []

    now = datetime.now(timezone.utc)
    last_updates = _get_last_updated_map()
    stale_items = []

    try:
        with get_db() as db:
            rows = db.fetchall(
                """SELECT d.draft_id, d.profile_id, d.scheme_id, d.status, d.created_at,
                          s.name as scheme_name, p.display_name as profile_name
                   FROM application_draft d
                   LEFT JOIN scheme s ON d.scheme_id = s.scheme_id
                   LEFT JOIN citizen_profile p ON d.profile_id = p.profile_id
                   WHERE d.status IN ('submitted', 'pending')"""
            )

        for r in rows:
            did = r["draft_id"]
            status = r["status"]
            created_at_str = r["created_at"]

            # Determine last activity time
            if did in last_updates:
                last_time = last_updates[did]
            else:
                try:
                    last_time = datetime.fromisoformat(created_at_str)
                except Exception:
                    last_time = now

            days_elapsed = (now - last_time).days

            if days_elapsed >= threshold_days:
                stale_items.append({
                    "draft_id": did,
                    "profile_id": r["profile_id"],
                    "profile_name": r["profile_name"] or r["profile_id"],
                    "scheme_id": r["scheme_id"],
                    "scheme_name": r["scheme_name"] or r["scheme_id"],
                    "status": status,
                    "days_inactive": days_elapsed,
                    "threshold_days": threshold_days,
                    "suggested_action": f"No status update for {days_elapsed} days. Consider calling local welfare department or checking portal.",
                })

    except Exception as exc:
        log.error("Failed to query stale drafts: %s", exc)

    log.info("StalenessCheck | checked submitted/pending drafts | found %d stale item(s)", len(stale_items))
    return stale_items
