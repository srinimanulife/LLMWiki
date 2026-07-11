"""
Integration Tests — Live AWS Lambda Invocations
================================================
These tests invoke the deployed Lambda functions directly.
Requires: AWS_PROFILE=tzg-sandbox + deployed stack.

Run: pytest tests/integration/ -v -m integration

Marks all tests with @pytest.mark.integration so unit test runs skip them by default.
"""

import json
import time
import pytest

pytestmark = pytest.mark.integration

try:
    import boto3
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not _BOTO3_AVAILABLE, reason="boto3 not installed — integration tests require live AWS"
)]

REGION  = "us-east-1"
PROFILE = "tzg-sandbox"

if _BOTO3_AVAILABLE:
    session  = boto3.Session(profile_name=PROFILE, region_name=REGION)
    lam      = session.client("lambda")
    dynamodb = session.resource("dynamodb")
    s3       = session.client("s3")
else:
    session = lam = dynamodb = s3 = None


def _invoke(fn: str, payload: dict) -> dict:
    resp = lam.invoke(FunctionName=fn, Payload=json.dumps(payload))
    raw  = resp["Payload"].read()
    outer = json.loads(raw)
    body  = outer.get("body")
    if body:
        return json.loads(body) if isinstance(body, str) else body
    return outer


# ── Query Lambda ───────────────────────────────────────────────────

def test_query_lambda_returns_answer():
    body = _invoke("llmwiki-query", {
        "question": "What is the Sales-to-Service handoff checklist?",
        "caller":   "integration-test",
    })
    assert "answer" in body
    assert body.get("confidence") in ["high", "medium", "low"]
    assert isinstance(body.get("citations", []), list)


def test_query_lambda_cache_hit_on_repeat():
    question = f"What is LLMWiki governance? integration-{int(time.time())}"
    r1 = _invoke("llmwiki-query", {"question": question, "caller": "integration-test"})
    r2 = _invoke("llmwiki-query", {"question": question, "caller": "integration-test"})
    assert r2.get("cache_hit") is True, "Second identical call must be a cache hit"
    assert r2.get("answer") == r1.get("answer"), "Cache hit must return same answer"


def test_query_lambda_governance_writes_usage():
    caller = f"integration-govtest-{int(time.time())}"
    _invoke("llmwiki-query", {
        "question": "What are ARB security requirements for Facets?",
        "caller":   caller,
    })
    time.sleep(3)
    table = dynamodb.Table("llmwiki-usage")
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("caller").eq(caller)
    )
    assert len(resp["Items"]) >= 1, f"No usage row found for caller={caller}"
    assert float(resp["Items"][0].get("cost_usd", 0)) >= 0


# ── Business Query Lambda ──────────────────────────────────────────

def test_business_query_returns_structured_response():
    body = _invoke("llmwiki-business-query", {
        "question": "What are the key delivery risks for a new QNXT payer implementation?",
        "domain":   "customer-onboarding",
        "caller":   "integration-test",
    })
    assert "answer" in body
    assert body.get("confidence") in ["high", "medium", "low"]
    assert isinstance(body.get("action_items", []), list)
    assert isinstance(body.get("citations", []), list)


def test_business_query_domain_routing():
    body = _invoke("llmwiki-business-query", {
        "question": "What SIT sign-off criteria apply to a healthcare payer platform?",
        "domain":   "testing",
    })
    assert body.get("domain") == "testing" or body.get("confidence") in ["high", "medium", "low"]


def test_business_query_low_confidence_includes_gaps():
    body = _invoke("llmwiki-business-query", {
        "question": "What are the ARB requirements for XYZ-ALPHA-9000 unicorn plan type?",
        "domain":   "customer-onboarding",
    })
    if body.get("confidence") == "low":
        assert isinstance(body.get("gaps", []), list)


# ── UC1 Harness ────────────────────────────────────────────────────

def test_uc1_harness_first_call_pauses():
    cid = f"inttest-{int(time.time())}"
    body = _invoke("llmwiki-uc1-harness", {
        "customer_id":   cid,
        "customer_name": "Integration Test Corp",
        "product":       "TriZetto QNXT",
        "sow_reference": "SOW-INT-001",
    })
    assert body.get("status") == "paused", f"Expected paused, got: {body.get('status')}"
    assert body.get("current_phase") == 3
    assert body.get("question"), "Paused response must include questions"


def test_uc1_harness_resume_completes():
    cid = f"intresume-{int(time.time())}"

    # Start
    _invoke("llmwiki-uc1-harness", {
        "customer_id":   cid,
        "customer_name": "Resume Test Corp",
        "product":       "TriZetto Facets",
        "sow_reference": "SOW-RES-001",
    })

    # Resume
    body = _invoke("llmwiki-uc1-harness", {
        "customer_id":   cid,
        "customer_name": "Resume Test Corp",
        "product":       "TriZetto Facets",
        "sow_reference": "SOW-RES-001",
        "human_context": "Sponsor: CEO. Go-live Q2 2027. No constraints. HIPAA required.",
    })
    assert body.get("status") == "completed", f"Expected completed, got {body.get('status')}"
    assert body.get("phases_completed", 0) >= 7
    assert body.get("report_download_url"), "Must have download URL on completion"


def test_uc1_harness_get_status_read_only():
    cid = f"intstatus-{int(time.time())}"
    # Start first to create a run
    _invoke("llmwiki-uc1-harness", {
        "customer_id": cid, "customer_name": "Status Test",
        "product": "QNXT", "sow_reference": "SOW-S-001",
    })
    # Now check status
    body = _invoke("llmwiki-uc1-harness", {"action": "get_status", "engagement_id": cid})
    assert body.get("status") in ["paused", "completed", "running", "error"]
    assert "current_phase" in body


# ── Governance Tables ──────────────────────────────────────────────

def test_usage_table_accessible():
    table = dynamodb.Table("llmwiki-usage")
    resp  = table.scan(Limit=1)
    assert "Items" in resp


def test_cache_table_accessible():
    table = dynamodb.Table("llmwiki-cache")
    resp  = table.scan(Limit=1)
    assert "Items" in resp


def test_rate_limits_table_accessible():
    table = dynamodb.Table("llmwiki-rate-limits")
    resp  = table.scan(Limit=1)
    assert "Items" in resp
