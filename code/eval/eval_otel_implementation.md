# OTel Implementation Guide — LLMWiki Eval

Three surfaces, one Phoenix backend. This doc covers what was tested locally and what each surface needs to emit live traces.

---

## What runs locally today

```
Phoenix container (arizephoenix/phoenix:latest)
  └── :6006  UI + REST API
  └── :4317  gRPC OTLP (for live instrumentation when packages are installed)

step1_seed_traces.py  →  POST /v1/projects/llmwiki-query/spans  (stdlib urllib, no packages needed)
step2_read_traces.py  →  GET  /v1/projects/llmwiki-query/spans
step3_run_evals.py    →  reads CSV, calls Bedrock (Claude + Nova Pro faithfulness judges)
step4_judge_comparison.py  →  reads eval_results.csv, prints agreement analysis
step5_experiments.py  →  calls Bedrock directly, compares prompt v1 vs v2
```

**Key constraint:** corporate Zscaler blocks `files.pythonhosted.org` with 403.  
`opentelemetry-*` and `openinference-*` packages are NOT installed in the system Python.  
All eval steps fall back to mock/REST mode gracefully — no package required to run the pipeline.

**To enable live gRPC tracing locally**, pre-bundle the wheels the same way neuro-san does:
```bash
# on a machine with PyPI access, download wheels:
pip download opentelemetry-api opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-grpc \
    openinference-instrumentation-bedrock \
    openinference-semantic-conventions \
    -d eval/wheels/
# then install offline:
pip install --no-index --find-links eval/wheels/ opentelemetry-api ...
```

---

## Lambda way

**Entry point:** `code/lambda/query/handler.py` → `answer_question()`

**What to add — cold-start instrumentation:**

```python
# handler.py top of file
import os
from eval.tracing import setup_tracing   # or inline if not bundled

_tracer = setup_tracing(
    service_name="llmwiki-query",
    project_name="llmwiki-query",
    collector_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
```

**What to add — per-request span in `answer_question()`:**

```python
def answer_question(question, kb_id, model_id, ...):
    with _tracer.start_as_current_span("llmwiki.query") as span:
        span.set_attribute("input.value", question)
        # ... existing retrieve + converse logic ...
        span.set_attribute("output.value", answer)
        span.set_attribute("llmwiki.confidence", confidence)
        span.set_attribute("llmwiki.citation_count", len(sources))
        span.set_attribute("llmwiki.domain", domain)
        span.set_attribute("llmwiki.retrieved_context", context_text)
        return answer, sources
```

**Infrastructure needed:**
- Phoenix running as ECS Fargate service in `llmwiki-cluster` (same VPC as Lambda)
- Lambda env var: `OTEL_EXPORTER_OTLP_ENDPOINT=http://<phoenix-private-ip>:4317`
- Lambda Layer: bundle `opentelemetry-*` + `openinference-instrumentation-bedrock` wheels
- Security group: Lambda → Phoenix on port 4317

**What appears in Phoenix UI:**  
One span per query → `input.value`, `output.value`, confidence, citation count, domain, latency.  
`BedrockInstrumentor` auto-adds child spans for each `bedrock-runtime` API call (retrieve + converse).

---

## Neuro SAN way

**Architecture:** every agent request passes through one of 5 coded tools, all inheriting from `LLMWikiBaseTool._invoke_skill()`. That single method is the instrumentation point.

**Entry point:** `code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py`

**What to add:**

```python
# llmwiki_base_tool.py __init__
import os
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if _endpoint:
        _provider = TracerProvider()
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_endpoint, insecure=True)))
        trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("neuro-san-agents")
    _OTEL_OK = True
except ImportError:
    _OTEL_OK = False
```

```python
# wrap _invoke_skill()
def _invoke_skill(self, function_name: str, payload: dict) -> dict:
    if not _OTEL_OK:
        return self._raw_invoke(function_name, payload)   # existing logic unchanged
    with _tracer.start_as_current_span(function_name) as span:
        span.set_attribute("neuro_san.tool", type(self).__name__)
        span.set_attribute("neuro_san.skill", function_name)
        span.set_attribute("input.value", str(payload.get("q", payload.get("question", "")))[:500])
        result = self._raw_invoke(function_name, payload)
        span.set_attribute("output.value", str(result.get("answer", ""))[:500])
        span.set_attribute("neuro_san.error", str(result.get("_error", False)))
        return result
```

**Infrastructure needed:**
- `OTEL_EXPORTER_OTLP_ENDPOINT` env var in the ECS task definition for `llmwiki-neuro-san`
- Phoenix reachable from ECS task on port 4317 (same VPC — no extra SG rule needed if Lambda already has it)
- `opentelemetry-*` wheels pre-bundled in the neuro-san Docker image (same pattern as existing wheels)
- Phoenix project name routed via header: `x-phoenix-project-name: neuro-san-agents`

**What appears in Phoenix UI:**  
One parent span per AAOSA session → 5 child tool spans in sequence:  
`ContextBootstrapTool` → `WikiQueryTool` → `ArtifactResolutionTool` → `GapDetectionTool` → `WikiContributeTool`

This shows the full delegation chain, which span took longest, and where failures occur — much richer than a single Lambda trace.

**Neuro SAN built-in tracing note:**  
The neuro-san wheel ships a `LangfuseTracingContext` for Langfuse integration. Setting `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` env vars activates it natively — but Langfuse is a separate SaaS product. Phoenix via OTel (Option B above) keeps everything self-hosted and in the same eval pipeline.

---

## Phoenix project routing summary

| Surface | Phoenix project | Populated by |
|---|---|---|
| Lambda RAG queries | `llmwiki-query` | `BedrockInstrumentor` auto-spans + manual `llmwiki.*` attributes |
| Neuro SAN AAOSA | `neuro-san-agents` | `_invoke_skill()` wrapper spans, one per coded tool |
| Seed (offline dev) | `llmwiki-query` | `step1_seed_traces.py` REST POST |

Both projects visible at `http://localhost:6006` (local) or ALB port 6006 (AWS).
