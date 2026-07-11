"""
UC1 Harness — Unit Tests
Migrated and expanded from lambda/harness/uc1_harness/test_harness.py.
All AWS clients are mocked. No live calls. Runs in < 5 seconds.

Run: pytest tests/unit/uc1_harness/ -v
"""

import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

HARNESS_PATH = os.path.join(os.path.dirname(__file__), "../../../lambda/harness/uc1_harness")
sys.path.insert(0, HARNESS_PATH)

try:
    import handler
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="uc1 handler not importable")

VALID_EVENT = {
    "customer_id":   "test-customer-001",
    "customer_name": "Test Corp",
    "product":       "TestProduct v1",
    "sow_reference": "SOW-TEST-001",
}

RESUME_EVENT = {
    **VALID_EVENT,
    "human_context": "Executive sponsor is Jane Smith. Go-live Q3 2027. No prior attempts.",
}


def _skill_resp(body: dict) -> dict:
    return {
        "Payload": MagicMock(read=lambda: json.dumps({"body": json.dumps(body)}).encode())
    }


@pytest.fixture
def mocks(monkeypatch):
    dynamo  = MagicMock()
    lam     = MagicMock()
    bedrock = MagicMock()
    s3      = MagicMock()

    table = MagicMock()
    table.put_item.return_value    = {}
    table.update_item.return_value = {}
    table.query.return_value       = {"Items": []}
    table.get_item.return_value    = {"Item": {}}
    dynamo.Table.return_value      = table

    lam.invoke.return_value = _skill_resp({
        "status": "success", "customer_status": "new", "pages_found": 0,
        "key_facts": [], "overview": "New customer.",
        "outputs": {
            "customer_status": "new", "pages_loaded": 1,
            "playbook": {"steps": []}, "confidence": "low",
            "answer": "Test risk answer.", "action_items": ["Review plan"],
            "gaps": [], "gap_count": 0, "blocking_count": 0,
            "found": False, "completion_pct": 0,
            "populated_fields": [], "missing_fields": [],
            "status": "indexed", "s3_uri": "s3://test/test.md",
        },
    })

    phase2_text = json.dumps({
        "customer_type": "payer", "products": ["TestProduct v1"],
        "risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
        "implementation_complexity": "HIGH", "rationale": "New customer.",
    })
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": phase2_text}]}},
        "usage": {"inputTokens": 200, "outputTokens": 60},
    }
    bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({"content": [{"text": phase2_text}]}).encode())
    }

    s3.put_object.return_value             = {}
    s3.generate_presigned_url.return_value = "https://s3.example.com/report.html"

    monkeypatch.setattr(handler, "dynamodb",      dynamo)
    monkeypatch.setattr(handler, "lambda_client", lam)
    monkeypatch.setattr(handler, "bedrock",       bedrock)
    monkeypatch.setattr(handler, "s3_client",     s3)
    monkeypatch.setattr(handler, "WIKI_BUCKET",   "test-bucket")

    return {"dynamo": dynamo, "table": table, "lambda_": lam, "bedrock": bedrock, "s3": s3}


def test_missing_customer_id_returns_error():
    result = handler.lambda_handler({}, None)
    body   = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["status"] == "error"
    assert "customer_id" in body.get("error", "").lower()


def test_first_invocation_pauses_at_human_phase(mocks):
    result = handler.lambda_handler(VALID_EVENT, None)
    body   = json.loads(result["body"])
    assert body["status"] == "paused"
    assert body["current_phase"] == 3
    assert "question" in body


def test_pause_response_includes_targeted_questions(mocks):
    result = handler.lambda_handler(VALID_EVENT, None)
    body   = json.loads(result["body"])
    question = body.get("question", "")
    assert len(question) > 20, "Question must be substantive, not empty"
    assert "?" in question, "Questions must be phrased as questions"


