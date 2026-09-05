"""
tests/test_field_mapper.py

Unit tests for drafting/field_mapper.py
Tests profile field extraction, missing document handling, and inferable field marking.
"""

import pytest
from drafting.field_mapper import map_fields


@pytest.fixture
def sample_profile() -> dict:
    return {
        "profile_id": "p-101",
        "display_name": "Ramkali Devi",
        "age": 38,
        "gender": "female",
        "state": "Uttar Pradesh",
        "annual_income": 65000,
        "category": "obc",
        "occupation": "farmer",
        "owns_land": True,
        "documents_available": ["Aadhaar card", "income certificate"],
    }


@pytest.fixture
def sample_scheme() -> dict:
    return {
        "scheme_id": "s-101",
        "name": "Scholarship Scheme",
        "required_documents": ["Aadhaar card", "income certificate", "caste certificate"],
        "application_fields": [
            {"field_id": "applicant_name", "label": "Full Name", "type": "string"},
            {"field_id": "gender", "label": "Gender", "type": "string"},
            {"field_id": "annual_income", "label": "Annual Income", "type": "number"},
            {"field_id": "caste_certificate", "label": "Caste Cert", "type": "document_upload"},
            {"field_id": "crop_type", "label": "Crop Type", "type": "string", "inferable": True},
        ],
    }


class TestFieldMapper:
    def test_direct_and_unresolved_mapping(self, sample_profile, sample_scheme):
        filled, unresolved = map_fields(sample_profile, sample_scheme)

        # Direct fields matched
        filled_ids = {f["field_id"]: f["value"] for f in filled}
        assert filled_ids.get("applicant_name") == "Ramkali Devi"
        assert filled_ids.get("gender") == "female"
        assert filled_ids.get("annual_income") == "65000"

        # Inferable field mapped with source='inferred'
        inferable_field = next(f for f in filled if f["field_id"] == "crop_type")
        assert inferable_field["source"] == "inferred"

        # Caste cert is missing from documents_available -> unresolved
        assert "caste_certificate" in unresolved

    def test_all_fields_resolved(self, sample_profile, sample_scheme):
        sample_profile["documents_available"].append("caste certificate")
        filled, unresolved = map_fields(sample_profile, sample_scheme)
        assert len(unresolved) == 0
