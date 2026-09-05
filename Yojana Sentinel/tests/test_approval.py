"""
tests/test_approval.py

Unit tests for approval/actions.py and approval/approval_log.py
Tests draft approval, rejection, editing, and audit logging.
"""

import pytest
from pathlib import Path
from approval.actions import approve_draft, reject_draft, request_edit, _conn

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"


@pytest.fixture
def sample_draft_id():
    """Create a temporary test draft in DB using valid foreign keys."""
    draft_id = "test-draft-999"
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO application_draft
               (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, draft_text, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, "profile-001", "up-scholarship-obc-2026", "[]", "[]", "Sample draft text", "drafted", "2026-09-01T10:00:00Z")
        )
    yield draft_id
    with _conn() as conn:
        conn.execute("DELETE FROM application_draft WHERE draft_id=?", (draft_id,))


class TestApprovalActions:
    def test_approve_draft_success(self, sample_draft_id):
        draft = approve_draft(sample_draft_id, approver_name="Vikram (Son)")
        assert draft["status"] == "approved"
        assert draft["approved_by"] == "Vikram (Son)"
        assert draft["approved_at"] is not None

    def test_reject_draft_success(self, sample_draft_id):
        draft = reject_draft(sample_draft_id, approver_name="Vikram (Son)", reason="No longer interested")
        assert draft["status"] == "rejected"

    def test_request_edit(self, sample_draft_id):
        new_fields = [{"field_id": "applicant_name", "value": "Ramkali Devi Updated"}]
        draft = request_edit(sample_draft_id, editor_name="Vikram (Son)", edited_fields=new_fields)
        assert draft["status"] == "drafted"
        assert draft["filled_fields"] == [{"field_id": "applicant_name", "value": "Ramkali Devi Updated", "source": "profile"}]
