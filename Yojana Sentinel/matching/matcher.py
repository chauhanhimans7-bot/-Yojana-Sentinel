"""
matching/matcher.py

Combines rules_engine.py results and other_conditions_reviewer.py results
into a single MatchResult per (CitizenProfile, Scheme) pair.

Scoring logic (all weights explicit and documented):

STEP 1 — Hard rule evaluation:
  Any rule returning "fail" → match_status: not_eligible, score: 0.

STEP 2 — other_conditions review (LLM):
  "likely_fail" on any condition → not_eligible, score: 0
  "unclear" on any condition → pushes final status to needs_review

STEP 3 — Document completeness score (0–100):
  score = (docs_present / docs_required) * 100
  If scheme has no required_documents → score = 100 (no constraint)

STEP 4 — Apply thresholds from config/scope.json:
  score >= strong_match_threshold AND no unclear conditions AND no missing info → strong_match
  score >= partial_match_threshold                                             → partial_match
  score <  partial_match_threshold                                             → partial_match (eligible, low doc completeness)

STEP 5 — missing_info population:
  Any document in scheme.required_documents not in profile.documents_available
  is added to missing_info with label "MISSING_DOCUMENT: <name>".
  Any hard rule that returned not_applicable due to a missing profile field
  is also surfaced in missing_info.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from matching.rules_engine import run_all_rules
from matching.other_conditions_reviewer import review_other_conditions

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_DEFAULT_STRONG = 80
_DEFAULT_PARTIAL = 50

def _load_thresholds() -> tuple[int, int]:
    """Load match thresholds from config/scope.json, with safe defaults."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "scope.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        strong = int(cfg.get("strong_match_threshold", _DEFAULT_STRONG))
        partial = int(cfg.get("partial_match_threshold", _DEFAULT_PARTIAL))
        assert partial < strong, "Config error: partial_match_threshold must be < strong_match_threshold"
        return strong, partial
    except Exception as exc:
        log.warning("Could not read thresholds from scope.json (%s). Using defaults %d/%d.", exc, _DEFAULT_STRONG, _DEFAULT_PARTIAL)
        return _DEFAULT_STRONG, _DEFAULT_PARTIAL


STRONG_THRESHOLD, PARTIAL_THRESHOLD = _load_thresholds()


# ── Profile field completeness check ─────────────────────────────────────────

# Fields that are legitimately optional (schema allows null)
_OPTIONAL_PROFILE_FIELDS = {"district", "managed_by", "family_status"}

# Structured rule → profile field mapping for missing_info detection
_RULE_TO_PROFILE_FIELD = {
    "age":            "age",
    "state":          "state",
    "income":         "annual_income",
    "category":       "category",
    "occupation":     "occupation",
    "gender":         "gender",
    "land_ownership": "owns_land",
}


def _detect_missing_profile_fields(profile: dict, scheme: dict, rule_results: dict) -> list[str]:
    """
    Returns a list of profile fields that are missing but were needed for rule evaluation.
    A field is flagged missing if:
      - The scheme has a non-null/non-empty constraint for that dimension, AND
      - The profile's corresponding field is None / empty.
    """
    missing = []
    rules = scheme.get("eligibility_rules", {})

    checks = [
        ("age",            rules.get("min_age") is not None or rules.get("max_age") is not None,           profile.get("age")),
        ("state",          bool(rules.get("states")),                                                         profile.get("state")),
        ("annual_income",  rules.get("max_annual_income") is not None,                                        profile.get("annual_income")),
        ("category",       bool(rules.get("categories")),                                                     profile.get("category")),
        ("occupation",     bool(rules.get("occupation")),                                                     profile.get("occupation")),
        ("gender",         (rules.get("gender") or "any") != "any",                                           profile.get("gender")),
        ("owns_land",      rules.get("land_ownership_required") is not None,                                  profile.get("owns_land")),
    ]

    for field_name, scheme_constrains, profile_value in checks:
        if scheme_constrains and (profile_value is None or profile_value == ""):
            missing.append(f"MISSING_PROFILE_FIELD: {field_name}")

    return missing


def _document_score(profile: dict, scheme: dict) -> tuple[float, list[str]]:
    """
    Calculate document completeness score and list of missing documents.
    Returns (score_0_to_100, missing_doc_list).
    """
    required_docs: list[str] = scheme.get("required_documents", [])
    if not required_docs:
        return 100.0, []

    available_raw = profile.get("documents_available", [])
    available = [d.strip().lower() for d in available_raw]

    missing_docs = []
    for doc in required_docs:
        doc_lower = doc.strip().lower()
        # Check for substring match to handle minor naming differences
        if not any(doc_lower in avail or avail in doc_lower for avail in available):
            missing_docs.append(f"MISSING_DOCUMENT: {doc}")

    present = len(required_docs) - len(missing_docs)
    score = (present / len(required_docs)) * 100.0
    return score, missing_docs


