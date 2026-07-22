# LLMWiki Execution Architectures — Harness vs Neuro-SAN / HOCON

> LLMWiki supports two fundamentally different ways to run an agent use case.
> Both call the same skill Lambdas and write to the same data stores.
> The difference is entirely in how orchestration is managed.

---

## Part 1 — The Lambda Harness Architecture

### What it is

A **Lambda Harness** is a single AWS Lambda function that runs a use case as a
deterministic, numbered workflow. Python code decides what to call, in what order,
and what to do with each result. There is no LLM involved in the orchestration
decisions — the LLM is only invoked directly for specific reasoning tasks
(classification, drafting, summarisation) within individual phases.

Think of it as a **conductor reading a fixed score** — every note is written down
in advance and played in order.

### Physical structure

```
code/
└── lambda/
    └── harness/
        └── {use_case}_harness/
            └── handler.py     ← one file owns the entire workflow
```

Each `handler.py` is a self-contained orchestrator. It does not share code with
any Neuro-SAN component.

### Runtime layout

```
┌──────────────────────────────────────────────────────────────────────┐
│                           AWS Cloud                                  │
│                                                                      │
│   Caller (UI / API / EventBridge)                                    │
│       │                                                              │
│       ▼                                                              │
│   Harness Lambda  (handler.py)                                       │
│       │                                                              │
│       ├── boto3.lambda_client.invoke() ──► Skill Lambda A            │
│       ├── boto3.lambda_client.invoke() ──► Skill Lambda B            │
│       ├── boto3.lambda_client.invoke() ──► Skill Lambda C            │
│       ├── bedrock.converse()           ──► Claude (direct)           │
│       ├── dynamodb.Table.put/update    ──► Run state table           │
│       ├── dynamodb.Table.put_item      ──► Audit log table           │
│       └── s3.put_object               ──► Output bucket             │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### How a run works — two HTTP calls

Every harness use case completes in exactly two HTTP calls:

**Call 1 — Fresh start**
The caller sends the input data. The harness runs the early phases (data loading,
classification, question generation), then **pauses at a hardcoded point** and
returns questions or a prompt for the human to answer. Nothing is written to the
knowledge base yet.

**Call 2 — Resume**
The caller sends the same identifiers plus the human's answers. The harness restores
prior phase results from DynamoDB, runs the remaining phases (knowledge retrieval,
reasoning, drafting, writing), and returns a completion summary with output URLs.

```
CALL 1  ──────────────────────────────────────────────────────────────
  Phase 1 │ Load / validate input data          Python only
  Phase 2 │ Classify the request                Skill Lambda
  Phase 3 │ Generate questions for the human    Direct Bedrock call
           │
           └── PAUSE  →  return questions to caller
                         set status = "paused" in DynamoDB
                         ↕  Human reads and answers  ↕

CALL 2  ──────────────────────────────────────────────────────────────
  Phase 4 │ Load prior knowledge from wiki      Skill Lambda
  Phase 5 │ Reason / draft / analyse            Direct Bedrock call
  Phase 6 │ Detect knowledge gaps               Skill Lambda
  Phase 7 │ Populate output template            Direct Bedrock call
  Phase 8 │ Write outputs + generate report     S3 puts, presigned URLs
           │
           └── COMPLETE  →  return summary + download URLs
                             set status = "completed" in DynamoDB
```

The number of phases and their content varies per use case. The two-call
pause-and-resume pattern is consistent across all harness implementations.

### State management

All run state lives in a DynamoDB table. After every phase, the harness writes the
phase result into a JSON blob in the run record. This gives the workflow durability
across Lambda invocations and allows the caller to poll progress at any time.

```
DynamoDB run record
  ├── run_id          Composite identifier (unique per run)
  ├── status          "running" | "paused" | "completed" | "error"
  ├── current_phase   1..N
  ├── phases_completed [1, 2, 3, ...]
  ├── phase_results   { "1": {...}, "2": {...}, ... }   ← JSON blob
  ├── created_at      ISO timestamp
  └── expires_at      TTL (30 days)
