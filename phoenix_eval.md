# Phoenix EVAL — LLMWiki Observability & Evaluation Guide

**Version:** 1.0  
**Date:** 2026-07-13  
**Status:** Implementation Guide  
**Scope:** Self-hosted Phoenix for tracing, evaluating, and improving LLMWiki's RAG pipeline and agentic Business Knowledge API — all data stays inside the environment

---

## Why Phoenix EVAL for LLMWiki

LLMWiki's query Lambda already answers questions reliably in demos. But today there is no way to know:

- Whether a prompt change to the query Lambda improved or degraded answer quality
- Which retrieval failures are due to bad chunking vs bad synthesis vs bad KB indexing
- Whether the Business Knowledge API's structured response (`answer + confidence + action_items + evidence`) is actually faithful to the retrieved wiki pages
- What "done" looks like when an AgentCore skill calls `/wiki/ask` and gets back a hallucinated citation

This is the **vibes problem**: testing agents by running a few queries and checking whether it looks right. It doesn't catch regressions, doesn't run in CI, and doesn't tell you whether a prompt fix broke three other things. Phoenix EVAL replaces vibes with a repeatable pipeline — traces, categorized failures, deterministic code checks, LLM-as-a-judge, and quantified experiments.

### Feasibility: Yes, fully self-hosted

Phoenix is open-source by Arize AI. It runs from a single Docker image (`ghcr.io/arize-ai/phoenix`) with no external calls. Traces are stored locally in a SQLite database inside the container. The only required change in LLMWiki is adding one environment variable to the Lambda and Streamlit containers that points them at the local Phoenix collector endpoint. **No data leaves the environment.**

---

## The Vibes Problem

Most agent testing follows the same pattern:

1. Run a few representative queries
2. Read the output
3. Decide it looks right
4. Ship

This catches catastrophic failures. It misses everything else:

- A prompt edit that fixed one failure introduced two regressions
- The KB retrieval works for provisioning questions but silently degrades for billing questions
- The agent's confidence scores are systematically inflated when the context is thin
- What looked right in the demo was hallucinated — the citation doesn't exist

The sharpest lesson from @seldo's workshop (github.com/seldo/aiewf-2026-demo): **choosing the wrong eval type is worse than having no eval**. On a financial analysis agent, a correctness eval scored 0 out of 13 because the model doesn't know what year it is and can't verify forward-looking financial data. The same agent scored 13 out of 13 on a faithfulness eval because every answer was grounded in the retrieved documents. Running the correctness eval would have concluded the agent was broken; running the faithfulness eval revealed it was actually working correctly within its constraints.

The fix is not to tune the eval — it's to pick the right eval in the first place.

---

## Architecture: Self-Hosted Phoenix for LLMWiki

```
┌─────────────────────────────────────────────────────────────────┐
│  LLMWiki Environment (AWS VPC / local dev)                      │
│                                                                  │
│  ┌──────────────┐    OTel traces    ┌────────────────────────┐  │
│  │ Lambda        │ ──────────────── │ Phoenix Container       │  │
│  │ (query)       │                  │ ghcr.io/arize-ai/phoenix│  │
│  └──────────────┘                  │                        │  │
│  ┌──────────────┐    OTel traces    │  :6006  → UI            │  │
│  │ Streamlit UI  │ ──────────────── │  :4317  → gRPC OTel     │  │
│  └──────────────┘                  │  :9000  → HTTP OTel     │  │
│  ┌──────────────┐                  │  ./phoenix.db (SQLite)  │  │
│  │ Eval scripts  │ ── Phoenix API ──│                        │  │
│  │ (local)       │                  └────────────────────────┘  │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

No trace data leaves this boundary.

---

## Step 0: Run Phoenix Locally

### Docker (primary path — WSL with docker.exe)

```bash
# Pull and run — exposes UI on :6006, OTel collector on :4317 (gRPC) and :9000 (HTTP)
docker.exe run -d \
  --name phoenix \
  -p 6006:6006 \
  -p 4317:4317 \
  -p 9000:9000 \
  -v phoenix-data:/mnt/data \
  -e PHOENIX_WORKING_DIR=/mnt/data \
  ghcr.io/arize-ai/phoenix:latest

# Verify
curl http://localhost:6006/healthz
```

Open the Phoenix UI: http://localhost:6006

### Docker Compose (for persistent dev setup)

```yaml
# docker-compose.phoenix.yml
version: "3.8"
services:
  phoenix:
    image: ghcr.io/arize-ai/phoenix:latest
    ports:
      - "6006:6006"    # UI
      - "4317:4317"    # OTel gRPC
      - "9000:9000"    # OTel HTTP
    volumes:
      - phoenix-data:/mnt/data
    environment:
      PHOENIX_WORKING_DIR: /mnt/data
volumes:
  phoenix-data:
```

```bash
docker.exe compose -f docker-compose.phoenix.yml up -d
```

---

## Step 1: Instrument LLMWiki

### Install dependencies

Add to `lambda/query/requirements.txt` and `streamlit/requirements.txt`:

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc
openinference-instrumentation-bedrock
arize-phoenix-otel
```

### Lambda query function instrumentation

The query Lambda (`lambda/query/handler.py`) already calls Bedrock and the S3 Vectors KB. Wrap it with OpenInference tracing:

```python
# lambda/query/tracing.py
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.bedrock import BedrockInstrumentor

def setup_tracing():
    """Call once at Lambda cold start."""
    collector_endpoint = os.environ.get(
        "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317"
    )
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=collector_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Auto-instruments all boto3 bedrock-runtime calls
    BedrockInstrumentor().instrument()
```

In `lambda/query/handler.py`:

```python
from tracing import setup_tracing
setup_tracing()   # top of module, outside the handler

def handler(event, context):
    tracer = trace.get_tracer("llmwiki.query")
    with tracer.start_as_current_span("llmwiki.query") as span:
        question = event.get("question", "")
        domain = event.get("domain", "general")

        span.set_attribute("llm.input.value", question)
        span.set_attribute("llmwiki.domain", domain)

        # ... existing retrieval + synthesis code ...

        span.set_attribute("llm.output.value", answer)
        span.set_attribute("llmwiki.confidence", confidence)
        span.set_attribute("llmwiki.citation_count", len(citations))

        return {"answer": answer, "citations": citations, "confidence": confidence}
```

Set the environment variable in Terraform or Lambda console:

```
PHOENIX_COLLECTOR_ENDPOINT = http://<phoenix-host>:4317
```

