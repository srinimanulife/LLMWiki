# LLMWiki Neuro SAN — Coded Tools

This package contains the Neuro SAN `CodedTool` implementations that bridge
the LLMWiki Lambda skill layer with the Neuro SAN AAOSA agent framework.

## Package structure

```
code/
  lambda/
    common/
      llmwiki_common.py       # Shared utilities — same source for Lambda Layer AND Neuro SAN
      governance.py
      harness_common.py
  neuro_san/
    coded_tools/
      llmwiki/
        __init__.py
        llmwiki_base_tool.py          # uses llmwiki_common.invoke_lambda when available
        context_bootstrap_tool.py     # SK-01 — Customer Briefing Loader
        wiki_query_tool.py            # SK-02 — Knowledge Finder
        wiki_contribute_tool.py       # SK-03 — Knowledge Recorder (HITL hardcoded)
        artifact_resolution_tool.py   # SK-04 — Template Auto-Fill
        gap_detection_tool.py         # SK-05 — Missing Info Radar
```

## Shared common library

`lambda/common/llmwiki_common.py` is the single source of truth for:
- `invoke_lambda(function_name, payload)` — boto3 Lambda invocation + API GW body unwrap
- `log_telemetry(...)` — DynamoDB telemetry logging
- `bedrock_converse(...)` — Bedrock Converse API wrapper
- `skill_response(...)` — standard skill contract response builder

The same file is packaged as a Lambda Layer (for Lambda functions) and
copied into the Docker image at `/app/lambda_common/` (for Neuro SAN coded tools).
`ENV PYTHONPATH=/app/lambda_common` in the Dockerfile makes it importable as `llmwiki_common`.

`llmwiki_base_tool.py` tries `from llmwiki_common import invoke_lambda` at import time.
If that succeeds (Docker container or local dev with PYTHONPATH set), it uses the shared
implementation. If not (standalone invocation without PYTHONPATH), it falls back to
inline boto3 — same behavior, no crash.

## Key design principle

Each coded tool is a thin wrapper:
- **Business logic lives in the HOCON NLP instruction block** (plain English)
- **The coded tool contains only the AWS API call** (via llmwiki_common or inline boto3)
- **Sensitive data (customer_id, api_key) travels via `sly_data`** — never in the LLM context

This means business analysts can change agent behavior by editing HOCON text.
No Python changes, no Lambda redeploy, no PR review required.

## How each tool maps to the existing Lambda

| Coded Tool | Lambda Function | Skill ID |
|-----------|-----------------|----------|
| `ContextBootstrapTool` | `llmwiki-skill-context-bootstrap` | SK-01 |
| `WikiQueryTool` | `llmwiki-skill-wiki-query` | SK-02 |
| `WikiContributeTool` | `llmwiki-skill-wiki-contribute` | SK-03 |
| `ArtifactResolutionTool` | `llmwiki-skill-artifact-resolution` | SK-04 |
| `GapDetectionTool` | `llmwiki-skill-gap-detection` | SK-05 |

## Sly Data security

The `sly_data` dict carries sensitive fields that must never enter the LLM context:
```python
sly_data = {
    "customer_id":    "bcbs-mn-001",          # customer identifier
    "llmwiki_api_key": "sk-...",               # LLMWiki API key
    "engagement_id":  "SOW-2026-BCBS-MN-001", # engagement reference
}
```

These are injected by AgentCore at session start and flow through every tool call
without ever appearing in the LLM's prompt or intermediate reasoning.

## Environment variables

All Lambda function names are configurable:

```bash
SK01_FUNCTION=llmwiki-skill-context-bootstrap
SK02_FUNCTION=llmwiki-skill-wiki-query
SK03_FUNCTION=llmwiki-skill-wiki-contribute
SK04_FUNCTION=llmwiki-skill-artifact-resolution
SK05_FUNCTION=llmwiki-skill-gap-detection
AWS_DEFAULT_REGION=us-east-1
```

## Running locally with Neuro SAN

```bash
# From the repo root — put lambda/common/ on PYTHONPATH so llmwiki_common is found
export PYTHONPATH=/path/to/llmwiki/code/lambda/common:$PYTHONPATH

# Then run Neuro SAN with the LLMWiki registry
ns run code/registries/llmwiki/manifest.hocon

# nsflow UI at localhost:4173
# Chat: "Run UC1 for customer bcbs-mn-001"
```

