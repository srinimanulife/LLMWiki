# LLMWiki Evaluation Strategy

**Version:** 1.0  
**Date:** 2026-07-08  
**Status:** Implementation Guide  
**Scope:** End-to-end quality measurement for LLMWiki's RAG pipeline, agentic skills, and Business Knowledge API — covering human UI queries, AgentCore skill invocations, and CI/CD quality gates

---

## Why Evaluation Matters Here

LLMWiki serves two fundamentally different caller types with different failure modes:

| Caller | Failure mode | Consequence |
|--------|-------------|-------------|
| **Human (Streamlit UI)** | Wrong answer with high confidence | User makes a bad decision and trusts it |
| **AgentCore skill** | Hallucinated citation / wrong structured field | Downstream agent cascades the error across UC2–UC10 |
| **Ingest pipeline** | Poor extraction quality | Bad knowledge contaminates the KB for everyone |

A human can notice and ignore a wrong answer. An agent cannot. This asymmetry means evaluation is not optional once AgentCore integration is live — a 5% hallucination rate in the Business Knowledge API propagates to every use case that calls it.

The governance layer (cost tracking, caching, rate limiting) tells you *how much* the system costs. This evaluation strategy tells you *how good* it is.

---

## The Four-Layer Evaluation Stack

```
Layer 4 — Business outcome  (quarterly, manual)
            "Did the agent's action produce the right result in production?"

Layer 3 — End-to-end agent trace  (weekly / pre-release)
            "Did the agent take the right steps in the right order?"

Layer 2 — RAG pipeline quality  (every deploy, RAGAS)
            "Did retrieval surface the right chunks? Did generation use them faithfully?"

Layer 1 — Deterministic unit checks  (every commit, <1 minute)
            "Do structured outputs parse? Are citations non-empty? Does format match contract?"
```

You run all four layers. You pay for Layer 1 on every commit (free — deterministic), Layer 2 on every deploy (cheap — RAGAS autoscores), Layer 3 before every release (moderate — LLM judge), and Layer 4 quarterly with a human reviewer.

---

## Part 1 — Golden Datasets

### 1.1 What a Golden Dataset Is

A golden dataset is a fixed set of (input, reference_output) pairs that you control and version. It is the only way to measure whether a change to the prompt, model, or retriever made things better or worse. Without it, every change is a blind bet.

For LLMWiki, you need **three separate golden datasets** — one per system boundary:

| Dataset | Input | Reference output | Use |
|---------|-------|-----------------|-----|
| **RAG-golden** | Question string | Answer text + 3–5 expected citation sources | RAGAS scoring, regression |
| **API-golden** | Business API request JSON | Full structured response (answer, citations, action_items, confidence, gaps) | Field-level regression, schema validation |
| **Agent-golden** | Agent goal + initial context | Expected tool call sequence + final answer | Trace-level evaluation |

### 1.2 How to Build a Reliable Test Set from Production Logs

The best golden examples come from real production traffic — not from developers inventing questions.

**Step 1 — Mine LLMWiki's `llmwiki-log` table.**  
Every query Lambda invocation already writes a log row. Export the last 90 days:

```python
# Pull all query logs from llmwiki-log
import boto3, json
db = boto3.resource("dynamodb", region_name="us-east-1")
table = db.Table("llmwiki-log")
resp = table.scan()
rows = resp["Items"]
# filter to query operations only
queries = [r for r in rows if r.get("operation") == "query"]
```

**Step 2 — Apply a stratified selection filter.**  
You want coverage across dimensions, not a random sample biased toward common questions:

```python
# Target distribution for a 200-example RAG-golden set:
STRATA = {
    "confidence=high":   60,   # 30% — confirm the easy cases stay easy
    "confidence=medium": 60,   # 30% — most improvement potential
    "confidence=low":    40,   # 20% — hard cases, catch regressions
    "cache_hit=false":   30,   # 15% — unique questions only
    "multi_domain":      10,   # 5%  — questions that span >1 wiki domain
}
```

**Step 3 — Write reference answers manually for the initial set.**  
Do not use the current model's output as the reference — that is circular. Have a subject-matter expert (or a senior consultant familiar with TriZetto provisioning standards) write 2–3 sentence reference answers for each selected question. For the API-golden set, fill every structured field.

**Step 4 — Validate references against source documents.**  
Each reference answer should cite at least one specific S3 wiki page that contains the supporting text. If you cannot find one, the question may be outside the current KB scope — add it to the `gaps` list instead.

### 1.3 How Many Examples You Actually Need

