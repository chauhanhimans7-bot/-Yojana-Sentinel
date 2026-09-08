"""
monitoring/demo_trigger.py

DEMO TOOL — for live on-stage use.

Manually injects a fake MonitoringEvent into the pipeline to simulate what
happens when the scheduler detects a real change on a government scheme portal.

This is what you run on stage to demonstrate the monitoring pipeline without
waiting for a real government portal to change.

CRITICAL DESIGN RULE:
  This script goes through the EXACT same downstream path as the real scheduler.
  It calls monitoring.event_log.append() to persist the event, then calls
  monitoring.scheduler.trigger_matching_for_scheme() to re-run the matcher.
  It is NOT a separate mock — it proves the real pipeline.

Supported event types to inject:
  deadline_approaching  — most impactful for demo (shows urgency + triggers matcher)
  new_scheme            — shows discovery story
  scheme_updated        — shows vigilance story
  scheme_closed         — shows staleness detection story

Usage (run from project root):
  python -m monitoring.demo_trigger --scheme <scheme_id> --event deadline_approaching
  python -m monitoring.demo_trigger --scheme <scheme_id> --event new_scheme
  python -m monitoring.demo_trigger --list-schemes        # see available scheme IDs

Example:
  python -m monitoring.demo_trigger --scheme up-scholarship-obc-2026 --event deadline_approaching
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMES_SEED = ROOT / "data" / "schemes_seed.json"
SCOPE_PATH   = ROOT / "config" / "scope.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

VALID_EVENT_TYPES = {
    "new_scheme",
    "deadline_approaching",
    "scheme_closed",
    "scheme_updated",
}


# ── Scheme lookup ──────────────────────────────────────────────────────────────

def _load_schemes() -> list[dict]:
    """Load scheme list from seed JSON (demo always uses seed for reliability)."""
    if not SCHEMES_SEED.exists():
        log.error("schemes_seed.json not found at %s. Cannot inject event.", SCHEMES_SEED)
        sys.exit(1)
    with open(SCHEMES_SEED, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_scheme(scheme_id: str, schemes: list[dict]) -> dict:
    """Find a scheme by ID; exit with helpful error if not found."""
    match = next((s for s in schemes if s["scheme_id"] == scheme_id), None)
    if match is None:
        available = [s["scheme_id"] for s in schemes]
        log.error(
            "scheme_id='%s' not found in schemes_seed.json.\n"
            "This would cause a silent no-op in production — failing loudly instead.\n"
            "Available scheme IDs:\n%s",
            scheme_id,
            "\n".join(f"  • {sid}" for sid in available),
        )
        sys.exit(1)
    return match


# ── Detail builders ────────────────────────────────────────────────────────────

def _build_detail(event_type: str, scheme: dict) -> str:
    """Build a specific, demo-readable detail string for the injected event."""
    name     = scheme.get("name", scheme["scheme_id"])
    deadline = scheme.get("deadline") or "no deadline"
    body     = scheme.get("issuing_body", "unknown issuing body")
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if event_type == "deadline_approaching":
        return (
            f"[DEMO TRIGGER] Deadline alert: '{name}' issued by {body}. "
            f"Deadline: {deadline}. "
            f"Event injected at {now_str} for demo purposes."
        )
    if event_type == "new_scheme":
        return (
            f"[DEMO TRIGGER] New scheme detected: '{name}' issued by {body}. "
            f"Category: {scheme.get('category', 'unknown')}. "
            f"Injected at {now_str}."
        )
    if event_type == "scheme_updated":
        return (
            f"[DEMO TRIGGER] Scheme updated: '{name}'. "
            f"Simulated change: eligibility_rules modified. "
            f"Injected at {now_str}."
        )
    if event_type == "scheme_closed":
        return (
            f"[DEMO TRIGGER] Scheme closed: '{name}'. "
            f"Deadline was {deadline}. Status now closed. "
            f"Injected at {now_str}."
        )
    return f"[DEMO TRIGGER] {event_type} for '{name}' injected at {now_str}."


# ── Core injection function ────────────────────────────────────────────────────

def inject_event(scheme_id: str, event_type: str) -> dict:
    """
    Inject a fake MonitoringEvent and trigger downstream matching if appropriate.

    This is the single entry point for demo injection — it uses the same
    event_log.append() and scheduler.trigger_matching_for_scheme() as the
    real scheduler, so the demo proves the actual production pipeline.

    Returns the emitted MonitoringEvent dict.
    """
    if event_type not in VALID_EVENT_TYPES:
        log.error(
            "Invalid event_type='%s'. Must be one of: %s",
            event_type, ", ".join(sorted(VALID_EVENT_TYPES)),
        )
        sys.exit(1)

    schemes = _load_schemes()
    scheme  = _find_scheme(scheme_id, schemes)

    detail  = _build_detail(event_type, scheme)

    # ── Check deduplication for deadline alerts ────────────────────────────────
    from monitoring.event_log import append as log_event, has_deadline_alert, get_events
    if event_type == "deadline_approaching" and has_deadline_alert(scheme_id):
        log.info("Deadline alert already active for scheme '%s'. Returning existing alert.", scheme_id)
        existing = get_events(scheme_id=scheme_id, event_type="deadline_approaching", limit=1)
        if existing:
            return existing[0]

    # ── Persist via real event_log (same as scheduler) ─────────────────────────
    event = log_event(event_type, scheme_id, detail)

    log.info("=" * 60)
    log.info("DEMO EVENT INJECTED")
    log.info("  Event ID   : %s", event["event_id"])
    log.info("  Type       : %s", event_type)
    log.info("  Scheme     : %s (%s)", scheme_id, scheme.get("name", ""))
    log.info("  Detail     : %s", detail[:120])
    log.info("=" * 60)

    # ── Trigger matcher for actionable events (same as scheduler) ──────────────
    if event_type in {"new_scheme", "deadline_approaching"}:
        log.info("Triggering matcher for scheme '%s'...", scheme_id)
        from monitoring.scheduler import trigger_matching_for_scheme
        trigger_matching_for_scheme(scheme_id, schemes)
        log.info("Matcher triggered. Check data/match_results.json for fresh results.")
    else:
        log.info(
            "Event type '%s' does not trigger re-matching "
            "(only new_scheme and deadline_approaching do).",
            event_type,
        )

    return event


# ── List helper ────────────────────────────────────────────────────────────────

def list_schemes() -> None:
    """Print all available scheme IDs for demo use."""
    schemes = _load_schemes()
    scope_path = SCOPE_PATH
    try:
        with open(scope_path, "r", encoding="utf-8") as f:
            scope = json.load(f)
        included_cats = set(scope.get("included_categories", []))
    except Exception:
        included_cats = set()

    print("\nAvailable Schemes for Demo Trigger")
    print("=" * 60)
    for s in schemes:
        cat    = s.get("category", "?")
        status = s.get("status", "?")
        in_scope = "✅" if cat in included_cats else "⬜ (out of scope)"
        deadline = s.get("deadline") or "rolling"
        print(f"  {in_scope}  {s['scheme_id']}")
        print(f"       Name    : {s.get('name', '')}")
        print(f"       Category: {cat}  |  Status: {status}  |  Deadline: {deadline}")
        print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Yojana Sentinel — Demo Event Injector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--scheme", metavar="SCHEME_ID", help="Scheme ID to target")
    p.add_argument(
        "--event",
        metavar="EVENT_TYPE",
        choices=sorted(VALID_EVENT_TYPES),
        default="deadline_approaching",
        help="Type of event to inject (default: deadline_approaching)",
    )
    p.add_argument(
        "--list-schemes",
        action="store_true",
        help="List all available scheme IDs and exit",
    )
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.list_schemes:
        list_schemes()
        sys.exit(0)

    if not args.scheme:
        parser.error("--scheme is required unless --list-schemes is specified.")

    inject_event(scheme_id=args.scheme, event_type=args.event)
    print(f"\n✅ Event '{args.event}' injected for scheme '{args.scheme}'.")
    print("   Check data/event_log.json and data/match_results.json for results.")
