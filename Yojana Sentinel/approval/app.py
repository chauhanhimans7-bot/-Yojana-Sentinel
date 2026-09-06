"""
approval/app.py — Unified End-to-End Yojana Sentinel Web Application

Connects all Yojana Sentinel modules into a single, seamless, browser-driven web app:
  1. 📥 Pending Approvals (/): Human-in-the-Loop approval dashboard for drafted applications.
  2. ⚡ Monitoring & Demo (/events): Live event log + interactive portal event injection trigger.
  3. 📊 Matching Engine (/matching): Citizen profile match scores, hard rule checks & reasoning.
  4. 🚚 Application Tracking (/tracking): Real-time application status state machine & submission tracking.
  5. 📜 Audit History (/history): Audit trail of approvals, rejections, edits, and state transitions.

Run:
  python main.py
or:
  python -m approval.app
Open http://127.0.0.1:5000 in your browser.
"""

import json
import logging
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, redirect, render_template, request, url_for, jsonify

# Core module integrations
from approval.actions import approve_draft, reject_draft, request_edit, ApprovalError
from monitoring.event_log import all_events
from monitoring.demo_trigger import inject_event
from matching.run_matching import run as run_matching_engine
from tracking.status_store import update_status, mark_submitted, unmark_submitted, get_transition_history, StatusTrackingError
from tracking.staleness_checker import find_stale_drafts

from db.database import get_db

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)
app.secret_key = "yojana-sentinel-dev-key"


# ── DB Helpers ────────────────────────────────────────────────────────────────

def _parse_json_col(d: dict, fields: list) -> dict:
    for f in fields:
        if isinstance(d.get(f), str):
            try:
                d[f] = json.loads(d[f])
            except Exception:
                d[f] = []
    return d


def load_drafts(status_filter: str = None) -> list[dict]:
    """Load ApplicationDrafts from DB with profile and scheme details."""
    drafts = []
    try:
        where_clause = f"WHERE status='{status_filter}'" if status_filter else ""
        with get_db() as db:
            rows = db.fetchall(
                f"SELECT * FROM application_draft {where_clause} ORDER BY created_at DESC"
            )

            for row in rows:
                d = _parse_json_col(dict(row), ["filled_fields", "unresolved_fields"])

                # Attach scheme info
                scheme_row = db.fetchone(
                    "SELECT name, deadline, source_url, category, issuing_body FROM scheme WHERE scheme_id=?",
                    (d["scheme_id"],)
                )
                d["scheme_name"]     = scheme_row["name"]     if scheme_row else d["scheme_id"]
                d["scheme_deadline"] = scheme_row["deadline"] if scheme_row else None
                d["scheme_url"]      = scheme_row["source_url"] if scheme_row else "#"
                d["scheme_category"] = scheme_row["category"]  if scheme_row else ""
                d["issuing_body"]    = scheme_row["issuing_body"] if scheme_row else ""

                # Attach match result (most recent)
                mr_row = db.fetchone(
                    """SELECT match_status, match_score, reasoning FROM match_result
                       WHERE profile_id=? AND scheme_id=?
                       ORDER BY evaluated_at DESC LIMIT 1""",
                    (d["profile_id"], d["scheme_id"])
                )
                d["match_status"]    = mr_row["match_status"]  if mr_row else "unknown"
                d["match_score"]     = mr_row["match_score"]   if mr_row else 0
                d["match_reasoning"] = mr_row["reasoning"]     if mr_row else ""

                # Attach profile display name
                pr_row = db.fetchone(
                    "SELECT display_name, language_preference, state, district FROM citizen_profile WHERE profile_id=?",
                    (d["profile_id"],)
                )
                d["profile_name"] = pr_row["display_name"]       if pr_row else d["profile_id"]
                d["lang_pref"]    = pr_row["language_preference"] if pr_row else "en"
                d["citizen_location"] = f"{pr_row['district'] or ''}, {pr_row['state'] or ''}".strip(", ") if pr_row else ""

                # Staleness check
                d["is_stale"] = (d.get("status") == "stale")
                d["staleness_reason"] = "Underlying scheme requirements were updated." if d["is_stale"] else ""

                drafts.append(d)
    except Exception as exc:
        log.error("Error loading drafts: %s", exc)
    return drafts


