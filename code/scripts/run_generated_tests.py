#!/usr/bin/env python3
"""
run_generated_tests.py — Standalone auto-test runner for generated Lambda handlers.

Imports generated handler.py directly, mocks all AWS clients using unittest.mock,
and runs happy path / missing input / edge case tests without needing real AWS.

Usage:
  python3 scripts/run_generated_tests.py --handler lambda/skills/claim_readiness/handler.py
  python3 scripts/run_generated_tests.py --handler lambda/harness/uc1_harness/handler.py
  python3 scripts/run_generated_tests.py --dir lambda/skills/          # all skills
  python3 scripts/run_generated_tests.py --dir lambda/harness/         # all harnesses
  python3 scripts/run_generated_tests.py --all                         # everything

Output: pass/fail per test case + summary table. Exit code 0 if all pass.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import traceback
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ════════════════════════════════════════════════════════════════════════════════
# Handler loader — import a handler.py without polluting sys.modules
# ════════════════════════════════════════════════════════════════════════════════

def load_handler(handler_path: str):
    """Dynamically import a handler.py and return the module."""
    spec = importlib.util.spec_from_file_location("handler_under_test", handler_path)
    mod  = importlib.util.module_from_spec(spec)
    # Pre-inject a fake boto3 so the module-level client initialization doesn't fail
    fake_boto3 = _make_fake_boto3()
    mod.__builtins__ = __builtins__
    sys.modules["boto3"]   = fake_boto3
    sys.modules["handler_under_test"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"Failed to import {handler_path}: {e}") from e
    return mod


def _make_fake_boto3():
    """Return a mock boto3 module that returns MagicMock clients/resources."""
    fake = MagicMock()
    # client() and resource() return mocks that don't blow up on attribute access
    fake.client.return_value  = MagicMock()
    fake.resource.return_value = MagicMock()
    return fake


# ════════════════════════════════════════════════════════════════════════════════
# AWS mock factory — injects standard responses for all harness/skill patterns
# ════════════════════════════════════════════════════════════════════════════════

class AWSMocks:
    """Reusable mock set for all generated handlers."""

    def __init__(self, handler_module, scenario: str = "happy"):
        self.mod      = handler_module
        self.scenario = scenario
        self.dynamo   = MagicMock()
        self.lambda_  = MagicMock()
        self.bedrock  = MagicMock()
        self.s3       = MagicMock()
        self.sns      = MagicMock()
        self._setup()

    def _lambda_response(self, body: dict) -> dict:
        return {
            "Payload": MagicMock(read=lambda: json.dumps({"body": json.dumps(body)}).encode())
        }

    def _bedrock_response(self, text: str) -> dict:
        return {
            "body": MagicMock(read=lambda: json.dumps({
                "content": [{"text": text}]
            }).encode())
        }

    def _setup(self):
        # DynamoDB table — generic success
        table_mock = MagicMock()
        table_mock.put_item.return_value    = {}
        table_mock.update_item.return_value = {}
        table_mock.get_item.return_value    = {"Item": {}}
        table_mock.query.return_value       = {"Items": []}
        self.dynamo.Table.return_value      = table_mock
        self.dynamo_table = table_mock

        # Lambda invoke — return a skill-shaped success response
        skill_success = {
            "status": "success",
            "customer_status": "new",
            "pages_found": 1,
            "key_facts":   ["Key fact about customer"],
            "overview":    "Test customer overview",
            "playbook":    {"steps": [{"step": 1, "title": "Kick-off", "description": "Initial meeting"}]},
            "outputs": {
                "customer_status": "new",
                "pages_loaded":    2,
                "playbook":        {"steps": []},
                "confidence":      "medium",
                "answer":          "Key risks include data migration complexity.",
                "action_items":    ["Review data migration plan", "Confirm BAA status"],
                "gaps":            [
                    {"title": "Missing BAA policy", "gap_type": "missing-artifact",
                     "blocking": True, "human_prompt": "Is a BAA required for this customer?"}
                ],
                "gap_count":  1,
                "blocking_count": 1,
                "found":           False,
                "completion_pct":  0,
                "populated_fields": [],
                "missing_fields":  [],
                "status":          "indexed",
                "s3_uri":          "s3://test-bucket/wiki/customers/test.md",
                "readiness_score": 85,
                "blocking_issues": [],
                "warnings":        [],
                "lines_checked":   3,
                "lines_ready":     3,
            }
        }
        self.lambda_.invoke.return_value = self._lambda_response(skill_success)

        # Bedrock — return valid classification JSON by default
        classification_json = json.dumps({
            "customer_type": "payer",
            "products":      ["TestProduct v1"],
            "risk_tier":     "HIGH",
            "go_live_urgency": "MEDIUM",
            "implementation_complexity": "HIGH",
            "rationale": "New customer with complex multi-system integration requirements."
        })
        self.bedrock.invoke_model.return_value = self._bedrock_response(classification_json)

        # S3
        self.s3.put_object.return_value           = {}
        self.s3.generate_presigned_url.return_value = "https://s3.example.com/report.html"

        # SNS
        self.sns.publish.return_value = {"MessageId": "test-msg-123"}

    def inject(self):
        """Inject mocks into the loaded handler module. Returns self for chaining."""
        mod = self.mod
        for attr, mock in [
            ("dynamodb",      self.dynamo),
            ("lambda_client", self.lambda_),
            ("bedrock",       self.bedrock),
            ("s3_client",     self.s3),
            ("sns",           self.sns),
        ]:
            if hasattr(mod, attr):
                setattr(mod, attr, mock)

        # Also set WIKI_BUCKET so S3 writes are attempted (not skipped)
        if hasattr(mod, "WIKI_BUCKET"):
            mod.WIKI_BUCKET = "test-llmwiki-bucket"

        # Override MODEL_ID to avoid real Bedrock calls in unit tests
        if hasattr(mod, "MODEL_ID"):
            mod.MODEL_ID = "us.anthropic.claude-sonnet-4-6"

        return self


# ════════════════════════════════════════════════════════════════════════════════
# Generic test cases that apply to ALL generated handlers
# ════════════════════════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self, name: str, passed: bool, error: str = ""):
        self.name   = name
        self.passed = passed
        self.error  = error


def _is_harness(mod) -> bool:
    """True if this module looks like a harness (has _phase1_* or _PhaseError)."""
    return hasattr(mod, "_PhaseError") or any(
        n.startswith("_phase") for n in dir(mod)
    )


def _is_skill(mod) -> bool:
    """True if this module looks like a skill Lambda."""
    return hasattr(mod, "SKILL_ID") or hasattr(mod, "_skill_response")


def run_all_tests(handler_path: str) -> list:
    """Load handler and run all applicable test cases. Returns list of TestResult."""
    results = []
    label   = os.path.basename(os.path.dirname(handler_path))

    # Load the module
    try:
        mod = load_handler(handler_path)
    except Exception as e:
        results.append(TestResult(f"{label}:import", False, str(e)))
        return results

    # Inject mocks
    mocks = AWSMocks(mod).inject()

    if _is_harness(mod):
        results += _test_harness(mod, mocks, label)
    elif _is_skill(mod):
        results += _test_skill(mod, mocks, label)
    else:
        # Generic Lambda — just test it doesn't crash on an empty event
        results += _test_generic(mod, mocks, label)

    return results


def _call_handler(mod, event: dict):
    """Call lambda_handler safely. Returns (result_dict, error_str)."""
    try:
        raw = mod.lambda_handler(event, None)
        if isinstance(raw, dict) and "body" in raw:
            body = raw["body"]
            return json.loads(body) if isinstance(body, str) else body, ""
        return raw, ""
    except Exception as e:
        return {}, traceback.format_exc()


def _test_skill(mod, mocks: AWSMocks, label: str) -> list:
    """Standard test suite for skill Lambdas."""
    results = []

    # T1 — Happy path: valid inputs → status=success
    mocks.inject()
    body, err = _call_handler(mod, {"inputs": {"customer_id": "test-001",
                                                "question": "What are the risks?",
                                                "artifact_type": "persona-template",
                                                "page_type": "customers",
                                                "page_slug": "test-customer-handoff-2026",
                                                "content": "# Test handoff\n\nCustomer: Test Corp",
                                                "claim_batch_id": "BATCH-001",
                                                "claim_lines": [
                                                    {"claim_id": "CLM-001", "service_date": "2026-01-01",
                                                     "diagnosis_code": "Z00.00", "amount": 450.0}
                                                ]},
                                    "version": "1.0", "invoked_by": "test"})
    passed = (err == "" and body.get("status") in ("success", "ready", "not_applicable", "indexed", "not_found"))
    results.append(TestResult(f"{label}:happy_path", passed,
                               err or (f"status={body.get('status')}" if not passed else "")))

    # T2 — Missing required input → 400 or error status
    mocks.inject()
    raw_result = mod.lambda_handler({}, None)
    if isinstance(raw_result, dict):
        status_code = raw_result.get("statusCode", 200)
        body2 = raw_result.get("body", "{}")
        body2 = json.loads(body2) if isinstance(body2, str) else body2
        passed2 = (status_code == 400 or body2.get("status") == "error"
                   or "error" in body2 or "required" in str(body2).lower())
    else:
        passed2 = False
    results.append(TestResult(f"{label}:missing_inputs",
                               passed2, "" if passed2 else f"Got: {raw_result}"))

    # T3 — Response has required skill contract fields
    mocks.inject()
    body3, err3 = _call_handler(mod, {"inputs": {"customer_id": "test-001",
                                                   "question": "test",
                                                   "artifact_type": "persona-template",
                                                   "page_type": "customers",
                                                   "page_slug": "test-customer-handoff-2026",
                                                   "content": "# Test handoff\n\nCustomer: Test Corp",
                                                   "claim_batch_id": "B-001",
                                                   "claim_lines": [{"claim_id": "C-1",
                                                       "service_date": "2026-01-01",
                                                       "diagnosis_code": "Z00", "amount": 100}]},
                                      "version": "1.0", "invoked_by": "test"})
    has_outputs = "outputs" in body3 or body3.get("status") in ("success", "ready", "not_applicable", "indexed", "not_found", "error")
    results.append(TestResult(f"{label}:contract_fields", err3 == "" and has_outputs,
                               err3 or ("missing 'outputs' or 'status'" if not has_outputs else "")))

    # T4 — Government customer returns not_applicable (if business rule applies)
    source = open(handler_path).read()
    if "not_applicable" in source and "government" in source:
        mocks.inject()
        body4, err4 = _call_handler(mod, {
            "inputs": {"customer_id": "gov-001", "customer_type": "government",
                       "claim_batch_id": "B-001",
                       "claim_lines": [{"claim_id": "C-1", "service_date": "2026-01-01",
                                        "diagnosis_code": "Z00", "amount": 100}]},
            "version": "1.0", "invoked_by": "test"
        })
        outputs4 = body4.get("outputs", body4)
        passed4 = err4 == "" and outputs4.get("status") == "not_applicable"
        results.append(TestResult(f"{label}:government_not_applicable", passed4,
                                   err4 or f"status={outputs4.get('status')}"))

    return results


def _test_harness(mod, mocks: AWSMocks, label: str) -> list:
    """Standard test suite for harness Lambdas."""
    results = []
    handler_path = importlib.util.find_spec("handler_under_test").origin

    # T1 — Missing customer_id → error
    mocks.inject()
    raw = mod.lambda_handler({}, None)
    body = json.loads(raw.get("body", "{}")) if isinstance(raw.get("body"), str) else raw.get("body", {})
    passed = body.get("status") == "error"
    results.append(TestResult(f"{label}:requires_customer_id", passed,
                               "" if passed else f"Got status={body.get('status')}"))

    # T2 — get_status action (no real run needed)
    mocks.inject()
    run_item = {
        "engagement_id":  "test-001",
        "run_id":         "run-test-001-999",
        "status":         "completed",
        "current_phase":  8,
        "phase_results":  "{}",
        "total_latency_ms": 3000,
    }
    mocks.dynamo_table.query.return_value = {"Items": [run_item]}
    raw2 = mod.lambda_handler({"action": "get_status", "engagement_id": "test-001"}, None)
    body2 = json.loads(raw2.get("body", "{}")) if isinstance(raw2.get("body"), str) else raw2.get("body", {})
    passed2 = body2.get("status") in ("completed", "running", "paused", "not_found")
    results.append(TestResult(f"{label}:get_status", passed2,
                               "" if passed2 else f"Got: {body2}"))

    # T3 — First invocation pauses if human_input_phase > 0
    source = open(handler_path).read()
    if "status.*paused" in source or '"paused"' in source:
        mocks.inject()
        mocks.dynamo_table.query.return_value = {"Items": []}  # no paused run
        event3 = {
            "customer_id":   "test-001",
            "customer_name": "Test Corp",
            "product":       "TestProduct",
            "sow_reference": "SOW-001",
        }
        raw3   = mod.lambda_handler(event3, None)
        body3  = json.loads(raw3.get("body", "{}")) if isinstance(raw3.get("body"), str) else raw3.get("body", {})
        # Should either pause or complete (if phase has no human input)
        passed3 = body3.get("status") in ("paused", "completed", "error")
        results.append(TestResult(f"{label}:first_invocation", passed3,
                                   "" if passed3 else f"Unexpected status: {body3.get('status')}"))

    # T4 — _build_report_html returns valid HTML
    if hasattr(mod, "_build_report_html"):
        try:
            p1 = {"overview": "Test overview", "key_facts": ["Fact 1"], "pages_found": 1}
            p2 = {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM",
                  "implementation_complexity": "HIGH", "rationale": "Test",
                  "customer_type": "payer", "products": ["TestProduct"]}
            p3 = {"summary": "Human provided context"}
            p4 = {"playbook_steps": 3, "pages_loaded": 5}
            p5 = {"confidence": "medium", "answer": "Risk answer", "action_items": ["Action 1"]}
            p6 = {"gaps": [{"title": "Gap 1", "gap_type": "missing-artifact",
                             "blocking": True, "human_prompt": "What is X?"}],
                  "gap_count": 1, "blocking_count": 1}
            p7 = {"found": False, "completion_pct": 0,
                  "populated_fields": [], "missing_fields": []}
            html = mod._build_report_html(
                "test-001", "Test Corp", "TestProduct", "SOW-001", "2026-01-01",
                p1, p2, p3, p4, p5, p6, p7
            )
            has_sections = (
                "<!DOCTYPE html>" in html and
                "Customer Overview" in html and
                "kpi" in html.lower() and
                "Knowledge Gaps" in html
            )
            results.append(TestResult(f"{label}:report_html_structure", has_sections,
                                       "" if has_sections else "HTML missing required sections"))
        except Exception as e:
            results.append(TestResult(f"{label}:report_html_structure", False, str(e)))

    return results


def _test_generic(mod, mocks: AWSMocks, label: str) -> list:
    """Fallback test suite for any Lambda that doesn't match skill or harness pattern."""
    results = []
    mocks.inject()
    try:
        raw = mod.lambda_handler({}, None)
        results.append(TestResult(f"{label}:no_crash_on_empty_event", True))
    except Exception as e:
        results.append(TestResult(f"{label}:no_crash_on_empty_event", False, str(e)))
    return results