For local testing, set it to `http://host.docker.internal:4317` if running Lambda locally in Docker, or `http://localhost:4317` if running directly.

### Streamlit UI instrumentation

In `streamlit/app.py`:

```python
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.bedrock import BedrockInstrumentor

# Run once at startup
_provider = TracerProvider()
_endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317")
_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=_endpoint, insecure=True))
)
trace.set_tracer_provider(_provider)
BedrockInstrumentor().instrument()
tracer = trace.get_tracer("llmwiki.streamlit")
```

Wrap the query call in the Ask Wiki page:

```python
with tracer.start_as_current_span("streamlit.ask_wiki") as span:
    span.set_attribute("llm.input.value", user_question)
    response = call_query_lambda(user_question)
    span.set_attribute("llm.output.value", response["answer"])
```

---

## Step 2: Read Traces Before Writing Any Eval

**Do not write a single eval before you have looked at traces.** This is the most important step. Real traces show you what is actually failing — not what you think is failing.

After running 10–20 representative LLMWiki queries through the Streamlit UI, open Phoenix at http://localhost:6006 and examine:

1. **Span waterfall** — how much time is retrieval vs synthesis? Is the KB call returning relevant chunks?
2. **Input/output** — read the actual retrieved context. Does the answer follow from the context, or is the model going off-script?
3. **Latency outliers** — which query types are slow? Does slow correlate with low confidence?
4. **Failures** — look for `confidence=low` traces. What's in the retrieved context? Empty? Wrong domain? Too many chunks?

Create a simple categorization before writing evals:

| Category | Root cause | Example |
|----------|-----------|---------|
| Retrieval miss | No relevant chunk in KB | Question about billing, KB has provisioning docs only |
| Faithfulness failure | Model adds facts not in context | Citation points to the right page but the answer adds extra claims |
| Format failure | Structured field is wrong | `action_items` is null when it should have 2-3 items |
| Confidence miscalibration | Model says high confidence when context is thin | Single-sentence chunk → confident answer |

This categorization tells you which eval type to build first.

---

## Step 3: The Eval Pipeline

### 3a. Read traces with the Phoenix Python client

```python
import phoenix as px

# Connect to local Phoenix
client = px.Client(endpoint="http://localhost:6006")

# Pull recent query traces as a dataframe
traces_df = client.get_spans_dataframe(project_name="llmwiki-query")

# Useful columns: input.value, output.value, attributes.llmwiki.confidence,
#                 attributes.llmwiki.domain, attributes.llmwiki.citation_count

print(traces_df[["input.value", "output.value", "attributes.llmwiki.confidence"]].head(20))
```

### 3b. Code evals (deterministic, free, run on every commit)

These check structural properties — no LLM required:

```python
import pandas as pd

def eval_has_answer(row) -> dict:
    answer = row.get("output.value", "")
    return {
        "label": "pass" if len(answer.strip()) > 20 else "fail",
        "score": 1 if len(answer.strip()) > 20 else 0,
        "explanation": "answer is non-empty"
    }

def eval_citation_present(row) -> dict:
    citation_count = row.get("attributes.llmwiki.citation_count", 0)
    return {
        "label": "pass" if int(citation_count) > 0 else "fail",
        "score": 1 if int(citation_count) > 0 else 0,
        "explanation": f"{citation_count} citations returned"
    }

def eval_confidence_calibrated(row) -> dict:
    """Low citation count should not produce high confidence."""
    count = int(row.get("attributes.llmwiki.citation_count", 0))
    conf = row.get("attributes.llmwiki.confidence", "low")
    if count == 0 and conf == "high":
        return {"label": "fail", "score": 0, "explanation": "high confidence with zero citations"}
    return {"label": "pass", "score": 1, "explanation": "confidence plausibly calibrated"}

# Run against trace dataframe
results = traces_df.apply(eval_has_answer, axis=1, result_type="expand")
print(results["label"].value_counts())
```

### 3c. Built-in LLM-as-a-judge evals (faithfulness and relevance)

Phoenix ships built-in eval templates for faithfulness (is the answer grounded in the context?) and relevance (did retrieval surface the right chunks?). These are the right evals for LLMWiki's RAG pipeline.

**Faithfulness** is the primary eval for LLMWiki because it checks what the system controls — whether synthesis stays grounded in retrieved context. Correctness (does the answer match a gold reference?) is harder to automate because many LLMWiki answers require SME validation against actual TriZetto configuration docs.

```python
import phoenix as px
from phoenix.evals import (
    BedrockModel,
    RAG_FAITHFULNESS_PROMPT_TEMPLATE,
    RAG_RELEVANCE_PROMPT_TEMPLATE,
    llm_classify,
)

# ── Judge model 1: Claude via Bedrock ──────────────────────────────────────
claude_judge = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",   # cross-region inference profile
    region_name="us-east-1",
)

# ── Judge model 2: Amazon Nova Pro via Bedrock ─────────────────────────────
nova_judge = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",          # cross-region inference profile
    region_name="us-east-1",
)

# Pull traces that have context (retrieved chunks stored as attribute)
# You need to add `llmwiki.retrieved_context` to your span attributes — see below
eval_df = traces_df[["input.value", "output.value", "attributes.llmwiki.retrieved_context"]].dropna()
eval_df = eval_df.rename(columns={
    "input.value": "input",
    "output.value": "output",
    "attributes.llmwiki.retrieved_context": "context"
})

# Run faithfulness with Claude judge
faithfulness_claude = llm_classify(
    dataframe=eval_df,
    template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
    model=claude_judge,
    rails=["faithful", "hallucinated"],
    provide_explanation=True,
)

# Run faithfulness with Nova Pro judge
faithfulness_nova = llm_classify(
    dataframe=eval_df,
    template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
    model=nova_judge,
    rails=["faithful", "hallucinated"],
    provide_explanation=True,
)

print("=== Claude judge ===")
print(faithfulness_claude["label"].value_counts())
print("\n=== Nova Pro judge ===")
print(faithfulness_nova["label"].value_counts())

# Compare judge agreement
agreed = (faithfulness_claude["label"] == faithfulness_nova["label"]).mean()
print(f"\nJudge agreement: {agreed:.1%}")
```

Add `llmwiki.retrieved_context` to your query Lambda span:

```python
# In handler.py, after KB retrieval
retrieved_text = "\n\n".join([chunk["content"] for chunk in kb_results])
span.set_attribute("llmwiki.retrieved_context", retrieved_text[:4000])  # truncate for span storage
```

