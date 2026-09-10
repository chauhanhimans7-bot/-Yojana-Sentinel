"""
drafting/create_draft.py

Orchestrates the full application drafting pipeline for a single MatchResult:
  1. Validates match_status — refuses to draft not_eligible; requires explicit
     override flag for needs_review.
  2. Calls field_mapper.map_fields() to build filled_fields + unresolved_fields.
  3. Calls draft_writer.generate_draft_text() to produce draft_text via LLM.
  4. Writes a new ApplicationDraft record (status: "drafted") to the DB
     and returns it.

Staleness policy:
  An existing draft for the same (profile_id, scheme_id) is NOT overwritten
  automatically. If such a draft exists, it is returned with a warning.
  If you need a fresh draft after a scheme_updated event, pass force_new=True.
  See docs/draft_staleness_policy.md for the full policy.

Usage:
  from drafting.create_draft import create_draft
  draft = create_draft(match_result, profile, scheme)
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from drafting.field_mapper import map_fields
from drafting.draft_writer import generate_draft_text, DraftWriterError
from db.database import get_db

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"


# ── Exceptions ────────────────────────────────────────────────────────────────

class DraftCreationError(Exception):
    """Raised when a draft cannot be created for a valid reason."""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_existing_draft(profile_id: str, scheme_id: str) -> dict | None:
    """Return the most recent drafted ApplicationDraft for this pair, or None."""
    try:
        with get_db() as db:
            row = db.execute(
                """SELECT * FROM application_draft
                   WHERE profile_id=? AND scheme_id=? AND status='drafted'
                   ORDER BY created_at DESC LIMIT 1""",
                (profile_id, scheme_id),
            ).fetchone()
        if row:
            d = dict(row)
            for field in ("filled_fields", "unresolved_fields"):
                if isinstance(d.get(field), str):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception:
                        d[field] = []
            return d
    except Exception as exc:
        log.warning("Could not check for existing draft: %s", exc)
    return None


def _save_draft(draft: dict) -> None:
    """Insert a new ApplicationDraft into the DB."""
    try:
        with get_db() as db:
            db.execute(
                """INSERT INTO application_draft
                   (draft_id, profile_id, scheme_id, filled_fields,
                    unresolved_fields, draft_text, status, created_at,
                    approved_by, approved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    draft["draft_id"],
                    draft["profile_id"],
                    draft["scheme_id"],
                    json.dumps(draft["filled_fields"], ensure_ascii=False),
                    json.dumps(draft["unresolved_fields"], ensure_ascii=False),
                    draft["draft_text"],
                    draft["status"],
                    draft["created_at"],
                    draft.get("approved_by"),
                    draft.get("approved_at"),
                ),
            )
        log.info("Draft saved to DB: draft_id=%s", draft["draft_id"])
    except Exception as exc:
        log.error("Failed to save draft to DB: %s", exc)
        raise DraftCreationError(f"Database write failed: {exc}") from exc


# ── Core function ─────────────────────────────────────────────────────────────