# ════════════════════════════════════════════════════════════════════════════════
# File discovery
# ════════════════════════════════════════════════════════════════════════════════

def discover_handlers(paths: list) -> list:
    """Expand paths to handler.py files."""
    handlers = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p) and p.endswith("handler.py"):
            handlers.append(p)
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                if "handler.py" in files:
                    handlers.append(os.path.join(root, "handler.py"))
    return sorted(set(handlers))


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run auto-tests on generated Lambda handlers (no AWS required)"
    )
    parser.add_argument("--handler", help="Path to a single handler.py")
    parser.add_argument("--dir",     help="Directory to scan for handler.py files")
    parser.add_argument("--all",     action="store_true",
                        help="Test all handlers in lambda/skills/ and lambda/harness/")
    args = parser.parse_args()

    paths = []
    if args.handler:
        paths = [args.handler]
    elif args.dir:
        paths = [args.dir]
    elif args.all:
        paths = [
            os.path.join(ROOT_DIR, "lambda", "skills"),
            os.path.join(ROOT_DIR, "lambda", "harness"),
        ]
    else:
        parser.print_help()
        sys.exit(1)

    handlers = discover_handlers(paths)
    if not handlers:
        print("No handler.py files found.")
        sys.exit(1)

    print(f"\nLLMWiki Generated Handler Test Runner")
    print(f"{'='*60}")
    print(f"Found {len(handlers)} handler(s) to test")
    print(f"{'='*60}\n")

    all_results  = []
    total_pass   = 0
    total_fail   = 0

    for handler_path in handlers:
        label = os.path.relpath(handler_path, ROOT_DIR)
        print(f"Testing: {label}")
        t0      = time.time()
        results = run_all_tests(handler_path)
        elapsed = int((time.time() - t0) * 1000)

        for r in results:
            icon = "  ✓" if r.passed else "  ✗"
            detail = f" ({r.error})" if not r.passed and r.error else ""
            print(f"{icon} {r.name}{detail}")
            if r.passed:
                total_pass += 1
            else:
                total_fail += 1
        all_results.extend(results)
        print(f"  [{elapsed}ms]")
        print()

    # Clean up sys.modules
    sys.modules.pop("handler_under_test", None)

    print(f"{'='*60}")
    print(f"RESULTS: {total_pass} passed / {total_fail} failed / {total_pass + total_fail} total")
    print(f"{'='*60}\n")

    sys.exit(0 if total_fail == 0 else 1)
