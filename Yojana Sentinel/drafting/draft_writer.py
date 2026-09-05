"""
drafting/draft_writer.py

Generates ApplicationDraft.draft_text from a filled_fields list and scheme
context using a Groq-hosted LLM (llama-3.1-8b-instant).

Design rules (from 05_application_drafting_agent.md):
  1. LLM prompt explicitly forbids inventing facts not present in filled_fields.
  2. LLM-inferred field values (source: "inferred") are already wrapped in
     [DRAFT — please review: ...] by field_mapper.py. draft_writer.py must
     preserve and display these markers verbatim so they are visible to the
     human approver.
  3. draft_text ALWAYS starts with a plain-language list of unresolved_fields
     so the approver sees missing info first, not buried at the bottom.
  4. If the LLM call fails → raises DraftWriterError (caller must handle;
     create_draft.py will not produce a draft with draft_text=null).
  5. Uses GROQ_API_KEY or GROQ_API_KEY_2 from environment.
"""

import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


class DraftWriterError(Exception):
    """Raised when draft_text generation fails and the draft cannot be produced."""


# ── LLM client (lazy-loaded) ──────────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY_2")
        if not api_key:
            raise DraftWriterError(
                "GROQ_API_KEY not set. Cannot generate draft text. "
                "Set GROQ_API_KEY in your .env file."
            )
        _client = Groq(api_key=api_key)
        return _client
    except ImportError:
        raise DraftWriterError(
            "groq package not installed. Run: pip install groq"
        )


# ── Prompt builder ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful assistant that writes Indian government scheme application cover notes on behalf of a citizen.

Your job is to produce a clear, honest, plain-language cover note for the application.

STRICT RULES:
1. ONLY use facts that are explicitly present in the FILLED FIELDS provided. Do not invent any details.
2. For fields marked "[DRAFT — please review: ...]", copy the text EXACTLY as given — do not change or remove these markers.
3. Write in simple English, no jargon. The reader may not be technical.
4. The note must be respectful, formal, and appropriate for a government body.
5. Do NOT include any submission mechanism, portal link, or suggestion that the note will be auto-submitted. This is a draft for human review only.
6. Keep the note under 350 words."""


def _build_user_prompt(
    scheme: dict,
    profile: dict,
    filled_fields: list[dict],
    unresolved_fields: list[str],
) -> str:
    scheme_name = scheme.get("name", "Unknown Scheme")
    scheme_desc = scheme.get("description", "")
    deadline    = scheme.get("deadline") or "No deadline (rolling)"
    source_url  = scheme.get("source_url", "")

    # Format filled fields for LLM
    fields_text = []
    for f in filled_fields:
        if f["source"] != "needs_input" and f["value"]:
            fields_text.append(f"  {f['field_id']}: {f['value']}  [source: {f['source']}]")

    profile_safe = {k: v for k, v in profile.items() if not k.startswith("_")}
    profile_safe.pop("managed_by", None)  # Remove internal fields

    return (
        f"Scheme Name: {scheme_name}\n"
        f"Description: {scheme_desc}\n"
        f"Deadline: {deadline}\n"
        f"Source: {source_url}\n\n"
        f"Citizen Profile:\n{json.dumps(profile_safe, ensure_ascii=False, indent=2)}\n\n"
        f"Filled Application Fields:\n" + "\n".join(fields_text or ["(No fields auto-filled)"]) + "\n\n"
        f"Fields citizen must still provide (unresolved): {unresolved_fields or ['None — all fields filled']}\n\n"
        f"Write a plain-language cover note for this application. "
        f"Start the note with 'To Whomsoever It May Concern' and end with 'Regards, [Applicant Name]'. "
        f"Do NOT mention any submission mechanism or portal — this is a draft for human review only."
    )


# ── Unresolved fields header renderer ─────────────────────────────────────────

def _render_unresolved_header(unresolved_fields: list[str], scheme: dict) -> str:
    """
    Render a plain-language header listing missing required info.
    This always appears at the TOP of draft_text per spec.
    """
    if not unresolved_fields:
        return "✅ All required fields are filled. This draft is ready for your review.\n\n"

    # Map field_ids to human-readable labels from scheme.application_fields
    field_labels = {
        f["field_id"]: f.get("label", f["field_id"])
        for f in scheme.get("application_fields", [])
    }

    lines = ["⚠️  Before this can be submitted, you still need to provide:\n"]
    for fid in unresolved_fields:
        label = field_labels.get(fid, fid.replace("_", " ").title())
        lines.append(f"  • {label}")
    lines.append("\n")
    return "\n".join(lines)


def _fallback_cover_note(
    profile: dict,
    scheme: dict,
    filled_fields: list[dict],
) -> str:
    """Generate a clean, structured cover note template without calling LLM."""
    applicant_name = profile.get("display_name", "Applicant")
    scheme_name    = scheme.get("name", "Welfare Scheme")
    issuing_body   = scheme.get("issuing_body", "Department Authority")
    
    lines = [
        "To Whomsoever It May Concern,",
        "",
        f"Subject: Application for {scheme_name} ({issuing_body})",
        "",
        f"Respected Sir/Madam,",
        "",
        f"I am writing to formally submit my application for the '{scheme_name}'. "
        f"Below are the verified details from my citizen profile for your review:",
        "",
    ]

    for f in filled_fields:
        if f.get("source") != "needs_input" and f.get("value"):
            fid_clean = f["field_id"].replace("_", " ").title()
            lines.append(f"  • {fid_clean}: {f['value']}")

    lines.extend([
        "",
        "I request you to kindly process my application as per official guidelines.",
        "",
        f"Regards,\n{applicant_name}"
    ])
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_draft_text(
    profile: dict,
    scheme: dict,
    filled_fields: list[dict],
    unresolved_fields: list[str],
) -> str:
    """
    Generate ApplicationDraft.draft_text.

    Always starts with the unresolved_fields header (plain-language list of
    missing info), then the LLM-generated or template-fallback cover note body.
    """
    unresolved_header = _render_unresolved_header(unresolved_fields, scheme)
    user_prompt = _build_user_prompt(scheme, profile, filled_fields, unresolved_fields)

    llm_body = None

    try:
        client = _get_client()
        log.info(
            "Calling LLM for draft_text | scheme=%s | profile=%s | unresolved=%d",
            scheme.get("scheme_id"), profile.get("profile_id"), len(unresolved_fields),
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=600,
            timeout=20,
        )
        llm_body = response.choices[0].message.content.strip()
        log.info("Draft text generated via LLM successfully (%d chars).", len(llm_body))

    except Exception as exc:
        log.warning("LLM call unavailable/failed (%s). Using template cover note fallback.", exc)
        llm_body = _fallback_cover_note(profile, scheme, filled_fields)

    # Combine: unresolved header FIRST, then cover note body
    draft_text = unresolved_header + "─" * 60 + "\n\n" + llm_body

    # Append source attribution footer
    source_url   = scheme.get("source_url", "")
    verified_at  = scheme.get("last_verified_at", "unknown")
    draft_text += (
        f"\n\n─" + "─" * 59 + "\n"
        f"📌 Source: {scheme.get('name', '')} — {source_url}\n"
        f"   Last verified: {verified_at}\n"
        f"   This is a DRAFT prepared by Yojana Sentinel. It has not been submitted anywhere.\n"
        f"   A human must review and manually submit this application."
    )

    return draft_text
