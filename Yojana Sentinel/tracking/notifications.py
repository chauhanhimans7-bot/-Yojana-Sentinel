"""
tracking/notifications.py

Mock notification delivery system for Yojana Sentinel.
Automatically triggered by tracking.staleness_checker.find_stale_drafts().

Stores generated notifications in data/notifications_log.json so the "agent follows up"
story can be rendered in the UI / CLI demo without needing real SMS or WhatsApp APIs.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tracking.staleness_checker import find_stale_drafts

log = logging.getLogger(__name__)

ROOT     = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "notifications_log.json"


def _load_notifications() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_notifications(items: list[dict]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def trigger_staleness_notifications(threshold_days: Optional[int] = None) -> list[dict]:
    """
    Run staleness check and automatically emit follow-up notifications for all stale drafts.
    Returns list of newly generated notification dicts.
    """
    stale_drafts = find_stale_drafts(threshold_days)
    if not stale_drafts:
        log.info("No stale drafts requiring notification.")
        return []

    existing = _load_notifications()
    existing_ids = {n.get("draft_id") for n in existing if n.get("type") == "staleness_nudge"}

    new_notifications = []
    now_str = datetime.now(timezone.utc).isoformat()

    for item in stale_drafts:
        did = item["draft_id"]
        # Avoid duplicate notification for the same draft if already notified
        if did in existing_ids:
            continue

        msg = (
            f"🔔 Follow-up Nudge for {item['profile_name']}:\n"
            f"Application for '{item['scheme_name']}' has been in '{item['status']}' state "
            f"for {item['days_inactive']} days without updates.\n"
            f"Suggested Action: {item['suggested_action']}"
        )

        nudge = {
            "notification_id": f"notif-{uuid.uuid4().hex[:10]}",
            "type":            "staleness_nudge",
            "draft_id":        did,
            "profile_name":    item["profile_name"],
            "scheme_name":     item["scheme_name"],
            "days_inactive":   item["days_inactive"],
            "message":         msg,
            "created_at":      now_str,
            "read":            False,
        }
        new_notifications.append(nudge)

    if new_notifications:
        all_items = new_notifications + existing
        _save_notifications(all_items)
        log.info("Triggered %d new staleness notification(s).", len(new_notifications))
        for n in new_notifications:
            log.info("  → [NOTIF] %s", n["message"].replace("\n", " | "))

    return new_notifications


def get_all_notifications() -> list[dict]:
    """Return all notifications, newest first."""
    return _load_notifications()