### 3d. Custom rubric eval for Business Knowledge API

The structured response contract (`answer + confidence + action_items + artifacts_referenced + evidence_required + gaps_detected`) needs a custom rubric because the built-in templates don't know about LLMWiki's schema.

```python
from phoenix.evals import llm_classify

BIZ_API_RUBRIC = """
You are evaluating a LLMWiki Business Knowledge API response for an AI agent.

The API should return:
- answer: direct response to the question
- confidence: high/medium/low based on evidence quality
- action_items: concrete next steps if applicable
- artifacts_referenced: specific wiki pages or documents cited
- gaps_detected: what the KB does not cover

Question: {input}
API Response: {output}
Retrieved Context: {context}

Score the response on the following criteria:
1. Does the confidence level match the evidence in the retrieved context? (miscalibrated = fail)
2. Are action_items specific and actionable, not generic advice? (generic = fail)
3. Are artifacts_referenced real citations from the context, not hallucinated? (hallucinated = fail)
4. Are gaps_detected honest about what the KB does not cover? (false confidence = fail)

If ALL four criteria pass, label: PASS
If ANY criterion fails, label: FAIL

Respond with exactly one word: PASS or FAIL, followed by a brief explanation.
""".strip()

biz_api_results = llm_classify(
    dataframe=eval_df,
    template=BIZ_API_RUBRIC,
    model=claude_judge,
    rails=["PASS", "FAIL"],
    provide_explanation=True,
)

print(biz_api_results["label"].value_counts())
print(biz_api_results[biz_api_results["label"] == "FAIL"]["explanation"].head(5))
```

---

## Step 4: LLM-as-a-Judge — Claude vs Amazon Nova Pro

LLMWiki uses Bedrock in AWS account 392568849512, region us-east-1. Both judges call Bedrock using the Lambda execution role (no separate keys needed if running inside AWS, or using the `tzg-sandbox` profile locally).

### Why compare two judges

A single judge has its own biases. Claude tends to be generous with faithfulness. Nova Pro may score differently on the same responses. When judges disagree, those are the borderline cases worth human review. When they agree, you can be more confident the label is correct.

### Amazon Nova Pro availability

Nova Pro is available in Bedrock us-east-1 as `us.amazon.nova-pro-v1:0` (cross-region inference profile, which handles routing automatically). It supports up to 300K input tokens and returns structured output.

```python
# Local test — verify Nova Pro is accessible from your Bedrock account
import boto3
import json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

resp = bedrock.invoke_model(
    modelId="us.amazon.nova-pro-v1:0",
    body=json.dumps({
        "messages": [{"role": "user", "content": "Is this answer faithful to the context? Answer YES or NO. Context: The TriZetto provisioning module requires a signed SOW. Answer: TriZetto provisioning requires a signed SOW."}],
        "inferenceConfig": {"maxTokens": 64}
    }),
    contentType="application/json",
    accept="application/json"
)
print(json.loads(resp["body"].read()))
```

### Full judge comparison script

```python
# scripts/run_faithfulness_eval.py
"""
Run faithfulness eval on recent LLMWiki traces using two Bedrock judges.
Usage:
    python scripts/run_faithfulness_eval.py --limit 50
"""
import argparse
import boto3
import pandas as pd
import phoenix as px
from phoenix.evals import BedrockModel, RAG_FAITHFULNESS_PROMPT_TEMPLATE, llm_classify

def main(limit: int):
    client = px.Client(endpoint="http://localhost:6006")
    df = client.get_spans_dataframe(project_name="llmwiki-query")
    df = df.rename(columns={
        "input.value": "input",
        "output.value": "output",
        "attributes.llmwiki.retrieved_context": "context"
    })
    df = df[["input", "output", "context"]].dropna().head(limit)
    print(f"Evaluating {len(df)} traces")

    session = boto3.Session(profile_name="tzg-sandbox", region_name="us-east-1")

    judges = {
        "claude_sonnet": BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name="us-east-1",
        ),
        "nova_pro": BedrockModel(
            model_id="us.amazon.nova-pro-v1:0",
            region_name="us-east-1",
        ),
    }

    results = {}
    for name, judge in judges.items():
        print(f"\nRunning {name} judge...")
        results[name] = llm_classify(
            dataframe=df,
            template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
            model=judge,
            rails=["faithful", "hallucinated"],
            provide_explanation=True,
        )
        print(results[name]["label"].value_counts())

    # Judge agreement analysis
    df_out = df.copy()
    df_out["claude_label"] = results["claude_sonnet"]["label"].values
    df_out["nova_label"] = results["nova_pro"]["label"].values
    df_out["agree"] = df_out["claude_label"] == df_out["nova_label"]
    df_out["claude_explanation"] = results["claude_sonnet"]["explanation"].values
    df_out["nova_explanation"] = results["nova_pro"]["explanation"].values

    agreement_rate = df_out["agree"].mean()
    print(f"\n=== Agreement rate: {agreement_rate:.1%} ===")

    disagreements = df_out[~df_out["agree"]]
    if not disagreements.empty:
        print(f"\nDisagreements ({len(disagreements)} cases — review these manually):")
        for _, row in disagreements.iterrows():
            print(f"\nQ: {row['input'][:80]}")
            print(f"  Claude: {row['claude_label']} — {row['claude_explanation'][:120]}")
            print(f"  Nova:   {row['nova_label']} — {row['nova_explanation'][:120]}")

    df_out.to_csv("eval_results.csv", index=False)
    print("\nResults saved to eval_results.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    main(**vars(parser.parse_args()))
```

Run it:

```bash
cd /mnt/c/Users/859600/OneDrive\ -\ Cognizant/AWSLab/LLMWiki
python scripts/run_faithfulness_eval.py --limit 50
```

---

## Step 5: Experiments — Proving a Prompt Change Worked

This is the step most eval guides skip. Running an eval tells you the current score. Running an **experiment** tells you whether a change improved the score — with a number you can defend.

Phoenix datasets + experiments let you A/B test prompt changes on the same set of inputs.

### Create a golden dataset from your traces

