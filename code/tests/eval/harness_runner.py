"""
Agent Eval Harness Runner
=========================
Generic runner that executes golden case contracts against any LLMWiki agent harness.
Reusable for UC1 (Sales-to-Service) and UC-PM (Problem Management).

Usage:
    python tests/eval/harness_runner.py --agent uc1 --golden tests/golden/uc1_agent_golden_v1.json
    python tests/eval/harness_runner.py --agent pm  --golden tests/golden/pm_agent_golden_v1.json

Output:
    Console: pass/fail per contract check
    JSON:    /tmp/eval_results_<agent>_<timestamp>.json
"""

import argparse
import json
import sys
import time
import boto3
from datetime import datetime, timezone

REGION  = "us-east-1"
PROFILE = "tzg-sandbox"

AGENT_CONFIG = {
    "uc1": {
        "function_name": "llmwiki-uc1-harness",
        "caller_tag":    "eval-uc1-harness",
        "description":   "UC1 Sales-to-Service Handoff",
    },
    "pm": {
        "function_name": "llmwiki-harness-uc-pm",
        "caller_tag":    "eval-pm-harness",
        "description":   "UC-PM Problem Management",
    },
}

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"


def _invoke(client, fn: str, payload: dict) -> dict:
    resp = client.invoke(FunctionName=fn, Payload=json.dumps(payload))
    raw  = resp["Payload"].read()
    outer = json.loads(raw)
    body  = outer.get("body")
    if body:
        return json.loads(body) if isinstance(body, str) else body
    return outer


def _check(condition: bool, name: str, detail: str = "") -> dict:
    sym = PASS if condition else FAIL
    print(f"    {sym} {name}" + (f" — {detail}" if detail else ""))
    return {"name": name, "passed": condition, "detail": detail}


def run_case(client, fn: str, case: dict) -> dict:
    """Run a single golden case and check all contract conditions. Generic across agents."""
    print(f"\n  {INFO} {case['case_id']}: {case['name']}")
    checks = []
    start  = time.time()

    try:
        body = _invoke(client, fn, case["input"])
    except Exception as e:
        checks.append(_check(False, "invocation_succeeds", str(e)))
        return {"case_id": case["case_id"], "passed": False, "checks": checks, "latency_ms": 0}

    latency_ms = int((time.time() - start) * 1000)
    contract   = case.get("contract", {})

    # ── Generic contract checks (apply to any harness) ────────────

    if "status_eq" in contract:
        checks.append(_check(
            body.get("status") == contract["status_eq"],
            "status",
            f"expected={contract['status_eq']} got={body.get('status')}",
        ))

    if "no_500" in contract and contract["no_500"]:
        checks.append(_check(
            body.get("status") != "internal_error" and "traceback" not in json.dumps(body).lower(),
            "no_500_error",
        ))

    if "error_field_present" in contract and contract["error_field_present"]:
        checks.append(_check("error" in body, "error_field_present"))

    if "error_mentions_any" in contract:
        error_text = str(body.get("error", "")).lower()
        matches = any(kw.lower() in error_text for kw in contract["error_mentions_any"])
        checks.append(_check(matches, "error_mentions_keyword",
                              f"keywords={contract['error_mentions_any']} in '{error_text[:100]}'"))

    if "phase_eq" in contract:
        checks.append(_check(
            body.get("current_phase") == contract["phase_eq"],
            "current_phase",
            f"expected={contract['phase_eq']} got={body.get('current_phase')}",
        ))

    if "fields_present" in contract:
        for field in contract["fields_present"]:
            checks.append(_check(field in body, f"field_present:{field}"))

    if "report_download_url_non_empty" in contract and contract["report_download_url_non_empty"]:
        url = body.get("report_download_url", "")
        if not url:
            pr = body.get("phase_results", {})
            if isinstance(pr, str):
                pr = json.loads(pr)
            url = pr.get("phase8", {}).get("report_download_url", "")
        checks.append(_check(bool(url), "report_download_url_present", url[:80] if url else "EMPTY"))

    if "phases_completed_gte" in contract:
        actual = body.get("phases_completed", 0)
        checks.append(_check(
            actual >= contract["phases_completed_gte"],
            "phases_completed",
            f"expected>={contract['phases_completed_gte']} got={actual}",
        ))

    if "question_count_eq" in contract:
        q = body.get("question", "")
        import re
        numbered = re.findall(r'(?:^|\n)\s*[123][.)]\s', q)
        count = len(numbered) if numbered else q.count("?")
        checks.append(_check(
            count >= contract["question_count_eq"],
            "question_count",
            f"expected>={contract['question_count_eq']} found={count}",
        ))

    if "question_topics_cover_any" in contract:
        q    = body.get("question", "").lower()
        hits = [t for t in contract["question_topics_cover_any"] if t.lower() in q]
        checks.append(_check(bool(hits), "question_topics", f"matched={hits}"))

    all_passed = all(c["passed"] for c in checks)
    print(f"    {'All passed' if all_passed else 'FAILURES'} — {latency_ms}ms")
    return {
        "case_id":    case["case_id"],
        "name":       case["name"],
        "tags":       case.get("tags", []),
        "passed":     all_passed,
        "checks":     checks,
        "latency_ms": latency_ms,
    }


def run_golden_set(agent: str, golden_file: str) -> dict:
    cfg    = AGENT_CONFIG[agent]
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    client  = session.client("lambda")

    with open(golden_file) as f:
        golden = json.load(f)

    cases = golden.get("cases", golden.get("examples", []))
    print(f"\n{'='*60}")
    print(f"  LLMWiki Agent Eval — {cfg['description']}")
    print(f"  Function: {cfg['function_name']}")
    print(f"  Cases: {len(cases)}")
    print(f"  Golden: {golden_file}")
    print(f"{'='*60}")

    results = []
    for case in cases:
        # Skip cases that require prior state for simple runner
        if case.get("prior_state") or case.get("case_id", "").endswith("-002"):
            print(f"\n  {INFO} {case['case_id']}: SKIP (requires prior workflow state — run via integration test)")
            continue
        result = run_case(client, cfg["function_name"], case)
        results.append(result)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{len(results)} passed  |  {failed} failed")
    print(f"{'='*60}")

    # Save results
    out_file = f"/tmp/eval_results_{agent}_{int(time.time())}.json"
    output = {
        "agent":        agent,
        "function":     cfg["function_name"],
        "golden_file":  golden_file,
        "run_at":       datetime.now(timezone.utc).isoformat(),
        "summary":      {"total": len(results), "passed": passed, "failed": failed},
        "results":      results,
        "go_no_go":     "GO" if failed == 0 else "NO-GO",
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {out_file}")
    print(f"  Verdict: {'✅ GO' if failed == 0 else '❌ NO-GO — fix failures before deploying'}")

    return output


def main():
    parser = argparse.ArgumentParser(description="LLMWiki Agent Eval Harness Runner")
    parser.add_argument("--agent",  default="uc1", choices=list(AGENT_CONFIG.keys()))
    parser.add_argument("--golden", help="Path to golden JSON file")
    args = parser.parse_args()

    default_golden = {
        "uc1": "tests/golden/uc1_agent_golden_v1.json",
        "pm":  "tests/golden/pm_agent_golden_v1.json",
    }
    golden_file = args.golden or default_golden[args.agent]

    output = run_golden_set(args.agent, golden_file)
    sys.exit(0 if output["go_no_go"] == "GO" else 1)


if __name__ == "__main__":
    main()
