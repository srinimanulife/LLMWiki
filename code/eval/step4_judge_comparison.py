"""
Step 4 — LLM-as-a-Judge: Claude vs Amazon Nova Pro comparison.

Reads eval_results.csv produced by step3, shows a full agreement analysis,
highlights disagreements for human review, and prints a summary table.

TWO MODES:
  --mode report  (default)
      Reads the CSV from step3 and reports the already-computed labels.
      No AWS calls needed.

  --mode rerun
      Re-runs both judges against the spans in the CSV via Bedrock.
      Requires valid AWS credentials.

Usage:
    python eval/step4_judge_comparison.py                  # report mode
    python eval/step4_judge_comparison.py --mode report
    python eval/step4_judge_comparison.py --mode rerun
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import (
    AWS_PROFILE, AWS_REGION,
    BEDROCK_MODEL_ID, NOVA_PRO_MODEL_ID,
)

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "eval_results.csv")


def _load_results(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Run step3_run_evals.py first.")
        sys.exit(1)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def report(rows: list[dict]) -> None:
    # Filter to rows that have judge labels
    judged = [r for r in rows if r.get("claude_label") and r.get("nova_label")]
    if not judged:
        print("  No faithfulness labels found in results CSV.")
        print("  Run step3 with faithfulness eval enabled first.")
        return

    total    = len(judged)
    cl_faith = sum(1 for r in judged if r["claude_label"] == "faithful")
    nv_faith = sum(1 for r in judged if r["nova_label"]   == "faithful")
    agreed   = sum(1 for r in judged
                   if r["claude_label"] == r["nova_label"])

    cl_rate   = cl_faith / total
    nv_rate   = nv_faith / total
    agr_rate  = agreed   / total

    print(f"\n=== Step 4: Judge Comparison ({total} evaluated spans) ===\n")
    print(f"  {'Judge':<20} {'Faithful':>10}  {'Hallucinated':>14}  {'Rate':>7}")
    print(f"  {'-'*58}")
    print(f"  {'Claude (Sonnet)':<20} {cl_faith:>10}  {total-cl_faith:>14}  {cl_rate:>7.1%}")
    print(f"  {'Nova Pro':<20} {nv_faith:>10}  {total-nv_faith:>14}  {nv_rate:>7.1%}")
    print(f"\n  Judge agreement: {agreed}/{total} ({agr_rate:.1%})")

    disagreements = [r for r in judged if r["claude_label"] != r["nova_label"]]
    if disagreements:
        print(f"\n  Disagreements ({len(disagreements)} — human review recommended):")
        print(f"  {'Question':<60}  {'Claude':<14} {'Nova'}")
        print(f"  {'-'*92}")
        for r in disagreements:
            q = r.get("question", "")[:58]
            print(f"  {q:<60}  {r['claude_label']:<14} {r['nova_label']}")
    else:
        print("\n  Judges fully agree — high confidence in labels.")

    # Domain breakdown
    by_domain: dict[str, list] = {}
    for r in judged:
        d = r.get("domain", "unknown")
        by_domain.setdefault(d, []).append(r)
    print(f"\n  Domain-level faithfulness (Claude judge):")
    print(f"  {'Domain':<25} {'Faithful':>10}  {'Total':>6}  {'Rate':>7}")
    print(f"  {'-'*52}")
    for domain, domain_rows in sorted(by_domain.items()):
        n_faith = sum(1 for r in domain_rows if r["claude_label"] == "faithful")
        n_total = len(domain_rows)
        rate    = n_faith / n_total if n_total else 0
        marker  = "✓" if rate >= 0.75 else "!"
        print(f"  {marker} {domain:<25} {n_faith:>10}  {n_total:>6}  {rate:>7.1%}")

    print("\n  Interpretation:")
    delta = abs(cl_rate - nv_rate)
    if delta < 0.05:
        print("    → Judges within 5% of each other — strong agreement on this trace set.")
    elif cl_rate > nv_rate:
        print(f"    → Claude is {delta:.1%} more generous than Nova Pro on faithfulness.")
        print("      Disagreements are the most useful cases for human calibration.")
    else:
        print(f"    → Nova Pro is {delta:.1%} more generous than Claude on faithfulness.")
        print("      Disagreements are the most useful cases for human calibration.")

    if agr_rate >= 0.80:
        print("    → Agreement ≥80% — labels are reliable for CI gating.")
    else:
        print("    → Agreement <80% — review disagreements before using labels for CI.")


def rerun(rows: list[dict], session) -> None:
    """Re-run both judges via Bedrock and update labels in place."""
    from step3_run_evals import run_faithfulness_evals
    print("\n  Re-running both judges via Bedrock...")
    faith_results = run_faithfulness_evals(rows, mock=False, session=session)
    # Write back to CSV
    faith_map = {r["span_id"]: r for r in faith_results}
    for row in rows:
        sid = row.get("span_id", "")
        if sid in faith_map:
            row.update({
                "claude_label":       faith_map[sid]["claude_label"],
                "nova_label":         faith_map[sid]["nova_label"],
                "judges_agree":       str(faith_map[sid]["judges_agree"]),
            })
    import csv as _csv
    fieldnames = list(rows[0].keys()) if rows else []
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Updated results → {RESULTS_CSV}")
    report(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Judge comparison: Claude vs Nova Pro")
    parser.add_argument("--mode",        choices=["report", "rerun"], default="report")
    parser.add_argument("--source-csv",  default=RESULTS_CSV)
    args = parser.parse_args()

    rows = _load_results(args.source_csv)

    if args.mode == "rerun":
        try:
            import boto3
            session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        except ImportError:
            print("ERROR: boto3 not installed")
            sys.exit(1)
        rerun(rows, session)
    else:
        report(rows)