def load_all_match_results() -> list[dict]:
    """Load all MatchResults from DB along with scheme and profile details."""
    results = []
    try:
        with get_db() as db:
            rows = db.fetchall(
                """SELECT m.*, s.name as scheme_name, s.category, p.display_name as profile_name
                   FROM match_result m
                   LEFT JOIN scheme s ON m.scheme_id = s.scheme_id
                   LEFT JOIN citizen_profile p ON m.profile_id = p.profile_id
                   ORDER BY m.match_score DESC, m.evaluated_at DESC"""
            )
            for r in rows:
                d = dict(r)
                if isinstance(d.get("missing_info"), str):
                    try:
                        d["missing_info"] = json.loads(d["missing_info"])
                    except Exception:
                        d["missing_info"] = []
                results.append(d)
    except Exception as exc:
        log.error("Error loading match results: %s", exc)
    return results


def load_all_schemes() -> list[dict]:
    """Load scheme metadata for forms and dropdowns."""
    schemes = []
    try:
        with get_db() as db:
            rows = db.fetchall("SELECT scheme_id, name, category, issuing_body, deadline FROM scheme ORDER BY name ASC")
            schemes = [dict(r) for r in rows]
    except Exception as exc:
        log.error("Error loading schemes: %s", exc)
    return schemes


# ── Route 1: Pending Approvals (Dashboard Home) ───────────────────────────────

@app.route("/")
def index():
    drafts = load_drafts(status_filter="drafted")
    error  = request.args.get("error", "")
    flash  = request.args.get("flash", "")
    return render_template(
        "index.html",
        page="pending",
        drafts=drafts,
        flash=flash,
        error=error,
        pending_count=len(drafts),
    )


# ── Route 2: Monitoring & Event Trigger Feed (/events) ─────────────────────────

@app.route("/events")
def events_view():
    events_list = all_events()
    schemes     = load_all_schemes()
    error       = request.args.get("error", "")
    flash       = request.args.get("flash", "")
    return render_template(
        "events.html",
        page="events",
        events_list=events_list,
        schemes=schemes,
        flash=flash,
        error=error,
        pending_count=len(load_drafts(status_filter="drafted")),
    )


@app.route("/events/trigger", methods=["POST"])
def trigger_event():
    scheme_id  = request.form.get("scheme_id")
    event_type = request.form.get("event_type", "deadline_approaching")
    try:
        event = inject_event(scheme_id=scheme_id, event_type=event_type)
        return redirect(url_for("index", flash=f"⚡ Injected '{event_type}' for {scheme_id}! Match results re-evaluated and drafts updated."))
    except Exception as e:
        log.error("Failed to inject event: %s", e)
        return redirect(url_for("events_view", error=f"Event injection failed: {e}"))


# ── Route 3: Matching Engine Dashboard (/matching) ────────────────────────────

@app.route("/matching")
def matching_view():
    results = load_all_match_results()
    flash   = request.args.get("flash", "")
    error   = request.args.get("error", "")
    return render_template(
        "matching.html",
        page="matching",
        results=results,
        flash=flash,
        error=error,
        pending_count=len(load_drafts(status_filter="drafted")),
    )


@app.route("/matching/run", methods=["POST"])
def run_matching_route():
    try:
        run_matching_engine(use_llm=False)
        from main import batch_create_drafts
        drafts_created = batch_create_drafts(use_llm=False)
        return redirect(url_for("matching_view", flash=f"📊 Matching engine executed successfully! {drafts_created} new/updated draft(s) ready for approval."))
    except Exception as e:
        log.error("Failed to run matching: %s", e)
        return redirect(url_for("matching_view", error=f"Matching failed: {e}"))


# ── Route 4: Application Tracking (/tracking) ─────────────────────────────────

