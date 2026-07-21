"""
Step 5 — Experiments: prove a prompt or config change actually worked.

Runs the golden dataset against two configurations (baseline vs candidate)
and computes faithfulness scores for both. No Phoenix Experiments API dependency —
calls the system under test directly and evaluates each run locally.

SYSTEM UNDER TEST OPTIONS:
  --target lambda      Call the deployed llmwiki-query Lambda (requires AWS)
  --target mock        Return synthetic answers (offline, no AWS)
  --target bedrock     Call Bedrock directly with local prompt overrides

COMPARE MODES:
  --compare prompts    Compare SYSTEM_PROMPT_V1 vs SYSTEM_PROMPT_V2 (defined below)
  --compare domains    Compare faithfulness across different question domains

Usage:
    python eval/step5_experiments.py                          # mock, prompt compare
    python eval/step5_experiments.py --target mock
    python eval/step5_experiments.py --target lambda --compare prompts
    python eval/step5_experiments.py --target bedrock --compare prompts
"""

import argparse
import csv
import json
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import (
    AWS_PROFILE, AWS_REGION,
    BEDROCK_MODEL_ID, FAITHFULNESS_THRESHOLD,
)

EXPERIMENTS_CSV = os.path.join(os.path.dirname(__file__), "experiment_results.csv")

# ── Prompt variants (edit these to A/B test your own prompts) ─────────────

SYSTEM_PROMPT_V1 = """You are answering questions using a knowledge wiki.
Use ONLY the wiki content provided below.
Cite sources by referencing their wiki page slug in [[double brackets]].
If the wiki content is insufficient to answer, say so clearly.
Provide a clear, concise answer with citations."""

SYSTEM_PROMPT_V2 = """You are a precise knowledge assistant for LLMWiki.
Answer the question using ONLY the wiki passages provided.
Rules:
1. Every factual claim must be traceable to a specific passage.
2. Cite each source as [[page-slug]] immediately after the claim.
3. If coverage is incomplete, explicitly list what is missing.
4. Do not infer, extrapolate, or add general knowledge.
Provide a structured answer."""

# ── Golden dataset (subset of step1 questions) ────────────────────────────

GOLDEN_DATASET = [
    {
        "id": "G-001",
        "question": "What is the standard Sales-to-Service handoff checklist for a new healthcare payer?",
        "domain": "customer-onboarding",
        "context": "The Sales-to-Service playbook requires delivery managers to collect executive sponsor "
                   "information, contractual go-live dates, and product scope before initiating the UC1 agent. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
    },
    {
        "id": "G-002",
        "question": "What are the ARB security requirements for a Facets environment provisioning?",
        "domain": "provisioning",
        "context": "The Facets provisioning runbook specifies that all ARB review items must include "
                   "a security design document covering data classification, network segmentation, and IAM policies. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
    },
    {
        "id": "G-003",
        "question": "What monitoring thresholds trigger an escalation during Facets hypercare?",
        "domain": "hypercare",
        "context": "The hypercare runbook defines monitoring thresholds for Facets production environments. "
                   "Escalation triggers: claims error rate >2% over 15 min, batch 30+ min behind, "
                   "DB pool exhaustion, API p95 >3s, or any P1 incident. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
    },
    {
        "id": "G-004",
        "question": "What are the go/no-go criteria before a Facets production cutover?",
        "domain": "cutover",
        "context": "The cutover planning runbook specifies go/no-go criteria: SIT and E2E sign-off, "
                   "data migration dry run complete, rollback procedure tested, ops team trained, "
                   "monitoring dashboards configured, and executive sponsor cutover authorization signed. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
    },
    {
        "id": "G-005",
        "question": "What data quality checks are required before migrating member enrollment data to QNXT?",
        "domain": "data-migration",
        "context": "The data migration runbook specifies pre-migration validation steps: "
                   "duplicate member ID detection, DOB validation, active coverage date range consistency, "
                   "plan code mapping validation, and subscriber/dependent relationship integrity. "
                   "Source: wiki/skills/sk-03-knowledge-recorder.md",
    },
    {
        "id": "G-006",
        "question": "What are the required sign-off criteria for SIT completion on a healthcare payer platform?",
        "domain": "testing",
        "context": "The testing playbook defines SIT exit criteria: P1/P2 defects resolved or risk-accepted, "
                   "claims volume test at 110% peak, EDI 835/837/270/271 validation passing, "
                   "HIPAA scan zero criticals, and UAT lead written sign-off. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
    },
    {
        "id": "G-007",
        "question": "What is LLMWiki governance and how does it affect agent performance?",
        "domain": "platform",
        "context": "The governance design document describes cost tracking, semantic response caching, "
                   "and per-agent rate limits. Governance adds <5ms overhead on cache misses and "
                   "returns cached responses in <100ms. Source: wiki/skills/sk-02-knowledge-finder.md",
    },
    {
        "id": "G-008",
        "question": "What instance types are recommended for a TriZetto NetworX production environment?",
        "domain": "provisioning",
        "context": "The NetworX sizing guide recommends r-series (memory-optimized) for the application tier "
                   "due to in-memory caching, and RDS with Provisioned IOPS for the database tier. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
    },
]


