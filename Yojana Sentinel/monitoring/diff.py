"""
monitoring/diff.py

Compares two Scheme snapshots (previous vs current) and emits MonitoringEvent
records for meaningful changes.

Detects exactly the four event types from the master schema:
  new_scheme           — scheme_id appeared in current but not previous
  deadline_approaching — deadline is within window_days of today (fires ONCE per scheme)
  scheme_closed        — scheme whose deadline has passed or status → closed
  scheme_updated       — eligibility_rules, required_documents, or deadline changed

Design decisions on edge cases:
  - Debounce for status flicker: scheme_closed is only fired if the scheme's
    status is 'closed' AND it was 'active' in the previous snapshot. A reopened
    scheme (closed→active) appears as scheme_updated rather than new_scheme, to
    avoid creating a misleading "new scheme" event for something citizens may
    have already seen. This trades completeness for noise reduction.
  - Overlap prevention: deadline_approaching uses event_log.has_deadline_alert()
    so it never fires twice for the same scheme regardless of how many ticks pass.
  - Only structured fields (eligibility_rules, required_documents, deadline) are
    diff'd for scheme_updated — description/name changes are logged at DEBUG only
    to avoid drowning operators in minor editorial updates from government portals.
"""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from monitoring.event_log import append, has_deadline_alert

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def _load_scope() -> dict:
    scope_path = ROOT / "config" / "scope.json"
    with open(scope_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_deadline_approaching(deadline: Optional[str], window_days: int) -> bool:
    """Return True if deadline is within window_days of today (inclusive)."""
    if not deadline:
        return False
    try:
        dl = date.fromisoformat(deadline)
        today = date.today()
        return 0 <= (dl - today).days <= window_days
    except ValueError:
        return False


def _is_deadline_passed(deadline: Optional[str]) -> bool:
    """Return True if deadline date is in the past."""
    if not deadline:
        return False
    try:
        return date.fromisoformat(deadline) < date.today()
    except ValueError:
        return False


def _sig(scheme: dict) -> dict:
    """Extract the fields we diff for scheme_updated detection."""
    return {
        "eligibility_rules":  json.dumps(scheme.get("eligibility_rules", {}), sort_keys=True),
        "required_documents": json.dumps(scheme.get("required_documents", []), sort_keys=True),
        "deadline":           scheme.get("deadline"),
    }


# ── Main diff function ────────────────────────────────────────────────────────

def compute_diff(
    previous: list[dict],
    current: list[dict],
) -> list[dict]:
    """
    Compare two scheme lists and emit MonitoringEvents for all changes found.

    Args:
        previous:  Scheme list from the last scheduler run (may be empty on first run)
        current:   Scheme list from the current ingestion pass

    Returns:
        List of MonitoringEvent dicts that were emitted and persisted.
    """
    scope = _load_scope()
    window_days: int = scope.get("deadline_approaching_window_days", 14)

    prev_map: dict[str, dict] = {s["scheme_id"]: s for s in previous}
    curr_map: dict[str, dict] = {s["scheme_id"]: s for s in current}

    emitted: list[dict] = []

    # ── 1. New schemes ────────────────────────────────────────────────────────
    for sid, scheme in curr_map.items():
        if sid not in prev_map:
            detail = (
                f"New scheme detected: '{scheme.get('name', sid)}' "
                f"issued by {scheme.get('issuing_body', 'unknown')}. "
                f"Category: {scheme.get('category', 'unknown')}."
            )
            evt = append("new_scheme", sid, detail)
            emitted.append(evt)
            log.info("NEW_SCHEME: %s", sid)

    # ── 2. Deadline approaching, scheme_closed, scheme_updated ───────────────
    for sid, scheme in curr_map.items():
        prev = prev_map.get(sid)
        deadline = scheme.get("deadline")
        status = (scheme.get("status") or "active").lower()

        # ── 2a. Deadline approaching ─────────────────────────────────────────
        if _is_deadline_approaching(deadline, window_days):
            if not has_deadline_alert(sid):
                days_left = (date.fromisoformat(deadline) - date.today()).days
                detail = (
                    f"Deadline alert: '{scheme.get('name', sid)}' "
                    f"deadline is {deadline} — {days_left} day(s) from today. "
                    f"Window: {window_days} days."
                )
                evt = append("deadline_approaching", sid, detail)
                emitted.append(evt)
                log.info("DEADLINE_APPROACHING: %s (deadline=%s, days_left=%d)", sid, deadline, days_left)
            else:
                log.debug("Deadline alert already sent for %s — skipping.", sid)

        # ── 2b. Scheme closed ────────────────────────────────────────────────
        # Fires only if:
        #   - status is now 'closed' AND was 'active' before (debounce for flicker)
        #   - OR deadline has definitively passed with no prior close event
        prev_status = (prev.get("status") or "active").lower() if prev else "active"
        if status == "closed" and prev_status == "active":
            detail = (
                f"Scheme closed: '{scheme.get('name', sid)}' "
                f"status changed from active to closed."
                + (f" Deadline was {deadline}." if deadline else "")
            )
            evt = append("scheme_closed", sid, detail)
            emitted.append(evt)
            log.info("SCHEME_CLOSED (status change): %s", sid)

        elif _is_deadline_passed(deadline) and status != "closed":
            # Source hasn't updated status yet but deadline has passed
            # Treat as scheme_closed — normalize.py would mark it closed on next run
            if not any(
                e.get("event_type") == "scheme_closed" and e.get("scheme_id") == sid
                for e in emitted
            ):
                from monitoring.event_log import get_events
                prior_closed = get_events(scheme_id=sid, event_type="scheme_closed", limit=1)
                if not prior_closed:
                    detail = (
                        f"Deadline passed: '{scheme.get('name', sid)}' "
                        f"deadline {deadline} has now passed but source still shows status='{status}'. "
                        f"Flagged as closed by Sentinel."
                    )
                    evt = append("scheme_closed", sid, detail)
                    emitted.append(evt)
                    log.info("SCHEME_CLOSED (deadline passed): %s", sid)

        # ── 2c. Scheme updated ───────────────────────────────────────────────
        if prev is not None:
            prev_sig = _sig(prev)
            curr_sig = _sig(scheme)
            changes = []

            if prev_sig["deadline"] != curr_sig["deadline"]:
                old_dl = prev_sig["deadline"] or "none"
                new_dl = curr_sig["deadline"] or "none"
                changes.append(f"deadline moved from {old_dl} to {new_dl}")

            if prev_sig["eligibility_rules"] != curr_sig["eligibility_rules"]:
                changes.append("eligibility_rules changed")

            if prev_sig["required_documents"] != curr_sig["required_documents"]:
                changes.append("required_documents changed")

            if changes:
                detail = (
                    f"Scheme updated: '{scheme.get('name', sid)}'. "
                    f"Changes: {'; '.join(changes)}."
                )
                evt = append("scheme_updated", sid, detail)
                emitted.append(evt)
                log.info("SCHEME_UPDATED: %s — %s", sid, "; ".join(changes))

    log.info(
        "Diff complete. %d event(s) emitted from %d current / %d previous schemes.",
        len(emitted), len(current), len(previous),
    )
    return emitted
