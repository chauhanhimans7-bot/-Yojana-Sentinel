"""
approval/actions.py

Three human actions on an ApplicationDraft:
  approve_draft(draft_id, approver_name)
  reject_draft(draft_id, approver_name, reason)
  request_edit(draft_id, editor_name, edited_fields)

Design rules (from 06_human_approval.md):
  1. approve_draft NEVER submits anything. It only sets status → "approved".
     The label "approved" means "ready for human to manually submit themselves."
  2. Approving a draft with non-empty unresolved_fields → warns and shows
     confirmation path (requires confirm_anyway=True). Documented choice:
     BLOCK with override, not silent allow, because unresolved govt fields
     are a real compliance risk.
  3. request_edit recomputes unresolved_fields after human fills in values.
  4. All three actions log to approval/approval_log.py.
  5. Concurrent approval conflict: last-write-wins. Both actions are logged
     so the conflict is visible after the fact.
  6. Stale draft (status == "stale") blocks approval until re-matched.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from approval.approval_log import log_action
from drafting.field_mapper import recompute_after_edit

from db.database import get_db

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"


# ── Exceptions ────────────────────────────────────────────────────────────────

class ApprovalError(Exception):
    """Raised when an approval action cannot be completed."""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_draft(draft_id: str) -> dict:
    """Fetch a draft by ID; raise ApprovalError if not found."""
    try:
        with get_db() as db:
            row = db.fetchone(
                "SELECT * FROM application_draft WHERE draft_id=?", (draft_id,)
            )
    except Exception as exc:
        raise ApprovalError(f"Database error fetching draft {draft_id}: {exc}") from exc

    if not row:
        raise ApprovalError(f"Draft '{draft_id}' not found in database.")

    d = dict(row)
    for field in ("filled_fields", "unresolved_fields"):
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
    return d


def _update_draft(draft_id: str, updates: dict) -> None:
    """Apply a dict of column→value updates to a draft row."""
    if not updates:
        return
    set_clause = ", ".join(f"{col}=?" for col in updates)
    values     = list(updates.values()) + [draft_id]
    with get_db() as db:
        db.execute(
            f"UPDATE application_draft SET {set_clause} WHERE draft_id=?",
            values,
        )


def _get_scheme(scheme_id: str) -> dict:
    """Load scheme from DB for recompute_after_edit calls."""
    try:
        with get_db() as db:
            row = db.fetchone("SELECT * FROM scheme WHERE scheme_id=?", (scheme_id,))
        if row:
            d = dict(row)
            for f in ("application_fields", "eligibility_rules", "required_documents"):
                if isinstance(d.get(f), str):
                    try:
                        d[f] = json.loads(d[f])
                    except Exception:
                        d[f] = [] if f != "eligibility_rules" else {}
            return d
    except Exception:
        pass
    return {}


# ── Actions ───────────────────────────────────────────────────────────────────

def approve_draft(
    draft_id: str,
    approver_name: str,
    confirm_anyway: bool = False,
) -> dict:
    """
    Mark a draft as approved.

    NOTE: This action does NOT submit anything to any government portal.
    "Approved" means the human has reviewed and signed off — they must
    then physically / manually submit it themselves outside this app.

    Args:
        draft_id:       ID of the ApplicationDraft to approve
        approver_name:  Name of the human approver (for audit log)
        confirm_anyway: Required=True to approve despite unresolved_fields

    Returns:
        Updated draft dict with status="approved"

    Raises:
        ApprovalError: if draft is not in "drafted" state, is stale,
                       or has unresolved_fields without confirm_anyway.
    """
    draft = _get_draft(draft_id)
    status = draft.get("status", "")

    if status == "stale":
        raise ApprovalError(
            f"Draft '{draft_id}' is marked STALE — the underlying scheme has changed. "
            f"Re-run matching for scheme '{draft['scheme_id']}' before approving."
        )

    if status == "approved":
        log.warning("Draft '%s' is already approved. No-op.", draft_id)
        return draft

    if status not in ("drafted",):
        raise ApprovalError(
            f"Cannot approve draft '{draft_id}': status is '{status}'. "
            f"Only drafts with status='drafted' can be approved."
        )

    # Unresolved fields check
    unresolved = draft.get("unresolved_fields", [])
    if unresolved and not confirm_anyway:
        raise ApprovalError(
            f"Draft '{draft_id}' has {len(unresolved)} unresolved field(s): "
            f"{unresolved}. "
            f"These must be filled before approving, OR pass confirm_anyway=True "
            f"to approve anyway (you will need to provide missing info when submitting manually)."
        )

    now = datetime.now(timezone.utc).isoformat()
    _update_draft(draft_id, {
        "status":      "approved",
        "approved_by": approver_name,
        "approved_at": now,
    })

    note = "Approved with unresolved fields — human will complete during manual submission." \
           if (unresolved and confirm_anyway) else "All fields resolved at time of approval."

    log_action(draft_id=draft_id, action="approve", actor_name=approver_name, note=note)

    log.info(
        "Draft APPROVED | draft_id=%s | by=%s | unresolved_at_approval=%d",
        draft_id, approver_name, len(unresolved),
    )

    draft["status"]      = "approved"
    draft["approved_by"] = approver_name
    draft["approved_at"] = now
    return draft


def reject_draft(
    draft_id: str,
    approver_name: str,
    reason: str,
) -> dict:
    """
    Mark a draft as rejected and log the reason.

    Args:
        draft_id:       ID of the ApplicationDraft
        approver_name:  Actor name
        reason:         Why it was rejected (stored in log for analysis)

    Returns:
        Updated draft dict with status="rejected"
    """
    draft = _get_draft(draft_id)
    status = draft.get("status", "")

    if status in ("rejected",):
        log.warning("Draft '%s' already rejected.", draft_id)
        return draft

    if status not in ("drafted", "approved"):
        raise ApprovalError(
            f"Cannot reject draft '{draft_id}': status is '{status}'."
        )

    _update_draft(draft_id, {
        "status":      "rejected",
        "approved_by": approver_name,     # Actor who rejected (reuse column for audit trail)
        "approved_at": datetime.now(timezone.utc).isoformat(),  # Actual rejection timestamp
    })
    log_action(draft_id=draft_id, action="reject", actor_name=approver_name, note=reason)

    log.info("Draft REJECTED | draft_id=%s | by=%s | reason=%s", draft_id, approver_name, reason[:80])

    draft["status"] = "rejected"
    return draft


def request_edit(
    draft_id: str,
    editor_name: str,
    edited_fields: list[dict],
) -> dict:
    """
    Apply human-provided corrections to filled_fields and recompute unresolved_fields.

    edited_fields must be a list of {field_id, value} dicts.
    After this call, any previously-unresolved field that now has a value is
    removed from unresolved_fields.  Status stays "drafted".

    Returns:
        Updated draft dict with merged filled_fields and recomputed unresolved_fields
    """
    draft = _get_draft(draft_id)
    scheme = _get_scheme(draft["scheme_id"])

    # Merge edits into existing filled_fields
    filled = {f["field_id"]: f for f in draft.get("filled_fields", [])}
    changed_fields = []

    for edit in edited_fields:
        fid = edit.get("field_id", "")
        val = str(edit.get("value", "")).strip()
        if fid and val:
            filled[fid] = {
                "field_id": fid,
                "value":    val,
                "source":   "profile",   # Human-provided → promoted to "profile" source
            }
            changed_fields.append(fid)

    new_filled = list(filled.values())
    new_unresolved = recompute_after_edit(new_filled, scheme) if scheme else []

    _update_draft(draft_id, {
        "filled_fields":     json.dumps(new_filled, ensure_ascii=False),
        "unresolved_fields": json.dumps(new_unresolved, ensure_ascii=False),
        "status":            "drafted",   # Stays drafted until re-approved
    })

    log_action(
        draft_id=draft_id,
        action="edit",
        actor_name=editor_name,
        note=f"Edited fields: {', '.join(changed_fields)}. Unresolved now: {len(new_unresolved)}.",
        extra={"edited_field_ids": changed_fields},
    )

    log.info(
        "Draft EDITED | draft_id=%s | by=%s | changed=%d | unresolved_now=%d",
        draft_id, editor_name, len(changed_fields), len(new_unresolved),
    )

    draft["filled_fields"]     = new_filled
    draft["unresolved_fields"] = new_unresolved
    draft["status"]            = "drafted"
    return draft
