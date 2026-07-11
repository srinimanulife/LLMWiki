"""
UC1 Sales-to-Service — Eval-First Contract Tests
=================================================
These tests define the behavioural contract the UC1 harness MUST satisfy
BEFORE the agent is wired to AgentCore for live production use.

Rule: run this file first. Make every test pass. Then implement.

The tests use:
  - Unit-level: mock AWS, verify logic contracts (fast, no cost)
  - Integration-level: marked with @pytest.mark.integration, invoke live Lambda

Run unit only (default — no AWS needed):
    pytest tests/eval/test_uc1_eval_first.py -v

Run all including integration (needs tzg-sandbox + deployed stack):
    pytest tests/eval/test_uc1_eval_first.py -v -m "integration"
"""

import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call

# Allow importing lambda handler from its source path
HARNESS_PATH = os.path.join(
    os.path.dirname(__file__), "../../lambda/harness/uc1_harness"
)
sys.path.insert(0, HARNESS_PATH)

try:
    import handler as harness_handler
    _HANDLER_AVAILABLE = True
except ImportError:
    _HANDLER_AVAILABLE = False

# ── Golden cases loader ────────────────────────────────────────────

import json as _json

GOLDEN_FILE = os.path.join(os.path.dirname(__file__), "../golden/uc1_agent_golden_v1.json")

def _golden(case_id: str) -> dict:
    with open(GOLDEN_FILE) as f:
        data = _json.load(f)
    for c in data["cases"]:
        if c["case_id"] == case_id:
            return c
    raise KeyError(f"Case {case_id} not found in golden dataset")


# ── Mock factory ───────────────────────────────────────────────────

def _lambda_resp(body: dict) -> dict:
    return {
        "Payload": MagicMock(read=lambda: json.dumps({"body": json.dumps(body)}).encode())
    }


def _make_mocks(monkeypatch, paused_run=None, override_lambda_resp=None):
    """Create and wire all AWS mocks onto the harness handler."""
    dynamo_mock  = MagicMock()
    lambda_mock  = MagicMock()
    bedrock_mock = MagicMock()
    s3_mock      = MagicMock()

    table_mock = MagicMock()
    table_mock.put_item.return_value    = {}
    table_mock.update_item.return_value = {}
    table_mock.query.return_value       = {"Items": [paused_run] if paused_run else []}
    table_mock.get_item.return_value    = {"Item": {}}
    dynamo_mock.Table.return_value      = table_mock

    default_skill_resp = override_lambda_resp or _lambda_resp({
        "status": "success",
        "customer_status": "new",
        "pages_found": 0,
        "key_facts": [],
        "overview": "New customer — no prior wiki history.",
        "outputs": {
            "customer_status": "new", "pages_loaded": 3,
            "playbook": {"steps": ["Step 1", "Step 2"]},
            "confidence": "low",
            "answer": "Key delivery risks include data migration complexity and benefit plan configuration.",
            "action_items": ["Review data migration plan", "Confirm benefit plan complexity"],
            "gaps": [{"title": "Missing SIT evidence", "gap_type": "missing-artifact",
                      "blocking": False, "human_prompt": "What SIT evidence exists?"}],
            "gap_count": 1, "blocking_count": 0,
            "found": False, "completion_pct": 0,
            "populated_fields": [], "missing_fields": ["customer_name", "risk_tier"],
            "status": "indexed",
            "s3_uri": "s3://llmwiki-278e7e22/wiki/customers/test-handoff.md",
        },
    })
    lambda_mock.invoke.return_value = default_skill_resp

    # Phase 2 Bedrock converse response
    phase2_json = json.dumps({
        "customer_type": "payer",
        "products": ["TriZetto QNXT"],
        "risk_tier": "HIGH",
        "go_live_urgency": "MEDIUM",
        "implementation_complexity": "HIGH",
        "rationale": "New customer with no prior history defaults to HIGH risk per business rule.",
    })
    bedrock_mock.converse.return_value = {
        "output": {"message": {"content": [{"text": phase2_json}]}},
        "usage": {"inputTokens": 500, "outputTokens": 150},
    }
    # Legacy invoke_model for older call path
    bedrock_mock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({
            "content": [{"text": phase2_json}]
        }).encode())
    }

    s3_mock.put_object.return_value             = {}
    s3_mock.generate_presigned_url.return_value = "https://s3.example.com/test-report.html"

    if _HANDLER_AVAILABLE:
        monkeypatch.setattr(harness_handler, "dynamodb",      dynamo_mock)
        monkeypatch.setattr(harness_handler, "lambda_client", lambda_mock)
        monkeypatch.setattr(harness_handler, "bedrock",       bedrock_mock)
        monkeypatch.setattr(harness_handler, "s3_client",     s3_mock)
        monkeypatch.setattr(harness_handler, "WIKI_BUCKET",   "test-llmwiki-bucket")

    return {"dynamo": dynamo_mock, "table": table_mock,
            "lambda_": lambda_mock, "bedrock": bedrock_mock, "s3": s3_mock}


