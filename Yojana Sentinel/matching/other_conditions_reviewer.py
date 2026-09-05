"""
matching/other_conditions_reviewer.py

Uses an LLM to evaluate whether a citizen profile plausibly satisfies each
free-text `other_conditions` entry on a scheme's eligibility_rules.

Returns a confidence-qualified verdict for every condition:
    "likely_pass"  — LLM judges the condition is likely satisfied
    "likely_fail"  — LLM judges the condition is likely NOT satisfied
    "unclear"      — LLM cannot determine from profile info alone

Design rules:
  - Never returns a bare pass/fail — always confidence-qualified.
  - "unclear" pushes the overall match toward `needs_review` in matcher.py.
  - LLM reasoning is always logged and returned as part of MatchResult.reasoning.
  - If the LLM call fails or times out → verdict is "unclear" (safe degradation).
  - The LLM is invoked via Groq using the GROQ_API_KEY from environment.
"""

import json
import logging
import os
from typing import Literal

log = logging.getLogger(__name__)

ConditionVerdict = Literal["likely_pass", "likely_fail", "unclear"]

# Valid verdict tokens the LLM must produce
_VALID_VERDICTS = {"likely_pass", "likely_fail", "unclear"}

# ── LLM client (lazy-loaded) ──────────────────────────────────────────────────

_client = None

def _get_client():
    """Lazy-load the Groq client on first use."""
    global _client
    if _client is not None:
        return _client

    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY_2")
        if not api_key:
            log.warning(
                "GROQ_API_KEY not set. other_conditions review will return 'unclear' for all conditions."
            )
            return None
        _client = Groq(api_key=api_key)
        return _client
    except ImportError:
        log.warning(
            "groq package not installed. other_conditions review will return 'unclear'. "
            "Install with: pip install groq"
        )
        return None


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an eligibility assessor for Indian government welfare schemes.
You are given a citizen profile and a specific condition from a scheme's eligibility rules.
Your task is to judge whether the citizen plausibly satisfies this condition based ONLY on
the information in the profile.

Return a JSON object with exactly two keys:
  "verdict": one of "likely_pass", "likely_fail", or "unclear"
  "reasoning": a one or two sentence explanation in plain English citing specific profile fields

Use "unclear" if the profile lacks the information needed to make a confident determination.
Never guess or invent facts not present in the profile.
Never return anything outside this JSON structure."""


def _build_user_prompt(profile: dict, condition: str, scheme_name: str) -> str:
    # Strip internal fields like _backstory before sending to LLM
    safe_profile = {k: v for k, v in profile.items() if not k.startswith("_")}
    return (
        f"Scheme: {scheme_name}\n\n"
        f"Condition to evaluate:\n{condition}\n\n"
        f"Citizen profile:\n{json.dumps(safe_profile, ensure_ascii=False, indent=2)}"
    )


def _call_llm(profile: dict, condition: str, scheme_name: str) -> tuple[ConditionVerdict, str]:
    """
    Call the LLM and parse its response.
    Returns (verdict, reasoning).
    Falls back to ("unclear", fallback_reason) on any error.
    """
    client = _get_client()
    if client is None:
        return "unclear", "LLM client unavailable — GROQ_API_KEY not set or groq package missing."

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(profile, condition, scheme_name)},
            ],
            temperature=0.0,   # Force deterministic output for eligibility decisions
            max_tokens=300,
            timeout=15,
        )
        raw = response.choices[0].message.content.strip()
        log.debug("LLM raw response for condition '%s': %s", condition[:80], raw)

        # Parse JSON
        parsed = json.loads(raw)
        verdict = parsed.get("verdict", "unclear").strip().lower()
        reasoning = parsed.get("reasoning", "No reasoning provided by LLM.").strip()

        if verdict not in _VALID_VERDICTS:
            log.warning(
                "LLM returned unexpected verdict '%s' — defaulting to unclear.", verdict
            )
            verdict = "unclear"

        return verdict, reasoning  # type: ignore[return-value]

    except json.JSONDecodeError as exc:
        log.warning("LLM response was not valid JSON: %s", exc)
        return "unclear", f"LLM response could not be parsed as JSON. Raw: {raw[:200]}"
    except Exception as exc:
        log.warning(
            "LLM call failed for condition '%s': %s — defaulting to unclear.",
            condition[:80],
            exc,
        )
        return "unclear", f"LLM call failed ({type(exc).__name__}): {exc}. Condition requires manual review."


# ── Public API ────────────────────────────────────────────────────────────────

def review_other_conditions(
    profile: dict,
    scheme: dict,
) -> list[dict]:
    """
    Evaluate all `other_conditions` entries on a scheme against a citizen profile.

    Returns a list of result dicts:
    [
      {
        "condition": "the raw condition text",
        "verdict": "likely_pass" | "likely_fail" | "unclear",
        "reasoning": "LLM's explanation"
      },
      ...
    ]

    An empty list is returned if the scheme has no other_conditions.
    """
    rules = scheme.get("eligibility_rules", {})
    conditions = rules.get("other_conditions", [])

    if not conditions:
        return []

    scheme_name = scheme.get("name", "Unknown Scheme")
    results = []

    for condition in conditions:
        condition_text = condition.strip()
        if not condition_text:
            continue

        # Skip the placeholder condition inserted by the scraper normalizer
        if "See source URL" in condition_text:
            log.debug("Skipping scraper placeholder condition for scheme '%s'.", scheme_name)
            continue

        log.info(
            "Reviewing other_condition | scheme='%s' | condition='%s'",
            scheme_name,
            condition_text[:80],
        )

        verdict, reasoning = _call_llm(profile, condition_text, scheme_name)

        log.info(
            "  → verdict: %s | reasoning: %s",
            verdict,
            reasoning[:120],
        )

        results.append({
            "condition": condition_text,
            "verdict": verdict,
            "reasoning": reasoning,
        })

    return results
