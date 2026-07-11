"""
Gate 1 — Deterministic Schema Checks (CI — every commit)
=========================================================
Zero LLM calls. Validates that Business API response payloads conform to
the defined contract. Runs in < 10 seconds.

Wired to: pre-commit hook + CodeBuild on every push.

Run: pytest tests/ci/test_schema_gate.py -v
"""

import json
import sys
import os
import pytest

try:
    from pydantic import BaseModel, field_validator, ValidationError
    from typing import Optional, List
    _PYDANTIC = True
except ImportError:
    _PYDANTIC = False


# ── Response schema models ─────────────────────────────────────────

if _PYDANTIC:
    class Citation(BaseModel):
        source:  str
        snippet: str
        s3_key:  Optional[str] = None

    class BusinessAPIResponse(BaseModel):
        answer:       str
        confidence:   str
        citations:    List[Citation]
        action_items: List[str]
        gaps:         List[str]
        domain:       Optional[str] = None
        trace_id:     Optional[str] = None
        cache_hit:    Optional[bool] = None

        @field_validator("confidence")
        @classmethod
        def confidence_enum(cls, v):
            assert v in {"high", "medium", "low"}, f"invalid confidence: {v}"
            return v

        @field_validator("answer")
        @classmethod
        def answer_non_empty(cls, v):
            assert len(v.strip()) >= 20, f"answer too short ({len(v)} chars)"
            return v

        @field_validator("citations")
        @classmethod
        def citations_list(cls, v):
            # citations may be empty on low-confidence answers
            return v


# ── Valid fixture responses ────────────────────────────────────────

VALID_HIGH_CONFIDENCE = {
    "answer": "The standard Sales-to-Service handoff checklist includes customer classification, executive sponsor confirmation, and go-live timeline.",
    "confidence": "high",
    "citations": [
        {"source": "wiki/customers/bcbs-mn-001.md", "snippet": "Handoff checklist section..."}
    ],
    "action_items": ["Schedule kickoff call", "Confirm executive sponsor"],
    "gaps": [],
    "domain": "customer-onboarding",
}

VALID_LOW_CONFIDENCE = {
    "answer": "I found limited information about this topic in the LLMWiki knowledge base.",
    "confidence": "low",
    "citations": [],
    "action_items": [],
    "gaps": ["Missing customer onboarding documentation for this product type"],
    "domain": "customer-onboarding",
}

VALID_MEDIUM_WITH_GAPS = {
    "answer": "Partial information found. ARB security requirements include VPC isolation and IAM least-privilege, but the specific Facets provisioning checklist is not yet documented.",
    "confidence": "medium",
    "citations": [
        {"source": "wiki/sources/arb-security-guide.md", "snippet": "VPC isolation requirement..."}
    ],
    "action_items": ["Document Facets provisioning checklist"],
    "gaps": ["Facets-specific provisioning checklist not in wiki"],
    "domain": "provisioning",
}


# ── Schema conformance tests ───────────────────────────────────────

@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
@pytest.mark.parametrize("fixture", [
    VALID_HIGH_CONFIDENCE,
    VALID_LOW_CONFIDENCE,
    VALID_MEDIUM_WITH_GAPS,
])
def test_valid_responses_pass_schema(fixture):
    """Valid response payloads must parse without errors."""
    BusinessAPIResponse(**fixture)  # raises ValidationError if invalid


@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
def test_missing_answer_fails():
    bad = {**VALID_HIGH_CONFIDENCE}
    del bad["answer"]
    with pytest.raises(ValidationError):
        BusinessAPIResponse(**bad)


@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
def test_invalid_confidence_enum_fails():
    bad = {**VALID_HIGH_CONFIDENCE, "confidence": "very_high"}
    with pytest.raises(ValidationError):
        BusinessAPIResponse(**bad)


@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
def test_too_short_answer_fails():
    bad = {**VALID_HIGH_CONFIDENCE, "answer": "Short."}
    with pytest.raises(ValidationError):
        BusinessAPIResponse(**bad)


@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
def test_missing_citations_key_fails():
    bad = {**VALID_HIGH_CONFIDENCE}
    del bad["citations"]
    with pytest.raises(ValidationError):
        BusinessAPIResponse(**bad)


@pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")
def test_all_confidence_values_valid():
    for conf in ["high", "medium", "low"]:
        resp = {**VALID_HIGH_CONFIDENCE, "confidence": conf}
        BusinessAPIResponse(**resp)