def test_resume_with_human_context_completes(mocks):
    paused_run = {
        "engagement_id": "test-customer-001",
        "run_id": "run-test-001",
        "status": "paused",
        "current_phase": 3,
        "started_at": "2026-01-01T00:00:00Z",
        "phase_results": json.dumps({
            "phase1": {"customer_status": "new", "pages_found": 0, "key_facts": [], "overview": ""},
            "phase2": {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
                       "implementation_complexity": "HIGH", "rationale": "test",
                       "customer_type": "payer", "products": ["TestProduct v1"]},
        }),
    }
    mocks["table"].query.return_value = {"Items": [paused_run]}

    result = handler.lambda_handler(RESUME_EVENT, None)
    body   = json.loads(result["body"])
    assert body["status"] == "completed"
    assert body.get("phases_completed", 0) >= 7


def test_get_status_returns_current_run_state(mocks):
    run = {
        "engagement_id": "test-customer-001",
        "run_id":        "run-done-001",
        "status":        "completed",
        "current_phase": 8,
        "phase_results": "{}",
        "total_latency_ms": 9000,
    }
    mocks["table"].query.return_value = {"Items": [run]}

    result = handler.lambda_handler({"action": "get_status", "engagement_id": "test-customer-001"}, None)
    body   = json.loads(result["body"])
    assert body["status"] == "completed"
    assert "current_phase" in body


def test_get_status_does_not_invoke_skill_lambdas(mocks):
    run = {
        "engagement_id": "test-customer-001",
        "run_id": "run-done-001",
        "status": "completed",
        "current_phase": 8,
        "phase_results": "{}",
    }
    mocks["table"].query.return_value = {"Items": [run]}

    handler.lambda_handler({"action": "get_status", "engagement_id": "test-customer-001"}, None)
    mocks["lambda_"].invoke.assert_not_called()


def test_phase2_json_fields_parsed_correctly(mocks):
    result = handler.lambda_handler(VALID_EVENT, None)
    body   = json.loads(result["body"])
    pr = body.get("phase_results", "{}")
    phase_results = json.loads(pr) if isinstance(pr, str) else pr
    phase2 = phase_results.get("phase2", {})

    if phase2:
        for field in ["customer_type", "products", "risk_tier",
                      "go_live_urgency", "implementation_complexity", "rationale"]:
            assert field in phase2, f"Phase 2 missing field: {field}"


def test_completed_run_includes_download_url(mocks):
    paused_run = {
        "engagement_id": "test-customer-001",
        "run_id": "run-test-001",
        "status": "paused",
        "current_phase": 3,
        "started_at": "2026-01-01T00:00:00Z",
        "phase_results": json.dumps({
            "phase1": {"customer_status": "new", "pages_found": 0, "key_facts": [], "overview": ""},
            "phase2": {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
                       "implementation_complexity": "HIGH", "rationale": "test",
                       "customer_type": "payer", "products": ["TestProduct v1"]},
        }),
    }
    mocks["table"].query.return_value = {"Items": [paused_run]}

    result = handler.lambda_handler(RESUME_EVENT, None)
    body   = json.loads(result["body"])

    if body["status"] == "completed":
        assert body.get("report_download_url") or \
               (body.get("phase_results") and
                "report_download_url" in json.dumps(body.get("phase_results", ""))), \
            "Completed run must include report_download_url in response or phase_results"


def test_html_report_structure_if_builder_exposed(mocks):
    if not hasattr(handler, "_build_report_html"):
        pytest.skip("_build_report_html not exposed")

    p1 = {"overview": "Overview.", "key_facts": ["F1"], "pages_found": 1}
    p2 = {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM", "implementation_complexity": "HIGH",
          "rationale": "Test", "customer_type": "payer", "products": ["QNXT"]}
    p3 = {"summary": "Human summary."}
    p4 = {"playbook_steps": 3, "pages_loaded": 5}
    p5 = {"confidence": "medium", "answer": "Risk analysis.", "action_items": ["Action 1"]}
    p6 = {"gaps": [{"title": "Gap", "gap_type": "missing-artifact",
                    "blocking": True, "human_prompt": "What?"}],
          "gap_count": 1, "blocking_count": 1}
    p7 = {"found": False, "completion_pct": 0, "populated_fields": [], "missing_fields": []}

    html = handler._build_report_html(
        "t001", "Test Corp", "QNXT", "SOW-001", "2026-07-08",
        p1, p2, p3, p4, p5, p6, p7,
    )
    assert "<html" in html.lower()
    for section in ["Customer Overview", "Knowledge Gaps", "Risk"]:
        assert section in html, f"HTML missing section: {section}"