```

If the Lambda times out after Phase 4, Phases 1–4 are already persisted.
The run can be resumed or debugged by inspecting `phase_results` directly.

### Direct Bedrock calls

Certain phases call Bedrock directly using `bedrock.converse()` — bypassing any
skill Lambda. These phases build their own prompts inline in the handler, call
Claude, and parse the JSON response. The prompt text lives inside the Python function.

```python
# Generic pattern for a direct Bedrock call inside a harness phase
resp = bedrock.converse(
    modelId=MODEL_ID,
    messages=[{"role": "user", "content": [{"text": prompt}]}],
    inferenceConfig={"maxTokens": N},
)
raw = resp["output"]["message"]["content"][0]["text"]
# parse, validate, return structured dict
```

Changing what Claude is asked means editing `handler.py` and redeploying the Lambda.

### Output artifacts

Phase 8 always writes structured output to S3 and records an audit entry in DynamoDB.
Typical outputs per run:

```
S3 bucket (output bucket)
  drafts/{id}/document.json         ← structured output (JSON)
  reports/{run_id}-report.html      ← formatted HTML report
  sessions/{batch}/{date}-handoff.md ← human-readable summary

DynamoDB audit log table
  log_date:   "session#{harness_name}#{date}"
  Content:    phases_completed, outcome, artifacts, handoff notes
  TTL:        90 days
```

All outputs are marked **DRAFT** until a human reviews and promotes them.
Nothing written by the harness goes directly to the live knowledge base.

### Error handling

Each phase is wrapped in try/except. If a phase throws:
- The run record is set to `status = "error"` with the error message
- The audit log still fires (in the `finally` block) so the record is complete
- The caller receives HTTP 500 with the run_id and failing phase number

Skill Lambda failures default to a safe fallback dict so the run can continue,
rather than aborting on every transient error.

---

## Part 2 — The Neuro-SAN / HOCON Architecture

### What it is

The **HOCON path** uses Neuro-SAN, an agent orchestration framework where
orchestration logic is written in plain English inside a `.hocon` configuration file.
There is no Python orchestration code. The **LLM itself** reads the English
instructions at runtime and decides which tool to call next, in what order,
and with what arguments.

Think of it as a **jazz ensemble following a lead sheet** — the chord structure
is defined, but the players improvise within it based on what they hear.

### Physical structure

```
code/
├── registries/
│   └── llmwiki/
│       ├── manifest.hocon          ← which networks to serve
│       └── {use_case}.hocon        ← agent network definition
│
└── neuro_san/
    └── coded_tools/
        └── llmwiki/
            ├── llmwiki_base_tool.py  ← shared Lambda invocation base class
            ├── {skill_a}_tool.py     ← thin wrapper around Skill Lambda A
            ├── {skill_b}_tool.py     ← thin wrapper around Skill Lambda B
            └── ...
```

### Runtime layout

```
┌──────────────────────────────────────────────────────────────────────┐
│              Local machine or ECS container                          │
│                                                                      │
│   ns run registries/llmwiki/manifest.hocon                          │
│       │                                                              │
│       ▼                                                              │
│   Neuro-SAN runtime                                                  │
│       │                                                              │
│       ▼                                                              │
│   FrontMan Agent  (LLM reading HOCON instructions)                   │
│       │                                                              │
│       │  LLM decides call sequence at runtime                       │
│       │                                                              │
│       ├── ToolA  →  tool_a_tool.py  →  Skill Lambda A               │
│       ├── ToolB  →  tool_b_tool.py  →  Skill Lambda B               │
│       ├── ToolC  →  tool_c_tool.py  →  Skill Lambda C               │
│       └── ...                                                        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### The three-layer call chain

Every tool invocation in the HOCON path traverses three distinct layers:

```
Layer 1 — HOCON  (binds a tool name to a Python class)
  "name":  "SomeTool"
  "class": "coded_tools.llmwiki.some_tool.SomeTool"
                 ↓  Neuro-SAN imports the class at startup

Layer 2 — Python CodedTool  (thin wrapper, one per skill)
  SomeTool.async_invoke(args, sly_data)
  • Reads named fields from args (what the LLM passed)
  • Pulls sensitive fields from sly_data (never from LLM args)
  • Builds the skill payload dict
  • Calls LLMWikiBaseTool._invoke_skill(lambda_name, payload)
                 ↓

Layer 3 — LLMWikiBaseTool  (shared invocation base)
  boto3.lambda_client.invoke(
      FunctionName="llmwiki-skill-{name}",
      InvocationType="RequestResponse",
      Payload=json.dumps(payload)
  )
                 ↓

AWS Lambda (skill backend — same Lambda the harness uses)
```

