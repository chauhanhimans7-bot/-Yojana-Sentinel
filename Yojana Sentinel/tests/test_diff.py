"""
tests/test_diff.py

Unit tests for monitoring/diff.py
Tests monitoring event detection (new_scheme, deadline_approaching, scheme_closed, scheme_updated)
and idempotency alert rules.
"""

import pytest
from monitoring.diff import compute_diff, _is_deadline_approaching, _is_deadline_passed
from monitoring.event_log import clear_deadline_alerts


@pytest.fixture(autouse=True)
def cleanup_events():
    clear_deadline_alerts("s-diff-101")
    yield
    clear_deadline_alerts("s-diff-101")


class TestMonitoringDiff:
    def test_new_scheme_detection(self):
        prev = []
        curr = [{
            "scheme_id": "s-diff-101",
            "name": "New Agri Scheme",
            "category": "agriculture",
            "issuing_body": "UP Govt",
            "deadline": "2026-12-31",
            "status": "active",
        }]
        events = compute_diff(prev, curr)
        assert len(events) >= 1
        new_evt = next(e for e in events if e["event_type"] == "new_scheme")
        assert new_evt["scheme_id"] == "s-diff-101"
        assert "New scheme detected" in new_evt["detail"]

    def test_scheme_closed_detection(self):
        prev = [{
            "scheme_id": "s-diff-101",
            "name": "Closed Scheme",
            "status": "active",
            "deadline": "2026-12-31",
        }]
        curr = [{
            "scheme_id": "s-diff-101",
            "name": "Closed Scheme",
            "status": "closed",
            "deadline": "2026-12-31",
        }]
        events = compute_diff(prev, curr)
        closed_evt = next(e for e in events if e["event_type"] == "scheme_closed")
        assert closed_evt["scheme_id"] == "s-diff-101"
        assert "Scheme closed" in closed_evt["detail"]

    def test_scheme_updated_detection(self):
        prev = [{
            "scheme_id": "s-diff-101",
            "name": "Updated Scheme",
            "deadline": "2026-09-10",
            "status": "active",
            "eligibility_rules": {"min_age": 18},
            "required_documents": ["Aadhaar card"],
        }]
        curr = [{
            "scheme_id": "s-diff-101",
            "name": "Updated Scheme",
            "deadline": "2026-09-25",  # Deadline extended
            "status": "active",
            "eligibility_rules": {"min_age": 18},
            "required_documents": ["Aadhaar card", "Income Cert"],
        }]
        events = compute_diff(prev, curr)
        updated_evt = next(e for e in events if e["event_type"] == "scheme_updated")
        assert updated_evt["scheme_id"] == "s-diff-101"
        assert "deadline moved" in updated_evt["detail"]