| Goal | Minimum | Recommended |
|------|---------|-------------|
| Basic regression detection | 50 | — |
| Statistical reliability (pass/fail decisions) | **100** | — |
| Segment-level analysis (by domain, confidence tier) | — | **500** |
| Agent trace evaluation (per use case) | 10–20 per UC | 50 per UC |

The 100-example minimum for statistical reliability comes from LXT.ai's benchmark analysis (Mar 2026): below 100 examples, a 3-percentage-point score change sits inside the confidence interval and cannot be distinguished from noise. At 500 examples you can reliably detect whether a prompt change improved retrieval for the `provisioning` domain without degrading `configuration`.

For LLMWiki with 10 use cases, the practical target is:
- **RAG-golden:** 500 examples, 50 per domain
- **API-golden:** 200 examples, 20 per domain  
- **Agent-golden:** 100 examples, 10 per UC

### 1.4 Why You Should Rotate Every 6 Months

Two failure modes happen if you never rotate:

1. **Overfitting.** Prompt engineers unconsciously optimize for the specific wording in the golden set. New deployment works well on the benchmark but degrades on real production queries with different phrasing.

2. **Distribution drift.** TriZetto's implementation processes evolve. New products, new SOW structures, new provisioning patterns. A golden set written in H1 2026 does not cover the HC Platform v3 provisioning workflow added in H2.

Rotation process:
- Every 6 months, mine the previous 6 months of production logs using the same stratified sampling approach
- Add 20% new examples, retire 20% oldest examples (keep 60% for continuity)
- Re-validate all reference answers against current S3 wiki pages
- Increment the dataset version tag (`rag-golden-v3`) and keep all prior versions in S3 for retrospective comparison

---

## Part 2 — RAGAS in Practice

### 2.1 What RAGAS Measures

RAGAS (Retrieval Augmented Generation Assessment) provides four independent metrics that separately diagnose whether the failure is in the retriever or the generator. This distinction is critical — identical low scores on a blended metric can have opposite fixes.

```
Input question
      │
      ▼
  Retriever  ─── Context Precision ──► "Of the chunks retrieved, how many are relevant?"
      │        ─── Context Recall ────► "Of all relevant chunks, how many were retrieved?"
      │
      ▼
  Generator  ─── Faithfulness ────────► "Does the answer make claims supported by the context?"
      │        ─── Answer Relevance ──► "Does the answer actually address the question asked?"
      ▼
    Answer
```

### 2.2 The Four Metrics

**Context Precision**  
Measures signal-to-noise in retrieval: what fraction of the retrieved chunks actually contributed to the answer. Low precision means the retriever is pulling irrelevant wiki pages and polluting the generator's context window.

```
Context Precision = relevant retrieved chunks / total retrieved chunks
```

*LLMWiki diagnosis:* If this is low, the Bedrock KB query is too broad — check `numberOfResults` setting and the S3 Vectors similarity threshold.

**Context Recall**  
Measures retrieval completeness: did the retriever find all the chunks needed to answer the question? Computed by checking whether each sentence in the reference answer can be attributed to a retrieved chunk.

```
Context Recall = attributed reference sentences / total reference sentences
```

*LLMWiki diagnosis:* If this is low and precision is fine, the knowledge gap is in the KB itself — either the source document was not ingested, or the wiki page summarization lost the relevant detail.

**Faithfulness**  
Measures hallucination: does every claim in the generated answer appear in (or be directly inferable from) the retrieved context? This is the most important metric for the Business Knowledge API — an agent acting on a hallucinated answer causes downstream failures.

```
Faithfulness = claims in answer that can be attributed to context / total claims in answer
```

*LLMWiki diagnosis:* If faithfulness drops after a model upgrade, the new model is more fluent but less grounded. Add an explicit `ONLY use information from the provided context` instruction to the system prompt.

**Answer Relevance**  
Measures whether the answer addresses the question — penalizes answers that are factually grounded but off-topic, incomplete, or padded.

*LLMWiki diagnosis:* Low answer relevance with high faithfulness means the generator is summarizing the retrieved context rather than directly answering the question. Tighten the prompt's answer format instruction.

### 2.3 Integrating RAGAS with LLMWiki

```python
# lambda/query/eval_ragas.py  (run offline, not in Lambda path)
from ragas import evaluate
from ragas.metrics import (
    context_precision, context_recall,
    faithfulness, answer_relevancy
)
from datasets import Dataset

def run_ragas_eval(golden_rows: list[dict]) -> dict:
    """
    golden_rows: list of dicts with keys:
        question, answer, contexts (list of retrieved chunk texts), ground_truth
    """
    ds = Dataset.from_list(golden_rows)
    result = evaluate(
        ds,
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    )
    return result   # dict with per-metric scores + per-row breakdown
```