The HOCON `"class"` field is the only binding between HOCON and Python.
The tool `"name"` is only used by the LLM in its reasoning — it has no
effect on which Python class is loaded.

### Sly data — the protected side channel

Neuro-SAN carries sensitive fields outside the LLM context window via `sly_data`.
These fields are set at session start and injected into every coded tool
automatically — the LLM never sees them and cannot manipulate them.

```python
sly_data = {
    "customer_id":     "...",   # injected at session boundary, never in LLM prompt
    "llmwiki_api_key": "...",   # injected at session boundary, never in LLM prompt
    "engagement_id":   "..."    # injected at session boundary, never in LLM prompt
}
```

Every `async_invoke()` pulls these via:
```python
ctx = self._extract_sly(sly_data)
customer_id = ctx["customer_id"] or args.get("customer_id", "")
```

If the LLM tries to pass a customer_id in `args`, the `sly_data` version wins.
This prevents prompt injection attacks from substituting a different entity's
context into the session.

### How the FrontMan orchestrates

The HOCON `instructions:` block is an English-language numbered guide.
The LLM follows it as it processes the conversation. Example structure:

```
STEP 1  Always call {ClassificationTool} FIRST.
        Use the returned category and risk tier in all subsequent steps.

STEP 2  Ask the user N targeted questions based on the classification.
        Wait for answers before continuing.      ← human pause, LLM-driven

STEP 3  Call {ContextTool} to load prior knowledge.

STEP 4  Call {QueryTool} to search the knowledge base.
        IF confidence = low or medium → call {GapTool}.
        IF GapTool returns blocking=true → STOP.

STEP 5  Compose the output document (LLM reasoning — no tool call).

STEP 6  Call {TemplateTool} to populate the standard template.

STEP 7  Call {WriteTool} to save the draft to the knowledge base.
```

The sequence is advisory — the LLM reads and follows it, but can ask follow-up
questions, handle unexpected results, or adapt phrasing between turns in a way
hardcoded Python never could.

### The AAOSA internal loop

The AAOSA protocol (loaded via `include "registries/aaosa.hocon"`) adds a
four-phase internal reasoning loop that runs silently before each visible action:

```
D — Determine:   Which tools can contribute to this step?
F — Fulfill:     Call them. Collect their outputs.
F — Follow-up:   Does any output need clarification?
C — Compile:     Synthesise all outputs into a coherent response.
```

This loop is invisible to the user — it is the structure the LLM uses to think
before each turn.

### HITL safety

The `WikiContributeTool` enforces human review for sensitive page types at two
independent layers — neither can be bypassed by any LLM instruction or argument:

```
Layer A — Python tool
  human_review_required = page_type in {"decisions", "evidence"}
  This flag is set in Python BEFORE the Lambda call.

Layer B — Skill Lambda
  Routes to wiki/pending/{page_type}/ regardless of any payload value.
  S3 prefix is hardcoded — not configurable.
```

No prompt injection, no argument manipulation, no instruction can change this.

---

## Part 3 — Side-by-Side Comparison

### The conceptual difference in one sentence

> **Harness:** Python tells the LLM what to think about, phase by phase.
> **HOCON:** English instructions tell the LLM what to do, and it figures out the rest.

---

### Architecture

| Dimension | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Orchestration written in** | Python | Plain English in HOCON |
| **Who decides call sequence** | Python code | The LLM at runtime |
| **Sequence flexibility** | Fixed — always the same numbered phases | Adaptive — LLM responds to intermediate results |
| **New use case requires** | New Python Lambda + deploy | New HOCON file (+ coded tools only if new skills needed) |
| **Changing orchestration logic** | Python edit + Lambda redeploy | Edit HOCON text, restart `ns run` |
| **Skill required to author** | Python + boto3 + DynamoDB | English writing + HOCON syntax |
| **Infrastructure** | Serverless — no always-on process | Requires a running container or process |

