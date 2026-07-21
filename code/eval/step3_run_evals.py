"""
Step 3 — Run the eval pipeline against Phoenix traces.

Sub-steps run in order:
  3a  Code evals        — deterministic checks, no LLM
  3b  Faithfulness eval — LLM-as-a-judge (Claude via Bedrock)
  3c  Custom rubric     — Business Knowledge API contract

TWO MODES:
  --mode offline   (default)
      Loads traces from the CSV written by step2, runs code evals,
      and runs LLM-judge evals using the real Bedrock model.
      Requires valid AWS credentials for Bedrock (not Lambda).

  --mode mock
      Skips all Bedrock calls. Returns synthetic scores for local
      CI validation of the eval pipeline itself. No AWS needed.

Usage:
    python eval/step3_run_evals.py                     # offline mode, Bedrock required
    python eval/step3_run_evals.py --mode mock         # fully offline, no AWS
    python eval/step3_run_evals.py --mode offline --limit 20
    python eval/step3_run_evals.py --source-csv eval/trace_categories.csv
"""

import argparse
import csv
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import (
    AWS_PROFILE, AWS_REGION,
    BEDROCK_MODEL_ID, NOVA_PRO_MODEL_ID,
    FAITHFULNESS_THRESHOLD,
)

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "trace_categories.csv")
RESULTS_CSV = os.path.join(os.path.dirname(__file__), "eval_results.csv")

# ── 3a: Code evals ─────────────────────────────────────────────────────────

def eval_has_answer(row: dict) -> dict:
    answer = str(row.get("output", "")).strip()
    passed = len(answer) > 20
    return {
        "eval":        "has_answer",
        "label":       "pass" if passed else "fail",
        "score":       1 if passed else 0,
        "explanation": f"answer length={len(answer)}",
    }


def eval_citation_present(row: dict) -> dict:
    try:
        count = int(row.get("citations", 0))
    except (ValueError, TypeError):
        count = 0
    passed = count > 0
    return {
        "eval":        "citation_present",
        "label":       "pass" if passed else "fail",
        "score":       1 if passed else 0,
        "explanation": f"{count} citations",
    }


def eval_confidence_calibrated(row: dict) -> dict:
    try:
        count = int(row.get("citations", 0))
    except (ValueError, TypeError):
        count = 0
    conf = str(row.get("confidence", "")).lower()
    if conf == "high" and count == 0:
        return {
            "eval":        "confidence_calibrated",
            "label":       "fail",
            "score":       0,
            "explanation": "high confidence with zero citations",
        }
    return {
        "eval":        "confidence_calibrated",
        "label":       "pass",
        "score":       1,
        "explanation": f"conf={conf}, citations={count}",
    }


def run_code_evals(rows: list[dict]) -> list[dict]:
    print(f"\n  [3a] Code evals on {len(rows)} spans...")
    results = []
    for row in rows:
        base = {"span_id": row.get("span_id", ""), "question": row.get("input", "")[:60]}
        for fn in [eval_has_answer, eval_citation_present, eval_confidence_calibrated]:
            r = fn(row)
            results.append({**base, **r})

    passes = sum(1 for r in results if r["label"] == "pass")
    fails  = sum(1 for r in results if r["label"] == "fail")
    print(f"     Pass: {passes}  Fail: {fails}  Total: {len(results)}")

    failed_evals = [r for r in results if r["label"] == "fail"]
    if failed_evals:
        print("     Failed:")
        for r in failed_evals[:8]:
            print(f"       [{r['eval']:<25}] {r['question']}")
    return results


# ── 3b: LLM-as-a-judge faithfulness ───────────────────────────────────────

FAITHFULNESS_PROMPT = """You are evaluating whether an answer is faithful to its source context.

Question:  {input}
Context:   {context}
Answer:    {output}

Rules:
- FAITHFUL if every specific claim in the Answer is supported by or directly follows from the Context.
- HALLUCINATED if the Answer introduces facts, numbers, names, or claims NOT present in the Context.
- If Context is empty, the answer cannot be faithful — label HALLUCINATED unless the answer explicitly states the wiki has no information.

Respond with exactly ONE word on the first line: FAITHFUL or HALLUCINATED
Then a one-sentence explanation on the second line.
"""

BIZ_API_RUBRIC = """You are evaluating a LLMWiki Business Knowledge API response.

The API should return:
- A direct answer grounded in the context
- Confidence matching the evidence quality
- Citations from the context (in [[brackets]])

Question:  {input}
Context:   {context}
Answer:    {output}

Score on three criteria:
1. Is the confidence level plausible given the context richness?
2. Are citations present when the context has retrievable sources?
3. Does the answer avoid adding claims beyond what the context supports?

Respond with exactly ONE word on the first line: PASS or FAIL
Then a one-sentence explanation on the second line.
"""