## Running in Docker (ECS)

The Dockerfile copies `lambda/common/` to `/app/lambda_common/` and sets
`ENV PYTHONPATH=/app/lambda_common` — no runtime setup needed.

## HITL safety

The `WikiContributeTool` hardcodes human-review routing for `decisions` and `evidence`
page types. This runs in Python before the Lambda call — no LLM instruction can bypass it.

---

## Why the Hard Harness is faster than Neuro SAN

Both paths call the same Lambda skills. The speed difference is entirely in how many
LLM (Bedrock) round-trips are needed before each skill gets called.

### Hard Harness — 3–4 LLM calls total

Python code is the orchestrator. It decides what to call next with no LLM involved.

```
Phase 1  → Lambda only (no LLM)         ~200 ms
Phase 2  → 1 Bedrock call               ~2 s
Phase 3  → wait for human input
Phase 4  → Lambda only (no LLM)         ~800 ms
Phase 5  → 1 Bedrock call               ~3 s
Phase 6  → Lambda only (no LLM)         ~500 ms
Phase 7  → 1 Bedrock call               ~2 s
Phase 8  → Lambda only (no LLM)         ~300 ms
──────────────────────────────────────────────
Total LLM calls: 3      Elapsed: ~9 s (excl. human pause)
```

Python `if/else` decides the sequence. No LLM is needed to figure out what comes next.

### Neuro SAN — 20–30 LLM calls total (AAOSA protocol)

The FrontMan LLM orchestrates sub-agents using the AAOSA
Determine → Fulfill → Follow-up → Compile protocol. Every step requires
multiple Bedrock round-trips:

```
For EACH tool the FrontMan invokes, AAOSA runs 4–5 rounds:

  Round 1  FrontMan → sub-agent: "Can you handle this?" (Determine)   ~2 s
  Round 2  Sub-agent → FrontMan: "Yes, strength=9" (Determine reply)  ~2 s
  Round 3  FrontMan → sub-agent: "Then fulfill it" (Fulfill)          ~2 s
  Round 4  Sub-agent executes → calls Lambda → returns result          ~1 s
  Round 5  FrontMan compiles response                                  ~2 s

With 6 tools (ProblemClassifier + SK-01 to SK-05):
  6 tools × ~4 AAOSA rounds × ~2 s per Bedrock call ≈ 48 s of LLM time
  Plus Lambda latency on top of that.
──────────────────────────────────────────────────────────────────────
Total LLM calls: ~24       Elapsed: ~60–120 s
```

Every "what should I do next" decision is a Bedrock round-trip. The FrontMan
cannot skip the negotiation — AAOSA is the protocol that makes the network
self-organising and business-analyst editable.

### The tradeoff

| | Hard Harness | Neuro SAN |
|---|---|---|
| **Speed** | Fast — Python decides, no negotiation | Slow — LLM negotiates every step |
| **Flexibility** | Fixed — change requires code + redeploy (~30 min) | Fluid — edit HOCON text, live in ~8 s |
| **Who orchestrates** | Python `if/else` | Claude reading plain-English instructions |
| **LLM calls** | 3–4 total | 20–30 total |
| **Best for** | Production SLA-bound workflows | Demos, rapid iteration, business-analyst tuning |

The Hard Harness trades adaptability for speed.
Neuro SAN trades speed for the ability to change orchestration logic without touching code —
which is exactly what the **Live Demo Toggle** tab demonstrates.

### Magnitude of slowness — observed end-to-end

**Hard Harness: ~45–90 seconds** (excluding the Phase 3 human pause)

```
3 Bedrock calls  × ~4 s each  =  ~12 s  LLM time
5 Lambda calls   × ~3 s each  =  ~15 s  skill time
DynamoDB + S3 overhead        =   ~5 s
─────────────────────────────────────────────────
Total                         ~  60 s
```

**Neuro SAN: ~5–10 minutes**

```
6 tools × 4–5 AAOSA rounds = ~24–30 Bedrock calls
24 Bedrock calls × ~4 s each =  ~96–150 s  LLM time
Same 5 Lambda calls          =    ~15 s    skill time
FrontMan compilation rounds  =    ~20 s
─────────────────────────────────────────────────
Total                         ~  420 s  (6–8 min)
```

**Rough multiplier: 5–8× slower than the Hard Harness.**