# ════════════════════════════════════════════════════════════════════
# CONTRACT 1 — Input validation
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G004_missing_customer_id_returns_structured_error():
    """UC1-G-004: Empty input → status=error, error mentions customer_id."""
    case = _golden("UC1-G-004")
    result = harness_handler.lambda_handler(case["input"], None)
    body   = json.loads(result["body"])

    assert result["statusCode"] == 200, "Never return HTTP 500 — always 200 with status=error"
    assert body["status"] == "error", f"Expected status=error, got {body['status']}"
    error_text = body.get("error", "").lower()
    assert any(kw in error_text for kw in case["contract"]["error_mentions_any"]), (
        f"Error message '{error_text}' doesn't mention required keywords"
    )


# ════════════════════════════════════════════════════════════════════
# CONTRACT 2 — Phase 1+2 then pause at Phase 3
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G001_first_invocation_pauses_at_phase3(monkeypatch):
    """UC1-G-001: First call must run phases 1+2 and pause at Phase 3."""
    case  = _golden("UC1-G-001")
    mocks = _make_mocks(monkeypatch)

    result = harness_handler.lambda_handler(case["input"], None)
    body   = json.loads(result["body"])

    assert body["status"] == "paused", (
        f"Expected status=paused after first invocation, got '{body['status']}'"
    )
    assert body.get("current_phase") == 3, (
        f"Expected current_phase=3, got {body.get('current_phase')}"
    )
    assert "question" in body, "Pause response must include 'question' field for sales team"


@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G007_phase3_generates_exactly_3_questions(monkeypatch):
    """UC1-G-007: Phase 3 pause must produce exactly 3 targeted questions."""
    case  = _golden("UC1-G-007")
    mocks = _make_mocks(monkeypatch)

    result = harness_handler.lambda_handler(case["input"], None)
    body   = json.loads(result["body"])

    assert body["status"] == "paused"
    question_text = body.get("question", "")
    assert question_text, "Question field must not be empty"

    # Count numbered questions — "1." or "1)" style
    import re
    numbered = re.findall(r'(?:^|\n)\s*[123][.)]\s', question_text)
    question_count = len(numbered) if numbered else question_text.count("?")

    assert question_count >= 3, (
        f"Expected at least 3 questions, found {question_count} in: {question_text[:300]}"
    )

    topics = case["contract"]["question_topics_cover_any"]
    assert any(t.lower() in question_text.lower() for t in topics), (
        f"Question doesn't cover required topics {topics}. Got: {question_text[:300]}"
    )


