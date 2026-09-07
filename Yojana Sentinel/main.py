"""
main.py — Yojana Sentinel Unified Orchestrator

Single command entry point to initialize, match, draft, simulate events, and
launch the human approval web interface.

Usage:
  python main.py                     # Full end-to-end pipeline with live web approval UI
  python main.py --demo              # Include live monitoring event simulation
  python main.py --no-llm            # Run LLM-free rule checks & template fallback
  python main.py --no-server         # Batch process pipeline without launching UI
  python main.py --port 8080         # Custom port for approval web server
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("yojana_sentinel")

ROOT = Path(__file__).resolve().parent

# Imports from Yojana Sentinel modules
from db.seed import run as seed_all
from matching.run_matching import run as run_matching_pipeline
from drafting.create_draft import create_draft, DraftCreationError
from monitoring.demo_trigger import inject_event as simulate_event
from approval.app import app


def batch_create_drafts(use_llm: bool = True) -> int:
    """Generate ApplicationDraft records for all strong and partial matches."""
    match_file = ROOT / "data" / "match_results.json"
    schemes_file = ROOT / "data" / "schemes_seed.json"
    profiles_file = ROOT / "data" / "profiles_seed.json"

    if not match_file.exists():
        log.error("match_results.json not found. Run matching first.")
        return 0

    with open(match_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    with open(schemes_file, "r", encoding="utf-8") as f:
        schemes = {s["scheme_id"]: s for s in json.load(f)}
    with open(profiles_file, "r", encoding="utf-8") as f:
        profiles = {p["profile_id"]: p for p in json.load(f)}

    actionable = [r for r in results if r.get("match_status") in ("strong_match", "partial_match")]
    log.info("Found %d actionable match result(s) to draft.", len(actionable))

    created = 0
    for r in actionable:
        pid = r["profile_id"]
        sid = r["scheme_id"]
        if pid in profiles and sid in schemes:
            try:
                # If LLM disabled, template generation is handled gracefully
                draft = create_draft(
                    match_result=r,
                    profile=profiles[pid],
                    scheme=schemes[sid],
                    force_new=True,
                )
                created += 1
                log.info("Created draft %s for profile=%s scheme=%s", draft["draft_id"], pid, sid)
            except DraftCreationError as exc:
                log.warning("Could not draft for profile=%s scheme=%s: %s", pid, sid, exc)
            except Exception as exc:
                log.error("Unexpected error drafting for profile=%s scheme=%s: %s", pid, sid, exc)

    return created


def run_pipeline(
    no_llm: bool = False,
    demo: bool = False,
    no_server: bool = False,
    host: str = "127.0.0.1",
    port: int = 5000,
) -> None:
    print("\n" + "═" * 70)
    print(" 🚀 YOJANA SENTINEL — Autonomous Welfare Scheme Agent")
    print("═" * 70 + "\n")

    # ── STEP 1: Seed Database ──────────────────────────────────────────────────
    log.info("▶ STEP 1/5: Seeding Database & Catalog...")
    seed_all()

    # ── STEP 2: Execute Matching Engine ──────────────────────────────────────
    log.info("▶ STEP 2/5: Executing Rules & Matching Engine...")
    use_llm = not no_llm
    match_results = run_matching_pipeline(use_llm=use_llm)
    log.info("Matching complete: %d results generated.", len(match_results))

    # ── STEP 3: Generate Application Drafts ──────────────────────────────────
    log.info("▶ STEP 3/5: Generating Pre-filled Application Drafts...")
    drafts_created = batch_create_drafts(use_llm=use_llm)
    log.info("Draft generation complete: %d drafts ready.", drafts_created)

    # ── STEP 4: Simulated Event Injection (Optional --demo) ───────────────────
    if demo:
        log.info("▶ STEP 4/5: Injecting Demo Monitoring Event...")
        try:
            evt = simulate_event(
                scheme_id="up-scholarship-obc-2026",
                event_type="deadline_approaching",
            )
            print(f"\n⚡ Demo Monitoring Event Injected:\n   Type: {evt['event_type']}\n   Detail: {evt['detail']}\n")
        except Exception as exc:
            log.error("Demo event simulation failed: %s", exc)
    else:
        log.info("▶ STEP 4/5: Demo event injection skipped (pass --demo to enable).")

    # ── STEP 5: Launch Approval Server ────────────────────────────────────────
    if no_server:
        log.info("▶ STEP 5/5: Skipping Web Server (--no-server passed). Pipeline complete.")
        print("\n✅ All processing completed successfully.")
        return

    log.info(f"▶ STEP 5/5: Starting Human Approval Web UI on http://{host}:{port} ...")
    print(f"\n🌐 Approval Dashboard ready at: http://{host}:{port}")
    print("   Press Ctrl+C to stop the server.\n")

    app.run(host=host, port=port, debug=False)


def main():
    parser = argparse.ArgumentParser(
        description="Yojana Sentinel — Autonomous Welfare Scheme Monitoring & Application Drafting Agent"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM condition review and prose writer (pure rule/template mode)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Simulate a live monitoring event during startup",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Run pipeline batch processing without starting web server UI",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for approval web server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for approval web server (default: 5000)",
    )

    args = parser.parse_args()
    run_pipeline(
        no_llm=args.no_llm,
        demo=args.demo,
        no_server=args.no_server,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