---

### Control flow

| Aspect | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Execution model** | Deterministic numbered phases | Conversational multi-turn loop |
| **Human pause point** | Hardcoded — always between phase N and N+1 | Defined in English instructions — LLM-driven |
| **Pause mechanism** | HTTP response `status="paused"` | LLM message asking user for input |
| **Resume trigger** | Re-POST with same ID + human answers | User types reply in chat |
| **Can LLM skip a step?** | No — Python always calls next phase | Yes — if LLM misinterprets instructions |
| **Can LLM add an unplanned step?** | No | Yes — LLM may ask a follow-up question freely |

---

### State and persistence

| Aspect | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Workflow state stored in** | DynamoDB (persistent, queryable) | Neuro-SAN in-process session (ephemeral) |
| **Survives process restart?** | Yes | No |
| **Cross-session resume** | Yes — same run_id across days | No — new session = new conversation |
| **Phase-level granularity** | Yes — each phase result stored separately | No — single conversation thread |
| **Progress polling** | Yes — `action=get_status` at any time | No — must watch the conversation |
| **Audit trail** | Always written — DynamoDB log table | OTel spans only (optional, requires setup) |

---

### LLM usage pattern

| Aspect | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **LLM role** | Reasoner for specific phases only | Full orchestrator + reasoner |
| **LLM call type** | `bedrock.converse()` — direct Python call | Neuro-SAN manages the LLM session |
| **Prompt ownership** | Hardcoded in Python phase functions | Written in HOCON `instructions:` |
| **Changing a prompt** | Edit Python, redeploy Lambda | Edit HOCON, restart process |
| **Number of LLM calls per run** | Fixed — one per reasoning phase | Variable — depends on conversation length |
| **Cost predictability** | High — fixed calls per run | Medium — varies with conversation turns |

---

### Skills and Lambda coverage

The harness calls a subset of skill Lambdas and handles some reasoning
directly via Bedrock. The HOCON path delegates all reasoning to the LLM and
uses the full skill set.

| Skill Lambda | Typical Harness usage | Typical HOCON usage |
|---|---|---|
| SK-01 context-bootstrap | Called as a phase | Called as a tool step |
| SK-02 wiki-query | Often replaced by direct Bedrock call | Called as a tool step (with conditional gap branch) |
| SK-03 wiki-contribute | Often replaced by direct S3 write | Called as final tool step |
| SK-04 artifact-resolution | Often replaced by direct Bedrock call | Called as a tool step |
| SK-05 gap-detection | Called as a phase | Called conditionally based on SK-02 confidence |
| SK-06 problem-classifier | Called as a phase | Called as first tool step |

---

### Outputs and artifacts

| Output type | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Primary knowledge artifact** | Structured JSON in S3 `drafts/` prefix | Markdown in S3 `wiki/pending/` prefix |
| **HTML report** | Generated in final phase | Not generated |
| **Session handoff summary** | Markdown file written to S3 | Not generated |
| **Presigned download URLs** | Returned in HTTP response | Not returned |
| **Knowledge gap records** | Written by SK-05 Lambda | Written by SK-05 Lambda (same) |
| **Format bias** | Structured, machine-readable | Prose, human-readable |

---

### Error and failure behaviour

| Scenario | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Skill Lambda unavailable** | Phase uses fallback dict, execution continues | LLM receives error, may retry or adapt |
| **LLM returns bad JSON** | Regex fallback + default dict | Neuro-SAN may retry the tool call |
| **Run fails mid-way** | DynamoDB record set to `status="error"`, audit log written | Session lost unless OTel was configured |
| **Blocking knowledge gap** | Phase result carries `gaps_blocking=true`, final status set | LLM stops and informs user which gap must be filled |
| **Missing required input** | HTTP 400 returned before any phase runs | LLM infers from context or asks user |
| **Observability** | DynamoDB phase_results + log table (always) | OTel spans (optional) + nsflow UI |

---

### Development and operational tradeoffs