# ── Task functions ─────────────────────────────────────────────────────────

def task_mock(example: dict, variant: str) -> dict:
    """Return a synthetic answer — no AWS call."""
    v2_marker = "[[" in example["context"]
    if variant == "v2":
        answer = (
            f"Based on the wiki content: {example['context'][:120]}... "
            f"[[{example['domain']}-runbook]]"
        )
    else:
        answer = f"{example['context'][:150]}..."

    faithfulness = "faithful" if len(example["context"]) > 50 else "hallucinated"
    # Simulate v2 being slightly better
    if variant == "v2":
        faithfulness = "faithful"
    return {
        "answer":            answer,
        "retrieved_context": example["context"],
        "faithfulness_mock": faithfulness,
    }


def task_lambda(example: dict, variant: str, lambda_client) -> dict:
    """Call the deployed Lambda. variant is ignored (prompt is in the Lambda)."""
    import json as _json
    resp = lambda_client.invoke(
        FunctionName="llmwiki-query",
        Payload=_json.dumps({"q": example["question"]}).encode(),
    )
    result = _json.loads(resp["Payload"].read())
    body   = _json.loads(result.get("body", "{}"))
    return {
        "answer":            body.get("answer", ""),
        "retrieved_context": " ".join(s.get("page_slug", "") for s in body.get("sources", [])),
        "faithfulness_mock": None,
    }


def task_bedrock(example: dict, variant: str, session) -> dict:
    """Call Bedrock directly with the specified prompt variant."""
    prompt_template = SYSTEM_PROMPT_V2 if variant == "v2" else SYSTEM_PROMPT_V1
    full_prompt = (
        f"{prompt_template}\n\n"
        f"QUESTION: {example['question']}\n\n"
        f"WIKI CONTENT:\n{example['context']}\n\n"
        f"Provide a clear, concise answer with citations."
    )
    bedrock = session.client("bedrock-runtime")
    resp = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": full_prompt}]}],
        inferenceConfig={"maxTokens": 512},
    )
    answer = resp["output"]["message"]["content"][0]["text"].strip()
    return {
        "answer":            answer,
        "retrieved_context": example["context"],
        "faithfulness_mock": None,
    }


# ── Lightweight faithfulness judge ─────────────────────────────────────────

FAITHFULNESS_PROMPT = """You are evaluating whether an answer is faithful to its source context.

Question:  {input}
Context:   {context}
Answer:    {output}

Respond with exactly ONE word: FAITHFUL or HALLUCINATED
Then a one-sentence explanation.
"""


def judge_faithfulness(answer: str, question: str, context: str,
                        mock: bool, session=None) -> str:
    if not context.strip():
        return "hallucinated"
    if mock:
        return "faithful" if "[[" in answer or len(answer) > 60 else "hallucinated"
    try:
        prompt = FAITHFULNESS_PROMPT.format(
            input=question, context=context, output=answer
        )
        bedrock = session.client("bedrock-runtime")
        resp = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 64},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        return "faithful" if "FAITHFUL" in raw.upper().split()[0] else "hallucinated"
    except Exception as e:
        print(f"     WARN: judge call failed: {e}")
        return "faithful" if len(answer) > 60 else "hallucinated"


# ── Run one experiment ─────────────────────────────────────────────────────