# ── Golden dataset schema conformance ─────────────────────────────

GOLDEN_FILE = os.path.join(os.path.dirname(__file__), "../golden/api_golden_v1.json")


def test_golden_dataset_loads():
    """Golden dataset JSON must parse cleanly."""
    assert os.path.exists(GOLDEN_FILE), f"Golden file missing: {GOLDEN_FILE}"
    with open(GOLDEN_FILE) as f:
        data = json.load(f)
    assert "examples" in data
    assert len(data["examples"]) > 0


def test_golden_dataset_has_required_request_fields():
    """Every golden example must have a question in its request."""
    with open(GOLDEN_FILE) as f:
        data = json.load(f)
    for ex in data["examples"]:
        assert "request" in ex, f"{ex['id']}: missing 'request'"
        assert "question" in ex["request"], f"{ex['id']}: request missing 'question'"
        assert len(ex["request"]["question"]) > 10, f"{ex['id']}: question too short"


def test_golden_dataset_expected_responses_valid():
    """Every expected_response must specify confidence_in with valid values."""
    valid_confs = {"high", "medium", "low"}
    with open(GOLDEN_FILE) as f:
        data = json.load(f)
    for ex in data["examples"]:
        expected = ex.get("expected_response", {})
        if "confidence" in expected:
            assert expected["confidence"] in valid_confs
        if "confidence_in" in expected:
            for c in expected["confidence_in"]:
                assert c in valid_confs, f"{ex['id']}: invalid confidence '{c}'"


# ── UC1 Golden dataset schema ─────────────────────────────────────

UC1_GOLDEN_FILE = os.path.join(os.path.dirname(__file__), "../golden/uc1_agent_golden_v1.json")


def test_uc1_golden_dataset_loads():
    assert os.path.exists(UC1_GOLDEN_FILE)
    with open(UC1_GOLDEN_FILE) as f:
        data = json.load(f)
    assert "cases" in data
    assert len(data["cases"]) >= 10


def test_uc1_golden_all_cases_have_contracts():
    with open(UC1_GOLDEN_FILE) as f:
        data = json.load(f)
    for case in data["cases"]:
        assert "case_id" in case,   f"Missing case_id"
        assert "contract" in case,  f"{case['case_id']}: missing contract"
        assert "input" in case,     f"{case['case_id']}: missing input"
        assert "tags" in case,      f"{case['case_id']}: missing tags"


def test_uc1_golden_no_duplicate_case_ids():
    with open(UC1_GOLDEN_FILE) as f:
        data = json.load(f)
    ids = [c["case_id"] for c in data["cases"]]
    assert len(ids) == len(set(ids)), f"Duplicate case IDs: {[i for i in ids if ids.count(i) > 1]}"


# ── PM Golden dataset schema ──────────────────────────────────────

PM_GOLDEN_FILE = os.path.join(os.path.dirname(__file__), "../golden/pm_agent_golden_v1.json")


def test_pm_golden_dataset_loads():
    assert os.path.exists(PM_GOLDEN_FILE), f"PM golden file missing: {PM_GOLDEN_FILE}"
    with open(PM_GOLDEN_FILE) as f:
        data = json.load(f)
    assert "cases" in data
    assert len(data["cases"]) >= 10


def test_pm_golden_all_cases_have_contracts():
    with open(PM_GOLDEN_FILE) as f:
        data = json.load(f)
    for case in data["cases"]:
        assert "case_id" in case,  f"Missing case_id"
        assert "contract" in case, f"{case['case_id']}: missing contract"
        assert "input" in case,    f"{case['case_id']}: missing input"
        assert "tags" in case,     f"{case['case_id']}: missing tags"


def test_pm_golden_no_duplicate_case_ids():
    with open(PM_GOLDEN_FILE) as f:
        data = json.load(f)
    ids = [c["case_id"] for c in data["cases"]]
    assert len(ids) == len(set(ids)), f"Duplicate case IDs: {[i for i in ids if ids.count(i) > 1]}"


def test_pm_golden_all_inputs_have_problem_id():
    with open(PM_GOLDEN_FILE) as f:
        data = json.load(f)
    for case in data["cases"]:
        # Skip cases that chain from prior state, or that intentionally test missing-field errors
        if case.get("prior_state"):
            continue
        contract = case.get("contract", {})
        if contract.get("error_field_present") or contract.get("status_eq") == "error":
            continue
        assert "problem_id" in case["input"], \
            f"{case['case_id']}: non-chained non-error case missing problem_id in input"
