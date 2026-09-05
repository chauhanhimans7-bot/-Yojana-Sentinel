"""
tests/test_matcher.py

Unit tests for matching/matcher.py
Covers:
- Hard rule failure short-circuits to not_eligible (score 0)
- Document completeness score calculation & missing doc flagging
- LLM likely_fail returning not_eligible
- LLM unclear pushing status to needs_review
- Partial match status for eligible profiles with missing paperwork
"""

import pytest
from unittest.mock import patch
from matching.matcher import match, STRONG_THRESHOLD, PARTIAL_THRESHOLD


def base_profile(**kwargs) -> dict:
    p = {
        "profile_id": "test-prof-01",
        "display_name": "Test Citizen",
        "age": 25,
        "gender": "female",
        "state": "Uttar Pradesh",
        "annual_income": 80000,
        "category": "obc",
        "occupation": "student",
        "owns_land": False,
        "documents_available": ["Aadhaar card", "income certificate", "caste certificate"],
    }
    p.update(kwargs)
    return p


def base_scheme(**kwargs) -> dict:
    s = {
        "scheme_id": "test-scheme-01",
        "name": "Test Welfare Scheme",
        "eligibility_rules": {
            "min_age": 18,
            "max_age": 35,
            "states": ["Uttar Pradesh"],
            "max_annual_income": 200000,
            "categories": ["obc"],
            "occupation": ["student"],
            "gender": "any",
            "land_ownership_required": None,
            "other_conditions": [],
        },
        "required_documents": ["Aadhaar card", "income certificate", "caste certificate"],
        "application_fields": [],
    }
    s.update(kwargs)
    return s


class TestMatcherHardRules:
    def test_hard_rule_fail_returns_not_eligible(self):
        """Profile failing hard rule (e.g. age too old) -> not_eligible with score 0."""
        p = base_profile(age=45)
        s = base_scheme()
        res = match(p, s, run_llm=False)
        assert res["match_status"] == "not_eligible"
        assert res["match_score"] == 0
        assert any("FAILED_RULE: age" in m for m in res["missing_info"])

    def test_hard_rule_pass_returns_match(self):
        """Profile passing all hard rules and docs -> strong_match."""
        p = base_profile()
        s = base_scheme()
        res = match(p, s, run_llm=False)
        assert res["match_status"] == "strong_match"
        assert res["match_score"] == 100.0


class TestDocumentCompleteness:
    def test_missing_some_documents_returns_partial_match(self):
        """Missing 1 out of 3 required documents -> partial_match."""
        p = base_profile(documents_available=["Aadhaar card", "income certificate"])
        s = base_scheme()
        res = match(p, s, run_llm=False)
        assert res["match_status"] == "partial_match"
        assert res["match_score"] == pytest.approx(66.7, 0.1)
        assert any("MISSING_DOCUMENT: caste certificate" in m for m in res["missing_info"])

    def test_missing_all_documents_returns_partial_match(self):
        """Person is eligible demographically but missing all docs -> partial_match with score 0."""
        p = base_profile(documents_available=[])
        s = base_scheme()
        res = match(p, s, run_llm=False)
        assert res["match_status"] == "partial_match"
        assert res["match_score"] == 0.0
        assert len(res["missing_info"]) == 3


class TestLLMOtherConditions:
    @patch("matching.matcher.review_other_conditions")
    def test_llm_likely_fail_returns_not_eligible(self, mock_review):
        """LLM verdict likely_fail on other_conditions -> not_eligible."""
        mock_review.return_value = [
            {"condition": "Must not be availing other scholarship", "verdict": "likely_fail", "reasoning": "Availing national scholarship."}
        ]
        p = base_profile()
        s = base_scheme(eligibility_rules={**base_scheme()["eligibility_rules"], "other_conditions": ["Must not be availing other scholarship"]})
        res = match(p, s, run_llm=True)
        assert res["match_status"] == "not_eligible"
        assert res["match_score"] == 0

    @patch("matching.matcher.review_other_conditions")
    def test_llm_unclear_pushes_to_needs_review(self, mock_review):
        """LLM verdict unclear on other_conditions -> needs_review."""
        mock_review.return_value = [
            {"condition": "Minimum 50% attendance", "verdict": "unclear", "reasoning": "Attendance certificate not attached."}
        ]
        p = base_profile()
        s = base_scheme(eligibility_rules={**base_scheme()["eligibility_rules"], "other_conditions": ["Minimum 50% attendance"]})
        res = match(p, s, run_llm=True)
        assert res["match_status"] == "needs_review"
        assert res["match_score"] < STRONG_THRESHOLD