@app.route("/tracking")
def tracking_view():
    all_drafts = load_drafts()
    flash = request.args.get("flash", "")
    error = request.args.get("error", "")

    # Attach transition history to each draft
    for d in all_drafts:
        d["history"] = get_transition_history(d["draft_id"])

    return render_template(
        "tracking.html",
        page="tracking",
        all_drafts=all_drafts,
        flash=flash,
        error=error,
        pending_count=len([d for d in all_drafts if d.get("status") == "drafted"]),
    )


@app.route("/tracking/update/<draft_id>", methods=["POST"])
def update_tracking_status(draft_id: str):
    new_status = request.form.get("new_status")
    note       = request.form.get("note", "").strip()
    try:
        if new_status == "submitted":
            mark_submitted(draft_id, note=note)
        else:
            update_status(draft_id, new_status, note=note)
        return redirect(url_for("tracking_view", flash=f"🚚 Updated draft '{draft_id}' status to '{new_status}'."))
    except StatusTrackingError as e:
        return redirect(url_for("tracking_view", error=str(e)))


# ── Route 5: Audit History (/history) ─────────────────────────────────────────

@app.route("/history")
def history_view():
    drafts = load_drafts()
    return render_template(
        "history.html",
        page="history",
        drafts=drafts,
        pending_count=len([d for d in drafts if d.get("status") == "drafted"]),
    )


# ── Approval / Rejection Handlers ─────────────────────────────────────────────

@app.route("/approve/<draft_id>", methods=["POST"])
def approve(draft_id: str):
    approver_name  = request.form.get("approver_name", "Family Representative")
    confirm_anyway = bool(request.form.get("confirm_anyway", False))
    try:
        approve_draft(draft_id, approver_name, confirm_anyway=confirm_anyway)
        return redirect(url_for("index", flash="✅ Application draft approved! It is now tracked under Application Tracking."))
    except ApprovalError as e:
        return redirect(url_for("index", error=str(e)))


@app.route("/reject/<draft_id>", methods=["GET", "POST"])
def reject(draft_id: str):
    if request.method == "POST":
        name   = request.form.get("approver_name", "Family Representative")
        reason = request.form.get("reason", "No reason provided.")
        try:
            reject_draft(draft_id, name, reason)
            return redirect(url_for("index", flash="❌ Application draft rejected and audit record logged."))
        except ApprovalError as e:
            return redirect(url_for("index", error=str(e)))

    flash = request.args.get("flash", "")
    error = request.args.get("error", "")
    return render_template(
        "reject.html",
        page="pending",
        draft_id=draft_id,
        flash=flash,
        error=error,
        pending_count=len(load_drafts(status_filter="drafted")),
    )


@app.route("/edit/<draft_id>", methods=["GET", "POST"])
def edit(draft_id: str):
    try:
        with get_db() as db:
            row = db.fetchone("SELECT * FROM application_draft WHERE draft_id=?", (draft_id,))
        if not row:
            return redirect(url_for("index", error=f"Draft {draft_id} not found."))
        d = _parse_json_col(dict(row), ["filled_fields", "unresolved_fields"])
    except Exception as e:
        return redirect(url_for("index", error=str(e)))

    if request.method == "POST":
        editor_name  = request.form.get("editor_name", "Family Representative")
        edited_fields = []
        for f in d.get("filled_fields", []):
            fid = f["field_id"]
            val = request.form.get(f"field_{fid}", "").strip()
            if val:
                edited_fields.append({"field_id": fid, "value": val})
        try:
            request_edit(draft_id, editor_name, edited_fields)
            return redirect(url_for("index", flash="✏️ Field parameters updated. Draft has been returned to review."))
        except ApprovalError as e:
            return redirect(url_for("index", error=str(e)))

    flash = request.args.get("flash", "")
    error = request.args.get("error", "")
    return render_template(
        "edit.html",
        page="pending",
        draft=d,
        flash=flash,
        error=error,
        pending_count=len(load_drafts(status_filter="drafted")),
    )


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n🛡️  Yojana Sentinel — Unified Web Application")
    print("   Running on http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