| Tradeoff | Lambda Harness | Neuro-SAN / HOCON |
|---|---|---|
| **Predictability** | High — identical path every run | Medium — LLM may vary phrasing or call order |
| **Testability** | High — each phase is a pure Python function | Medium — requires conversation-level testing |
| **Debugging** | High — inspect DynamoDB phase_results | Moderate — requires OTel or nsflow traces |
| **Iteration speed on logic** | Low — Python edit + Lambda redeploy cycle | High — edit HOCON text, restart process |
| **Conversation quality** | Low — two fixed calls, no natural dialogue | High — multi-turn, LLM asks follow-up questions |
| **Long-running workflows** | Excellent — DynamoDB survives days between calls | Poor — session state is in-memory |
| **Enterprise audit** | Excellent — every phase logged permanently | Basic — only what OTel captures |
| **Cost control** | Predictable — fixed LLM calls per run | Variable — depends on conversation depth |

---

### When to use which path

**Use the Lambda Harness when:**
- The workflow steps are contractually or regulatorily fixed
- You need a durable audit trail and cross-session resume capability
- The output must include a structured report (HTML, PDF, JSON)
- The use case is batch-oriented — triggered by an event, not a conversation
- You need predictable cost per run
- Multiple teams need to inspect or replay any individual phase result

**Use the Neuro-SAN / HOCON path when:**
- The use case is conversational — user and agent exchange information naturally
- Orchestration logic will change frequently and fast iteration matters
- The LLM needs freedom to adapt to unexpected intermediate results
- You want to compose a new use case without writing Python
- You are prototyping — the exact step sequence is not yet settled
- Multiple use cases share the same skill set and you want to avoid duplicating Python code

---

## The Shared Foundation — Skill Lambdas

Both paths converge on the same set of skill Lambdas. This is the key
architectural principle: the skills are independently deployable and testable,
and either orchestration layer can call them without modification.

```
                     ┌──────────────────────────────────┐
                     │         Skill Lambdas            │
                     │   SK-01 context-bootstrap        │
                     │   SK-02 wiki-query               │
                     │   SK-03 wiki-contribute          │
                     │   SK-04 artifact-resolution      │
                     │   SK-05 gap-detection            │
                     │   SK-06 problem-classifier       │
                     └────────────┬─────────────────────┘
                                  │  same Lambdas, same payloads
               ┌──────────────────┴──────────────────┐
               │                                     │
┌──────────────▼────────────────┐  ┌─────────────────▼─────────────────┐
│      Lambda Harness            │  │     Neuro-SAN / HOCON             │
│  handler.py                    │  │  FrontMan + CodedTools            │
│  Fixed numbered phases         │  │  LLM-driven sequence             │
│  DynamoDB run state            │  │  In-process session state        │
│  Direct Bedrock calls          │  │  LLM is the reasoner             │
│  HTML reports + presigned URLs │  │  Markdown wiki pages only        │
└────────────────────────────────┘  └───────────────────────────────────┘
```

Improving a skill Lambda (e.g. better retrieval in wiki-query, smarter gap
classification) benefits both paths immediately. Neither orchestration layer
needs to change.

---

## The Change Impact Matrix

A quick reference for where a given type of change must be made:

```
What you change                     Harness  CodedTool  HOCON  Lambda
──────────────────────────────────  ───────  ─────────  ─────  ──────
Phase/step sequence                 ✏️        –          –      –
Phase prompt text                   ✏️        –          –      –
HOCON step instructions             –         –         ✏️      –
HOCON parameter schema              –        ✏️         ✏️      maybe
Add a new tool (HOCON side)         –        ✏️(new)    ✏️      maybe
Skill Lambda payload field          –        ✏️         –      ✏️
Skill Lambda response field         ✏️        ✏️         –      ✏️
S3 output path / bucket             ✏️        –          –      maybe
HITL page routing rules             –        ✏️         –      ✏️
Sly data fields                     –        ✏️         –      ✏️
```

---

*Source files:*
*`code/lambda/harness/` · `code/registries/llmwiki/` · `code/neuro_san/coded_tools/llmwiki/`*
*Last updated 2026-07-22*