Build the eval dataset by invoking the query Lambda with `return_contexts=True` (add this flag to the handler) and pairing each response with its golden reference answer:

```python
# build_ragas_dataset.py
import boto3, json
lambda_client = boto3.client("lambda", region_name="us-east-1")

rows = []
for example in golden_dataset:
    resp = lambda_client.invoke(
        FunctionName="llmwiki-query",
        Payload=json.dumps({
            "body": json.dumps({
                "question":        example["question"],
                "return_contexts": True,   # add to handler
                "caller":          "ragas-eval",
            }),
            "httpMethod": "POST",
        }),
    )
    body = json.loads(json.loads(resp["Payload"].read())["body"])
    rows.append({
        "question":    example["question"],
        "answer":      body["answer"],
        "contexts":    body.get("contexts", []),
        "ground_truth": example["reference_answer"],
    })

scores = run_ragas_eval(rows)
```

### 2.4 Score Thresholds

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Context Precision | ≥ 0.80 | 0.65–0.79 | < 0.65 |
| Context Recall | ≥ 0.80 | 0.65–0.79 | < 0.65 |
| Faithfulness | ≥ 0.80 | 0.70–0.79 | < 0.70 |
| Answer Relevance | ≥ 0.80 | 0.70–0.79 | < 0.70 |

RAGAS documentation (Dec 2025) defines ≥ 0.8 on all four metrics as a strong RAG pipeline. For the Business Knowledge API where downstream agents act on the output, treat 0.75 as the hard floor for Faithfulness — below that, hallucination risk is too high for unattended agent use.

### 2.5 Mapping Low Scores to LLMWiki Components

```
Low Context Precision  →  Bedrock KB: reduce numberOfResults, raise similarity threshold
Low Context Recall     →  Ingest pipeline: check chunking strategy, add missing source docs
Low Faithfulness       →  System prompt: add grounding instruction, reduce temperature
Low Answer Relevance   →  Prompt template: sharpen answer format, add explicit question-answering instruction
```

---

## Part 3 — Trace-Level Agent Evaluation

### 3.1 Why Final-Output Evaluation Misses Everything

When AgentCore's Sales-to-Service skill calls LLMWiki's Business Knowledge API, the final answer is only the last step in a multi-step trace:

```
AgentCore receives SOW trigger
    → calls /wiki/query/customer-onboarding  (step 1)
    → calls /wiki/query/provisioning          (step 2)
    → calls /wiki/ask with aggregated context (step 3)
    → constructs handoff checklist            (step 4)
    → writes to downstream system             (step 5)
```

