"""
monitoring/event_log.py

Append-only log of every MonitoringEvent ever fired.
Provides query helpers used by the scheduler, diff, and Phase 8 demo UI.

Events are stored in the `monitoring_event` table (defined in db/schema.sql).
A local JSON fallback (`data/event_log.json`) is maintained in parallel for
demo display purposes.

Public API:
  append(event: dict) → None          — persist one event
  get_events(scheme_id, event_type)  — query events
  has_deadline_alert(scheme_id)      — check if alert already fired
  all_events()                       — return full log (latest first)
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.database import get_db

log = logging.getLogger(__name__)

ROOT          = Path(__file__).resolve().parent.parent
DB_PATH       = ROOT / "data" / "yojana_sentinel.db"
LOG_JSON_PATH = ROOT / "data" / "event_log.json"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_event_id() -> str:
    return f"evt-{uuid.uuid4().hex[:12]}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_log(events: list[dict]) -> None:
    """Persist full event list to JSON for demo dashboard consumption (local fallback)."""
    try:
        LOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except (OSError, PermissionError) as exc:
        log.warning("Could not write event_log.json (%s). Event is saved in DB.", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def append(
    event_type: str,
    scheme_id: str,
    detail: str,
    event_id: Optional[str] = None,
    detected_at: Optional[str] = None,
) -> dict:
    """
    Persist a MonitoringEvent to the DB and JSON log.
    Returns the completed event dict.
    """
    event = {
        "event_id":   event_id or _make_event_id(),
        "event_type": event_type,
        "scheme_id":  scheme_id,
        "detected_at": detected_at or _now_utc(),
        "detail":     detail,
    }

    # ── DB insert ─────────────────────────────────────────────────────────────
    try:
        with get_db() as db:
            db.execute(
                """INSERT INTO monitoring_event
                   (event_id, event_type, scheme_id, detected_at, detail)
                   VALUES (?, ?, ?, ?, ?)""",
                (event["event_id"], event["event_type"], event["scheme_id"],
                 event["detected_at"], event["detail"]),
            )
        log.info(
            "Event logged | type=%-25s scheme=%-40s detail=%s",
            event_type, scheme_id, detail[:80],
        )
    except Exception as exc:
        log.error("Failed to write event to DB: %s", exc)

    # ── JSON log (local fallback — safely caught if file system is read-only) ──
    try:
        existing = all_events(source="json")
        existing.insert(0, event)
        _write_json_log(existing)
    except Exception as exc:
        log.warning("JSON log update skipped: %s", exc)

    return event


def get_events(
    scheme_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Query events from DB, optionally filtered by scheme_id and/or event_type."""
    parts = []
    params: list = []

    if scheme_id:
        parts.append("scheme_id = ?")
        params.append(scheme_id)
    if event_type:
        parts.append("event_type = ?")
        params.append(event_type)

    where = ("WHERE " + " AND ".join(parts)) if parts else ""
    sql = f"SELECT * FROM monitoring_event {where} ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)

    try:
        with get_db() as db:
            rows = db.fetchall(sql, params)
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("DB query failed: %s — falling back to JSON log.", exc)
        events = all_events(source="json")
        if scheme_id:
            events = [e for e in events if e.get("scheme_id") == scheme_id]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events[:limit]


def has_deadline_alert(scheme_id: str) -> bool:
    """
    Returns True if a deadline_approaching event has already been fired
    for this scheme — prevents repeat-firing on every scheduler tick.
    """
    events = get_events(scheme_id=scheme_id, event_type="deadline_approaching", limit=1)
    return len(events) > 0


def all_events(source: str = "db") -> list[dict]:
    """Return all events, latest first. source='db' or 'json'."""
    if source == "json":
        if not LOG_JSON_PATH.exists():
            return []
        try:
            with open(LOG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    try:
        with get_db() as db:
            rows = db.fetchall(
                "SELECT * FROM monitoring_event ORDER BY detected_at DESC"
            )
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("DB events query failed (%s). Falling back to JSON.", exc)
        return all_events(source="json")


def clear_deadline_alerts(scheme_id: str) -> None:
    """
    Remove deadline_approaching records for a scheme.
    Only used in test/reset utilities — never called by production scheduler.
    """
    try:
        with get_db() as db:
            db.execute(
                "DELETE FROM monitoring_event WHERE scheme_id=? AND event_type='deadline_approaching'",
                (scheme_id,),
            )
        log.info("Cleared deadline alerts for scheme: %s", scheme_id)
    except Exception as exc:
        log.warning("Could not clear deadline alerts from DB: %s", exc)