```python
import phoenix as px

client = px.Client(endpoint="http://localhost:6006")
df = client.get_spans_dataframe(project_name="llmwiki-query")

# Select 30 diverse examples — high/medium/low confidence, multiple domains
golden = df.sample(n=30, random_state=42)[["input.value", "attributes.llmwiki.domain"]]
golden = golden.rename(columns={"input.value": "question", "attributes.llmwiki.domain": "domain"})

# Upload as a reusable dataset
dataset = client.upload_dataset(
    dataframe=golden,
    dataset_name="llmwiki-golden-v1",
    input_keys=["question", "domain"],
)
print(f"Dataset ID: {dataset.id}")
```

### Define the task function (calls your Lambda)

```python
import boto3
import json

lambda_client = boto3.client("lambda", region_name="us-east-1")

def call_llmwiki(question: str, domain: str = "general") -> str:
    resp = lambda_client.invoke(
        FunctionName="llmwiki-query",
        Payload=json.dumps({"question": question, "domain": domain})
    )
    result = json.loads(resp["Payload"].read())
    return result.get("answer", "")

def task(example) -> dict:
    answer = call_llmwiki(
        question=example["question"],
        domain=example.get("domain", "general")
    )
    return {"answer": answer}
```

### Run experiment: current prompt vs new prompt

```python
from phoenix.experiments import run_experiment, evaluate_experiment
from phoenix.evals import BedrockModel, RAG_FAITHFULNESS_PROMPT_TEMPLATE, llm_classify

judge = BedrockModel(model_id="us.anthropic.claude-sonnet-4-6", region_name="us-east-1")

def faithfulness_evaluator(output, example, **_):
    result = llm_classify(
        dataframe=pd.DataFrame([{
            "input": example["question"],
            "output": output["answer"],
            "context": output.get("context", ""),
        }]),
        template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
        model=judge,
        rails=["faithful", "hallucinated"],
    )
    label = result.iloc[0]["label"]
    return {"score": 1.0 if label == "faithful" else 0.0, "label": label}

# Experiment A: current system prompt
experiment_a = run_experiment(
    dataset=dataset,
    task=task,
    evaluators=[faithfulness_evaluator],
    experiment_name="prompt-v1-baseline",
)

# ... make your prompt change to the Lambda ...

# Experiment B: new system prompt
experiment_b = run_experiment(
    dataset=dataset,
    task=task,
    evaluators=[faithfulness_evaluator],
    experiment_name="prompt-v2-candidate",
)

# Compare in Phoenix UI: http://localhost:6006 → Experiments
# Or compare programmatically:
print(f"Baseline faithfulness: {experiment_a.get_evaluations()['score'].mean():.2f}")
print(f"Candidate faithfulness: {experiment_b.get_evaluations()['score'].mean():.2f}")
```

The Phoenix Experiments UI shows a side-by-side view of every example, both outputs, and both scores. This replaces eyeballing with a quantified comparison.

---

## The Correctness vs Faithfulness Lesson (Applied to LLMWiki)

From @seldo's workshop: a correctness eval on the financial analysis agent scored 0/13. The same agent scored 13/13 on faithfulness. Both evals were run on the same traces. The agent was actually working correctly — the correctness eval was wrong for this use case.

**How this applies to LLMWiki:**

LLMWiki answers questions about TriZetto configuration, HealthEdge provisioning, and client implementation workflows. Most answers require consulting specific wiki pages that contain the authoritative answer. The model cannot verify whether an answer is "correct" without access to the ground truth doc — but it can be evaluated on whether it stays faithful to what was retrieved.

**Start with faithfulness, not correctness.**

Correctness evals require a human-validated golden answer for every question. Building that takes weeks. Faithfulness evals run immediately on production traces and catch the most dangerous failure mode: a model that sounds confident while adding facts not in the retrieved context.

Build correctness evals only for the Business Knowledge API endpoints that return structured data (`action_items`, `confidence`) and where you can validate the output against a known document. The table below guides the choice:

| LLMWiki use case | Primary eval | Why |
|-----------------|-------------|-----|
| Streamlit Q&A (human users) | Faithfulness | Ground answers in wiki pages; correctness requires SME review |
| `/wiki/ask` Business API | Faithfulness + Custom rubric | Faithfulness for the answer; rubric for structured fields |
| `/wiki/query/{domain}` | Relevance + Faithfulness | Did retrieval surface the right domain chunks? |
| Ingest pipeline quality | Code eval | Does the wiki page have the right schema? Non-empty `summary`, `tags`, `content`? |
| AgentCore skill invocations | Faithfulness | Downstream agents cascade hallucinations — faithfulness is the safety net |

---

## Seeing LLMWiki Traces in Phoenix UI

After instrumenting the Lambda and running queries:

1. Open http://localhost:6006
2. Select **Projects** → `llmwiki-query`
3. Each query appears as a root span with child spans for:
   - The Bedrock InvokeModel call (KB retrieval)
   - The Bedrock InvokeModel call (synthesis with Claude)
4. Click any span to see:
   - `input.value`: the user question
   - `output.value`: the synthesized answer
   - `llmwiki.retrieved_context`: the chunks that were used
   - `llmwiki.confidence`: what the system returned
   - Latency waterfall: where time was spent

The most useful view is **latency vs confidence** — traces where low confidence took a long time usually indicate a retrieval path that is working hard but finding little relevant content. Those are the best candidates for KB expansion.

---

## Eval CI Integration

Once you have a golden dataset and eval scripts, run them on every Lambda deploy:

```bash
# scripts/eval_ci.sh
#!/bin/bash
set -e

# 1. Deploy the new Lambda (already handled by deploy.sh)
# 2. Run 20-query sample eval
python scripts/run_faithfulness_eval.py --limit 20

# 3. Check agreement threshold — fail if faithfulness < 75%
python - <<'EOF'
import pandas as pd
df = pd.read_csv("eval_results.csv")
faithfulness_rate = (df["claude_label"] == "faithful").mean()
print(f"Faithfulness rate: {faithfulness_rate:.1%}")
if faithfulness_rate < 0.75:
    print("FAIL: faithfulness below 75% threshold")
    exit(1)
print("PASS")
EOF
```

Add to `scripts/deploy.sh` after the Lambda deploy step:

```bash
echo "Running post-deploy eval..."
bash scripts/eval_ci.sh
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start Phoenix | `docker.exe run -d -p 6006:6006 -p 4317:4317 ghcr.io/arize-ai/phoenix:latest` |
| Open UI | http://localhost:6006 |
| Pull traces | `px.Client("http://localhost:6006").get_spans_dataframe("llmwiki-query")` |
| Run faithfulness eval | `python scripts/run_faithfulness_eval.py --limit 50` |
| Run experiments | See Step 5 above |
| Stop Phoenix | `docker.exe stop phoenix` |
| View Phoenix logs | `docker.exe logs phoenix` |

### Environment variables to set

| Component | Variable | Value |
|-----------|----------|-------|
| Lambda (query) | `PHOENIX_COLLECTOR_ENDPOINT` | `http://<phoenix-host>:4317` |
| Streamlit | `PHOENIX_COLLECTOR_ENDPOINT` | `http://<phoenix-host>:4317` |
| Local dev (WSL) | `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:4317` |
| Docker-in-Docker | `PHOENIX_COLLECTOR_ENDPOINT` | `http://host.docker.internal:4317` |

### Companion documents

- `llmwiki-eval-strategy.md` — four-layer eval stack, golden datasets, RAGAS scoring
- `AgenticDesign.md` — Business Knowledge API contract (the structured response that needs the custom rubric eval)
- `LLMWikiDesign.md` — Lambda architecture, S3 Vectors setup

---

## What to Build First

1. **Today**: Start Phoenix, run 20 queries through Streamlit, look at the traces
2. **This week**: Add `llmwiki.retrieved_context` to the query Lambda span, run the faithfulness eval with both judges
3. **Next week**: Build the golden dataset (30 examples), run your first experiment before changing the query prompt
4. **Phase 2 (Business API)**: Add the custom rubric eval for the structured response contract before any agent integrates with `/wiki/ask`

The vibes problem is not solved by running more evals. It's solved by running the **right** evals, on real traces, before you change anything.

---

## Phoenix EVAL for Neuro SAN Agents

### Is Phoenix EVAL a good fit for Neuro SAN?

Yes — and in some ways it fits Neuro SAN **better** than it fits the Lambda-based pipeline.

LLMWiki's query Lambda makes a single Bedrock call. Neuro SAN agents run the AAOSA protocol: a Determine round (FrontMan asks all sub-agents "are you relevant?"), then a Fulfill round (FrontMan calls each relevant sub-agent), and finally a Compile round (FrontMan synthesizes all responses). That's 5–10 LLM calls per UC1 session, spread across `ContextBootstrapTool`, `WikiQueryTool`, `ArtifactResolutionTool`, `GapDetectionTool`, and `WikiContributeTool`.

Phoenix EVAL is OpenTelemetry-native. Neuro SAN already ships with **Langfuse** observability built in — and Langfuse exports traces over OpenTelemetry. That means you can route Neuro SAN traces to Phoenix's OTel collector endpoint with one environment variable change, no code change to the agent network.

The result: every AAOSA session appears in Phoenix as a root span with child spans per tool call, per Bedrock invoke, and per wiki API call. You can then run the same faithfulness and custom rubric evals described earlier against the Neuro SAN traces — the trace schema is the same OpenInference format either way.

### Architecture: dual-source traces in one Phoenix instance

```
┌──────────────────────────────────────────────────────────────────┐
│  Phoenix Container  (self-hosted, no data egress)                │
│  :4317 (gRPC)  :9000 (HTTP)  :6006 (UI)                         │
│                                                                  │
│  Project: llmwiki-query       ← Lambda + Streamlit traces       │
│  Project: neuro-san-agents    ← Neuro SAN AAOSA session traces  │
└─────────┬──────────────────────────────┬─────────────────────────┘
          │ OTel gRPC                    │ OTel gRPC
┌─────────▼────────────┐    ┌────────────▼────────────────────────┐
│ Lambda query (SK-02) │    │ Neuro SAN ECS Fargate               │
│ Streamlit UI         │    │ LANGFUSE_HOST=http://phoenix:4317   │
└──────────────────────┘    │ (or OTEL_EXPORTER_OTLP_ENDPOINT)   │
                            └─────────────────────────────────────┘
```

Both trace sources land in Phoenix. Use separate Phoenix project names (`llmwiki-query` for Lambda, `neuro-san-agents` for Neuro SAN) so you can filter and eval them independently or together.

### Step 1: Route Neuro SAN traces to Phoenix

Neuro SAN supports Langfuse for observability. Langfuse can forward traces to any OTel endpoint — point it at Phoenix:

**Option A — Langfuse as the middleman (if you already use Langfuse)**

In Langfuse, enable OTel export and set the export endpoint to `http://phoenix:4317`. All Neuro SAN traces flow: Neuro SAN → Langfuse → Phoenix.

**Option B — Direct OTel export (simpler, no Langfuse dependency)**

Set these environment variables in the Neuro SAN ECS task definition:

```json
{ "name": "OTEL_EXPORTER_OTLP_ENDPOINT",  "value": "http://phoenix:4317" },
{ "name": "OTEL_EXPORTER_OTLP_PROTOCOL",  "value": "grpc" },
{ "name": "OTEL_SERVICE_NAME",            "value": "neuro-san-agents" },
{ "name": "LANGFUSE_ENABLED",             "value": "false" }
```

For local dev (`ns run`), set them in `.env`:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_SERVICE_NAME=neuro-san-agents
```

Then start Phoenix and run a UC1 session:

```bash
# Start Phoenix
docker.exe run -d --name phoenix -p 6006:6006 -p 4317:4317 \
  ghcr.io/arize-ai/phoenix:latest

# Run Neuro SAN locally
ns run

# Send a test request
curl -X POST http://localhost:8080/api/v1/uc1_sales_to_service/streaming_chat \
  -H "Content-Type: application/json" \
  -d '{"user_message": {"text": "Onboard test-customer-001"}, "sly_data": {"customer_id": "test-customer-001"}}'

# Open Phoenix UI: http://localhost:6006 → Projects → neuro-san-agents
```

### Step 2: What AAOSA traces look like in Phoenix

Each UC1 session appears as a span tree:

```
UC1SalesToServiceAgent (root)  18.2s
├── AAOSA-Determine              1.2s  — FrontMan asks all 5 sub-agents
│   ├── ContextBootstrap-Determine  0.2s
│   ├── WikiQuery-Determine         0.3s
│   ├── ArtifactResolution-Determine 0.2s
│   ├── GapDetection-Determine      0.2s
│   └── WikiContribute-Determine    0.3s
├── ContextBootstrapTool         0.5s  — SK-01, 0 LLM tokens
│   ├── GET /wiki/customer/{id}   0.2s
│   └── GET /wiki/playbook/UC1    0.3s
├── WikiQueryTool                2.1s  — SK-02, 3680 tokens (Bedrock)
│   └── bedrock:InvokeModel       1.8s  llm.input/output captured
├── ArtifactResolutionTool       2.8s  — SK-04, 2200 tokens
│   └── bedrock:InvokeModel       2.6s
├── GapDetectionTool             0.9s  — SK-05
└── AAOSA-Compile               10.0s  — FrontMan synthesizes, 1840 tokens
    └── bedrock:InvokeModel       9.7s
