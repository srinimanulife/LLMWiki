"""
Master runner — executes all 5 Phoenix eval steps end-to-end.

Runs fully offline by default (no AWS, no docker required to start the script
— but Phoenix must be running for Steps 0-2).

Usage:
    python eval/run_all_steps.py                    # fully offline (mock)
    python eval/run_all_steps.py --aws              # use real Bedrock judges
    python eval/run_all_steps.py --skip-docker      # Phoenix already running
    python eval/run_all_steps.py --step 3           # run only step 3

Exit code 0 = all steps passed the CI gate.
Exit code 1 = at least one step failed.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import PHOENIX_ENDPOINT, PROJECT_LAMBDA, FAITHFULNESS_THRESHOLD


def _phoenix_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{PHOENIX_ENDPOINT}/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _run_step(label: str, script: str, extra_args: list[str] = None) -> bool:
    args = [sys.executable, os.path.join(os.path.dirname(__file__), script)]
    if extra_args:
        args += extra_args
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(args, cwd=os.path.dirname(__file__))
    ok = result.returncode == 0
    status = "PASS" if ok else "FAIL"
    print(f"\n  [{status}] {label}")
    return ok


def run_all(skip_docker: bool, use_aws: bool, only_step: int | None) -> bool:
    results = {}

    # ── Step 0: Start Phoenix ─────────────────────────────────────────────
    if only_step is None or only_step == 0:
        if skip_docker:
            if _phoenix_healthy():
                print("\n[Step 0] Phoenix already running — skipping docker start")
                results[0] = True
            else:
                print("\n[Step 0] FAIL: --skip-docker set but Phoenix not healthy at "
                      f"{PHOENIX_ENDPOINT}")
                results[0] = False
        else:
            results[0] = _run_step("Step 0: Start Phoenix", "step0_start_phoenix.py")
            if not results[0]:
                print("  Cannot continue without Phoenix — exiting")
                return False
            # Brief settle time
            time.sleep(2)

    # ── Step 1: Seed traces ───────────────────────────────────────────────
    if only_step is None or only_step == 1:
        extra = ["--mode", "live" if use_aws else "seed",
                 "--project", PROJECT_LAMBDA]
        results[1] = _run_step("Step 1: Seed / live-capture traces",
                                "step1_seed_traces.py", extra)

    # ── Step 2: Read and categorise traces ────────────────────────────────
    if only_step is None or only_step == 2:
        results[2] = _run_step("Step 2: Read traces and categorise",
                                "step2_read_traces.py",
                                ["--project", PROJECT_LAMBDA, "--limit", "100"])

    # ── Step 3: Run eval pipeline ─────────────────────────────────────────
    if only_step is None or only_step == 3:
        mode  = "offline" if use_aws else "mock"
        extra = ["--mode", mode]
        results[3] = _run_step("Step 3: Run eval pipeline (code + faithfulness + rubric)",
                                "step3_run_evals.py", extra)

    # ── Step 4: Judge comparison ──────────────────────────────────────────
    if only_step is None or only_step == 4:
        results[4] = _run_step("Step 4: Judge comparison (Claude vs Nova Pro)",
                                "step4_judge_comparison.py", ["--mode", "report"])

    # ── Step 5: Experiments ───────────────────────────────────────────────
    if only_step is None or only_step == 5:
        target = "bedrock" if use_aws else "mock"
        results[5] = _run_step("Step 5: Experiments (prompt A/B test)",
                                "step5_experiments.py",
                                ["--target", target, "--compare", "prompts"])

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  EVAL PIPELINE SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for step, ok in sorted(results.items()):
        status = "PASS" if ok else "FAIL"
        marker = "✓" if ok else "✗"
        print(f"  {marker} Step {step}: {status}")
        if not ok:
            all_pass = False

    if all_pass:
        print(f"\n  ALL STEPS PASSED — Phoenix UI: {PHOENIX_ENDPOINT}")
    else:
        print(f"\n  SOME STEPS FAILED — check output above")
    return all_pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all Phoenix eval steps end-to-end")
    parser.add_argument("--aws",         action="store_true",
                        help="Use real Bedrock judges and Lambda (requires AWS creds)")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Skip docker start — assume Phoenix already running")
    parser.add_argument("--step",        type=int, default=None,
                        help="Run only this step number (0-5)")
    args = parser.parse_args()

    ok = run_all(
        skip_docker=args.skip_docker,
        use_aws=args.aws,
        only_step=args.step,
    )
    sys.exit(0 if ok else 1)
