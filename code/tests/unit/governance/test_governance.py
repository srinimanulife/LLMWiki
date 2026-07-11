"""
Governance Module — Unit Tests
Tests cost tracking, cache key generation, rate limit logic, and fallback behavior.
No live DynamoDB. All clients mocked.

Run: pytest tests/unit/governance/ -v
"""

import json
import sys
import os
import time
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

# conftest.py in this directory patches boto3 into sys.modules before collection.
# The GOV_PATH is also set there. Import governance directly.
try:
    import governance as gov
    _AVAILABLE = True
except ImportError as _e:
    _AVAILABLE = False
    _IMPORT_ERR = str(_e)

pytestmark = pytest.mark.skipif(
    not _AVAILABLE,
    reason=f"governance module not importable: {locals().get('_IMPORT_ERR', 'unknown')}",
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level client singletons between tests."""
    gov._dynamodb = None
    gov._bedrock  = None
    yield
    gov._dynamodb = None
    gov._bedrock  = None


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock()
    table = MagicMock()
    table.put_item.return_value    = {}
    table.update_item.return_value = {"Attributes": {"count": Decimal("1")}}
    table.get_item.return_value    = {"Item": {}}
    table.scan.return_value        = {"Items": []}
    table.query.return_value       = {"Items": []}
    db.Table.return_value = table
    monkeypatch.setattr(gov, "_dynamodb", db)
    return {"db": db, "table": table}


# ── Cost calculation ───────────────────────────────────────────────

def test_record_usage_cost_calculation_sonnet(mock_db):
    cost = gov.record_usage(
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        caller="test",
        operation="query",
    )
    # $0.003/1K input + $0.015/1K output = $0.003 + $0.0075 = $0.0105
    assert abs(cost - 0.0105) < 0.0001, f"Expected ~0.0105, got {cost}"


def test_record_usage_cost_calculation_haiku(mock_db):
    cost = gov.record_usage(
        model_id="us.anthropic.claude-haiku-4-5-20251001",
        input_tokens=2000,
        output_tokens=1000,
        caller="test",
        operation="query",
    )
    # $0.0008/1K * 2 + $0.004/1K * 1 = $0.0016 + $0.004 = $0.0056
    assert abs(cost - 0.0056) < 0.0001, f"Expected ~0.0056, got {cost}"


def test_record_usage_cache_hit_zero_cost(mock_db):
    cost = gov.record_usage(
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        caller="test",
        operation="query",
        cache_hit=True,
    )
    assert cost == 0.0, "Cache hit with zero tokens should produce zero cost"


def test_record_usage_writes_to_primary_table(mock_db):
    gov.record_usage("us.anthropic.claude-sonnet-4-6", 100, 50, caller="unit-test")
    mock_db["table"].put_item.assert_called_once()
    item = mock_db["table"].put_item.call_args[1]["Item"]
    assert item["caller"] == "unit-test"
    assert "timestamp" in item
    assert "cost_usd" in item
    assert "request_id" in item


def test_record_usage_fallback_on_access_denied(mock_db):
    from botocore.exceptions import ClientError
    mock_db["table"].put_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "not authorized to perform: dynamodb:PutItem"}},
        "PutItem",
    )
    # Should not raise — fails open
    cost = gov.record_usage("us.anthropic.claude-sonnet-4-6", 100, 50, caller="fallback-test")
    assert isinstance(cost, float)


def test_record_usage_fails_open_on_any_exception(mock_db):
    mock_db["table"].put_item.side_effect = Exception("Unexpected error")
    cost = gov.record_usage("us.anthropic.claude-sonnet-4-6", 100, 50, caller="test")
    assert isinstance(cost, float), "record_usage must never raise — fail open"


# ── Cache key ─────────────────────────────────────────────────────

def test_cache_key_deterministic():
    k1 = gov._cache_key("What is the handoff checklist?", domain="uc1", kb_id="kb-123")
    k2 = gov._cache_key("What is the handoff checklist?", domain="uc1", kb_id="kb-123")
    assert k1 == k2, "Same inputs must produce same cache key"


def test_cache_key_case_insensitive():
    k1 = gov._cache_key("What is the handoff checklist?")
    k2 = gov._cache_key("WHAT IS THE HANDOFF CHECKLIST?")
    assert k1 == k2, "Cache key must normalize case"


def test_cache_key_domain_sensitive():
    k1 = gov._cache_key("What are the risks?", domain="provisioning")
    k2 = gov._cache_key("What are the risks?", domain="testing")
    assert k1 != k2, "Different domains must produce different cache keys"


def test_cache_key_is_hex_string():
    k = gov._cache_key("test question")
    assert len(k) == 64, "SHA-256 hex digest must be 64 chars"
    assert all(c in "0123456789abcdef" for c in k)


# ── Cache get / put ───────────────────────────────────────────────

def test_cache_put_writes_to_table(mock_db):
    gov.cache_put("test question", {"answer": "test"}, domain="uc1", kb_id="")
    mock_db["table"].put_item.assert_called_once()
    item = mock_db["table"].put_item.call_args[1]["Item"]
    assert "cache_key" in item
    assert "response_json" in item
    assert "expires_at" in item
    assert item["expires_at"] > int(time.time())


def test_cache_get_returns_none_on_miss(mock_db):
    mock_db["table"].get_item.return_value = {"Item": None}
    result = gov.cache_get("unknown question", domain="uc1")
    assert result is None


def test_cache_get_returns_hit_on_exact_match(mock_db):
    question = "What is the handoff checklist?"
    cached_result = {"answer": "The checklist includes...", "confidence": "high"}
    key = gov._cache_key(question)

    mock_db["table"].get_item.return_value = {
        "Item": {
            "cache_key":     key,
            "response_json": json.dumps(cached_result),
            "expires_at":    int(time.time()) + 3600,
        }
    }

    result = gov.cache_get(question)
    assert result is not None
    assert result["answer"] == cached_result["answer"]


def test_cache_get_fails_open_on_exception(mock_db):
    mock_db["table"].get_item.side_effect = Exception("Network error")
    result = gov.cache_get("any question")
    assert result is None, "cache_get must return None on exception — fail open"


# ── Rate limiting ─────────────────────────────────────────────────

def test_check_rate_limit_allows_first_request(mock_db):
    mock_db["table"].update_item.return_value = {
        "Attributes": {"count": Decimal("1"), "expires_at": Decimal(str(int(time.time()) + 120))}
    }
    allowed, info = gov.check_rate_limit("test-caller", window_minutes=1, max_requests=30)
    assert allowed is True
    assert info["count"] == 1


def test_check_rate_limit_blocks_at_max(mock_db):
    mock_db["table"].update_item.return_value = {
        "Attributes": {"count": Decimal("31"), "expires_at": Decimal(str(int(time.time()) + 120))}
    }
    allowed, info = gov.check_rate_limit("heavy-caller", window_minutes=1, max_requests=30)
    assert allowed is False
    assert info["count"] == 31


def test_check_rate_limit_fails_open_on_access_denied(mock_db):
    from botocore.exceptions import ClientError
    mock_db["table"].update_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "UpdateItem"
    )
    allowed, info = gov.check_rate_limit("test-caller")
    assert allowed is True, "Rate limit must fail open on AccessDenied"


# ── Pure Python cosine similarity ─────────────────────────────────

def test_cosine_identical_vectors():
    v = [1.0, 0.5, 0.25]
    assert abs(gov._cosine(v, v) - 1.0) < 1e-6


def test_cosine_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(gov._cosine(a, b)) < 1e-6


def test_cosine_empty_vectors():
    assert gov._cosine([], [1.0, 2.0]) == 0.0
    assert gov._cosine([], []) == 0.0


def test_cosine_mismatched_lengths():
    assert gov._cosine([1.0, 2.0], [1.0]) == 0.0


def test_cosine_similar_vectors_high_score():
    a = [0.9, 0.1, 0.05]
    b = [0.88, 0.12, 0.06]
    score = gov._cosine(a, b)
    assert score > 0.99, f"Very similar vectors should score >0.99, got {score}"
