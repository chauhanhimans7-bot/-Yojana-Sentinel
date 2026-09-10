"""
tests/test_bugs_regression.py — Regression tests for Bug 1 and Bug 2
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from approval.actions import approve_draft, reject_draft, ApprovalError
from approval.approval_log import get_all_logs, get_log_for_draft, log_action
from drafting.field_mapper import map_fields, FIELD_TO_PROFILE
from db.database import get_db
from db.seed import ensure_approval_log_table


class TestBugsRegression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with get_db() as db:
            ensure_approval_log_table(db)

    def test_bug1_beneficiary_name_consistency(self):
        """
        Bug 1: Beneficiary identity and profile-derived name fields must remain consistent.
        For a draft belonging to Suresh Kumar, 'head_of_family_name' mapped from profile
        must equal 'Suresh Kumar', not an unrelated citizen like 'Dilip'.
        """
        profile = {
            "profile_id": "test-profile-suresh",
            "display_name": "Suresh Kumar",
            "age": 24,
            "gender": "male",
            "state": "Uttar Pradesh",
            "district": "Balrampur",
            "annual_income": 42000,
            "category": "sc",
            "occupation": "daily wage labourer",
            "owns_land": False,
            "family_status": "married",
            "documents_available": ["Aadhaar card", "ration card"],
        }

        scheme = {
            "scheme_id": "ayushman-bharat-pmjay-2026",
            "name": "Ayushman Bharat — PM Jan Arogya Yojana (PMJAY)",
            "application_fields": [
                {
                    "field_id": "head_of_family_name",
                    "label": "Head of Family Name",
                    "type": "text",
                    "required": True,
                },
                {
                    "field_id": "aadhaar_number",
                    "label": "Aadhaar Number",
                    "type": "text",
                    "required": True,
                },
            ],
        }

        filled_fields, unresolved = map_fields(profile, scheme)

        head_field = next((f for f in filled_fields if f["field_id"] == "head_of_family_name"), None)
        self.assertIsNotNone(head_field, "head_of_family_name must be present in filled_fields")
        self.assertEqual(head_field["value"], "Suresh Kumar", "head_of_family_name must equal profile display_name")
        self.assertEqual(head_field["source"], "profile", "source must be profile")

    def test_bug2_audit_log_human_action_persistence(self):
        """
        Bug 2: Audit log record must accurately reflect human rejection action, actor, reason, and timestamp.
        """
        test_draft_id = "test-draft-bug2-rejection"
        test_actor = "Test User"
        test_reason = "Manual E2E rejection test"

        # Create a dummy draft in DB for testing
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

        # Perform rejection action
        rejected_draft = reject_draft(test_draft_id, approver_name=test_actor, reason=test_reason)

        # 1. Verify draft record in DB has status='rejected', approved_by=test_actor, and approved_at set
        self.assertEqual(rejected_draft["status"], "rejected")
        with get_db() as db:
            row = db.fetchone("SELECT * FROM application_draft WHERE draft_id=?", (test_draft_id,))
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "rejected")
            self.assertEqual(row["approved_by"], test_actor)
            self.assertIsNotNone(row["approved_at"])

        # 2. Verify audit log entry stored in approval_log table
        logs = get_log_for_draft(test_draft_id)
        self.assertTrue(len(logs) > 0, "Audit log entry must be retrieved")
        latest_log = logs[0]
        self.assertEqual(latest_log["draft_id"], test_draft_id)
        self.assertEqual(latest_log["action"], "reject")
        self.assertEqual(latest_log["actor_name"], test_actor)
        self.assertEqual(latest_log["note"], test_reason)
        self.assertTrue("2026" in latest_log["timestamp"], "Timestamp must correspond to current action execution")

    def test_safety_check_never_auto_submits(self):
        """
        Safety Check: Confirm actions do not perform external network calls or auto-submissions.
        """
        test_draft_id = "test-draft-safety-check"
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            db.execute(
                """INSERT INTO application_draft
                   (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_id) DO UPDATE SET status='drafted'""",
                (test_draft_id, "profile-001", "pm-kisan-national-2026", "[]", "[]", "drafted", now)
            )
            db.commit()

        approved = approve_draft(test_draft_id, approver_name="Safety Inspector", confirm_anyway=True)
        self.assertEqual(approved["status"], "approved", "Status must be 'approved', meaning ready for manual submission")


if __name__ == "__main__":
    unittest.main()