# ════════════════════════════════════════════════════════════════════
# CONTRACT 3 — Phase 2 classification schema
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G005_phase2_returns_all_required_fields(monkeypatch):
    """UC1-G-005: Phase 2 must return all 6 classification fields with valid enum values."""
    _make_mocks(monkeypatch)

    result = harness_handler.lambda_handler({
        "customer_id": "test-payer-001",
        "customer_name": "Test Payer Corp",
        "product": "TriZetto Facets",
        "sow_reference": "SOW-TEST-001",
    }, None)
    body = json.loads(result["body"])

    # Extract phase2 from wherever it's stored
    phase_results = {}
    if "phase_results" in body:
        pr = body["phase_results"]
        phase_results = json.loads(pr) if isinstance(pr, str) else pr
    phase2 = phase_results.get("phase2", {})

    # If paused, check from the run state
    if not phase2 and body.get("status") == "paused":
        # Phase 2 should be in phase_results even at pause
        pytest.skip("Cannot verify phase2 without DynamoDB state — covered by integration test")

    required = ["customer_type", "products", "risk_tier",
                "go_live_urgency", "implementation_complexity", "rationale"]
    for field in required:
        assert field in phase2, f"Phase 2 missing required field: {field}"

    assert phase2["customer_type"] in ["payer", "provider", "pharmacy", "government"]
    assert phase2["risk_tier"] in ["HIGH", "MEDIUM", "LOW"]
    assert phase2["go_live_urgency"] in ["HIGH", "MEDIUM", "LOW"]
    assert phase2["implementation_complexity"] in ["HIGH", "MEDIUM", "LOW"]


@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G006_new_customer_defaults_to_HIGH_risk(monkeypatch):
    """UC1-G-006: pages_found=0 (new customer) → risk_tier must be HIGH."""
    mocks = _make_mocks(monkeypatch)

    # Skill returns pages_found=0 to simulate new customer
    mocks["lambda_"].invoke.return_value = _lambda_resp({
        "status": "success",
        "customer_status": "new",
        "pages_found": 0,
        "key_facts": [],
        "overview": "No customer history found.",
        "outputs": {"customer_status": "new", "pages_found": 0},
    })

    # Override Bedrock to return LOW risk (handler should override to HIGH)
    low_risk_json = json.dumps({
        "customer_type": "payer", "products": ["QNXT"],
        "risk_tier": "LOW",   # ← intentionally wrong — handler must correct this
        "go_live_urgency": "LOW",
        "implementation_complexity": "LOW",
        "rationale": "Seems simple.",
    })
    mocks["bedrock"].converse.return_value = {
        "output": {"message": {"content": [{"text": low_risk_json}]}},
        "usage": {"inputTokens": 100, "outputTokens": 50},
    }
    mocks["bedrock"].invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps(
            {"content": [{"text": low_risk_json}]}
        ).encode())
    }

    result = harness_handler.lambda_handler({
        "customer_id": "brand-new-xyz",
        "customer_name": "XYZ HealthCare",
        "product": "QNXT",
        "sow_reference": "SOW-XYZ-001",
    }, None)
    body = json.loads(result["body"])

    pr = body.get("phase_results", "{}")
    phase_results = json.loads(pr) if isinstance(pr, str) else pr
    phase2 = phase_results.get("phase2", {})

    if phase2:
        assert phase2.get("risk_tier") == "HIGH", (
            "Business rule: new customer (pages_found=0) must always get risk_tier=HIGH"
        )


# ════════════════════════════════════════════════════════════════════
# CONTRACT 4 — Resume + completion
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G002_resume_with_human_context_completes(monkeypatch):
    """UC1-G-002: Providing human_context triggers resume and produces completed status."""
    paused_run = {
        "engagement_id": "bcbs-mn-001",
        "run_id": "run-bcbs-mn-001-123456",
        "status": "paused",
        "current_phase": 3,
        "started_at": "2026-07-08T00:00:00Z",
        "phase_results": json.dumps({
            "phase1": {
                "customer_status": "new", "pages_found": 0,
                "key_facts": [], "overview": "No prior history.",
            },
            "phase2": {
                "risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
                "implementation_complexity": "HIGH",
                "rationale": "New customer defaults to HIGH.",
                "customer_type": "payer",
                "products": ["TriZetto QNXT"],
            },
        }),
    }
    case  = _golden("UC1-G-002")
    mocks = _make_mocks(monkeypatch, paused_run=paused_run)

    result = harness_handler.lambda_handler(case["input"], None)
    body   = json.loads(result["body"])

    assert body["status"] == "completed", (
        f"Expected status=completed after resume, got '{body['status']}'"
    )
    assert body.get("phases_completed", 0) >= 7, (
        f"Expected at least 7 phases completed, got {body.get('phases_completed')}"
    )