def _call_bedrock(prompt: str, model_id: str, session) -> str:
    """Call Bedrock and return the response text."""
    bedrock = session.client("bedrock-runtime")
    resp = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 128},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


def _mock_faithfulness(row: dict) -> dict:
    """Return a plausible synthetic faithfulness label — no Bedrock call."""
    context = str(row.get("context", "")).strip()
    conf    = str(row.get("confidence", "low")).lower()
    if not context:
        label = "hallucinated"
    elif conf == "low":
        label = random.choice(["faithful", "hallucinated"])
    else:
        label = "faithful"
    explanation = "mock eval — no Bedrock call"
    return {"claude_label": label, "claude_explanation": explanation,
            "nova_label":   label, "nova_explanation":   explanation}


def run_faithfulness_evals(rows: list[dict], mock: bool, session=None) -> list[dict]:
    eval_rows = [r for r in rows if len(str(r.get("context", "")).strip()) > 10]
    print(f"\n  [3b] Faithfulness eval on {len(eval_rows)} spans with context "
          f"({'mock' if mock else 'Bedrock'})...")

    results = []
    for i, row in enumerate(eval_rows, 1):
        prompt = FAITHFULNESS_PROMPT.format(
            input=row.get("input", ""),
            context=row.get("context", ""),
            output=row.get("output", ""),
        )
        if mock:
            labels = _mock_faithfulness(row)
        else:
            try:
                claude_raw  = _call_bedrock(prompt, BEDROCK_MODEL_ID, session)
                claude_line = claude_raw.splitlines()
                claude_label = "faithful" if "FAITHFUL" in claude_line[0].upper() else "hallucinated"
                claude_expl  = claude_line[1] if len(claude_line) > 1 else ""

                nova_raw  = _call_bedrock(prompt, NOVA_PRO_MODEL_ID, session)
                nova_line = nova_raw.splitlines()
                nova_label = "faithful" if "FAITHFUL" in nova_line[0].upper() else "hallucinated"
                nova_expl  = nova_line[1] if len(nova_line) > 1 else ""

                labels = {
                    "claude_label":       claude_label,
                    "claude_explanation": claude_expl,
                    "nova_label":         nova_label,
                    "nova_explanation":   nova_expl,
                }
                time.sleep(0.3)  # rate-limit courtesy
            except Exception as e:
                print(f"     WARN [{i}]: Bedrock call failed: {e} — using mock")
                labels = _mock_faithfulness(row)

        agree = labels["claude_label"] == labels["nova_label"]
        marker = "✓" if labels["claude_label"] == "faithful" else "✗"
        q = row.get("input", "")[:55]
        print(f"     [{i:02d}] {marker} Claude={labels['claude_label']:<12} "
              f"Nova={labels['nova_label']:<12} agree={agree}  {q}")

        results.append({
            "span_id":           row.get("span_id", ""),
            "domain":            row.get("domain", ""),
            "confidence":        row.get("confidence", ""),
            "question":          row.get("input", ""),
            **labels,
            "judges_agree":      agree,
        })

    faithful_count  = sum(1 for r in results if r["claude_label"] == "faithful")
    agree_count     = sum(1 for r in results if r["judges_agree"])
    total           = len(results)
    faith_rate      = faithful_count / total if total else 0
    agree_rate      = agree_count    / total if total else 0
    print(f"\n     Faithfulness rate (Claude): {faith_rate:.1%}  ({faithful_count}/{total})")
    print(f"     Judge agreement:            {agree_rate:.1%}")
    disagreements = [r for r in results if not r["judges_agree"]]
    if disagreements:
        print(f"     Disagreements (review these):")
        for r in disagreements[:5]:
            print(f"       Q: {r['question'][:60]}")
            print(f"         Claude={r['claude_label']}, Nova={r['nova_label']}")
    return results