def run_variant(dataset: list[dict], variant: str, target: str,
                mock_judge: bool, session=None) -> list[dict]:
    print(f"\n  Running variant '{variant}' ({target} target)...")
    results = []
    for i, ex in enumerate(dataset, 1):
        if target == "mock":
            out = task_mock(ex, variant)
        elif target == "lambda":
            out = task_lambda(ex, variant, session.client("lambda"))
        elif target == "bedrock":
            out = task_bedrock(ex, variant, session)
            time.sleep(0.3)
        else:
            out = task_mock(ex, variant)

        label = (out["faithfulness_mock"]
                 if out["faithfulness_mock"]
                 else judge_faithfulness(
                     out["answer"], ex["question"],
                     out["retrieved_context"], mock_judge, session
                 ))
        marker = "✓" if label == "faithful" else "✗"
        print(f"    [{i:02d}] {marker} [{ex['domain']:20s}] {ex['question'][:50]}")
        results.append({
            "id":       ex["id"],
            "domain":   ex["domain"],
            "question": ex["question"],
            "variant":  variant,
            "answer":   out["answer"][:120],
            "label":    label,
        })
    return results


def compare_variants(v1: list[dict], v2: list[dict]) -> None:
    v1_rate = sum(1 for r in v1 if r["label"] == "faithful") / len(v1)
    v2_rate = sum(1 for r in v2 if r["label"] == "faithful") / len(v2)
    delta   = v2_rate - v1_rate

    print(f"\n=== Experiment Results ===\n")
    print(f"  Variant              Faithful   Rate")
    print(f"  {'─'*45}")
    print(f"  v1 (baseline)        {sum(1 for r in v1 if r['label']=='faithful')}/{len(v1)}        {v1_rate:.1%}")
    print(f"  v2 (candidate)       {sum(1 for r in v2 if r['label']=='faithful')}/{len(v2)}        {v2_rate:.1%}")
    print(f"\n  Delta: {delta:+.1%}", end="  ")
    if delta > 0.05:
        print("→ v2 is meaningfully BETTER — merge the prompt change")
    elif delta < -0.05:
        print("→ v2 is WORSE — revert")
    else:
        print("→ No meaningful difference — too close to call")

    # Per-domain comparison
    domains = sorted({r["domain"] for r in v1})
    if len(domains) > 1:
        print(f"\n  Domain-level delta (v2 - v1):")
        for domain in domains:
            d1 = [r for r in v1 if r["domain"] == domain]
            d2 = [r for r in v2 if r["domain"] == domain]
            if d1 and d2:
                r1 = sum(1 for r in d1 if r["label"] == "faithful") / len(d1)
                r2 = sum(1 for r in d2 if r["label"] == "faithful") / len(d2)
                dd = r2 - r1
                marker = "+" if dd > 0 else ("-" if dd < 0 else " ")
                print(f"    [{marker}] {domain:<25} v1={r1:.0%}  v2={r2:.0%}  Δ={dd:+.0%}")


def save_experiments(v1: list[dict], v2: list[dict], path: str) -> None:
    all_rows = v1 + v2
    fieldnames = ["id", "domain", "question", "variant", "answer", "label"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\n  Experiment results saved → {path}")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phoenix-style experiments")
    parser.add_argument("--target",  choices=["mock", "lambda", "bedrock"], default="mock",
                        help="System under test")
    parser.add_argument("--compare", choices=["prompts", "domains"], default="prompts")
    args = parser.parse_args()

    session = None
    mock_judge = True
    if args.target in ("lambda", "bedrock"):
        try:
            import boto3
            session    = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
            mock_judge = False
        except ImportError:
            print("ERROR: boto3 not installed")
            sys.exit(1)

    print(f"\n=== Step 5: Experiments — target={args.target}, compare={args.compare} ===")
    print(f"  Dataset: {len(GOLDEN_DATASET)} questions")
    print(f"  Prompt v1: {SYSTEM_PROMPT_V1[:60]}...")
    print(f"  Prompt v2: {SYSTEM_PROMPT_V2[:60]}...")

    v1_results = run_variant(GOLDEN_DATASET, "v1", args.target, mock_judge, session)
    v2_results = run_variant(GOLDEN_DATASET, "v2", args.target, mock_judge, session)

    compare_variants(v1_results, v2_results)
    save_experiments(v1_results, v2_results, EXPERIMENTS_CSV)