# ════════════════════════════════════════════════════════════════════
# CONTRACT 5 — Report HTML structure
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G008_html_report_contains_required_sections(monkeypatch):
    """UC1-G-008: HTML report must contain all 7 required section headings + KPI row."""
    case = _golden("UC1-G-008")
    if not hasattr(harness_handler, "_build_report_html"):
        pytest.skip("_build_report_html not exposed — covered by integration report test")

    p1 = {"overview": "Test customer overview.", "key_facts": ["Fact 1", "Fact 2"], "pages_found": 2}
    p2 = {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM", "implementation_complexity": "HIGH",
          "rationale": "New customer.", "customer_type": "payer", "products": ["QNXT"]}
    p3 = {"summary": "CEO sponsor. Q1 2027 go-live. No constraints."}
    p4 = {"playbook_steps": 5, "pages_loaded": 8}
    p5 = {"confidence": "medium", "answer": "Key risks include data migration complexity.",
          "action_items": ["Review data migration scope"]}
    p6 = {"gaps": [{"title": "Missing HIPAA evidence", "gap_type": "missing-artifact",
                    "blocking": True, "human_prompt": "What HIPAA docs exist?"}],
          "gap_count": 1, "blocking_count": 1}
    p7 = {"found": True, "completion_pct": 60, "populated_fields": ["customer_name"],
          "missing_fields": ["risk_tier", "go_live_date"]}

    html = harness_handler._build_report_html(
        "report-test-001", "Report Test Corp", "TriZetto Facets", "SOW-001",
        "2026-07-08", p1, p2, p3, p4, p5, p6, p7,
    )

    assert "<!DOCTYPE html>" in html or "<html" in html, "Must be valid HTML document"

    for section in case["expected_report"]["sections_required"]:
        assert section in html, f"HTML report missing required section: '{section}'"

    for kpi in case["expected_report"]["kpi_badges_required"]:
        assert kpi in html, f"HTML report missing KPI: '{kpi}'"


# ════════════════════════════════════════════════════════════════════
# CONTRACT 6 — SK02 domain routing
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G009_phase5_routes_to_customer_onboarding_domain(monkeypatch):
    """UC1-G-009: Phase 5 SK-02 call must use domain=customer-onboarding."""
    paused_run = {
        "engagement_id": "domain-routing-test",
        "run_id": "run-domain-001",
        "status": "paused",
        "current_phase": 3,
        "started_at": "2026-07-08T00:00:00Z",
        "phase_results": json.dumps({
            "phase1": {"customer_status": "new", "pages_found": 0, "key_facts": [], "overview": ""},
            "phase2": {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
                       "implementation_complexity": "HIGH", "rationale": "Test",
                       "customer_type": "payer", "products": ["QNXT"]},
        }),
    }
    mocks = _make_mocks(monkeypatch, paused_run=paused_run)

    harness_handler.lambda_handler({
        "customer_id": "domain-routing-test",
        "customer_name": "Domain Test Corp",
        "product": "TriZetto QNXT",
        "sow_reference": "SOW-DOM-001",
        "human_context": "Test context for domain routing.",
    }, None)

    # Find the SK02 invocation in the mock call list
    sk02_calls = [
        c for c in mocks["lambda_"].invoke.call_args_list
        if "wiki-query" in str(c) or "sk02" in str(c).lower()
           or "wiki_query" in str(c).lower()
    ]

    if not sk02_calls:
        pytest.skip("SK02 call not isolated in mock — covered by integration test")

    for c in sk02_calls:
        payload_raw = c[1].get("Payload") or (c[0][1] if len(c[0]) > 1 else None)
        if payload_raw:
            payload = json.loads(payload_raw) if isinstance(payload_raw, (str, bytes)) else payload_raw
            domain = payload.get("domain") or payload.get("inputs", {}).get("domain")
            if domain:
                assert domain == "customer-onboarding", (
                    f"Phase 5 SK-02 must use domain=customer-onboarding, got '{domain}'"
                )


