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

log = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parent.parent
LOG_PATH     = ROOT / "data" / "approval_log.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_log(entries: list[dict]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def log_action(
    draft_id: str,
    action: str,            # "approve" | "reject" | "edit"
    actor_name: str,
    note: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """
    Append a human action to the approval log.
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
    entries = _load_log()
    # Latest first
    entries.insert(0, entry)
    _save_log(entries)

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