```

The attributes that matter for evals:

| Span | Key attribute | What to eval |
|------|--------------|--------------|
| WikiQueryTool | `input.value` (question), `output.value` (answer), `llmwiki.retrieved_context` | Faithfulness: does the answer follow from the retrieved context? |
| AAOSA-Compile | `input.value` (all sub-agent results), `output.value` (final answer) | Custom rubric: does the compiled answer match the Business API contract? |
| WikiContributeTool | `output.value` (contributed page) | Code eval: was the page contributed to the right path? Non-empty content? |
| GapDetectionTool | `output.value` (gaps list) | Code eval: if `confidence=low` on WikiQuery, was a gap recorded? |

### Step 3: Read Neuro SAN traces with the Phoenix client

```python
import phoenix as px

client = px.Client(endpoint="http://localhost:6006")

# Pull UC agent traces
neuro_df = client.get_spans_dataframe(project_name="neuro-san-agents")

# Filter to WikiQueryTool spans only — these have the KB-grounded answers
wiki_query_spans = neuro_df[
    neuro_df["name"].str.contains("WikiQueryTool", na=False)
][["input.value", "output.value", "attributes.llmwiki.retrieved_context",
   "attributes.llmwiki.confidence", "parent_id"]]

print(f"WikiQueryTool invocations: {len(wiki_query_spans)}")
print(wiki_query_spans.head(5))
```

### Step 4: Run faithfulness eval on Neuro SAN WikiQueryTool spans

The faithfulness eval runs identically against Neuro SAN spans as against Lambda spans — the data shape is the same:

```python
from phoenix.evals import BedrockModel, RAG_FAITHFULNESS_PROMPT_TEMPLATE, llm_classify

claude_judge = BedrockModel(model_id="us.anthropic.claude-sonnet-4-6", region_name="us-east-1")

eval_df = wiki_query_spans.rename(columns={
    "input.value": "input",
    "output.value": "output",
    "attributes.llmwiki.retrieved_context": "context"
}).dropna(subset=["context"])

faithfulness = llm_classify(
    dataframe=eval_df,
    template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
    model=claude_judge,
    rails=["faithful", "hallucinated"],
    provide_explanation=True,
)
print(faithfulness["label"].value_counts())
```

### Step 5: AAOSA-specific custom rubric — eval the compiled answer

The AAOSA Compile span is unique to Neuro SAN. The FrontMan synthesizes all sub-agent tool results into a final response. This is where errors cascade: a hallucinated WikiQueryTool answer can corrupt the compiled answer even if the individual tool response was flagged. Eval the compile span separately:

```python
AAOSA_COMPILE_RUBRIC = """
You are evaluating the final compiled output of a Neuro SAN UC1 Sales-to-Service agent.

The agent ran the following tools and synthesized a final answer:
Context (all tool outputs):  {context}
Final compiled answer:       {output}
Original inquiry:            {input}

Evaluate on four criteria:
1. SYNTHESIS: Does the compiled answer faithfully reflect the tool outputs — no added claims?
2. STRUCTURE: Does it include customer_status, persona_populated, gaps_detected, wiki_page_created?
3. GAP HONESTY: If any tool reported low confidence or missing fields, are those gaps surfaced?
4. NO HALLUCINATION: Are all specific claims (page names, customer IDs, artifact types) traceable to a tool output?

If ALL four pass: PASS
If ANY fail: FAIL, plus one sentence naming what failed.
""".strip()

compile_spans = neuro_df[neuro_df["name"].str.contains("AAOSA-Compile", na=False)].copy()
# Aggregate child tool outputs into "context" field
# (join output.value from all sibling spans under the same root span)

compile_eval_df = compile_spans.rename(columns={
    "input.value": "input",
    "output.value": "output",
}).assign(context="[tool outputs from child spans — see aggregation script]")

compile_results = llm_classify(
    dataframe=compile_eval_df,
    template=AAOSA_COMPILE_RUBRIC,
    model=claude_judge,
    rails=["PASS", "FAIL"],
    provide_explanation=True,
)
print(compile_results["label"].value_counts())
```

### Step 6: Code evals specific to Neuro SAN

These are deterministic checks on AAOSA behavior — no LLM judge required:

```python
def eval_all_tools_determined(row) -> dict:
    """Every UC1 run should have 5 Determine spans — one per sub-agent."""
    span_name = row.get("name", "")
    # Count Determine spans for the same root span (checked at session level)
    return {"label": "skip", "score": None}  # implemented at session level below

def eval_gap_recorded_on_low_confidence(session_spans: pd.DataFrame) -> dict:
    """If any WikiQueryTool span has confidence=low, GapDetectionTool must also exist."""
    wq = session_spans[session_spans["name"].str.contains("WikiQueryTool", na=False)]
    gd = session_spans[session_spans["name"].str.contains("GapDetectionTool", na=False)]
    low_conf = wq[wq.get("attributes.llmwiki.confidence", pd.Series()) == "low"]
    if len(low_conf) > 0 and len(gd) == 0:
        return {"label": "fail", "score": 0, "explanation": "low confidence detected but GapDetection not called"}
    return {"label": "pass", "score": 1, "explanation": "gap detection correctly triggered or not needed"}

def eval_contribute_called_last(session_spans: pd.DataFrame) -> dict:
    """WikiContributeTool should be the last tool called (after all others complete)."""
    tools = session_spans[session_spans["name"].str.contains("Tool", na=False)]
    if tools.empty:
        return {"label": "skip", "score": None}
    last_tool = tools.sort_values("start_time").iloc[-1]["name"]
    return {
        "label": "pass" if "WikiContribute" in last_tool else "fail",
        "score": 1 if "WikiContribute" in last_tool else 0,
        "explanation": f"last tool was {last_tool}"
    }

# Group spans by session (root span id) and run session-level checks
for root_id, session_spans in neuro_df.groupby("context.trace_id"):
    result = eval_gap_recorded_on_low_confidence(session_spans)
    if result["label"] == "fail":
        print(f"Session {root_id}: {result['explanation']}")