Evaluating only step 5's output cannot tell you:
- Whether step 1 retrieved the right customer context (it may have retrieved a different customer's data)
- Whether step 3's aggregation was faithful to steps 1 and 2
- Whether the agent called the right domain endpoint or hallucinated the domain parameter

The GUIDE paper (arXiv, Apr 2026) quantified this gap: LLM judge accuracy drops from ~93% on short traces (3–5 steps) to ~75% on long traces (50+ steps). In a 10-step AgentCore skill invocation, you can expect roughly 1 in 8 evaluations to produce the wrong verdict if you evaluate the final output only.

### 3.2 The 3-Level Trace Evaluation Framework

```
Level 1 — Step correctness
    For each tool call in the trace:
    "Was this the right tool? Were the parameters correct?"
    Scored: per-step pass/fail

Level 2 — Trajectory coherence  
    Across the full tool call sequence:
    "Did the agent take the right steps in the right order?
     Did it skip a required step? Did it take an unnecessary detour?"
    Scored: trajectory similarity to reference trace (edit distance)

Level 3 — Final answer quality
    On the output of the last step:
    "Is the answer correct given the original goal?"
    Scored: RAGAS Faithfulness + Answer Relevance + field-level checks
```

All three levels are needed. Level 3 alone misses step-level errors that cancel out (two wrong steps that happen to produce a right answer). Level 1 alone misses trajectory errors (right steps in wrong order, or missing steps). Level 2 alone is over-sensitive to stylistic variation in tool call ordering.

### 3.3 Applying the Framework to LLMWiki's Agent Skills

**What to collect.** The AgentCore skill invocation must emit a structured trace. Add trace logging to the business_query Lambda:

```python
# lambda/business_query/handler.py — trace emission
import uuid, time

def answer_business_question(body: dict, caller: str) -> dict:
    trace_id = str(uuid.uuid4())
    steps = []

    # Step 1 — domain routing
    t0 = time.time()
    domain = route_domain(body["question"])
    steps.append({
        "step": 1, "action": "domain_routing",
        "input": body["question"][:200],
        "output": domain,
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # Step 2 — KB retrieval
    t0 = time.time()
    contexts = retrieve_from_kb(body["question"], domain)
    steps.append({
        "step": 2, "action": "kb_retrieval",
        "input": {"question": body["question"], "domain": domain},
        "output": {"chunk_count": len(contexts)},
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # Step 3 — generation
    # ... etc

    result = build_result(contexts, body)
    result["trace_id"] = trace_id
    result["trace_steps"] = steps
    return result
```

**Level 1 check — per-step parameter validation:**

```python
def eval_step_correctness(step: dict, reference_step: dict) -> dict:
    checks = {
        "action_match":  step["action"] == reference_step["action"],
        "domain_match":  step.get("output") == reference_step.get("expected_output"),
        "no_extra_calls": True,  # checked at trajectory level
    }
    return {"step": step["step"], "passed": all(checks.values()), "checks": checks}
```

**Level 2 check — trajectory edit distance:**

```python
def trajectory_similarity(actual_steps: list, reference_steps: list) -> float:
    """
    Normalized edit distance between actual and reference action sequences.
    1.0 = identical trajectory. 0.0 = nothing in common.
    """
    actual_actions    = [s["action"] for s in actual_steps]
    reference_actions = [s["action"] for s in reference_steps]

    # Levenshtein distance (insertions, deletions, substitutions)
    n, m = len(actual_actions), len(reference_actions)
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n+1): dp[i][0] = i
    for j in range(m+1): dp[0][j] = j
    for i in range(1, n+1):
        for j in range(1, m+1):
            cost = 0 if actual_actions[i-1] == reference_actions[j-1] else 1
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)

    max_len = max(n, m)
    return 1.0 - (dp[n][m] / max_len) if max_len > 0 else 1.0
```

**Level 3 check — final answer quality** uses the RAGAS pipeline from Part 2.

### 3.4 Trace Thresholds for AgentCore Skills

| Level | Metric | Gate threshold |
|-------|--------|---------------|
| 1 | Step correctness | ≥ 90% of steps pass across the eval set |
| 2 | Trajectory similarity | ≥ 0.85 average across eval set |
| 3 | Faithfulness | ≥ 0.80 (hard block on deploy) |
| 3 | Answer relevance | ≥ 0.75 |

A trajectory similarity of 1.0 is not the target — some agent runs legitimately take alternative valid paths. The 0.85 threshold flags genuine regressions (missing required steps, wrong domain routing) while allowing equivalent-quality paths through.

---

## Part 4 — Eval-Driven Development

### 4.1 Write the Test Before the Prompt

The most common evaluation mistake is writing the prompt, then writing a test to check if the prompt works. This produces tests that are tautologically correct — the test describes what the prompt does, not what it should do.

The correct order:

```
1. Define the behaviour contract (what should happen)
2. Write a test that checks the contract
3. Confirm the test FAILS with the current prompt
4. Write / modify the prompt until the test passes
5. Add the passing test to the regression suite
```

For LLMWiki, this means defining the API contract first:

```python
# tests/golden/test_provisioning_domain.py

# Written BEFORE the provisioning domain was implemented
EXPECTED = {
    "domain": "provisioning",
    "confidence": "high",
    "citations": lambda cites: len(cites) >= 2,                          # at least 2 sources
    "action_items": lambda items: any("BOM" in i for i in items),        # mentions BOM
    "gaps": lambda gaps: isinstance(gaps, list),                         # field present
    "answer": lambda ans: "standard" in ans.lower() or "template" in ans.lower(),
}

def test_provisioning_bom_question():
    resp = invoke_business_api({
        "question": "What is the BOM template for Product X environment provisioning?",
        "domain":   "provisioning",
    })
    for field, check in EXPECTED.items():
        val = resp.get(field)
        if callable(check):
            assert check(val), f"{field}={val!r} failed check"
        else:
            assert val == check, f"{field}: expected {check!r}, got {val!r}"
```

### 4.2 Every Production Failure Becomes a Test Case

When a production failure is reported — wrong answer, missing citation, hallucinated action item — the first action before any fix is to write a test that reproduces it.

**Workflow:**

```
Production failure reported
    │
    ▼
1. Add the failing (question, expected_output) pair to the golden dataset
   with a "regression" tag and the incident date
    │
    ▼
2. Run the test — confirm it fails on the current build
    │
    ▼
3. Identify root cause (retriever / generator / prompt / KB content)
    │
    ▼
4. Apply fix
    │
    ▼
5. Confirm the new test passes, no other golden tests regressed
    │
    ▼
6. Deploy — the test runs on every future commit
```

This converts every incident into a permanent regression guard. After 6 months of this discipline, your golden dataset contains the hardest real-world cases the system has ever encountered — which is exactly what a golden dataset should be.

**Tag the regression examples in DynamoDB:**

```python
# Store in llmwiki-index or a dedicated eval table
regression_example = {
    "example_id":   "reg-2026-07-08-provisioning-bom",
    "type":         "regression",
    "question":     "What is the BOM for a Facets EC2 provisioning?",
    "reference":    "The BOM for Facets EC2 provisioning includes...",
    "incident_date": "2026-07-08",
    "root_cause":   "wiki page missing Facets EC2 section",
    "domain":       "provisioning",
    "tags":         ["regression", "provisioning", "bom"],
}
```

### 4.3 Prompt Versioning Discipline

Every prompt change must be versioned and linked to its eval result:

```python
# lambda/query/prompts.py
PROMPT_REGISTRY = {
    "v1.0": {
        "system": "You are LLMWiki...",
        "released": "2026-05-01",
        "ragas_scores": {"faithfulness": 0.81, "relevance": 0.78, "precision": 0.83, "recall": 0.79},
    },
    "v1.1": {
        "system": "You are LLMWiki... ONLY use information from the provided context.",
        "released": "2026-06-15",
        "ragas_scores": {"faithfulness": 0.88, "relevance": 0.81, "precision": 0.83, "recall": 0.80},
        "change_reason": "Faithfulness regression on provisioning domain — added grounding constraint",
    },
}
CURRENT_PROMPT_VERSION = "v1.1"
```

The `change_reason` field is critical. Without it, prompt history is noise — with it, it is a diagnostic record.

---

## Part 5 — CI/CD Quality Gates

### 5.1 Three-Tier Gate Architecture

```
Commit push
    │
    ▼
Gate 1 — Deterministic checks  (< 1 minute, no LLM calls)
    ✓ Schema validation: all API responses parse against Pydantic model
    ✓ Non-empty fields: answer, citations, confidence present
    ✓ Citation format: each citation has url + snippet
    ✓ Confidence enum: value in {"high", "medium", "low"}
    ✓ Domain routing: known domains route to correct endpoint
    BLOCKS commit if any check fails

    │
    ▼  (on PR / merge to main)

Gate 2 — RAGAS regression  (5–15 minutes, Bedrock calls on 50-example subset)
    ✓ Faithfulness ≥ 0.80
    ✓ Context Precision ≥ 0.80
    ✓ Context Recall ≥ 0.80
    ✓ Answer Relevance ≥ 0.75
    ✓ No metric dropped > 0.05 from baseline
    BLOCKS merge if any threshold breached

    │
    ▼  (on deploy to staging)

Gate 3 — LLM-as-judge on full golden set  (20–40 minutes, full 200-example API-golden)
    ✓ Judge agreement ≥ 90% on structured field correctness
    ✓ Regression set: all tagged regression examples pass
    ✓ Agent trace Level 2 trajectory similarity ≥ 0.85
    BLOCKS promotion to production if failed
```

### 5.2 Implementing Gate 1 — Deterministic Checks

```python
# tests/ci/test_schema.py — runs on every commit, zero LLM cost
from pydantic import BaseModel, field_validator
from typing import Optional
import pytest

class Citation(BaseModel):
    source: str
    snippet: str
    s3_key:  Optional[str] = None

class BusinessAPIResponse(BaseModel):
    answer:       str
    confidence:   str
    citations:    list[Citation]
    action_items: list[str]
    gaps:         list[str]
    domain:       str
    trace_id:     Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def confidence_enum(cls, v):
        assert v in {"high", "medium", "low"}, f"invalid confidence: {v}"
        return v

    @field_validator("answer")
    @classmethod
    def answer_non_empty(cls, v):
        assert len(v.strip()) > 20, "answer too short — likely a generation failure"
        return v

    @field_validator("citations")
    @classmethod
    def citations_non_empty(cls, v):
        assert len(v) >= 1, "at least one citation required"
        return v

# Parametrize over canned Lambda invocations (mock Bedrock in unit tests)
@pytest.mark.parametrize("fixture", load_gate1_fixtures())
def test_response_schema(fixture):
    BusinessAPIResponse(**fixture["response"])   # raises if invalid
```

### 5.3 Implementing Gate 2 — RAGAS Regression

Run on a 50-example random sample from the RAG-golden set (not the full 500) to keep CI under 15 minutes:

```python
# tests/ci/test_ragas_gate.py
import json, boto3, random
from ragas import evaluate
from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy

THRESHOLDS = {
    "context_precision": 0.80,
    "context_recall":    0.80,
    "faithfulness":      0.80,
    "answer_relevancy":  0.75,
}
BASELINE_FILE = "tests/baselines/ragas_baseline.json"
MAX_DROP      = 0.05   # block if any metric drops more than 5pp from baseline

def test_ragas_gate():
    with open("tests/golden/rag_golden.json") as f:
        golden = json.load(f)

    sample = random.sample(golden, min(50, len(golden)))
    rows   = build_ragas_rows(sample)   # invoke Lambda, collect contexts
    scores = evaluate(rows, metrics=[context_precision, context_recall,
                                     faithfulness, answer_relevancy])

    # Load baseline
    try:
        with open(BASELINE_FILE) as f:
            baseline = json.load(f)
    except FileNotFoundError:
        baseline = {}   # first run — no baseline yet

    failures = []
    for metric, threshold in THRESHOLDS.items():
        score = scores[metric]
        if score < threshold:
            failures.append(f"{metric}={score:.3f} < threshold {threshold}")
        if metric in baseline and (baseline[metric] - score) > MAX_DROP:
            failures.append(f"{metric} dropped {baseline[metric]-score:.3f} from baseline")

    assert not failures, "\n".join(failures)
```

### 5.4 Implementing Gate 3 — LLM-as-Judge

Use Bedrock Claude as the judge. The judge receives the question, the LLMWiki response, and the reference answer, and returns a structured verdict:

```python
# tests/ci/llm_judge.py
import boto3, json

JUDGE_PROMPT = """
You are evaluating a response from LLMWiki, a knowledge retrieval system.

QUESTION: {question}

REFERENCE ANSWER: {reference}

LLMWIKI RESPONSE:
- Answer: {answer}
- Confidence: {confidence}  
- Citations: {citations}
- Action Items: {action_items}

Evaluate each dimension. Respond ONLY with valid JSON.

{{
  "factual_accuracy": <0.0–1.0>,   // claims match reference
  "citation_quality": <0.0–1.0>,   // citations support the answer
  "completeness":     <0.0–1.0>,   // all key points from reference are present
  "action_items_correct": <true/false>,  // action items are appropriate
  "overall_verdict":  <"pass"/"fail">,
  "reasoning":        "<one sentence>"
}}
"""

def judge_response(question, reference, response, model_id="us.anthropic.claude-haiku-4-5-20251001"):
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    prompt  = JUDGE_PROMPT.format(
        question=question,
        reference=reference,
        answer=response["answer"],
        confidence=response["confidence"],
        citations=json.dumps(response.get("citations", []), indent=2),
        action_items=json.dumps(response.get("action_items", []), indent=2),
    )
    resp = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    return json.loads(resp["output"]["message"]["content"][0]["text"])
```

**Use Haiku for Gate 3, not Sonnet.** Haiku is 10× cheaper and sufficient for structured-output judgment. Reserve Sonnet for trace-level evaluation where reasoning complexity is higher.

### 5.5 Setting Thresholds That Don't Block Velocity

The goal of quality gates is to catch regressions, not to enforce perfection. Two anti-patterns to avoid:

**Anti-pattern 1: Absolute perfection threshold.**  
Setting faithfulness ≥ 0.95 on day one will block every deploy. The system probably scores 0.83 today. Set the threshold at current_score − 0.03 to start, then tighten it monthly as you improve.

**Anti-pattern 2: No human override.**  
Some deploys are urgent (security patches, cost fixes). Build a documented override path: a PR with the label `eval-waiver` bypasses Gate 2 and 3 but fires a Slack alert and requires a post-deploy evaluation within 24 hours.

**Recommended threshold ramp:**

| Month | Faithfulness gate | Context Precision gate | LLM judge pass rate |
|-------|------------------|----------------------|---------------------|
| Month 1 | 0.75 | 0.75 | 80% |
| Month 3 | 0.78 | 0.78 | 85% |
| Month 6 | 0.80 | 0.80 | 90% |
| Month 12 | 0.83 | 0.83 | 93% |

---

## Part 6 — Judge Calibration

### 6.1 Why Correlation Alone Is Not Sufficient

The most common judge calibration mistake is reporting Pearson or Spearman correlation between LLM judge scores and human scores and declaring the judge "validated." Correlation measures linear agreement — it does not measure whether the judge is classifying correctly.

A judge that assigns 0.7 to everything humans call "pass" and 0.5 to everything humans call "fail" has a correlation of 1.0 but is useless for a binary gate. The threshold-crossing behaviour is what matters for CI/CD gates, and correlation doesn't capture it.

### 6.2 What Cohen's Kappa Tells You That Correlation Doesn't

Cohen's Kappa measures agreement between two raters (the LLM judge and a human expert) on categorical decisions (pass/fail), corrected for the probability of random agreement:

```
κ = (P_observed - P_chance) / (1 - P_chance)

P_observed = fraction of cases where judge and human agree
P_chance   = probability of agreement if both rated randomly
             (based on the marginal distribution of each rater's labels)
```

A judge with 90% raw agreement on a dataset where 90% of examples pass (i.e., always says "pass") has κ = 0 — it's just guessing the base rate.

**Kappa interpretation:**

| κ | Interpretation |
|---|---------------|
| < 0.40 | Poor — judge is unreliable for quality gates |
| 0.40–0.60 | Moderate — useful for monitoring, not blocking |
| 0.61–0.80 | Substantial — suitable for advisory gates |
| **≥ 0.80** | **Very strong — suitable for blocking quality gates** |

The ICLR 2026 Judge's Verdict Benchmark (Han et al.) evaluated 54 LLMs as judges. Fewer than half cleared κ ≥ 0.80 when judging LLM-generated text. The models that failed were not obviously bad — some had high raw agreement — but their failure modes (systematic biases toward agreeing with confident-sounding answers, length bias) were invisible to correlation analysis.

### 6.3 Calibrating LLMWiki's Judge

**Step 1 — Build a calibration set.**  
Take 100 examples from the API-golden set. Have a TriZetto subject-matter expert independently label each as pass/fail on factual accuracy and completeness. This is your ground truth.

**Step 2 — Run the judge on the calibration set.**

```python
# tests/calibration/calibrate_judge.py
from sklearn.metrics import cohen_kappa_score, f1_score
import json

def calibrate_judge(calibration_set: list[dict]) -> dict:
    human_labels = []
    judge_labels = []

    for example in calibration_set:
        human_labels.append(1 if example["human_verdict"] == "pass" else 0)
        verdict     = judge_response(example["question"], example["reference"], example["response"])
        judge_labels.append(1 if verdict["overall_verdict"] == "pass" else 0)

    kappa   = cohen_kappa_score(human_labels, judge_labels)
    macro_f1 = f1_score(human_labels, judge_labels, average="macro")

    return {
        "cohen_kappa":         round(kappa, 3),
        "macro_f1":            round(macro_f1, 3),
        "human_pass_rate":     sum(human_labels) / len(human_labels),
        "judge_pass_rate":     sum(judge_labels) / len(judge_labels),
        "calibration_n":       len(calibration_set),
        "gate_ready":          kappa >= 0.80,
    }
```

**Step 3 — If κ < 0.80, identify and fix the bias.**  
Common failure modes for Claude-as-judge on LLMWiki responses:
- **Length bias:** Longer answers rated higher even if less accurate. Fix: add `Length of the answer must not influence your score` to judge prompt.
- **Confidence sycophancy:** Responses with `"confidence": "high"` rated higher regardless of content. Fix: omit confidence field from judge input.
- **Citation count bias:** More citations = higher score regardless of relevance. Fix: score citation quality, not count.

### 6.4 Multi-Judge Consensus for High-Stakes Evaluations

For the Agent-golden trace evaluations (which feed the go/no-go decision for AgentCore releases), single-judge evaluation is insufficient. Per the ICLR 2026 benchmark, 3-judge consensus achieves Cohen's Kappa ~0.95 and Macro F1 97–98% — near-human reliability.

```python
def consensus_judge(question, reference, response, n_judges=3) -> dict:
    """
    Run N independent judge calls with varied temperatures and/or prompts.
    Return majority verdict with confidence.
    """
    verdicts = []
    for i in range(n_judges):
        # Vary temperature slightly to get independent samples
        result = judge_response(question, reference, response)
        verdicts.append(result["overall_verdict"])

    pass_count = verdicts.count("pass")
    fail_count = verdicts.count("fail")
    majority   = "pass" if pass_count > fail_count else "fail"

    return {
        "verdict":     majority,
        "confidence":  max(pass_count, fail_count) / n_judges,   # 1.0 = unanimous
        "votes":       {"pass": pass_count, "fail": fail_count},
        "use_for_gate": True,
    }
```

Use 3-judge consensus only for Gate 3 (full golden set, pre-production). Gates 1 and 2 are deterministic or cheap-LLM — they don't benefit from consensus.

---

## Part 7 — AWS AgentCore Eval Integration

AgentCore (the orchestration layer for LLMWiki's agentic skills) provides its own evaluation hooks. LLMWiki's eval strategy sits alongside these, not in competition with them:

| Layer | AgentCore native | LLMWiki eval strategy |
|-------|-----------------|----------------------|
| Skill invocation correctness | AgentCore skill routing metrics | Gate 1 schema checks on Business API responses |
| Knowledge retrieval quality | Not covered | Gate 2 RAGAS on every deploy |
| Trace-level correctness | AgentCore session replay logs | Level 1–3 trace eval framework (Part 3) |
| Cost per eval run | AgentCore token budget | `record_usage()` governance module — eval runs tagged `caller="ragas-eval"` |
| Judge calibration | Not covered | Cohen's Kappa calibration pipeline (Part 6) |

**Integration point:** AgentCore session replay logs are the primary source for building the Agent-golden dataset. Export AgentCore traces (if available) or the `trace_steps` array from the business_query Lambda into the agent golden dataset builder. This ensures the trajectory reference traces reflect actual AgentCore invocation patterns, not synthetic sequences invented during dataset construction.

**Eval cost management:** Every eval run invokes Bedrock. Tag all eval invocations with `caller="ragas-eval"` or `caller="ci-judge"` so the governance dashboard separates eval spend from production spend. Gate 2 on 50 examples costs approximately $0.15–0.25 per CI run with Haiku. Budget ~$30/month for a team running 2 CI pipelines per day.

---

## Part 8 — Implementation Checklist

### Phase A — Foundation (Week 1–2)
- [ ] Export 90 days of `llmwiki-log` query rows
- [ ] Apply stratified sampling to select 200 RAG-golden candidates
- [ ] Have SME write/validate reference answers for all 200
- [ ] Store golden dataset in `s3://llmwiki-278e7e22/eval/rag-golden-v1.json`
- [ ] Add `return_contexts=True` flag to query Lambda for RAGAS data collection
- [ ] Run baseline RAGAS scores — record in `tests/baselines/ragas_baseline.json`

### Phase B — CI gates (Week 3–4)
- [ ] Implement Gate 1 Pydantic schema tests — wire to pre-commit hook
- [ ] Implement Gate 2 RAGAS regression test — wire to GitHub Actions / CodeBuild PR check
- [ ] Calibrate LLM judge on 100-example calibration set — record κ score
- [ ] If κ ≥ 0.80: implement Gate 3 LLM-as-judge — wire to deploy pipeline
- [ ] Set initial thresholds (current_score − 0.03), document in `tests/thresholds.json`

### Phase C — Agent eval (Week 5–6)
- [ ] Add `trace_steps` emission to business_query Lambda
- [ ] Build Agent-golden: 10 examples per UC (start with UC1 Sales-to-Service)
- [ ] Implement Level 1 step correctness checker
- [ ] Implement Level 2 trajectory similarity scorer
- [ ] Wire 3-judge consensus to Gate 3 for AgentCore skill releases

### Phase D — Ops cadence (Ongoing)
- [ ] Every production failure → regression test added within 24 hours
- [ ] Monthly: review false positive / false negative rate on judge verdicts
- [ ] Monthly: tighten gate thresholds by 0.01–0.02 if no false blocks in prior month
- [ ] Every 6 months: rotate golden dataset (add 20% new, retire 20% oldest)
- [ ] Every 6 months: re-calibrate judge against fresh human labels

---

## Reference Summary

| Metric / Benchmark | Value | Source |
|---|---|---|
| Golden dataset minimum for statistical reliability | ~100 examples | LXT.ai benchmark analysis, Mar 2026 |
| Golden dataset for segment-level analysis | ~500 examples | LXT.ai benchmark analysis, Mar 2026 |
| RAGAS strong pipeline threshold | ≥ 0.8 all four metrics | RAGAS official docs, Dec 2025 |
| LLM judge accuracy, short traces (3–5 steps) | ~93% | GUIDE paper, arXiv Apr 2026 |
| LLM judge accuracy, long traces (50+ steps) | ~75% | GUIDE paper, arXiv Apr 2026 |
| Cohen's Kappa "very strong" threshold | ≥ 0.80 | Judge's Verdict Benchmark, ICLR 2026 |
| LLMs clearing κ ≥ 0.80 (54 tested) | < half | Judge's Verdict Benchmark, ICLR 2026 |
| 3-judge consensus κ | ~0.95 | Judge's Verdict Benchmark, ICLR 2026 |
| 3-judge consensus Macro F1 | 97–98% | Judge's Verdict Benchmark, ICLR 2026 |

---

*Related docs: `llmwiki-governance.md` (cost tracking + caching), `AgenticDesign.md` (Business Knowledge API contract), `LLMWikiDesign.md` (core architecture)*