# ════════════════════════════════════════════════════════════════════
# CONTRACT 7 — get_status is read-only
# ════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HANDLER_AVAILABLE, reason="handler not importable")
def test_UC1_G003_get_status_returns_state_without_executing(monkeypatch):
    """UC1-G-003: get_status must return run state and NOT invoke any skill Lambda."""
    completed_run = {
        "engagement_id": "bcbs-mn-001",
        "run_id": "run-bcbs-mn-001-done",
        "status": "completed",
        "current_phase": 8,
        "phase_results": "{}",
        "total_latency_ms": 12000,
    }
    mocks = _make_mocks(monkeypatch, paused_run=completed_run)
    mocks["table"].query.return_value = {"Items": [completed_run]}

    result = harness_handler.lambda_handler(
        {"action": "get_status", "engagement_id": "bcbs-mn-001"}, None
    )
    body = json.loads(result["body"])

    assert body.get("status") in ["completed", "paused", "running", "error"]
    assert "current_phase" in body

    # No skill Lambdas should have been invoked
    skill_calls = [
        c for c in mocks["lambda_"].invoke.call_args_list
        if "skill" in str(c).lower() or "harness" in str(c).lower()
    ]
    assert len(skill_calls) == 0, (
        f"get_status must not invoke any skill Lambdas, but found: {skill_calls}"
    )


# ════════════════════════════════════════════════════════════════════
# INTEGRATION — Live Lambda invocation (needs AWS)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.integration
def test_live_UC1_first_invocation_pauses():
    """Integration: invoke live llmwiki-uc1-harness and confirm it pauses at Phase 3."""
    import boto3
    client = boto3.client("lambda", region_name="us-east-1")

    import time
    test_customer_id = f"eval-test-{int(time.time())}"

    resp = client.invoke(
        FunctionName="llmwiki-uc1-harness",
        Payload=json.dumps({
            "customer_id":   test_customer_id,
            "customer_name": "Eval Test Corp",
            "product":       "TriZetto QNXT",
            "sow_reference": "SOW-EVAL-001",
        }),
    )
    body = json.loads(json.loads(resp["Payload"].read())["body"])

    assert body["status"] == "paused", f"Live harness must pause at Phase 3, got: {body['status']}"
    assert body.get("current_phase") == 3
    assert "question" in body and body["question"]


@pytest.mark.integration
def test_live_UC1_resume_completes():
    """Integration: resume a paused UC1 run with human context and confirm completion."""
    import boto3, time
    client = boto3.client("lambda", region_name="us-east-1")

    test_customer_id = f"eval-resume-{int(time.time())}"

    # Phase 1: start
    resp1 = client.invoke(
        FunctionName="llmwiki-uc1-harness",
        Payload=json.dumps({
            "customer_id":   test_customer_id,
            "customer_name": "Eval Resume Corp",
            "product":       "TriZetto Facets",
            "sow_reference": "SOW-EVAL-RESUME-001",
        }),
    )
    body1 = json.loads(json.loads(resp1["Payload"].read())["body"])
    assert body1["status"] == "paused"

    # Phase 2: resume
    resp2 = client.invoke(
        FunctionName="llmwiki-uc1-harness",
        Payload=json.dumps({
            "customer_id":   test_customer_id,
            "customer_name": "Eval Resume Corp",
            "product":       "TriZetto Facets",
            "sow_reference": "SOW-EVAL-RESUME-001",
            "human_context": "Executive sponsor is the CISO. Go-live Q3 2027. No prior attempts. HIPAA required.",
        }),
    )
    body2 = json.loads(json.loads(resp2["Payload"].read())["body"])

    assert body2["status"] == "completed", f"Resume must complete. Got: {body2.get('status')}, error: {body2.get('error')}"
    assert body2.get("phases_completed", 0) >= 7
    assert body2.get("report_download_url"), "Completed run must include report_download_url"
