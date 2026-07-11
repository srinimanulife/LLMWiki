#!/usr/bin/env python3
"""
generate_pipeline.py — End-to-end pipeline orchestrator.

Reads a UC brief (.md), finds all referenced workflow and skill specs,
generates code for each, runs tests, and reports results.

Usage:
  python3 scripts/generate_pipeline.py --brief wiki_seed/skills/uc-01-brief.md
  python3 scripts/generate_pipeline.py --brief wiki_seed/skills/uc-01-brief.md --deploy
  python3 scripts/generate_pipeline.py --workflow wiki_seed/skills/wf-UC1-sales-to-service.md
  python3 scripts/generate_pipeline.py --skill wiki_seed/skills/sk-06-claim-validation.md

What it does:
  1. Parse brief / workflow / skill spec (whatever is provided)
  2. For each skill spec referenced → run generate_skill_lambda.py
  3. For the workflow spec → run generate_harness.py
  4. Run auto-tests on every generated file
  5. Print a summary report

After all generation, optionally deploys with --deploy.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_SEED = os.path.join(ROOT_DIR, "wiki_seed", "skills")
SCRIPTS   = os.path.join(ROOT_DIR, "scripts")


# ════════════════════════════════════════════════════════════════════════════════
# Brief parser — extracts workflow and skill spec references
# ════════════════════════════════════════════════════════════════════════════════

def parse_brief(brief_path: str) -> dict:
    """Parse a UC brief to find its workflow spec and skill spec references."""
    with open(brief_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Extract front matter
    fm = {}
    fm_match = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                v = v.strip().strip('"').strip("'")
                fm[k.strip()] = v

    use_case_id = fm.get("use_case_id", "UC99")
    domain      = fm.get("domain", "general")

    # Find workflow spec reference in the brief text
    wf_match = re.search(r"wf-(" + use_case_id + r"[^`\s]+\.md)", raw, re.IGNORECASE)
    workflow_spec = None
    if wf_match:
        wf_file = os.path.join(WIKI_SEED, wf_match.group(0).replace("`", ""))
        if os.path.exists(wf_file):
            workflow_spec = wf_file

    # Auto-discover workflow spec if not found in text
    if not workflow_spec:
        for fname in os.listdir(WIKI_SEED):
            if fname.startswith(f"wf-{use_case_id.upper()}") and fname.endswith(".md"):
                workflow_spec = os.path.join(WIKI_SEED, fname)
                break
        if not workflow_spec:
            for fname in os.listdir(WIKI_SEED):
                if fname.lower().startswith(f"wf-{use_case_id.lower()}") and fname.endswith(".md"):
                    workflow_spec = os.path.join(WIKI_SEED, fname)
                    break

    # Find skill IDs referenced in the brief
    skill_ids = list(set(re.findall(r"SK-\d+", raw)))

    # Map skill IDs to spec files
    skill_specs = []
    for sk_id in skill_ids:
        sk_num = sk_id.replace("SK-", "").zfill(2)
        for fname in os.listdir(WIKI_SEED):
            # Match files like sk-06-*.md
            if re.match(rf"sk-0?{sk_num.lstrip('0')}-.*\.md", fname, re.IGNORECASE) and not fname.startswith("_"):
                spec_path = os.path.join(WIKI_SEED, fname)
                if spec_path not in skill_specs:
                    skill_specs.append(spec_path)

    return {
        "use_case_id":   use_case_id,
        "domain":        domain,
        "brief_path":    brief_path,
        "workflow_spec": workflow_spec,
        "skill_specs":   skill_specs,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Individual generator runners
# ════════════════════════════════════════════════════════════════════════════════

def _run_script(script_name: str, args_list: list, label: str) -> dict:
    """Run a generator script as a subprocess. Returns result dict."""
    cmd = [sys.executable, os.path.join(SCRIPTS, script_name)] + args_list
    print(f"\n  Running: {script_name} {' '.join(args_list)}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT_DIR)
    elapsed = int((time.time() - t0) * 1000)
    success = result.returncode == 0
    if success:
        print(f"  OK [{elapsed}ms] — {label}")
    else:
        print(f"  FAILED [{elapsed}ms] — {label}")
        print(f"  stderr: {result.stderr.strip()[:500]}")
    return {
        "label":    label,
        "success":  success,
        "elapsed":  elapsed,
        "stdout":   result.stdout,
        "stderr":   result.stderr,
    }


def run_skill_generator(spec_path: str, deploy: bool = False,
                        region: str = "us-east-1", profile: str = "tzg-sandbox") -> dict:
    """Generate a skill Lambda from a spec file."""
    args = ["--spec", spec_path, "--region", region, "--profile", profile]
    if deploy:
        args.append("--deploy")
    return _run_script("generate_skill_lambda.py", args,
                       f"Skill: {os.path.basename(spec_path)}")


def run_harness_generator(spec_path: str, deploy: bool = False,
                          region: str = "us-east-1", profile: str = "tzg-sandbox") -> dict:
    """Generate a harness Lambda from a workflow spec file."""
    args = ["--spec", spec_path, "--region", region, "--profile", profile]
    if deploy:
        args.append("--deploy")
    return _run_script("generate_harness.py", args,
                       f"Harness: {os.path.basename(spec_path)}")


# ════════════════════════════════════════════════════════════════════════════════
# Test runner
# ════════════════════════════════════════════════════════════════════════════════

def run_tests_for_generated_files(results: list) -> list:
    """Run pytest on every test file that was generated."""
    test_results = []

    # Find test files from previous generation
    test_dirs = []
    for r in results:
        if not r["success"]:
            continue
        # Infer test dir from the spec path
        stdout = r.get("stdout", "")
        for line in stdout.splitlines():
            if "Wrote:" in line and ("test_" in line):
                test_file = line.replace("  Wrote:", "").strip()
                test_dir  = os.path.dirname(test_file)
                if test_dir not in test_dirs:
                    test_dirs.append(test_dir)

    for test_dir in test_dirs:
        if not os.path.isdir(test_dir):
            continue
        test_files = [f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py")]
        for tf in test_files:
            test_path = os.path.join(test_dir, tf)
            print(f"\n  Running tests: {test_path}")
            t0 = time.time()
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, cwd=test_dir,
            )
            elapsed = int((time.time() - t0) * 1000)
            passed  = result.returncode == 0

            # Count pass/fail from pytest output
            m = re.search(r"(\d+) passed", result.stdout)
            m_fail = re.search(r"(\d+) failed", result.stdout)
            n_pass = int(m.group(1)) if m else 0
            n_fail = int(m_fail.group(1)) if m_fail else 0

            status = "PASS" if passed else "FAIL"
            print(f"  {status} [{elapsed}ms] — {n_pass} passed, {n_fail} failed — {tf}")
            if not passed:
                # Print short output
                for line in result.stdout.splitlines()[-20:]:
                    print(f"    {line}")

            test_results.append({
                "test_file": test_path,
                "passed":    passed,
                "n_pass":    n_pass,
                "n_fail":    n_fail,
                "elapsed":   elapsed,
                "output":    result.stdout[-2000:],
            })

    return test_results


# ════════════════════════════════════════════════════════════════════════════════
# Summary printer
# ════════════════════════════════════════════════════════════════════════════════

def print_summary(gen_results: list, test_results: list):
    print("\n" + "="*72)
    print("PIPELINE SUMMARY")
    print("="*72)

    print(f"\n{'GENERATION':-<40}")
    gen_ok   = sum(1 for r in gen_results if r["success"])
    gen_fail = len(gen_results) - gen_ok
    for r in gen_results:
        icon = "✓" if r["success"] else "✗"
        print(f"  {icon} {r['label']:<45} {r['elapsed']}ms")
    print(f"\n  Generated: {gen_ok}/{len(gen_results)} OK   ({gen_fail} failed)")

    print(f"\n{'TESTS':-<40}")
    if not test_results:
        print("  No tests were run (generation may have failed or no test files found)")
    else:
        test_ok   = sum(1 for r in test_results if r["passed"])
        test_fail = len(test_results) - test_ok
        total_pass = sum(r["n_pass"] for r in test_results)
        total_fail = sum(r["n_fail"] for r in test_results)
        for r in test_results:
            icon = "✓" if r["passed"] else "✗"
            fname = os.path.basename(r["test_file"])
            print(f"  {icon} {fname:<45} {r['n_pass']} pass / {r['n_fail']} fail")
        print(f"\n  Test files: {test_ok}/{len(test_results)} OK")
        print(f"  Test cases: {total_pass} passed, {total_fail} failed")

    overall_ok = gen_ok == len(gen_results) and all(r["passed"] for r in test_results)
    print(f"\n{'='*72}")
    print(f"OVERALL: {'ALL GOOD ✓' if overall_ok else 'ISSUES FOUND ✗'}")
    print(f"{'='*72}\n")
    return overall_ok


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LLMWiki end-to-end generation pipeline: brief → code → tests"
    )
    # Input — one of these three
    parser.add_argument("--brief",    help="Path to a UC brief (uc-NN-*.md) — generates harness + all referenced skills")
    parser.add_argument("--workflow", help="Path to a workflow spec (wf-UCnn-*.md) — generates harness only")
    parser.add_argument("--skill",    help="Path to a skill spec (sk-NN-*.md) — generates that skill only")

    parser.add_argument("--deploy",   action="store_true", help="Deploy each Lambda after generating")
    parser.add_argument("--no-test",  action="store_true", help="Skip running tests after generation")
    parser.add_argument("--region",   default="us-east-1")
    parser.add_argument("--profile",  default="tzg-sandbox")
    args = parser.parse_args()

    if not any([args.brief, args.workflow, args.skill]):
        parser.print_help()
        sys.exit(1)

    print(f"\nLLMWiki Generation Pipeline")
    print(f"{'='*60}")
    print(f"Region : {args.region}")
    print(f"Profile: {args.profile}")
    print(f"Deploy : {args.deploy}")
    print(f"Tests  : {not args.no_test}")
    print(f"{'='*60}")

    gen_results  = []
    specs_to_run = {"skills": [], "workflow": None}

    if args.skill:
        # Single skill mode
        specs_to_run["skills"] = [os.path.abspath(args.skill)]

    elif args.workflow:
        # Single workflow mode
        specs_to_run["workflow"] = os.path.abspath(args.workflow)

    elif args.brief:
        # Full brief mode — parse brief to discover workflow + skills
        brief_path = os.path.abspath(args.brief)
        if not os.path.exists(brief_path):
            print(f"ERROR: brief not found: {brief_path}")
            sys.exit(1)

        print(f"\nParsing brief: {brief_path}")
        brief = parse_brief(brief_path)
        print(f"  Use Case    : {brief['use_case_id']}")
        print(f"  Domain      : {brief['domain']}")
        print(f"  Workflow    : {brief['workflow_spec'] or 'NOT FOUND'}")
        print(f"  Skill specs : {len(brief['skill_specs'])} found")
        for s in brief["skill_specs"]:
            print(f"    - {os.path.basename(s)}")

        if brief["workflow_spec"]:
            specs_to_run["workflow"] = brief["workflow_spec"]
        specs_to_run["skills"] = brief["skill_specs"]

    # ── Generate skills ───────────────────────────────────────────────────────
    if specs_to_run["skills"]:
        print(f"\n{'─'*60}")
        print(f"GENERATING {len(specs_to_run['skills'])} SKILL(S)")
        print(f"{'─'*60}")
        for spec_path in specs_to_run["skills"]:
            r = run_skill_generator(spec_path, deploy=args.deploy,
                                    region=args.region, profile=args.profile)
            gen_results.append(r)

    # ── Generate harness ──────────────────────────────────────────────────────
    if specs_to_run["workflow"]:
        print(f"\n{'─'*60}")
        print("GENERATING HARNESS")
        print(f"{'─'*60}")
        r = run_harness_generator(specs_to_run["workflow"], deploy=args.deploy,
                                  region=args.region, profile=args.profile)
        gen_results.append(r)

    if not gen_results:
        print("ERROR: Nothing to generate. Check your spec file paths.")
        sys.exit(1)

    # ── Run tests ─────────────────────────────────────────────────────────────
    test_results = []
    if not args.no_test:
        print(f"\n{'─'*60}")
        print("RUNNING AUTO-TESTS")
        print(f"{'─'*60}")
        test_results = run_tests_for_generated_files(gen_results)

    # ── Summary ───────────────────────────────────────────────────────────────
    ok = print_summary(gen_results, test_results)
    sys.exit(0 if ok else 1)
