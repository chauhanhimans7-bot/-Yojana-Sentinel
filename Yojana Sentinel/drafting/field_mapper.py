"""
drafting/field_mapper.py

Maps a CitizenProfile dict + Scheme dict into:
  - filled_fields: list of {field_id, value, source} dicts
  - unresolved_fields: list of field_ids the citizen must still supply

Design rules (from 05_application_drafting_agent.md):
  1. EXPLICIT mapping table (field_id → CitizenProfile attribute) — no fuzzy-
     matching on labels, which would introduce silent errors.
  2. Mapping is SCOPED PER CALL (no global state) to avoid cross-scheme bleed.
  3. Fields split into three buckets:
       source: "profile"      — value taken directly from CitizenProfile
       source: "inferred"     — LLM may draft text; field must be marked inferable=true
       source: "needs_input"  — no data available; goes to unresolved_fields
  4. Document-upload fields: marked needs_input if the required doc is NOT in
     profile.documents_available; marked profile if it IS available.
  5. Missing required fields block the draft; missing optional fields don't.
"""

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


# ── Explicit field_id → CitizenProfile attribute mapping ──────────────────────
# Key = field_id as it appears in Scheme.application_fields
# Value = CitizenProfile attribute name, or None if it must be inferred/input

FIELD_TO_PROFILE: dict[str, Optional[str]] = {
    # Identity
    "applicant_name":       "display_name",
    "beneficiary_name":     "display_name",
    "head_of_family_name":  "display_name",
    "student_name":         "display_name",

    # Demographics
    "dob":                  None,   # Not in CitizenProfile — must be needs_input (DOB not stored)
    "gender":               "gender",
    "category":             "category",
    "annual_income":        "annual_income",
    "address":              None,   # Not in CitizenProfile — needs_input

    # Financial
    "bank_account_number":  None,   # Sensitive — needs_input
    "ifsc_code":            None,   # Sensitive — needs_input
    "bpl_card_number":      None,   # needs_input
    "ration_card_number":   None,   # needs_input
    "loan_account_number":  None,   # needs_input
    "bank_name":            None,   # needs_input

    # Documents (handled via documents_available check)
    "aadhaar_number":       None,   # Sensitive number — needs_input
    "child_aadhaar":        None,
    "income_certificate":   None,   # document_upload type
    "caste_certificate":    None,   # document_upload type
    "residence_proof":      None,   # document_upload type
    "mcp_card_number":      None,   # needs_input

    # Agriculture-specific
    "land_area_acres":      None,   # needs_input — not stored in profile
    "khasra_number":        None,   # needs_input
    "crop_type":            None,   # needs_input (inferable from occupation)

    # Education-specific
    "institution_name":     None,   # needs_input
    "course_name":          None,   # needs_input
    "class_enrolled":       None,   # needs_input
    "school_name":          None,   # needs_input

    # Health-specific
    "lmp_date":             None,   # needs_input (medical — must never be guessed)
    "anganwadi_centre":     None,   # needs_input

    # Household
    "family_members_count": None,   # needs_input
    "mobile_number":        None,   # needs_input
}

# Fields that the LLM may INFER (draft plausible text) vs must get from citizen.
# Only mark True if the field is genuinely non-sensitive and can be reasoned about
# from profile data (e.g. crop_type can be guessed from "farmer" occupation).
INFERABLE_FIELD_IDS = {
    "crop_type",       # Can be inferred from occupation = "farmer" + state context
}

# Document name → field_id mapping for document_upload fields
# Used to check if a doc is available in CitizenProfile.documents_available
DOC_FIELD_TO_DOC_NAME: dict[str, list[str]] = {
    "income_certificate":  ["income certificate"],
    "caste_certificate":   ["caste certificate"],
    "residence_proof":     ["residence proof", "domicile certificate"],
}


# ── Core mapper ───────────────────────────────────────────────────────────────

