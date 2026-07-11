"""
Integration test stubs for Sales-to-Service Handoff harness — auto-generated.
Mocks all AWS clients. Fill in assertion values after reviewing generated code.
Run with: python -m pytest test_harness.py -v
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call
import handler


# ── Minimal valid inputs ──────────────────────────────────────────────────
VALID_EVENT = {
    "customer_id":   "test-customer-001",
    "customer_name": "Test Corp",
    "product":       "TestProduct v1",
    "sow_reference": "SOW-TEST-001",
}

RESUME_EVENT = {
    **VALID_EVENT,
    "human_context": "Executive sponsor is Jane Smith. Go-live Q3. No prior attempts.",
}


def _make_lambda_response(body: dict) -> dict:
    return {
        "Payload": MagicMock(read=lambda: json.dumps({"body": json.dumps(body)}).encode())
    }


@pytest.fixture
def mock_aws(monkeypatch):
    """Patch all AWS clients used by the harness."""
    dynamo_mock  = MagicMock()
    lambda_mock  = MagicMock()
    bedrock_mock = MagicMock()
    s3_mock      = MagicMock()

    table_mock = MagicMock()
    table_mock.put_item.return_value    = {}
    table_mock.update_item.return_value = {}
    table_mock.query.return_value       = {"Items": []}
    table_mock.get_item.return_value    = {"Item": {}}
    dynamo_mock.Table.return_value      = table_mock

    lambda_mock.invoke.return_value = _make_lambda_response({
        "status": "success", "customer_status": "new", "pages_found": 0,
        "key_facts": [], "overview": "Test customer",
        "outputs": {
            "customer_status": "new", "pages_loaded": 1,
            "playbook": {"steps": []}, "confidence": "low",
            "answer": "Test risk answer",
            "action_items": ["Review data migration plan"],
            "gaps": [], "found": False, "completion_pct": 0,
            "populated_fields": [], "missing_fields": [],
            "status": "indexed", "s3_uri": "s3://test-bucket/test.md",
        }
    })

    bedrock_mock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps({
            "content": [{"text": '{"customer_type":"payer","products":["TestProduct v1"],
                "risk_tier":"HIGH","go_live_urgency":"MEDIUM",
                "implementation_complexity":"HIGH","rationale":"New customer"}'}]
        }).encode())
    }

    s3_mock.put_object.return_value           = {}
    s3_mock.generate_presigned_url.return_value = "https://s3.example.com/report.html"

    monkeypatch.setattr(handler, "dynamodb",      dynamo_mock)
    monkeypatch.setattr(handler, "lambda_client", lambda_mock)
    monkeypatch.setattr(handler, "bedrock",       bedrock_mock)
    monkeypatch.setattr(handler, "s3_client",     s3_mock)
    monkeypatch.setattr(handler, "WIKI_BUCKET",   "test-llmwiki-bucket")

    return {"dynamo": dynamo_mock, "table": table_mock,
            "lambda_": lambda_mock, "bedrock": bedrock_mock, "s3": s3_mock}


def test_missing_customer_id_returns_error():
    """Harness must reject events with no customer_id."""
    result = handler.lambda_handler({}, None)
    body   = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["status"] == "error"
    assert "customer_id" in body.get("error", "").lower()

def test_first_invocation_pauses_at_human_phase(mock_aws):
    """First call should run phases 1-2 then pause waiting for human input."""
    result = handler.lambda_handler(VALID_EVENT, None)
    body   = json.loads(result["body"])
    assert body["status"] == "paused"
    assert body["current_phase"] == 3
    assert "question" in body


def test_resume_with_human_context_completes(mock_aws):
    """Providing human_context should resume and complete all phases."""
    # Make _find_paused_run return a paused run so resume path is taken
    paused_run = {
        "engagement_id": "test-customer-001",
        "run_id": "run-test-customer-001-999",
        "status": "paused",
        "current_phase": 3,
        "started_at": "2026-01-01T00:00:00Z",
        "phase_results": '{"phase1": {"customer_status": "new", "pages_found": 0}, "phase2": {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM", "implementation_complexity": "HIGH", "rationale": "test", "customer_type": "payer", "products": ["TestProduct"]}}',
    }
    mock_aws["table"].query.return_value = {"Items": [paused_run]}
    event = RESUME_EVENT

    result = handler.lambda_handler(event, None)
    body   = json.loads(result["body"])
    assert body["status"] == "completed"
    assert body.get("phases_completed") is not None


def test_get_status_action(mock_aws):
    """get_status action should return current run state."""
    run_item = {
        "engagement_id":  "test-customer-001",
        "run_id":         "run-test-customer-001-999",
        "status":         "completed",
        "current_phase":  8,
        "phase_results":  "{}",
        "total_latency_ms": 5000,
    }
    mock_aws["table"].query.return_value = {"Items": [run_item]}
    event  = {"action": "get_status", "engagement_id": "test-customer-001"}
    result = handler.lambda_handler(event, None)
    body   = json.loads(result["body"])
    assert body["status"] == "completed"


def test_report_html_contains_required_sections(mock_aws):
    """The HTML report must contain all required section headings."""
    mock_aws["table"].query.return_value = {"Items": []}
    event = RESUME_EVENT

    result = handler.lambda_handler(event, None)

    p1 = {'overview': 'Test overview', 'key_facts': ['Fact 1'], 'pages_found': 1}
    p2 = {'risk_tier': 'HIGH', 'go_live_urgency': 'MEDIUM', 'implementation_complexity': 'HIGH',
          'rationale': 'Test', 'customer_type': 'payer', 'products': ['TestProduct']}
    p3 = {'summary': 'Human context'}
    p4 = {'playbook_steps': 3, 'pages_loaded': 5}
    p5 = {'confidence': 'medium', 'answer': 'Risk answer', 'action_items': ['Action 1']}
    p6 = {'gaps': [{'title': 'Gap 1', 'gap_type': 'missing-artifact',
                    'blocking': True, 'human_prompt': 'What is X?'}],
          'gap_count': 1, 'blocking_count': 1}
    p7 = {'found': False, 'completion_pct': 0, 'populated_fields': [], 'missing_fields': []}
    if hasattr(handler, '_build_report_html'):
        html = handler._build_report_html(
            'test-001', 'Test Corp', 'TestProduct', 'SOW-001', '2026-01-01',
            p1, p2, p3, p4, p5, p6, p7,
        )
        assert '<!DOCTYPE html>' in html
        assert 'Customer Overview' in html
        assert 'Knowledge Gaps' in html
        assert 'kpi' in html.lower()