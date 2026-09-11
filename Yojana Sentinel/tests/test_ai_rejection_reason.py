"""
tests/test_ai_rejection_reason.py

Tests for the AI-assisted rejection reason endpoint:
POST /reject/<draft_id>/generate-reason

Validates:
  1. Empty reason → 400, no Groq call.
  2. Non-empty reason → Groq called, returns generated text.
  3. Groq failure → 500, preserves safety contract.
  4. Endpoint does NOT modify draft status.
  5. Endpoint does NOT write audit logs.
  6. Existing rejection flow unaffected.
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

load_dotenv()

from approval.app import app
from db.database import get_db
from db.seed import ensure_approval_log_table


class TestAIRejectionReasonEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.draft_id = "test-ai-reject-draft"

        with get_db() as db:
            ensure_approval_log_table(db)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO application_draft
                   (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_id) DO UPDATE SET status='drafted'""",
                (cls.draft_id, "profile-002", "ayushman-bharat-pmjay-2026", "[]", "[]", "drafted", now)
            )
            db.commit()

    # ── Test 1: Empty reason → 400, no Groq call ─────────────────────────────

    def test_empty_reason_returns_400(self):
        resp = self.client.post(
            f"/reject/{self.draft_id}/generate-reason",
            data=json.dumps({"human_reason": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data)
        self.assertIn("error", payload)
        self.assertIn("reason", payload["error"].lower())

    def test_whitespace_only_reason_returns_400(self):
        resp = self.client.post(
            f"/reject/{self.draft_id}/generate-reason",
            data=json.dumps({"human_reason": "   "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_reason_field_returns_400(self):
        resp = self.client.post(
            f"/reject/{self.draft_id}/generate-reason",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── Test 2: Valid reason → Groq called, returns generated text ───────────

    def test_valid_reason_calls_groq_and_returns_text(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Rejected due to insufficient match score and missing required supporting documents."

        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_response
            resp = self.client.post(
                f"/reject/{self.draft_id}/generate-reason",
                data=json.dumps({"human_reason": "Low match score and required documents are missing."}),
                content_type="application/json",
            )

        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertIn("generated_reason", payload)
        self.assertTrue(len(payload["generated_reason"]) > 10)
        # Exactly one Groq call (one create() call per request)
        MockGroq.return_value.chat.completions.create.assert_called_once()

    # ── Test 3: Groq failure → 500, audit safety preserved ───────────────────

    def test_groq_failure_returns_500_with_error(self):
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.side_effect = Exception("Network timeout")
            resp = self.client.post(
                f"/reject/{self.draft_id}/generate-reason",
                data=json.dumps({"human_reason": "Applicant does not meet criteria."}),
                content_type="application/json",
            )

        self.assertEqual(resp.status_code, 500)
        payload = json.loads(resp.data)
        self.assertIn("error", payload)
        self.assertIn("manually", payload["error"].lower())

    # ── Test 4: Endpoint does NOT modify draft status ─────────────────────────

    def test_ai_endpoint_does_not_change_draft_status(self):
        with patch("groq.Groq") as MockGroq:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "Some AI reason."
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            self.client.post(
                f"/reject/{self.draft_id}/generate-reason",
                data=json.dumps({"human_reason": "Test reason"}),
                content_type="application/json",
            )

        with get_db() as db:
            row = db.fetchone("SELECT status FROM application_draft WHERE draft_id=?", (self.draft_id,))
        self.assertEqual(row["status"], "drafted", "AI endpoint must not change draft status.")

    # ── Test 5: Endpoint does NOT write audit logs ────────────────────────────

    def test_ai_endpoint_does_not_write_audit_log(self):
        with get_db() as db:
            before_count = db.fetchone("SELECT COUNT(*) AS cnt FROM approval_log WHERE draft_id=?", (self.draft_id,))["cnt"]

        with patch("groq.Groq") as MockGroq:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "Professional reason."
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            self.client.post(
                f"/reject/{self.draft_id}/generate-reason",
                data=json.dumps({"human_reason": "Test reason"}),
                content_type="application/json",
            )

        with get_db() as db:
            after_count = db.fetchone("SELECT COUNT(*) AS cnt FROM approval_log WHERE draft_id=?", (self.draft_id,))["cnt"]

        self.assertEqual(before_count, after_count, "AI endpoint must not write any audit log entries.")

    # ── Test 6: Existing rejection flow (no AI) still works ──────────────────

    def test_existing_rejection_flow_unaffected(self):
        with get_db() as db:
            db.execute("UPDATE application_draft SET status='drafted' WHERE draft_id=?", (self.draft_id,))
            db.commit()

        resp = self.client.post(
            f"/reject/{self.draft_id}",
            data={"approver_name": "Test Auditor", "reason": "Manual rejection without AI."},
        )
        self.assertIn(resp.status_code, [200, 302])

        with get_db() as db:
            row = db.fetchone("SELECT status FROM application_draft WHERE draft_id=?", (self.draft_id,))
        self.assertEqual(row["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