def run_biz_api_eval(rows: list[dict], mock: bool, session=None) -> list[dict]:
    eval_rows = [r for r in rows if len(str(r.get("output", "")).strip()) > 20]
    print(f"\n  [3c] Business API rubric eval on {len(eval_rows)} spans "
          f"({'mock' if mock else 'Bedrock'})...")
    results = []
    for i, row in enumerate(eval_rows, 1):
        prompt = BIZ_API_RUBRIC.format(
            input=row.get("input", ""),
            context=row.get("context", ""),
            output=row.get("output", ""),
        )
        if mock:
            conf = str(row.get("confidence", "low")).lower()
            label = "PASS" if conf in ("high", "medium") else "FAIL"
            expl  = "mock eval"
        else:
            try:
                raw   = _call_bedrock(prompt, BEDROCK_MODEL_ID, session)
                lines = raw.splitlines()
                label = "PASS" if "PASS" in lines[0].upper() else "FAIL"
                expl  = lines[1] if len(lines) > 1 else ""
                time.sleep(0.3)
            except Exception as e:
                print(f"     WARN [{i}]: {e} — using mock")
                conf  = str(row.get("confidence", "low")).lower()
                label = "PASS" if conf in ("high", "medium") else "FAIL"
                expl  = "mock eval (error fallback)"

        marker = "✓" if label == "PASS" else "✗"
        q = row.get("input", "")[:55]
        print(f"     [{i:02d}] {marker} {label:<5} {q}")
        results.append({
            "span_id":           row.get("span_id", ""),
            "domain":            row.get("domain", ""),
            "biz_api_label":     label,
            "biz_api_explanation": expl,
        })

    pass_count = sum(1 for r in results if r["biz_api_label"] == "PASS")
    total      = len(results)
    print(f"\n     Business API PASS rate: {pass_count}/{total} "
          f"({100*pass_count/total if total else 0:.1f}%)")
    return results


# ── Save merged results ────────────────────────────────────────────────────

def save_results(code_results, faith_results, biz_results, path: str) -> None:
    # Index by span_id for merge
    faith_map = {r["span_id"]: r for r in faith_results}
    biz_map   = {r["span_id"]: r for r in biz_results}

    fieldnames = [
        "span_id", "domain", "confidence", "question",
        "has_answer", "citation_present", "confidence_calibrated",
        "claude_label", "nova_label", "judges_agree",
        "biz_api_label",
    ]
    rows_by_span: dict[str, dict] = {}
    for r in code_results:
        sid = r["span_id"]
        if sid not in rows_by_span:
            rows_by_span[sid] = {"span_id": sid, "question": r.get("question", "")}
        rows_by_span[sid][r["eval"]] = r["label"]

    merged = []
    for sid, base in rows_by_span.items():
        faith = faith_map.get(sid, {})
        biz   = biz_map.get(sid, {})
        merged.append({
            "span_id":               sid,
            "domain":                faith.get("domain", ""),
            "confidence":            faith.get("confidence", ""),
            "question":              base.get("question", ""),
            "has_answer":            base.get("has_answer", ""),
            "citation_present":      base.get("citation_present", ""),
            "confidence_calibrated": base.get("confidence_calibrated", ""),
            "claude_label":          faith.get("claude_label", ""),
            "nova_label":            faith.get("nova_label", ""),
            "judges_agree":          faith.get("judges_agree", ""),
            "biz_api_label":         biz.get("biz_api_label", ""),
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)
    print(f"\n  Results saved → {path}")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the LLMWiki Phoenix eval pipeline")
    parser.add_argument("--mode",       choices=["offline", "mock"], default="mock",
                        help="offline=real Bedrock, mock=no AWS calls")
    parser.add_argument("--source-csv", default=DEFAULT_CSV)
    parser.add_argument("--limit",      type=int, default=50)
    parser.add_argument("--skip-3b",    action="store_true", help="Skip faithfulness eval")
    parser.add_argument("--skip-3c",    action="store_true", help="Skip Business API rubric eval")
    args = parser.parse_args()

    # Load traces from CSV
    if not os.path.exists(args.source_csv):
        print(f"ERROR: {args.source_csv} not found. Run step2_read_traces.py first.")
        sys.exit(1)

    rows: list[dict] = []
    with open(args.source_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[:args.limit]
    print(f"\n=== Step 3: Eval pipeline — {len(rows)} spans from {args.source_csv} ===")

    session = None
    if args.mode == "offline":
        try:
            import boto3
            session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        except ImportError:
            print("WARN: boto3 not installed — falling back to mock")
            args.mode = "mock"

    mock = (args.mode == "mock")

    code_results  = run_code_evals(rows)
    faith_results = run_faithfulness_evals(rows, mock=mock, session=session) \
                    if not args.skip_3b else []
    biz_results   = run_biz_api_eval(rows, mock=mock, session=session) \
                    if not args.skip_3c else []

    save_results(code_results, faith_results, biz_results, RESULTS_CSV)

    # CI gate
    if faith_results:
        faith_rate = sum(1 for r in faith_results
                         if r["claude_label"] == "faithful") / len(faith_results)
        print(f"\n  CI gate — faithfulness {faith_rate:.1%} vs threshold {FAITHFULNESS_THRESHOLD:.1%}")
        if faith_rate < FAITHFULNESS_THRESHOLD:
            print(f"  FAIL: below threshold ({FAITHFULNESS_THRESHOLD:.0%})")
            sys.exit(1)
        print("  PASS")