def _build_reasoning(
    rule_results: dict,
    other_condition_results: list[dict],
    doc_score: float,
    missing_docs: list[str],
    missing_fields: list[str],
    final_status: str,
    final_score: float,
) -> str:
    """Build a specific, named reasoning string for MatchResult."""
    lines = []

    # Hard rules
    for rule_name, result in rule_results.items():
        lines.append(f"[{result.upper()}] {rule_name}")

    # Document completeness
    lines.append(f"[DOCUMENT_SCORE] {doc_score:.0f}/100")
    for md in missing_docs:
        lines.append(f"  → {md}")

    # Missing profile fields
    for mf in missing_fields:
        lines.append(f"  → {mf}")

    # other_conditions
    for ocr in other_condition_results:
        verdict = ocr.get("verdict", "unclear").upper()
        cond = ocr.get("condition", "")[:80]
        reasoning = ocr.get("reasoning", "")
        lines.append(f"[{verdict}] other_condition: '{cond}' — {reasoning}")

    lines.append(f"FINAL: status={final_status}, score={final_score:.0f}")
    return "\n".join(lines)


# ── Core match function ───────────────────────────────────────────────────────

def match(profile: dict, scheme: dict, run_llm: bool = True) -> dict:
    """
    Produce a MatchResult dict for a single (profile, scheme) pair.

    Args:
        profile:  CitizenProfile dict
        scheme:   Scheme dict
        run_llm:  If False, skip other_conditions LLM review (for fast offline testing)
    """
    now = datetime.now(timezone.utc).isoformat()

    profile_id = profile.get("profile_id", "unknown")
    scheme_id  = scheme.get("scheme_id", "unknown")

    # Filter scheme by included_categories
    # (category filter is enforced in run_matching.py before calling match)

    # ── STEP 1: Hard rules ────────────────────────────────────────────────────
    rule_results = run_all_rules(profile, scheme)

    hard_fails = [name for name, result in rule_results.items() if result == "fail"]
    if hard_fails:
        reasoning = _build_reasoning(rule_results, [], 0, [], [], "not_eligible", 0)
        log.info(
            "  [NOT_ELIGIBLE] profile=%s scheme=%s — hard_fails=%s",
            profile_id, scheme_id, hard_fails,
        )
        return {
            "profile_id":    profile_id,
            "scheme_id":     scheme_id,
            "match_score":   0,
            "match_status":  "not_eligible",
            "missing_info":  [f"FAILED_RULE: {f}" for f in hard_fails],
            "reasoning":     reasoning,
            "evaluated_at":  now,
        }

    # ── STEP 2: other_conditions (LLM) ────────────────────────────────────────
    other_results = []
    if run_llm:
        try:
            other_results = review_other_conditions(profile, scheme)
        except Exception as exc:
            log.warning("other_conditions review raised unexpectedly: %s. Defaulting all to unclear.", exc)
            conditions = scheme.get("eligibility_rules", {}).get("other_conditions", [])
            other_results = [
                {"condition": c, "verdict": "unclear", "reasoning": f"Review failed: {exc}"}
                for c in conditions if "See source URL" not in c
            ]

    llm_hard_fails  = [r for r in other_results if r["verdict"] == "likely_fail"]
    llm_unclear     = [r for r in other_results if r["verdict"] == "unclear"]

    if llm_hard_fails:
        doc_score, missing_docs = _document_score(profile, scheme)
        missing_fields = _detect_missing_profile_fields(profile, scheme, rule_results)
        reasoning = _build_reasoning(rule_results, other_results, 0, missing_docs, missing_fields, "not_eligible", 0)
        log.info(
            "  [NOT_ELIGIBLE via LLM] profile=%s scheme=%s — llm_fails: %d condition(s)",
            profile_id, scheme_id, len(llm_hard_fails),
        )
        return {
            "profile_id":   profile_id,
            "scheme_id":    scheme_id,
            "match_score":  0,
            "match_status": "not_eligible",
            "missing_info": [f"CONDITION_FAIL: {r['condition'][:80]}" for r in llm_hard_fails],
            "reasoning":    reasoning,
            "evaluated_at": now,
        }

    # ── STEP 3: Document completeness score ───────────────────────────────────
    doc_score, missing_docs = _document_score(profile, scheme)
    missing_fields = _detect_missing_profile_fields(profile, scheme, rule_results)
    all_missing = missing_docs + missing_fields

    # ── STEP 4: Determine final status ────────────────────────────────────────
    if llm_unclear:
        final_status = "needs_review"
        final_score  = min(doc_score, STRONG_THRESHOLD - 1)  # Can't be strong while unclear
    elif doc_score >= STRONG_THRESHOLD and not all_missing:
        final_status = "strong_match"
        final_score  = doc_score
    elif doc_score >= PARTIAL_THRESHOLD:
        final_status = "partial_match"
        final_score  = doc_score
    else:
        final_status = "partial_match"  # Still eligible but low doc coverage
        final_score  = doc_score

    reasoning = _build_reasoning(
        rule_results, other_results, doc_score, missing_docs, missing_fields, final_status, final_score
    )

    log.info(
        "  [%s] profile=%s scheme=%s score=%.0f missing=%d",
        final_status.upper(), profile_id, scheme_id, final_score, len(all_missing),
    )

    return {
        "profile_id":   profile_id,
        "scheme_id":    scheme_id,
        "match_score":  round(final_score, 1),
        "match_status": final_status,
        "missing_info": all_missing,
        "reasoning":    reasoning,
        "evaluated_at": now,
    }