```
Hard Harness  ~60 s    ████
Neuro SAN    ~420 s    ████████████████████████████████
```

The slowness is not network or Lambda latency — it is purely the **AAOSA negotiation
tax**. A single Hard Harness `if skill == "SK-01": call_lambda()` (microseconds)
becomes 4–5 Bedrock conversations in Neuro SAN before the same Lambda fires.

The 600-second WebSocket timeout in the Streamlit UI (`_AgentSession.recv_stream`)
exists specifically to accommodate this — a complete UC1 or UC-PM Neuro SAN run
reliably lands at 6–8 minutes end-to-end.

---

## "Lambdas" and "Agent Core" — what they actually are

### Lambdas = AWS Lambda functions (real AWS compute)

Every coded tool is a thin boto3 wrapper that invokes an actual AWS Lambda function
in the LLMWiki account. Neuro SAN never implements business logic directly — it
delegates to the same Lambda layer that the Hard Harness uses.

| Coded Tool | AWS Lambda function | Skill |
|---|---|---|
| `ContextBootstrapTool` | `llmwiki-skill-context-bootstrap` | SK-01 |
| `WikiQueryTool` | `llmwiki-skill-wiki-query` | SK-02 |
| `WikiContributeTool` | `llmwiki-skill-wiki-contribute` | SK-03 |
| `ArtifactResolutionTool` | `llmwiki-skill-artifact-resolution` | SK-04 |
| `GapDetectionTool` | `llmwiki-skill-gap-detection` | SK-05 |
| `ProblemClassifierTool` | `llmwiki-skill-problem-classifier` | SK-06 |

The Lambda functions are where the actual work happens — Bedrock calls, DynamoDB reads,
S3 writes, SNS alerts. The coded tools contain nothing except a `boto3.invoke()` call
and a result unwrap.

### Agent Core = Neuro SAN's own execution engine (not an AWS service)

There is no separate "AgentCore" service deployed in AWS. The term refers to the
neuro-san library's internal execution stack running inside the ECS sidecar container.
The layers from user message to AWS Lambda call:

```
User types in Streamlit chat
        │
        ▼
_AgentSession (Streamlit)         — holds the WebSocket open across turns
        │  WebSocket JSON
        ▼
neuro-san-server (port 8080)      — receives message, routes to network by name
        │
        ▼
FrontManActivation                — reads HOCON instructions, drives AAOSA rounds
        │  LangChain ainvoke()
        ▼
LangChainRunContext               — builds Claude chain from instructions + tool schemas,
        │                           calls Bedrock, receives tool-call decision
        ▼
ClassActivation                   — importlib loads the coded tool named in "class"
        │
        ▼
YourCodedTool.async_invoke()      — boto3 → AWS Lambda → result returned to Claude
```

### How both paths fit in the overall solution

Both the Hard Harness and Neuro SAN call **the exact same Lambda functions**.
The only difference is who orchestrates the sequence of calls.

```
┌──────────────────────────────────────────────────────────────┐
│  LLMWiki Platform                                            │
│                                                              │
│  Hard Harness path (Python orchestrator):                    │
│  Streamlit → llmwiki-uc1-harness Lambda                      │
│              └─ Python code calls SK-01…SK-05 in fixed order │
│              └─ flow is hardcoded, auditable, production-safe │
│                                                              │
│  Neuro SAN path (NLP orchestrator):                          │
│  Streamlit → neuro-san-server (ECS sidecar)                  │
│              └─ Claude reads HOCON instructions              │
│              └─ Claude decides which skill to call and when  │
│              └─ coded tools call the same SK-01…SK-05        │
│                                                              │
│  Same Lambda skills. Different orchestrator.                 │
│  Hard Harness: change Python → PR → CI/CD → 30 min          │
│  Neuro SAN:    edit HOCON text → S3 → live in ~8 seconds     │
└──────────────────────────────────────────────────────────────┘
```

---

## How NLP instructions become Python execution

This is the full translation pipeline — from the plain-English text you write in a HOCON
file to an actual Lambda call or Python method execution.

### Layer 1 — HOCON → Python dict (pyhocon)

`pyhocon` reads the `.hocon` file. Every `"instructions"`, `"function.description"`,
`"class"`, and `"tools"` key becomes a plain Python dictionary. No magic yet.

### Layer 2 — `ActivationFactory` routes each agent to the right type

