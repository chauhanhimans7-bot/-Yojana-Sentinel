"""
tests/test_rules_engine.py

Unit tests for matching/rules_engine.py
Each rule function has at least one passing and one failing test.
Also covers the edge case: all-null scheme rules + profile with no occupation.
"""

import pytest
from matching.rules_engine import (
    check_age,
    check_state,
    check_income,
    check_category,
    check_occupation,
    check_gender,
    check_land_ownership,
    run_all_rules,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def profile(**kwargs) -> dict:
    base = {
        "profile_id": "test-001",
        "display_name": "Test User",
        "age": 30,
        "gender": "female",
        "state": "Uttar Pradesh",
        "annual_income": 80000,
        "category": "obc",
        "occupation": "farmer",
        "owns_land": True,
        "documents_available": ["Aadhaar card", "bank passbook"],
    }
    base.update(kwargs)
    return base


def scheme_rules(**kwargs) -> dict:
    """Build a minimal scheme dict with customizable eligibility_rules."""
    base_rules = {
        "min_age": None,
        "max_age": None,
        "states": [],
        "max_annual_income": None,
        "categories": [],
        "occupation": [],
        "gender": "any",
        "land_ownership_required": None,
        "other_conditions": [],
    }
    base_rules.update(kwargs)
    return {"scheme_id": "test-scheme", "name": "Test Scheme", "eligibility_rules": base_rules,
            "required_documents": [], "application_fields": []}


# ── check_age ─────────────────────────────────────────────────────────────────

class TestCheckAge:
    def test_pass_within_range(self):
        p = profile(age=25)
        s = scheme_rules(min_age=18, max_age=40)
        assert check_age(p, s) == "pass"

    def test_fail_too_young(self):
        p = profile(age=15)
        s = scheme_rules(min_age=18, max_age=60)
        assert check_age(p, s) == "fail"

    def test_fail_too_old(self):
        p = profile(age=65)
        s = scheme_rules(min_age=18, max_age=55)
        assert check_age(p, s) == "fail"

    def test_not_applicable_no_restriction(self):
        p = profile(age=100)
        s = scheme_rules(min_age=None, max_age=None)
        assert check_age(p, s) == "not_applicable"

    def test_not_applicable_no_age_in_profile(self):
        p = profile(age=None)
        s = scheme_rules(min_age=18, max_age=60)
        assert check_age(p, s) == "not_applicable"

    def test_pass_exactly_min_age(self):
        p = profile(age=18)
        s = scheme_rules(min_age=18, max_age=None)
        assert check_age(p, s) == "pass"

    def test_pass_exactly_max_age(self):
        p = profile(age=60)
        s = scheme_rules(min_age=None, max_age=60)
        assert check_age(p, s) == "pass"


# ── check_state ───────────────────────────────────────────────────────────────

class TestCheckState:
    def test_pass_state_in_list(self):
        p = profile(state="Uttar Pradesh")
        s = scheme_rules(states=["Uttar Pradesh", "Bihar"])
        assert check_state(p, s) == "pass"

    def test_fail_state_not_in_list(self):
        p = profile(state="Maharashtra")
        s = scheme_rules(states=["Uttar Pradesh"])
        assert check_state(p, s) == "fail"

    def test_not_applicable_empty_states(self):
        p = profile(state="Kerala")
        s = scheme_rules(states=[])
        assert check_state(p, s) == "not_applicable"

    def test_not_applicable_no_profile_state(self):
        p = profile(state="")
        s = scheme_rules(states=["Uttar Pradesh"])
        assert check_state(p, s) == "not_applicable"


# ── check_income ──────────────────────────────────────────────────────────────

class TestCheckIncome:
    def test_pass_income_below_ceiling(self):
        p = profile(annual_income=60000)
        s = scheme_rules(max_annual_income=100000)
        assert check_income(p, s) == "pass"

    def test_fail_income_above_ceiling(self):
        p = profile(annual_income=300000)
        s = scheme_rules(max_annual_income=200000)
        assert check_income(p, s) == "fail"

    def test_pass_income_exactly_at_ceiling(self):
        p = profile(annual_income=200000)
        s = scheme_rules(max_annual_income=200000)
        assert check_income(p, s) == "pass"

    def test_not_applicable_null_ceiling(self):
        p = profile(annual_income=9999999)
        s = scheme_rules(max_annual_income=None)
        assert check_income(p, s) == "not_applicable"

    def test_not_applicable_no_profile_income(self):
        p = profile(annual_income=None)
        s = scheme_rules(max_annual_income=100000)
        assert check_income(p, s) == "not_applicable"


# ── check_category ────────────────────────────────────────────────────────────

class TestCheckCategory:
    def test_pass_category_in_list(self):
        p = profile(category="obc")
        s = scheme_rules(categories=["obc", "sc"])
        assert check_category(p, s) == "pass"

    def test_fail_category_not_in_list(self):
        p = profile(category="general")
        s = scheme_rules(categories=["sc", "st", "obc"])
        assert check_category(p, s) == "fail"

    def test_not_applicable_empty_categories(self):
        p = profile(category="general")
        s = scheme_rules(categories=[])
        assert check_category(p, s) == "not_applicable"

    def test_case_insensitive_match(self):
        p = profile(category="OBC")
        s = scheme_rules(categories=["obc"])
        assert check_category(p, s) == "pass"


# ── check_occupation ──────────────────────────────────────────────────────────

class TestCheckOccupation:
    def test_pass_exact_match(self):
        p = profile(occupation="farmer")
        s = scheme_rules(occupation=["farmer"])
        assert check_occupation(p, s) == "pass"

    def test_pass_substring_match(self):
        p = profile(occupation="small farmer")
        s = scheme_rules(occupation=["farmer"])
        assert check_occupation(p, s) == "pass"

    def test_fail_no_match(self):
        p = profile(occupation="teacher")
        s = scheme_rules(occupation=["farmer", "labourer"])
        assert check_occupation(p, s) == "fail"

    def test_not_applicable_empty_occupation(self):
        p = profile(occupation="anything")
        s = scheme_rules(occupation=[])
        assert check_occupation(p, s) == "not_applicable"

    def test_not_applicable_missing_profile_occupation(self):
        p = profile(occupation=None)
        s = scheme_rules(occupation=["farmer"])
        assert check_occupation(p, s) == "not_applicable"


# ── check_gender ──────────────────────────────────────────────────────────────

class TestCheckGender:
    def test_pass_matching_gender(self):
        p = profile(gender="female")
        s = scheme_rules(gender="female")
        assert check_gender(p, s) == "pass"

    def test_fail_wrong_gender(self):
        p = profile(gender="male")
        s = scheme_rules(gender="female")
        assert check_gender(p, s) == "fail"

    def test_not_applicable_any(self):
        p = profile(gender="other")
        s = scheme_rules(gender="any")
        assert check_gender(p, s) == "not_applicable"

    def test_not_applicable_missing_profile_gender(self):
        p = profile(gender=None)
        s = scheme_rules(gender="female")
        assert check_gender(p, s) == "not_applicable"


# ── check_land_ownership ──────────────────────────────────────────────────────

class TestCheckLandOwnership:
    def test_pass_owns_land_required(self):
        p = profile(owns_land=True)
        s = scheme_rules(land_ownership_required=True)
        assert check_land_ownership(p, s) == "pass"

    def test_fail_does_not_own_land_but_required(self):
        p = profile(owns_land=False)
        s = scheme_rules(land_ownership_required=True)
        assert check_land_ownership(p, s) == "fail"

    def test_pass_no_land_when_not_required(self):
        p = profile(owns_land=False)
        s = scheme_rules(land_ownership_required=False)
        assert check_land_ownership(p, s) == "pass"

    def test_fail_has_land_when_must_not_own(self):
        p = profile(owns_land=True)
        s = scheme_rules(land_ownership_required=False)
        assert check_land_ownership(p, s) == "fail"

    def test_not_applicable_null_requirement(self):
        p = profile(owns_land=True)
        s = scheme_rules(land_ownership_required=None)
        assert check_land_ownership(p, s) == "not_applicable"

    def test_handles_integer_sqlite_bool(self):
        """SQLite stores booleans as 0/1 integers — must be handled."""
        p = profile(owns_land=1)   # SQLite integer representation
        s = scheme_rules(land_ownership_required=True)
        assert check_land_ownership(p, s) == "pass"

        p2 = profile(owns_land=0)
        assert check_land_ownership(p2, s) == "fail"


# ── Edge case: all-null scheme (zero restrictions) ────────────────────────────

class TestAllNullScheme:
    """
    Edge case from phase spec: a scheme with zero restrictions on every field
    (all nulls / empty arrays) must not return any 'fail' results.
    """
    def test_no_fails_when_scheme_has_no_restrictions(self):
        p = profile()
        s = scheme_rules()  # All defaults → all null/empty
        results = run_all_rules(p, s)
        for rule_name, result in results.items():
            assert result != "fail", (
                f"Rule '{rule_name}' returned 'fail' for an all-null scheme — should be 'not_applicable'."
            )

    def test_profile_missing_occupation_against_null_occupation_scheme(self):
        """Profile with no occupation against scheme with no occupation restriction → not_applicable."""
        p = profile(occupation=None)
        s = scheme_rules(occupation=[])
        assert check_occupation(p, s) == "not_applicable"

    def test_profile_missing_occupation_against_restricted_scheme(self):
        """Profile with no occupation against scheme that DOES restrict occupation → not_applicable (not fail)."""
        p = profile(occupation=None)
        s = scheme_rules(occupation=["farmer"])
        # Missing profile field → not_applicable; matcher.py escalates to needs_review
        assert check_occupation(p, s) == "not_applicable"


# ── run_all_rules composite ───────────────────────────────────────────────────

class TestRunAllRules:
    def test_returns_all_seven_dimensions(self):
        p = profile()
        s = scheme_rules()
        results = run_all_rules(p, s)
        expected_keys = {"age", "state", "income", "category", "occupation", "gender", "land_ownership"}
        assert set(results.keys()) == expected_keys

    def test_hard_fail_visible_in_composite(self):
        p = profile(age=10)
        s = scheme_rules(min_age=18)
        results = run_all_rules(p, s)
        assert results["age"] == "fail"