```

### Step 7: Experiments — A/B test HOCON prompt changes

Neuro SAN agent behavior is defined in HOCON instruction blocks. Changing the UC1 FrontMan's instructions is a 3-line edit in `uc1_sales_to_service.hocon`. Phoenix Experiments let you prove the change improved things before merging.

```python
import phoenix as px
from phoenix.experiments import run_experiment, evaluate_experiment

client = px.Client(endpoint="http://localhost:6006")

# Golden dataset: 20 UC1 test scenarios (same structure as the Neuro SAN test JSON)
golden = client.upload_dataset(
    dataframe=pd.DataFrame([
        {"question": "Onboard BCBS-MN-001 using the S2S playbook",
         "customer_id": "bcbs-mn-001", "expected_gaps": 0},
        {"question": "Onboard brand-new-customer-2026 with no prior history",
         "customer_id": "brand-new-customer-2026", "expected_gaps": 1},
        # ... 18 more
    ]),
    dataset_name="neuro-san-uc1-golden-v1",
    input_keys=["question", "customer_id"],
)

import requests

def task(example) -> dict:
    resp = requests.post(
        "http://localhost:8080/api/v1/uc1_sales_to_service/streaming_chat",
        json={
            "user_message": {"text": example["question"]},
            "sly_data": {"customer_id": example["customer_id"], "use_case": "UC1"}
        },
        timeout=60
    )
    return resp.json()

# Run experiment with current HOCON instructions
experiment_a = run_experiment(
    dataset=golden,
    task=task,
    experiment_name="uc1-hocon-v1-baseline",
)

# ... edit uc1_sales_to_service.hocon instructions ...
# ns run (hot-reloads in 5 seconds)

# Run experiment with new HOCON instructions
experiment_b = run_experiment(
    dataset=golden,
    task=task,
    experiment_name="uc1-hocon-v2-gap-detection-improved",
)

# Compare in Phoenix UI: http://localhost:6006 → Experiments
```

---

## Common Eval Framework — Lambda and Neuro SAN Together

### Can you use one eval harness for both?

Yes. This is the recommended approach. The Lambda query pipeline and Neuro SAN's WikiQueryTool both call the same LLMWiki KB and return the same structured response (`answer + confidence + action_items + gaps_detected`). The eval logic for faithfulness, the custom rubric, and the code checks is identical — the only difference is which Phoenix project you pull traces from.

Build one shared eval library and parameterize the project name:

```python
# scripts/llmwiki_eval.py
"""
Shared eval harness for LLMWiki Lambda pipeline and Neuro SAN agents.
Usage:
    python scripts/llmwiki_eval.py --source lambda --limit 50
    python scripts/llmwiki_eval.py --source neuro-san --limit 50
    python scripts/llmwiki_eval.py --source both --limit 50
"""
import argparse
import pandas as pd
import phoenix as px
from phoenix.evals import BedrockModel, RAG_FAITHFULNESS_PROMPT_TEMPLATE, llm_classify

PHOENIX_PROJECT_MAP = {
    "lambda":    "llmwiki-query",
    "neuro-san": "neuro-san-agents",
}

WIKI_QUERY_SPAN_FILTER = {
    "lambda":    lambda df: df,                                            # Lambda: all spans are WikiQuery
    "neuro-san": lambda df: df[df["name"].str.contains("WikiQueryTool")],  # Neuro SAN: filter to WikiQueryTool
}

def load_eval_df(client: px.Client, source: str, limit: int) -> pd.DataFrame:
    project = PHOENIX_PROJECT_MAP[source]
    df = client.get_spans_dataframe(project_name=project)
    df = WIKI_QUERY_SPAN_FILTER[source](df)
    df = df.rename(columns={
        "input.value": "input",
        "output.value": "output",
        "attributes.llmwiki.retrieved_context": "context",
        "attributes.llmwiki.confidence": "confidence",
    })
    df = df[["input", "output", "context", "confidence"]].dropna(subset=["context"])
    return df.head(limit)

def run_faithfulness(df: pd.DataFrame, source: str) -> pd.DataFrame:
    judge = BedrockModel(model_id="us.anthropic.claude-sonnet-4-6", region_name="us-east-1")
    results = llm_classify(
        dataframe=df,
        template=RAG_FAITHFULNESS_PROMPT_TEMPLATE,
        model=judge,
        rails=["faithful", "hallucinated"],
        provide_explanation=True,
    )
    rate = (results["label"] == "faithful").mean()
    print(f"[{source}] Faithfulness: {rate:.1%} ({len(df)} spans)")
    return results

def run_code_evals(df: pd.DataFrame, source: str) -> None:
    empty_answers = (df["output"].str.len() < 20).sum()
    zero_context = (df["context"].str.len() < 10).sum()
    high_conf_no_context = (
        (df["confidence"] == "high") & (df["context"].str.len() < 50)
    ).sum()
    print(f"[{source}] Code evals — empty answers: {empty_answers}, "
          f"zero context: {zero_context}, overconfident: {high_conf_no_context}")

def main(source: str, limit: int) -> None:
    client = px.Client(endpoint="http://localhost:6006")
    sources = ["lambda", "neuro-san"] if source == "both" else [source]

    all_results = {}
    for src in sources:
        df = load_eval_df(client, src, limit)
        if df.empty:
            print(f"[{src}] No traces found in Phoenix — run some queries first")
            continue
        run_code_evals(df, src)
        all_results[src] = run_faithfulness(df, src)

    if len(all_results) == 2:
        lambda_rate = (all_results["lambda"]["label"] == "faithful").mean()
        neuro_rate  = (all_results["neuro-san"]["label"] == "faithful").mean()
        print(f"\n=== Comparison ===")
        print(f"Lambda faithfulness:    {lambda_rate:.1%}")
        print(f"Neuro SAN faithfulness: {neuro_rate:.1%}")
        delta = neuro_rate - lambda_rate
        direction = "better" if delta > 0 else "worse"
        print(f"Neuro SAN is {abs(delta):.1%} {direction} than Lambda on faithfulness")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["lambda", "neuro-san", "both"], default="both")
    parser.add_argument("--limit", type=int, default=50)
    main(**vars(parser.parse_args()))
