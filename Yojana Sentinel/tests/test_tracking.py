"""
tests/test_tracking.py

Unit tests for tracking/status_store.py and tracking/staleness_checker.py
Tests application status transitions, staleness windows, and notification triggers.
"""

import pytest
import json
from pathlib import Path
from tracking.status_store import mark_submitted, update_status, _conn
from tracking.staleness_checker import find_stale_drafts, LOG_PATH

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"


@pytest.fixture
def sample_submitted_draft():
    draft_id = "test-track-888"
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO application_draft
               (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, draft_text, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, "profile-001", "up-scholarship-obc-2026", "[]", "[]", "Tracking text", "approved", "2026-08-01T10:00:00Z")
        )
    yield draft_id
    with _conn() as conn:
        conn.execute("DELETE FROM application_draft WHERE draft_id=?", (draft_id,))


class TestStatusTracking:
    def test_mark_submitted_and_update(self, sample_submitted_draft):
        draft = mark_submitted(sample_submitted_draft, submitted_at="2026-08-02T10:00:00Z")
        assert draft["status"] == "submitted"

        updated = update_status(sample_submitted_draft, new_status="pending", note="Under review by officer")
        assert updated["status"] == "pending"

    def test_staleness_checker_identifies_old_draft(self, sample_submitted_draft):
        # Set status to submitted with an old timestamp in transition log
        with _conn() as conn:
            conn.execute("UPDATE application_draft SET status='submitted' WHERE draft_id=?", (sample_submitted_draft,))

        old_log = [{
            "draft_id": sample_submitted_draft,
            "old_status": "approved",
            "new_status": "submitted",
            "timestamp": "2026-08-01T10:00:00Z",
            "note": "Manual submission"
        }]
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(old_log, f)

        stale = find_stale_drafts(threshold_days=1)
        stale_ids = [d["draft_id"] for d in stale]
        assert sample_submitted_draft in stale_ids
