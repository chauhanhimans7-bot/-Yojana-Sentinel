"""
matching/rules_engine.py

Pure, deterministic eligibility rule functions.
Each function accepts a CitizenProfile dict and a Scheme dict and returns:
    "pass"            — the profile satisfies this rule
    "fail"            — the profile is definitively ineligible on this rule
    "not_applicable"  — the rule does not apply (nulls / empty lists on scheme side)

Rules:
  - All functions are side-effect-free and LLM-free.
  - A missing / null value on the SCHEME side means "no restriction" → pass / not_applicable.
  - A missing / null value on the PROFILE side that the rule NEEDS → "needs_review"
    (handled in matcher.py — these functions return "not_applicable" to signal
     the field is not constraining, but matcher.py checks profile completeness separately).
  - These functions cover the seven structured eligibility dimensions.
  - other_conditions is handled separately in other_conditions_reviewer.py.
"""

from typing import Literal

RuleResult = Literal["pass", "fail", "not_applicable"]


# ── Age ───────────────────────────────────────────────────────────────────────

def check_age(profile: dict, scheme: dict) -> RuleResult:
    """
    Check min_age / max_age constraints.
    Both null → not_applicable (no age restriction).
    Profile has no age recorded → not_applicable (matcher will flag as missing_info).
    """
    rules = scheme.get("eligibility_rules", {})
    min_age = rules.get("min_age")
    max_age = rules.get("max_age")

    if min_age is None and max_age is None:
        return "not_applicable"

    age = profile.get("age")
    if age is None:
        # Cannot evaluate — treated as not_applicable here;
        # matcher.py will detect the missing field and mark needs_review.
        return "not_applicable"

    if min_age is not None and age < min_age:
        return "fail"
    if max_age is not None and age > max_age:
        return "fail"

    return "pass"


# ── State ─────────────────────────────────────────────────────────────────────

def check_state(profile: dict, scheme: dict) -> RuleResult:
    """
    Check state eligibility.
    Empty list = no state restriction → pass for everyone.
    """
    rules = scheme.get("eligibility_rules", {})
    allowed_states = rules.get("states", [])

    if not allowed_states:
        return "not_applicable"  # All-India / no restriction

    profile_state = (profile.get("state") or "").strip()
    if not profile_state:
        return "not_applicable"  # Missing profile field — matcher handles

    if profile_state in allowed_states:
        return "pass"
    return "fail"


# ── Income ────────────────────────────────────────────────────────────────────

def check_income(profile: dict, scheme: dict) -> RuleResult:
    """
    Check maximum annual income ceiling.
    null = no income restriction → not_applicable (pass for everyone).
    """
    rules = scheme.get("eligibility_rules", {})
    max_income = rules.get("max_annual_income")

    if max_income is None:
        return "not_applicable"

    income = profile.get("annual_income")
    if income is None:
        return "not_applicable"  # Missing field — matcher handles

    if income <= max_income:
        return "pass"
    return "fail"


# ── Category ──────────────────────────────────────────────────────────────────

def check_category(profile: dict, scheme: dict) -> RuleResult:
    """
    Check social category (general | obc | sc | st | ews | other).
    Empty list = no category restriction → not_applicable.
    """
    rules = scheme.get("eligibility_rules", {})
    allowed = rules.get("categories", [])

    if not allowed:
        return "not_applicable"

    profile_cat = (profile.get("category") or "").strip().lower()
    if not profile_cat:
        return "not_applicable"

    if profile_cat in [c.lower() for c in allowed]:
        return "pass"
    return "fail"


# ── Occupation ────────────────────────────────────────────────────────────────

def check_occupation(profile: dict, scheme: dict) -> RuleResult:
    """
    Check occupation eligibility.
    Empty list = no occupation restriction → not_applicable.
    Comparison is case-insensitive and substring-aware
    (e.g. profile "small farmer" matches scheme "farmer").
    """
    rules = scheme.get("eligibility_rules", {})
    allowed = rules.get("occupation", [])

    if not allowed:
        return "not_applicable"

    profile_occ = (profile.get("occupation") or "").strip().lower()
    if not profile_occ:
        return "not_applicable"

    for allowed_occ in allowed:
        if allowed_occ.lower() in profile_occ or profile_occ in allowed_occ.lower():
            return "pass"
    return "fail"


# ── Gender ────────────────────────────────────────────────────────────────────

def check_gender(profile: dict, scheme: dict) -> RuleResult:
    """
    Check gender restriction.
    "any" → not_applicable (no restriction).
    """
    rules = scheme.get("eligibility_rules", {})
    required_gender = (rules.get("gender") or "any").strip().lower()

    if required_gender == "any":
        return "not_applicable"

    profile_gender = (profile.get("gender") or "").strip().lower()
    if not profile_gender:
        return "not_applicable"

    if profile_gender == required_gender:
        return "pass"
    return "fail"


# ── Land Ownership ────────────────────────────────────────────────────────────

def check_land_ownership(profile: dict, scheme: dict) -> RuleResult:
    """
    Check land ownership requirement.
    null on scheme → not_applicable (no restriction).
    true on scheme → profile must own land.
    false on scheme → profile must NOT own land (rare, but handled).
    """
    rules = scheme.get("eligibility_rules", {})
    land_required = rules.get("land_ownership_required")

    if land_required is None:
        return "not_applicable"

    profile_owns = profile.get("owns_land")
    if profile_owns is None:
        return "not_applicable"  # Missing field — matcher handles

    # Normalize: SQLite stores 0/1; Python may give bool or int
    owns = bool(profile_owns)

    if land_required is True:
        return "pass" if owns else "fail"
    if land_required is False:
        return "pass" if not owns else "fail"

    return "not_applicable"


# ── Composite helper ──────────────────────────────────────────────────────────

ALL_RULE_CHECKS = [
    ("age",            check_age),
    ("state",          check_state),
    ("income",         check_income),
    ("category",       check_category),
    ("occupation",     check_occupation),
    ("gender",         check_gender),
    ("land_ownership", check_land_ownership),
]


def run_all_rules(profile: dict, scheme: dict) -> dict[str, RuleResult]:
    """
    Run every structured eligibility check and return a mapping of
    dimension_name → RuleResult.
    """
    return {name: fn(profile, scheme) for name, fn in ALL_RULE_CHECKS}