```

Run it:

```bash
# Compare both systems on the same day's traces
python scripts/llmwiki_eval.py --source both --limit 50
```

### Why a common eval is valuable

The Lambda query function and Neuro SAN's WikiQueryTool both call `/wiki/ask` — they go to the same KB, hit the same Claude model, and return the same response schema. A faithfulness regression in one is often a signal for the other: if the KB has a stale chunk, both systems are affected.

Running the same eval against both traces answers a sharper question: **does the AAOSA orchestration layer add or remove faithfulness risk?** If Neuro SAN's WikiQueryTool spans score identically to Lambda spans, the orchestration is neutral and the KB quality is the source of truth. If they diverge, it's either the FrontMan's instructions shaping the WikiQueryTool call differently, or the AAOSA Compile step adding hallucinated synthesis on top of faithful tool outputs.

That diagnosis is only possible when you're running the same eval harness against both sources.

### Eval coverage map — Lambda vs Neuro SAN

| Eval type | Lambda (query) | Neuro SAN (WikiQueryTool) | Neuro SAN (AAOSA-Compile) |
|-----------|---------------|--------------------------|--------------------------|
| Faithfulness (RAG) | ✅ primary eval | ✅ same eval, same template | ✅ custom rubric (synthesis layer) |
| Relevance (retrieval) | ✅ built-in Phoenix template | ✅ same | not applicable |
| Custom rubric (Business API contract) | ✅ `/wiki/ask` response fields | ✅ WikiQueryTool output fields | ✅ compiled output fields |
| Code evals (non-empty, citations) | ✅ Lambda span attrs | ✅ WikiQueryTool span attrs | ✅ session-level checks |
| AAOSA protocol correctness | not applicable | not applicable | ✅ Neuro SAN-specific checks |
| Gap detection trigger logic | not applicable | not applicable | ✅ session-level code eval |
| Confidence calibration | ✅ Lambda span attr | ✅ WikiQueryTool span attr | ✅ check in compiled answer |
| Injection resistance | ✅ code eval on output | ✅ same | ✅ check Sly Data fields not in output |

### Common golden dataset

Both systems can be tested against the same 30-question golden dataset. The Lambda version calls the query Lambda directly; the Neuro SAN version calls the REST API:

```python
# scripts/build_golden_dataset.py
"""
Upload a shared golden dataset to Phoenix that works for both Lambda and Neuro SAN eval.
"""
import phoenix as px
import pandas as pd

client = px.Client(endpoint="http://localhost:6006")

GOLDEN_QUESTIONS = [
    # TriZetto provisioning domain
    {"question": "What documents are required before starting a TriZetto provisioning project?",
     "domain": "provisioning", "customer_id": None},
    {"question": "What are the decision gates for UC2 environment provisioning?",
     "domain": "provisioning", "customer_id": None},
    # Customer-specific domain
    {"question": "What are the known delivery risks for BCBS-MN?",
     "domain": "customer-onboarding", "customer_id": "bcbs-mn-001"},
    {"question": "What IAM roles were created during BCBS-MN onboarding?",
     "domain": "customer-onboarding", "customer_id": "bcbs-mn-001"},
    # HealthEdge domain
    {"question": "What SIT testing scenarios must pass before G4 gate?",
     "domain": "testing", "customer_id": None},
    # ... 25 more
]

dataset = client.upload_dataset(
    dataframe=pd.DataFrame(GOLDEN_QUESTIONS),
    dataset_name="llmwiki-shared-golden-v1",
    input_keys=["question", "domain", "customer_id"],
)
print(f"Uploaded {len(GOLDEN_QUESTIONS)} questions as dataset: {dataset.id}")
```

The same dataset ID is passed to Lambda experiments and Neuro SAN experiments. Phoenix's Experiments UI shows both runs side by side, making it straightforward to see where one system outperforms the other.

### CI integration — run both evals on every deploy

```bash
# scripts/eval_ci_full.sh
#!/bin/bash
set -e

echo "=== Running common LLMWiki eval (Lambda + Neuro SAN) ==="

# 1. Run shared eval
python scripts/llmwiki_eval.py --source both --limit 20

# 2. Parse results and enforce thresholds
python - <<'EOF'
import pandas as pd

lambda_df   = pd.read_csv("eval_results_lambda.csv")
neuro_df    = pd.read_csv("eval_results_neuro_san.csv")

lambda_faith = (lambda_df["claude_label"] == "faithful").mean()
neuro_faith  = (neuro_df["claude_label"] == "faithful").mean()

print(f"Lambda faithfulness:    {lambda_faith:.1%}")
print(f"Neuro SAN faithfulness: {neuro_faith:.1%}")

failed = False
if lambda_faith < 0.75:
    print("FAIL: Lambda faithfulness below 75%")
    failed = True
if neuro_faith < 0.75:
    print("FAIL: Neuro SAN faithfulness below 75%")
    failed = True
if failed:
    exit(1)
print("PASS: both systems above threshold")
EOF
```

---

## Updated Quick Reference

| Task | Command |
|------|---------|
| Start Phoenix | `docker.exe run -d -p 6006:6006 -p 4317:4317 ghcr.io/arize-ai/phoenix:latest` |
| Open UI | http://localhost:6006 |
| Lambda traces | Project: `llmwiki-query` |
| Neuro SAN traces | Project: `neuro-san-agents` |
| Run common eval | `python scripts/llmwiki_eval.py --source both --limit 50` |
| Run Neuro SAN experiment | See Step 7 above |
| Build golden dataset | `python scripts/build_golden_dataset.py` |

### Additional env vars for Neuro SAN ECS task

| Variable | Value | Effect |
|----------|-------|--------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://phoenix:4317` | Route traces to Phoenix |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Use gRPC (matches Phoenix port 4317) |
| `OTEL_SERVICE_NAME` | `neuro-san-agents` | Phoenix project name |
| `LANGFUSE_ENABLED` | `false` | Disable Langfuse if routing to Phoenix instead |

If you want **both** Langfuse and Phoenix, keep `LANGFUSE_ENABLED=true` and add the OTel vars — Langfuse will export a copy to Phoenix while retaining its own trace store.

---

### Summary: Neuro SAN + Phoenix EVAL

Phoenix EVAL applies to Neuro SAN without structural changes — it's OTel all the way down. The AAOSA multi-agent session produces richer traces than a single Lambda call, which means you can eval at multiple layers: the WikiQueryTool span (same faithfulness eval as Lambda), the AAOSA-Compile span (new synthesis rubric), and the full session (AAOSA protocol correctness checks). The shared eval harness runs against both systems from one script, giving you a direct faithfulness comparison between the Lambda path and the Neuro SAN path on every deploy.
