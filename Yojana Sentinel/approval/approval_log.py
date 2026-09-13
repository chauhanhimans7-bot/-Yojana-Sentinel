"""
approval/approval_log.py

Append-only audit log for every human action on an ApplicationDraft.
Records: approve, reject, request_edit — with actor name, timestamp, and notes.

Stored in:
  - SQLite: uses the application_draft table's approved_by / approved_at columns
    for the primary state, and a separate approval_log JSON file for the full audit trail.
  - data/approval_log.json: human-readable flat log for demo display.

This is the audit trail that lets an operator review WHO approved WHAT and WHEN,
and also surfaces conflicts (e.g. two people acting on the same draft).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.database import get_db

log = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parent.parent
LOG_PATH     = ROOT / "data" / "approval_log.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_log() -> list[dict]:
    # ── Try DB first ──────────────────────────────────────────────────────────
    try:
        with get_db() as db:
            rows = db.fetchall("SELECT * FROM approval_log ORDER BY timestamp DESC LIMIT 200")
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("extra"), str):
                    try:
                        d["extra"] = json.loads(d["extra"])
                    except Exception:
                        d["extra"] = {}
                results.append(d)
            return results
    except Exception as exc:
        log.warning("Could not read approval_log from DB: %s — checking JSON log.", exc)

    # ── Fallback to JSON log ──────────────────────────────────────────────────
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_log(entries: list[dict]) -> None:
    """Persist log to JSON (local fallback — safely caught if file system is read-only)."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except (OSError, PermissionError) as exc:
        log.warning("Could not write approval_log.json (%s). Log saved in DB.", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def log_action(
    draft_id: str,
    action: str,            # "approve" | "reject" | "edit"
    actor_name: str,
    note: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """
    Append a human action to the approval log (DB + JSON fallback).
    Returns the log entry dict.
    """
    entry = {
        "log_id":     f"log-{uuid.uuid4().hex[:10]}",
        "draft_id":   draft_id,
        "action":     action,
        "actor_name": actor_name,
        "timestamp":  _now_utc(),
        "note":       note or "",
        "extra":      extra or {},
    }

    # ── DB insert ─────────────────────────────────────────────────────────────
    try:
        with get_db() as db:
            db.execute(
                """INSERT INTO approval_log
                   (log_id, draft_id, action, actor_name, timestamp, note, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry["log_id"],
                    entry["draft_id"],
                    entry["action"],
                    entry["actor_name"],
                    entry["timestamp"],
                    entry["note"],
                    json.dumps(entry["extra"], ensure_ascii=False),
                ),
            )
    except Exception as exc:
        log.error("Failed to write approval_log entry to DB: %s", exc)

    # ── JSON fallback log ─────────────────────────────────────────────────────
    try:
        entries = _load_log()
        entries.insert(0, entry)
        _save_log(entries)
    except Exception as exc:
        log.warning("JSON approval log save skipped: %s", exc)

    log.info(
        "ApprovalLog | action=%-10s draft=%-20s actor=%s",
        action, draft_id, actor_name,
    )
    return entry


def get_log_for_draft(draft_id: str) -> list[dict]:
    """Return all log entries for a specific draft, newest first."""
    return [e for e in _load_log() if e.get("draft_id") == draft_id]


def get_all_logs(limit: int = 200) -> list[dict]:
    """Return all log entries newest-first, up to limit."""
    return _load_log()[:limit]
