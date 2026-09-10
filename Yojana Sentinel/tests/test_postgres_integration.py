"""
tests/test_postgres_integration.py — Dedicated PostgreSQL / Supabase Integration Test
"""

import json
import unittest
from datetime import datetime, timezone

from approval.actions import reject_draft
from approval.approval_log import get_all_logs, get_log_for_draft
from db.database import get_db
from db.seed import ensure_approval_log_table


class TestPostgresIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with get_db() as db:
            ensure_approval_log_table(db)
            cls.is_postgres = db.is_postgres

    def test_supabase_postgres_approval_log_persistence(self):
        """
        Verify that approval_log table exists and persists human actions directly
        in PostgreSQL / Supabase DB.
        """
        test_draft_id = "test-postgres-e2e-draft"
        test_actor = "Test User (Postgres Integration)"
        test_reason = "Production E2E audit verification"

        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            db.execute(
                """INSERT INTO application_draft
                   (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_id) DO UPDATE SET status='drafted'""",
                (test_draft_id, "profile-002", "up-sc-postmatric-scholarship-2026", "[]", "[]", "drafted", now)
            )
            db.commit()

        # Reject draft
        rejected = reject_draft(test_draft_id, approver_name=test_actor, reason=test_reason)
        self.assertEqual(rejected["status"], "rejected")

        # Query approval_log directly from database
        with get_db() as db:
            if db.is_postgres:
                rows = db.fetchall("SELECT * FROM approval_log WHERE draft_id = %s", (test_draft_id,))
            else:
                rows = db.fetchall("SELECT * FROM approval_log WHERE draft_id = ?", (test_draft_id,))

        self.assertTrue(len(rows) > 0, "approval_log DB row must exist")
        db_log = dict(rows[0])
        self.assertEqual(db_log["draft_id"], test_draft_id)
        self.assertEqual(db_log["action"], "reject")
        self.assertEqual(db_log["actor_name"], test_actor)
        self.assertEqual(db_log["note"], test_reason)

        # Verify get_all_logs reads from DB
        logs = get_log_for_draft(test_draft_id)
        self.assertTrue(len(logs) > 0)
        self.assertEqual(logs[0]["actor_name"], test_actor)


if __name__ == "__main__":
    unittest.main()
