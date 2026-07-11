"""
Unit test stubs for ClaimReadinessSkill — auto-generated from skill spec.
Fill in mock_response values before running.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

import handler  # the generated handler.py


HAPPY_PATH_INPUT = {"claim_id": "CLM-001", "service_date": "2026-05-01", "diagnosis_code": "Z00.00", "amount": 450.00}


def _make_event(inputs: dict) -> dict:
    return {"inputs": inputs, "version": "1.0", "invoked_by": "test-runner"}


def test_happy_path(monkeypatch):
    event = _make_event(HAPPY_PATH_INPUT)
    # TODO: mock boto3 clients used by this skill
    result = handler.lambda_handler(event, None)
    body = json.loads(result["body"])
    assert body["status"] == "success"
    assert "outputs" in body
    assert body["outputs"].get("status") in ("ready", "success", "not_applicable")


def test_missing_required_input():
    event = _make_event({})  # empty inputs
    result = handler.lambda_handler(event, None)
    assert result["statusCode"] == 400


def test_government_customer_returns_not_applicable():
    inputs = dict(HAPPY_PATH_INPUT)
    inputs["customer_type"] = "government"
    event = _make_event(inputs)
    # TODO: mock boto3 clients
    result = handler.lambda_handler(event, None)
    body = json.loads(result["body"])
    assert body["outputs"].get("status") == "not_applicable"