`neuro_san/internals/graph/registry/activation_factory.py` → `create_agent_activation()`
reads each tool spec dict and decides:

```
Has "class" key?         → ClassActivation      your ProblemClassifierTool, WikiQueryTool, etc.
Has "function" + tools?  → BranchActivation     sub-agents doing AAOSA Determine/Fulfill
Is the first agent?      → FrontManActivation   UCPMProblemManagementAgent, UC1SalesToServiceAgent
Has "toolbox"?           → ToolboxActivation    MCP servers
Has http:// URL?         → ExternalActivation   remote agents
```

### Layer 3 — `LangChainRunContext.create_resources()` builds the LLM chain

`neuro_san/internals/run_context/langchain/core/langchain_run_context.py`

```python
# Your "instructions" block becomes the system prompt sent to Claude
SystemMessage(content=agent_spec["instructions"])

# Each entry in "tools" becomes a LangChain BaseTool
for tool_name in agent_spec["tools"]:
    tool = LangChainOpenAIFunctionTool(
        name        = tool_name,
        description = tool_spec["function"]["description"],  # what Claude reads to decide
        args_schema = <pydantic model from "parameters">
    )

# LangChain wires: LLM + tools + system_prompt → a runnable chain
create_agent(model=bedrock_claude, tools=[...], system_prompt=instructions)
```

**Your plain-English `instructions` IS the system prompt.**
**Your `function.description` IS the tool menu Claude reads to decide what to call next.**
Nothing more. There is no NLP-to-code compiler.

### Layer 4 — `LangChainOpenAIFunctionTool._arun()` bridges LLM decision → Python

When Claude decides "I want to call ProblemClassifier", LangChain calls `_arun()`:

```python
async def _arun(self, **kwargs):
    # kwargs = the JSON args Claude generated (problem_id, product, severity ...)
    args = PydanticArgumentDictionaryConverter.convert(kwargs)

    # Fires the next agent's activation (another Claude call or a CodedTool)
    result = await self.tool_caller.make_one_tool_function_call(self.invocation, args)
    return result   # Claude receives this as the tool result and continues reasoning
```

For a **coded tool** (`ClassActivation`), `make_one_tool_function_call` does:

```python
# Dynamically imports the class named in the HOCON "class" field
module = importlib.import_module("coded_tools.llmwiki.problem_classifier_tool")
klass  = getattr(module, "ProblemClassifierTool")
tool   = klass()

# Calls YOUR async_invoke() — this is where boto3 / Lambda is called
result = await tool.async_invoke(args, sly_data)
```

### Complete round-trip for one AAOSA turn

```
User: "Run RCA for PRB0042 on QNXT Batch Processing P2"
    │
    ▼
FrontManActivation.submit_message()
    │  instructions → SystemMessage to Claude (Bedrock)
    │  tools list   → LangChain tool schemas Claude can call
    ▼
Claude reads NLP instructions, decides:
    "STEP 1 — call ProblemClassifier first"
    │
    ▼
LangChainOpenAIFunctionTool._arun(problem_id="PRB0042", product="QNXT", ...)
    │
    ▼
ClassActivation → importlib loads ProblemClassifierTool
    │
    ▼
ProblemClassifierTool.async_invoke(args, sly_data)
    │  boto3 invokes llmwiki-skill-problem-classifier Lambda
    ▼
Returns: {normalized_category: "Batch Processing", risk_tier: "medium", ...}
    │
    ▼
Claude receives tool result, reads NLP instructions again:
    "STEP 2 — ask SME questions..."
    → sends HUMAN-type message back to user (waiting_for_human = True)
```

### Key source files (in `neuro_san-0.6.74-py3-none-any.whl`)

| File | Role |
|------|------|
| `internals/graph/registry/activation_factory.py` | Routes HOCON spec → correct Activation type |
| `internals/graph/activations/front_man_activation.py` | Root agent — submits user message, drives the turn loop |
| `internals/graph/activations/calling_activation.py` | Base for all LLM-calling agents; owns `make_tool_function_calls` |
| `internals/graph/activations/class_activation.py` | Resolves `"class"` key → dynamically imports your CodedTool |
| `internals/run_context/langchain/core/langchain_run_context.py` | Builds the LangChain chain from instructions + tools; calls Bedrock |
| `internals/run_context/langchain/core/langchain_openai_function_tool.py` | The bridge: LLM tool-call decision → Python `_arun()` |