def map_fields(profile: dict, scheme: dict) -> tuple[list[dict], list[str]]:
    """
    Map scheme.application_fields to filled_fields and unresolved_fields.

    Args:
        profile: CitizenProfile dict
        scheme:  Scheme dict with application_fields list

    Returns:
        (filled_fields, unresolved_fields)
        filled_fields:    list of {field_id, value, source}
        unresolved_fields: list of field_id strings the citizen must provide
    """
    application_fields: list[dict] = scheme.get("application_fields", [])
    documents_available: list[str] = [
        d.strip().lower() for d in (profile.get("documents_available") or [])
    ]

    filled_fields: list[dict] = []
    unresolved_fields: list[str] = []

    seen_field_ids = set()
    for field_def in application_fields:
        field_id   = field_def.get("field_id", "")
        field_type = field_def.get("type", "text")
        required   = field_def.get("required", True)
        inferable  = field_def.get("inferable", field_id in INFERABLE_FIELD_IDS)

        if not field_id or field_id in seen_field_ids:
            continue
        seen_field_ids.add(field_id)

        # ── document_upload fields ─────────────────────────────────────────────
        if field_type == "document_upload":
            value, source = _resolve_document_field(field_id, documents_available)
            if source == "needs_input" and required:
                if field_id not in unresolved_fields:
                    unresolved_fields.append(field_id)
            filled_fields.append({
                "field_id": field_id,
                "value":    value,
                "source":   source,
            })
            continue

        # ── Structured profile mapping ─────────────────────────────────────────
        profile_attr = FIELD_TO_PROFILE.get(field_id)

        if profile_attr is not None:
            # Direct profile mapping
            raw_value = profile.get(profile_attr)
            if raw_value is not None and raw_value != "":
                value  = str(raw_value)
                source = "profile"
            else:
                # Profile attribute exists in mapping but is null/empty
                if inferable:
                    value  = _infer_value(field_id, profile, scheme)
                    source = "inferred"
                else:
                    value  = ""
                    source = "needs_input"
                    if required:
                        unresolved_fields.append(field_id)
        else:
            # No profile mapping — inferable or needs_input
            if inferable:
                value  = _infer_value(field_id, profile, scheme)
                source = "inferred"
            else:
                value  = ""
                source = "needs_input"
                if required:
                    unresolved_fields.append(field_id)

        filled_fields.append({
            "field_id": field_id,
            "value":    value,
            "source":   source,
        })

    log.info(
        "field_mapper | scheme='%s' | filled=%d | needs_input=%d",
        scheme.get("scheme_id", "?"),
        sum(1 for f in filled_fields if f["source"] != "needs_input"),
        len(unresolved_fields),
    )

    return filled_fields, unresolved_fields


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_document_field(
    field_id: str,
    documents_available: list[str],
) -> tuple[str, str]:
    """
    Check if the document required by a document_upload field is available.
    Returns (value, source).
    """
    expected_doc_names = DOC_FIELD_TO_DOC_NAME.get(field_id, [field_id.replace("_", " ")])
    for doc_name in expected_doc_names:
        doc_lower = doc_name.strip().lower()
        if any(doc_lower in avail or avail in doc_lower for avail in documents_available):
            return f"[Document available: {doc_name}]", "profile"
    return "", "needs_input"


def _infer_value(field_id: str, profile: dict, scheme: dict) -> str:
    """
    Return a plausible draft value for inferable fields.
    The returned string is ALWAYS wrapped in [DRAFT — please review: ...]
    so it's visually obvious to the human approver.
    """
    if field_id == "crop_type":
        occ = (profile.get("occupation") or "").lower()
        state = profile.get("state", "Uttar Pradesh")
        if "farmer" in occ:
            return "[DRAFT — please review: Wheat / Paddy (common crops in Uttar Pradesh — confirm with farmer)]"
        return "[DRAFT — please review: Please specify main crop grown]"

    return f"[DRAFT — please review: {field_id} could not be automatically filled]"


# ── Recompute unresolved after human edit ─────────────────────────────────────

def recompute_after_edit(
    filled_fields: list[dict],
    scheme: dict,
) -> list[str]:
    """
    After a human edits filled_fields, recompute unresolved_fields.
    A field is resolved if its value is non-empty and source is not needs_input.
    Used by approval/actions.py after request_edit().
    """
    application_fields = {
        f["field_id"]: f
        for f in scheme.get("application_fields", [])
    }
    unresolved = []
    for entry in filled_fields:
        fid = entry.get("field_id", "")
        val = entry.get("value", "")
        src = entry.get("source", "needs_input")
        field_def = application_fields.get(fid, {})
        required = field_def.get("required", True)
        if required and (not val or src == "needs_input"):
            unresolved.append(fid)
    return unresolved