def create_draft(
    match_result: dict,
    profile: dict,
    scheme: dict,
    allow_needs_review: bool = False,
    force_new: bool = False,
) -> dict:
    """
    Create an ApplicationDraft for a matched (profile, scheme) pair.

    Args:
        match_result:       MatchResult dict from matching/matcher.py
        profile:            CitizenProfile dict
        scheme:             Scheme dict
        allow_needs_review: If True, allow drafting when match_status is
                            'needs_review'. Requires explicit opt-in because
                            needs_review means eligibility itself is uncertain.
        force_new:          If True, create a fresh draft even if one already
                            exists (use after scheme_updated events).

    Returns:
        ApplicationDraft dict with status: "drafted"

    Raises:
        DraftCreationError: if match_status is not_eligible, or needs_review
                            without allow_needs_review, or draft_text generation fails.
    """
    profile_id  = profile.get("profile_id", "unknown")
    scheme_id   = scheme.get("scheme_id", "unknown")
    match_status = match_result.get("match_status", "")

    # ── Validation ─────────────────────────────────────────────────────────────
    if match_status == "not_eligible":
        raise DraftCreationError(
            f"Cannot create draft: match_status is 'not_eligible' for "
            f"profile={profile_id}, scheme={scheme_id}. "
            f"Eligibility must be strong_match, partial_match, or needs_review."
        )

    if match_status == "needs_review" and not allow_needs_review:
        raise DraftCreationError(
            f"Cannot create draft: match_status is 'needs_review' for "
            f"profile={profile_id}, scheme={scheme_id}. "
            f"Pass allow_needs_review=True to override. Note: needs_review means "
            f"eligibility itself is uncertain, not just paperwork completeness."
        )

    # ── Staleness: return existing draft if present (unless force_new) ─────────
    if not force_new:
        existing = _get_existing_draft(profile_id, scheme_id)
        if existing:
            log.warning(
                "Draft already exists for profile=%s scheme=%s (draft_id=%s). "
                "Returning existing. Pass force_new=True to regenerate.",
                profile_id, scheme_id, existing.get("draft_id"),
            )
            return existing

    # ── Step 1: Map fields ─────────────────────────────────────────────────────
    log.info("Mapping fields | profile=%s scheme=%s", profile_id, scheme_id)
    filled_fields, unresolved_fields = map_fields(profile, scheme)

    # ── Step 2: Generate draft text ────────────────────────────────────────────
    log.info("Generating draft text...")
    try:
        draft_text = generate_draft_text(
            profile=profile,
            scheme=scheme,
            filled_fields=filled_fields,
            unresolved_fields=unresolved_fields,
        )
    except DraftWriterError as exc:
        # Hard fail — never produce a draft with draft_text=null
        raise DraftCreationError(
            f"Draft text generation failed for profile={profile_id}, scheme={scheme_id}. "
            f"Reason: {exc}"
        ) from exc

    # ── Step 3: Build ApplicationDraft ────────────────────────────────────────
    draft = {
        "draft_id":          f"draft-{uuid.uuid4().hex[:12]}",
        "profile_id":        profile_id,
        "scheme_id":         scheme_id,
        "filled_fields":     filled_fields,
        "unresolved_fields": unresolved_fields,
        "draft_text":        draft_text,
        "status":            "drafted",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "approved_by":       None,
        "approved_at":       None,
    }

    # ── Step 4: Persist ────────────────────────────────────────────────────────
    _save_draft(draft)

    log.info(
        "Draft created | draft_id=%s | profile=%s | scheme=%s | unresolved=%d",
        draft["draft_id"], profile_id, scheme_id, len(unresolved_fields),
    )
    return draft


# ── CLI helper for quick testing ──────────────────────────────────────────────

if __name__ == "__main__":
    """
    Quick smoke test: create a draft from the first strong/partial match in
    data/match_results.json using seed data.
    Run: python -m drafting.create_draft
    """
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Load seed data
    with open(ROOT / "data" / "match_results.json", "r", encoding="utf-8") as f:
        results = json.load(f)
    with open(ROOT / "data" / "schemes_seed.json", "r", encoding="utf-8") as f:
        schemes = {s["scheme_id"]: s for s in json.load(f)}
    with open(ROOT / "data" / "profiles_seed.json", "r", encoding="utf-8") as f:
        profiles = {p["profile_id"]: p for p in json.load(f)}

    # Find first actionable match
    actionable = [r for r in results if r["match_status"] in ("strong_match", "partial_match")]
    if not actionable:
        print("No strong_match or partial_match results found. Run matching first.")
        sys.exit(1)

    r = actionable[0]
    print(f"\nCreating draft for: profile={r['profile_id']} scheme={r['scheme_id']} ({r['match_status']})")

    try:
        draft = create_draft(
            match_result=r,
            profile=profiles[r["profile_id"]],
            scheme=schemes[r["scheme_id"]],
            force_new=True,
        )
        print(f"\n✅ Draft created: {draft['draft_id']}")
        print(f"   Unresolved fields: {draft['unresolved_fields']}")
        print(f"\n--- DRAFT TEXT ---\n{draft['draft_text']}")
    except DraftCreationError as e:
        print(f"\n❌ Draft creation failed: {e}")
        sys.exit(1)
