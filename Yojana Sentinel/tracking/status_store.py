"""
tracking/status_store.py

State machine and persistent status tracking for ApplicationDrafts.

State Machine:
  drafted  ──→ approved  ──→ submitted ──→ pending ──→ resolved (terminal)
    │             │               │           │
    └──→ rejected └──→ rejected   └──→ rejected (terminal)

Transitions:
  - mark_submitted(draft_id, submitted_at, note)
      Transition: approved → submitted
      Meaning: Citizen/family member confirms they manually submitted the application outside the app.

  - update_status(draft_id, new_status, note)
      Transition: submitted → pending → resolved / rejected
      Meaning: Manual/mock status update (since Indian government schemes lack public status APIs).

  - unmark_submitted(draft_id, note)
      Transition: submitted → approved
      Meaning: Correction path if a citizen accidentally marked a draft as submitted.

  - Every status transition is logged with timestamp, previous state, new state, and note.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.database import get_db

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"
LOG_PATH = ROOT / "data" / "status_transition_log.json"


class StatusTrackingError(Exception):
    """Raised when an invalid status transition is attempted."""


# ── Allowed state transitions ──────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, set[str]] = {
    "drafted":   {"approved", "rejected"},
    "approved":  {"submitted", "rejected"},
    "submitted": {"pending", "approved", "rejected", "resolved"},
    "pending":   {"resolved", "rejected", "submitted"},
    "resolved":  set(),  # Terminal state
    "rejected":  set(),  # Terminal state
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_draft(draft_id: str) -> dict:
    try:
        with get_db() as db:
            row = db.fetchone("SELECT * FROM application_draft WHERE draft_id=?", (draft_id,))
    except Exception as exc:
        raise StatusTrackingError(f"Database error fetching draft {draft_id}: {exc}") from exc

    if not row:
        raise StatusTrackingError(f"ApplicationDraft '{draft_id}' not found.")

    return dict(row)


def _log_transition(draft_id: str, old_status: str, new_status: str, note: str = "") -> None:
    entry = {
        "draft_id":   draft_id,
        "old_status": old_status,
        "new_status": new_status,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "note":       note,
    }
    try:
        from approval.approval_log import log_action
        log_action(
            draft_id=draft_id,
            action=f"status_change:{new_status}",
            actor_name="Human Operator",
            note=f"Transitioned from '{old_status}' to '{new_status}'. {note}".strip(),
            extra={"old_status": old_status, "new_status": new_status},
        )
    except Exception as exc:
        log.warning("Could not log status transition to DB: %s", exc)

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logs = []
        if LOG_PATH.exists():
            try:
                with open(LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.insert(0, entry)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except (OSError, PermissionError) as exc:
        log.warning("Could not write status_transition_log.json (%s). Status update saved in DB.", exc)

    log.info("StatusTransition | draft=%s | %s ──→ %s | note: %s", draft_id, old_status, new_status, note)


# ── Core State Machine Functions ──────────────────────────────────────────────

def update_status(draft_id: str, new_status: str, note: str = "") -> dict:
    """
    Transition an ApplicationDraft to a new status.
    Validates state machine rules and logs the transition.
    """
    draft = _get_draft(draft_id)
    current_status = draft.get("status", "drafted")

    if current_status == new_status:
        log.info("Draft '%s' is already in status '%s'. No-op.", draft_id, new_status)
        return draft

    allowed = VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise StatusTrackingError(
            f"Invalid transition from '{current_status}' to '{new_status}' for draft '{draft_id}'. "
            f"Allowed next states from '{current_status}': {sorted(allowed) or 'None (terminal state)'}"
        )

    with get_db() as db:
        db.execute(
            "UPDATE application_draft SET status=? WHERE draft_id=?",
            (new_status, draft_id),
        )

    _log_transition(draft_id, current_status, new_status, note)
    draft["status"] = new_status
    return draft


def mark_submitted(draft_id: str, submitted_at: Optional[str] = None, note: str = "") -> dict:
    """
    Mark an approved draft as manually submitted by the citizen/family member.
    """
    draft = _get_draft(draft_id)
    current = draft.get("status")

    if current != "approved":
        raise StatusTrackingError(
            f"Cannot mark draft '{draft_id}' as submitted: current status is '{current}'. "
            f"Only 'approved' drafts can be marked as submitted."
        )

    time_str = submitted_at or datetime.now(timezone.utc).isoformat()
    full_note = f"Manually submitted by human on {time_str}. {note}".strip()

    return update_status(draft_id, "submitted", note=full_note)


def unmark_submitted(draft_id: str, note: str = "Corrected erroneous submission marking") -> dict:
    """
    Recovery path: revert status from 'submitted' back to 'approved' if citizen marked submission by mistake.
    """
    draft = _get_draft(draft_id)
    current = draft.get("status")

    if current != "submitted":
        raise StatusTrackingError(
            f"Cannot unmark submission for draft '{draft_id}': status is '{current}', expected 'submitted'."
        )

    return update_status(draft_id, "approved", note=note)


def get_transition_history(draft_id: str) -> list[dict]:
    """Return all status transition log entries for a given draft."""
    try:
        from approval.approval_log import get_log_for_draft
        db_logs = get_log_for_draft(draft_id)
        if db_logs:
            return [
                {
                    "draft_id":   e["draft_id"],
                    "old_status": e.get("extra", {}).get("old_status", "") if isinstance(e.get("extra"), dict) else "",
                    "new_status": e.get("extra", {}).get("new_status", e["action"]) if isinstance(e.get("extra"), dict) else e["action"],
                    "timestamp":  e["timestamp"],
                    "note":       e.get("note", ""),
                }
                for e in db_logs
            ]
    except Exception as exc:
        log.warning("Could not load transition history from DB: %s", exc)

    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
            return [e for e in logs if e.get("draft_id") == draft_id]
    except Exception:
        return []
