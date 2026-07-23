# PM Problem Management — Neuro-SAN / HOCON Path: Full Technical Architecture & Flow

> **Use case:** Problem Management RCA — AAOSA orchestration path
> **HOCON definition:** `code/registries/llmwiki/uc_pm_problem_management.hocon`
> **Manifest:** `code/registries/llmwiki/manifest.hocon`
> **Coded tools:** `code/neuro_san/coded_tools/llmwiki/`
> **Base tool (shared):** `code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py`
> **Alternative path (no Neuro-SAN):** `code/pm-harness-technical-flow.md`

---

## What Neuro-SAN Is

Neuro-SAN is an agent orchestration framework. Instead of writing Python to decide
which skill to call next, you write plain English instructions in a `.hocon` file.
The LLM reads those instructions and decides the call sequence at runtime.

The `uc_pm_problem_management.hocon` file defines:
- One **FrontMan** agent (`UCPMProblemManagementAgent`) that receives the user's request
- Six **sub-agents** (called "tools" in HOCON) that the FrontMan can delegate to
- The **AAOSA protocol** — a structured Determine → Fulfill → Follow-up → Compile loop

The FrontMan never calls AWS directly. Everything goes through its sub-agents.

---

## System Overview

```
User / nsflow UI / API
        │
        │  Natural language message:
        │  "Run RCA for PRB0042, product QNXT, component Batch Processing, severity P2"
        ▼
Neuro-SAN runtime (ns run registries/llmwiki/manifest.hocon)
        │
        ▼
UCPMProblemManagementAgent  ← FrontMan (HOCON instructions, no Python)
        │
        │  LLM reads instructions, follows STEP 1..STEP 7 sequence
        │
        ├── ProblemClassifierTool    →  problem_classifier_tool.py  →  Lambda SK-06
        ├── ContextBootstrapTool     →  context_bootstrap_tool.py   →  Lambda SK-01
        ├── WikiQueryTool            →  wiki_query_tool.py           →  Lambda SK-02
        ├── GapDetectionTool         →  gap_detection_tool.py        →  Lambda SK-05
        ├── ArtifactResolutionTool   →  artifact_resolution_tool.py  →  Lambda SK-04
        └── WikiContributeTool       →  wiki_contribute_tool.py      →  Lambda SK-03
```

---

## The Three-Layer Architecture

Every call from FrontMan to a sub-agent traverses three layers:

```
Layer 1: HOCON (agent definition)
  "class": "coded_tools.llmwiki.wiki_query_tool.WikiQueryTool"
         ↓
Layer 2: Python CodedTool (thin wrapper)
  wiki_query_tool.py :: WikiQueryTool.async_invoke(args, sly_data)
  Reads args, builds payload, calls LLMWikiBaseTool._invoke_skill()
         ↓
Layer 3: LLMWikiBaseTool._invoke_skill()
  boto3.lambda_client.invoke(FunctionName="llmwiki-skill-wiki-query", ...)
         ↓
AWS Lambda (skill backend, independent of Neuro-SAN)
```

The HOCON binds to Python via the `"class"` field only. The tool name
(`"name": "WikiQuery"`) is only used by the LLM when composing its response —
it has no runtime effect on which Python class is loaded.

---

## Sly Data — Security Channel

Neuro-SAN carries sensitive fields in a separate channel called **sly_data**.
These fields never appear in the LLM context window — they are injected at
the session boundary and forwarded to each coded tool automatically.

```
sly_data = {
    "customer_id":    "QNXT-PRB0042-batch",  ← never seen by the LLM
    "llmwiki_api_key": "...",                  ← never seen by the LLM
    "engagement_id":   "BATCH-001"             ← never seen by the LLM
}
```

Every `async_invoke(args, sly_data)` begins with:
```python
ctx = self._extract_sly(sly_data)
customer_id = ctx["customer_id"] or args.get("customer_id", "")
```

This means the LLM never needs to pass `customer_id` or `api_key` — they arrive
through the protected side channel. If the LLM does pass them in `args`, the code
prefers the `sly_data` version.

---

## HOCON Execution Flow — Step by Step

The FrontMan's `instructions:` block defines a 7-step sequence. The LLM follows
these steps as it processes the conversation. Unlike the harness, **the LLM decides
the pace and can ask follow-up questions between steps**.

### STEP 1 — ProblemClassifier (always first)

```
FrontMan reads HOCON instructions: "Always call ProblemClassifier FIRST."

FrontMan calls ProblemClassifier with named fields:
  problem_id      = "PRB0042"
  product         = "QNXT"
  component       = "Batch Processing"
  severity        = "P2"
  problem_summary = (extracted from user message)
         ↓
ProblemClassifierTool.async_invoke(args, sly_data)
  │
  ├─ _extract_sly(sly_data) → customer_id, api_key, engagement_id
  ├─ Falls back on inquiry string if problem_id or product not found as named fields
  │    (regex scan for PRB/INC patterns, product name scan)
  ├─ Builds payload:
  │    {
  │      "skill":      "ProblemClassifierSkill",
  │      "version":    "1.0",
  │      "invoked_by": "pm-neuro-san-agent",
  │      "inputs": {
  │        "problem_id":      "PRB0042",
  │        "product":         "QNXT",
  │        "component":       "Batch Processing",
  │        "severity":        "P2",
  │        "problem_summary": "...",
  │        "related_records": [],
  │        "ingest_batch_id": "BATCH-001"
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-problem-classifier", payload
       )
           │
           └──► boto3.lambda_client.invoke(
                    FunctionName="llmwiki-skill-problem-classifier",
                    InvocationType="RequestResponse"
                )
                │
                └──► Lambda: llmwiki-skill-problem-classifier
                         Returns: {
                           normalized_category:       "Batch Processing",
                           recurrence_type:           "unique",
                           risk_tier:                 "medium",
                           classification_confidence: "high",
                           alert_sent:                false
                         }

ProblemClassifierTool returns to FrontMan:
  {
    "skill_id":                  "SK-06",
    "normalized_category":       "Batch Processing",
    "recurrence_type":           "unique",
    "risk_tier":                 "medium",
    "classification_confidence": "high",
    "alert_sent":                false,
    "latency_ms":                320
  }
```

**If `risk_tier = "high"`:** FrontMan immediately informs the user that an ops
SNS alert has been sent, per HOCON instructions.

---

### STEP 2 — FrontMan asks SME questions (no tool call)

```
FrontMan generates 3-5 targeted questions based on the classification result.
This is a pure LLM reasoning step — no coded tool, no Lambda.

Example output to user:
  "Based on the classification:
   1. What was the observable symptom and when did it first occur?
   2. What changed recently in Batch Processing?
   3. Was a workaround applied and was it effective?"

FrontMan WAITS. No further steps until user responds.
```

This is the human-in-the-loop pause point in the Neuro-SAN path.
Unlike the harness (which pauses at a hardcoded Phase 3), the LLM
pauses here because the HOCON instructions say "Wait for the user's answers
before continuing to Step 3."

---

### STEP 3 — ContextBootstrap (after user answers)

```
User provides SME answers. FrontMan continues.

FrontMan calls ContextBootstrap with named fields:
  product             = "QNXT"
  normalized_category = "Batch Processing"   ← from Step 1
  use_case            = "UC-PM"
         ↓
ContextBootstrapTool.async_invoke(args, sly_data)
  │
  ├─ customer_id comes from sly_data (not from LLM args)
  ├─ Builds payload:
  │    {
  │      "skill":      "ContextBootstrapSkill",
  │      "inputs": {
  │        "customer_id": "QNXT-PRB0042-batch",  ← from sly_data
  │        "use_case":    "UC-PM",
  │        "agent_id":    "pm-neuro-san-agent"
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-context-bootstrap", payload
       )
           │
           └──► Lambda: llmwiki-skill-context-bootstrap
                    Retrieves IN PARALLEL:
                    - Prior RCA records for this product/component
                    - KEDB entries matching normalized_category
                    - UC-PM implementation playbook steps
                    Returns: {
                      customer_status:     "existing",
                      pages_loaded:        3,
                      key_facts:           [...],
                      playbook_steps:      [...],
                      prior_contributions: ["rca-PRB0038-final.md", ...]
                    }

ContextBootstrapTool returns to FrontMan:
  {
    "skill_id":           "SK-01",
    "customer_status":    "existing",
    "pages_loaded":       3,
    "key_facts":          ["QNXT batch processor had memory issue Mar 2025"],
    "playbook_steps":     ["Classify → Load context → Draft RCA → ..."],
    "prior_contributions": ["rca-PRB0038-final.md"],
    "latency_ms":         410
  }
```

---

### STEP 4 — WikiQuery + conditional GapDetection

```
FrontMan calls WikiQuery with named fields:
  question = "What are known resolution patterns for QNXT Batch Processing
              memory issues and how were prior incidents resolved?"
  domain   = "problem-management"
  use_case = "UC-PM"
         ↓
WikiQueryTool.async_invoke(args, sly_data)
  │
  ├─ customer_id from sly_data
  ├─ Builds payload:
  │    {
  │      "skill": "WikiQuerySkill",
  │      "inputs": {
  │        "question":    "What are known resolution patterns for...",
  │        "domain":      "problem-management",
  │        "customer_id": "QNXT-PRB0042-batch",
  │        "use_case":    "UC-PM",
  │        "intent":      "handoff-preparation"
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-wiki-query", payload
       )
           │
           └──► Lambda: llmwiki-skill-wiki-query
                    → Bedrock KB semantic search
                    → Claude synthesis of retrieved passages
                    Returns: {
                      answer:      "In Mar 2025 a similar batch issue was resolved by...",
                      confidence:  "medium",
                      sources:     ["rca-PRB0038-final.md", "kedb-batch-memory.md"],
                      action_items: [...]
                    }

WikiQueryTool returns to FrontMan:
  {
    "skill_id":        "SK-02",
    "confidence":      "medium",
    "answer":          "...",
    "action_items":    [...],
    "sources":         ["rca-PRB0038-final", "kedb-batch-memory"],
    "wiki_page_count": 2,
    "latency_ms":      680
  }
```

**Conditional branch on confidence:**

```
IF confidence = "high":
    FrontMan proceeds directly to Step 5 (ArtifactResolution)

IF confidence = "medium" or "low":
    FrontMan calls GapDetection first

         ↓ (medium confidence in this example)

GapDetectionTool.async_invoke(args, sly_data)
  │
  ├─ question                = (original WikiQuery question)
  ├─ domain                  = "problem-management"
  ├─ use_case                = "UC-PM"
  ├─ low_confidence_response = { confidence: "medium", ...WikiQuery result... }
  ├─ customer_id from sly_data
  │
  ├─ Builds payload:
  │    {
  │      "skill": "GapDetectionSkill",
  │      "inputs": {
  │        "question":                "...",
  │        "domain":                  "problem-management",
  │        "use_case":                "UC-PM",
  │        "customer_id":             "QNXT-PRB0042-batch",
  │        "low_confidence_response": { "confidence": "medium" }
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-gap-detection", payload
       )
           │
           └──► Lambda: llmwiki-skill-gap-detection
                    Classifies gaps, records with status="suggested" in DynamoDB
                    Returns: {
                      gap_count: 2,
                      blocking:  false,
                      gaps: [
                        { title: "QNXT memory pool configuration docs",
                          gap_type: "entity", blocking: false },
                        { title: "Batch processor restart SOP",
                          gap_type: "concept", blocking: false }
                      ]
                    }

GapDetectionTool returns to FrontMan:
  {
    "skill_id":  "SK-05",
    "gap_count": 2,
    "blocking":  false,
    "gaps":      [...],
    "latency_ms": 290
  }

IF blocking = true:
    FrontMan STOPS. Informs user which gap must be filled before RCA can proceed.
    No further steps. No draft written.

IF blocking = false:
    FrontMan continues to Step 5.
```

---

### STEP 5 — FrontMan composes the RCA draft (no tool call)

```
FrontMan synthesises all collected context:
  - SK-01 output: customer_status, key_facts, prior_contributions, playbook_steps
  - SME answers from Step 2
  - SK-02 output: wiki answer, action_items, sources
  - SK-05 output: gaps, blocking status

Pure LLM reasoning. No coded tool. No Lambda.

FrontMan writes a structured RCA Markdown document:

  ## Root Cause Analysis — PRB0042
  **Status:** DRAFT — awaiting SME review
  **Product:** QNXT | **Component:** Batch Processing | **Severity:** P2
  **Category:** Batch Processing | **Recurrence:** unique

  ### Timeline
  (from SME answers — list of events with approximate times)

  ### Root Cause
  (direct cause — one paragraph)

  ### Contributing Factors
  - High overnight batch volume
  - Memory pool not tuned for claim volume spike

  ### Impact Assessment
  (systems affected, SLA breach Y/N)

  ### Resolution Applied
  (what was done to restore service)

  ### Preventive Actions
  1. Tune memory pool allocator
  2. Add pre-batch memory headroom check
  3. Document in KEDB

  ### KEDB Entry
  Symptom: Batch fails at 02:00 under high volume
  Known Fix: Restart processor, apply memory patch
  Recurrence Risk: unique
```

---

### STEP 6 — ArtifactResolution

```
FrontMan calls ArtifactResolution with named fields:
  artifact_type     = "rca-template"
  available_context = {
      problem_id, product, component, severity,
      normalized_category, recurrence_type, risk_tier,
      timeline, root_cause, contributing_factors,
      impact, resolution, preventive_actions
  }
  use_case = "UC-PM"
         ↓
ArtifactResolutionTool.async_invoke(args, sly_data)
  │
  ├─ customer_id injected into available_context from sly_data
  ├─ Builds payload:
  │    {
  │      "skill": "ArtifactResolutionSkill",
  │      "inputs": {
  │        "artifact_type":     "rca-template",
  │        "customer_id":       "QNXT-PRB0042-batch",
  │        "available_context": { ...all RCA context... },
  │        "use_case":          "UC-PM"
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-artifact-resolution", payload
       )
           │
           └──► Lambda: llmwiki-skill-artifact-resolution
                    Searches wiki/templates/ for "rca-template"
                    Populates all fields from available_context
                    Marks unresolved fields as [MISSING — SME INPUT REQUIRED]
                    Returns: {
                      found:            true,
                      completion_pct:   78,
                      populated_fields: [...],
                      missing_fields:   ["root_cause_evidence"],
                      artifact_content: "# RCA Template — PRB0042\n..."
                    }

ArtifactResolutionTool returns to FrontMan:
  {
    "skill_id":         "SK-04",
    "found":            true,
    "completion_pct":   78,
    "populated_fields": [...],
    "missing_fields":   ["root_cause_evidence"],
    "artifact_content": "# RCA Template...",
    "latency_ms":       510
  }

IF completion_pct < 60%:
    FrontMan lists missing fields and asks user to provide them.

IF completion_pct >= 60%:
    FrontMan proceeds to Step 7.
```

---

### STEP 7 — WikiContribute (final write — always DRAFT)

```
FrontMan calls WikiContribute with EXACTLY these named fields
(HOCON instructions are explicit about field names — wrong names cause errors):
  page_type = "decisions"          ← hardcoded to trigger HITL routing
  page_slug = "rca-PRB0042-draft"
  content   = (complete RCA markdown from Step 5 + Step 6)
  agent_id  = "UCPMProblemManagementAgent"
         ↓
WikiContributeTool.async_invoke(args, sly_data)
  │
  ├─ Reads content from args — accepts multiple key names as fallback:
  │    args.get("content") or args.get("filled_template") or args.get("markdown")
  │    or args.get("body") or args.get("rca_markdown") or args.get("inquiry")
  │    (LLMs sometimes use the wrong key name — the tool is defensive)
  │
  ├─ SECURITY CHECK (hardcoded in Python, not configurable):
  │    human_review_required = page_type in {"decisions", "evidence"}
  │    → page_type="decisions" → human_review_required = TRUE
  │    This check runs in the Python tool AND in the Lambda.
  │    No LLM instruction, argument, or prompt injection can change this.
  │
  ├─ Builds payload:
  │    {
  │      "skill": "WikiContributeSkill",
  │      "inputs": {
  │        "page_type":             "decisions",
  │        "page_slug":             "rca-PRB0042-draft",
  │        "content":               "# Root Cause Analysis...",
  │        "agent_id":              "UCPMProblemManagementAgent",
  │        "customer_id":           "QNXT-PRB0042-batch",
  │        "use_case":              "UC-PM",
  │        "human_review_required": true
  │      }
  │    }
  │
  └──► LLMWikiBaseTool._invoke_skill(
           "llmwiki-skill-wiki-contribute", payload
       )
           │
           └──► Lambda: llmwiki-skill-wiki-contribute
                    Routes to wiki/pending/decisions/ (never wiki/live/)
                    Validates YAML frontmatter (title, date, problem_id,
                      status: DRAFT, use_case_tags: [UC-PM], contributing_agent)
                    Writes to S3: wiki/pending/decisions/rca-PRB0042-draft.md
                    Returns: {
                      status:   "pending-review",
                      s3_uri:   "s3://llmwiki-bucket/wiki/pending/decisions/rca-PRB0042-draft.md",
                      page_slug: "rca-PRB0042-draft"
                    }

WikiContributeTool returns to FrontMan:
  {
    "skill_id":              "SK-03",
    "page_status":           "pending-review",
    "s3_uri":                "s3://llmwiki-bucket/wiki/pending/decisions/rca-PRB0042-draft.md",
    "page_slug":             "rca-PRB0042-draft",
    "human_review_required": true,
    "note":                  "Routed to wiki/pending/ — awaiting human review",
    "latency_ms":            380
  }

FrontMan responds to user:
  "RCA draft saved to review queue at
   s3://llmwiki-bucket/wiki/pending/decisions/rca-PRB0042-draft.md.
   A human SME must review and promote to FINAL before it is indexed
   as a KEDB entry."
```

---

## Complete Call Sequence Summary

```
User message → FrontMan (HOCON + LLM)
    │
    ├─ STEP 1   ProblemClassifierTool   → SK-06 Lambda
    │
    ├─ STEP 2   FrontMan asks questions (LLM only, no tool)
    │           ↕ USER PAUSE ↕
    │
    ├─ STEP 3   ContextBootstrapTool    → SK-01 Lambda
    │
    ├─ STEP 4a  WikiQueryTool           → SK-02 Lambda  → Bedrock KB + Claude
    │
    ├─ STEP 4b  GapDetectionTool        → SK-05 Lambda  (only if confidence ≠ high)
    │           IF blocking=true → STOP
    │
    ├─ STEP 5   FrontMan drafts RCA (LLM only, no tool)
    │
    ├─ STEP 6   ArtifactResolutionTool  → SK-04 Lambda
    │
    └─ STEP 7   WikiContributeTool      → SK-03 Lambda  → S3 write (pending/decisions/)
```

---

## All Lambda Invocations

| Step | Coded tool class | FUNCTION env var | Lambda name | Purpose |
|---|---|---|---|---|
| 1 | `ProblemClassifierTool` | `SK06_FUNCTION` | `llmwiki-skill-problem-classifier` | Normalise category, risk tier, fire SNS if P1 |
| 3 | `ContextBootstrapTool` | `SK01_FUNCTION` | `llmwiki-skill-context-bootstrap` | Load prior RCAs, KEDB entries, UC-PM playbook |
| 4a | `WikiQueryTool` | `SK02_FUNCTION` | `llmwiki-skill-wiki-query` | Semantic search → Bedrock KB → Claude synthesis |
| 4b | `GapDetectionTool` | `SK05_FUNCTION` | `llmwiki-skill-gap-detection` | Classify + record knowledge gaps |
| 6 | `ArtifactResolutionTool` | `SK04_FUNCTION` | `llmwiki-skill-artifact-resolution` | Find + populate RCA template |
| 7 | `WikiContributeTool` | `SK03_FUNCTION` | `llmwiki-skill-wiki-contribute` | Write draft to S3 pending/decisions/ |

Steps 2 and 5 are pure LLM reasoning — no coded tool, no Lambda, no boto3 call.

---

## Storage Written During This Flow

| # | Write | Location | Key / path | Who writes it |
|---|---|---|---|---|
| 1 | RCA draft page | S3 `WIKI_BUCKET` | `wiki/pending/decisions/rca-PRB0042-draft.md` | SK-03 Lambda (via WikiContributeTool) |
| 2 | Gap records | DynamoDB `llmwiki-gaps` (or equivalent) | `gap_id` (UUID) | SK-05 Lambda |

Unlike the harness path, there is **no run-state table**, **no phase_results JSON**,
**no session audit log**, and **no HTML report**. Neuro-SAN itself manages conversation
state. The only persistent outputs are the RCA draft in S3 and any gap records in DynamoDB.

---

## LLMWikiBaseTool — The Shared Invocation Layer

Every coded tool inherits from `LLMWikiBaseTool`. It provides:

```python
# llmwiki_base_tool.py

class LLMWikiBaseTool:

    def _invoke_skill(self, function_name, payload):
        # Tries llmwiki_common first (local dev via PYTHONPATH)
        # Falls back to inline boto3 (Docker / production)
        # Wraps call in OTel span if OTEL_EXPORTER_OTLP_ENDPOINT is set
        ...

    def _raw_invoke(self, function_name, payload):
        resp = boto3.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode()
        )
        # Unwraps API Gateway envelope: raw → outer → body → inner dict
        ...

    @staticmethod
    def _extract_sly(sly_data):
        return {
            "customer_id":   sly_data.get("customer_id", ""),
            "api_key":       sly_data.get("llmwiki_api_key", ""),
            "engagement_id": sly_data.get("engagement_id", "")
        }
```

The OTel path (`_invoke_skill_traced`) records each tool call as a span with:
`neuro_san.tool`, `neuro_san.skill`, `input.value`, `output.value`,
`neuro_san.confidence`, `openinference.span.kind = "CHAIN"`.
This is a no-op if `OTEL_EXPORTER_OTLP_ENDPOINT` is not set.

---

## HOCON ↔ Python ↔ Lambda — The Contract

```
HOCON field             Python reads             Lambda receives
──────────────────────  ───────────────────────  ─────────────────────────────────
"name": "WikiQuery"     (not read by Python)     (not received by Lambda)
"class": "...Tool"      Python import path       (not received by Lambda)
"parameters": {...}     args dict keys           payload["inputs"] keys
"instructions": "..."   (not read by Python)     (not received by Lambda)
sly_data (runtime)      _extract_sly(sly_data)   payload["inputs"]["customer_id"]
```

**Key rule:** Changing `"instructions"` in HOCON never affects the Python tool or
the Lambda — it only changes what the LLM reasons about. Changing `"parameters"`
schema DOES require a matching change in the Python `async_invoke()` to read the
new field and pass it in the payload, and optionally a change in the Lambda to act
on it.

---

## How the Lambda Gets Called — The "Magic" Explained

> **Common misconception:** The Python coded tool files are NOT auto-generated from
> the HOCON file. They are manually written. HOCON and Python are two separate
> artifacts that you wire together with one single field: `"class"`.

Here is the complete chain from HOCON instruction to Lambda execution:

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOCON file  (uc_pm_problem_management.hocon)                       │
│                                                                      │
│  {                                                                   │
│    "name":  "WikiQuery",              ← LLM uses this name only     │
│    "class": "coded_tools.llmwiki      ← THIS is the binding         │
│              .wiki_query_tool         ← Python module path          │
│              .WikiQueryTool"          ← Python class name           │
│  }                                                                   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ Neuro-SAN imports the class at startup
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Python CodedTool  (wiki_query_tool.py)                             │
│                                                                      │
│  class WikiQueryTool(CodedTool, LLMWikiBaseTool):                   │
│      FUNCTION = os.environ.get(                                     │
│          "SK02_FUNCTION",              ← env var name               │
│          "llmwiki-skill-wiki-query"    ← fallback Lambda name       │
│      )                                                               │
│                                                                      │
│      async def async_invoke(self, args, sly_data):                  │
│          payload = { ... }                                           │
│          return self._invoke_skill(self.FUNCTION, payload)  ←──┐   │
└────────────────────────────────────────────────────────────────┼───┘
                                                                 │
                       inherited from LLMWikiBaseTool            │
                       ▼                                         │
┌─────────────────────────────────────────────────────────────────────┐
│  LLMWikiBaseTool._invoke_skill(function_name, payload)              │
│                                                                      │
│  boto3.client("lambda").invoke(                                     │
│      FunctionName = "llmwiki-skill-wiki-query",  ← resolved here   │
│      InvocationType = "RequestResponse",                            │
│      Payload = json.dumps(payload).encode()                         │
│  )                                                                   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
            AWS Lambda: llmwiki-skill-wiki-query
```

### Why the Lambda name is never in the HOCON

The HOCON file is plain text that the LLM reads. If the Lambda name were in the
HOCON, the LLM would see it — and in principle could reason about it, hallucinate
variations of it, or expose it in a response. By keeping the Lambda name inside
the Python class (as `FUNCTION = os.environ.get(...)`), the Lambda name is
completely hidden from the LLM. The LLM only ever sees `"name": "WikiQuery"`.

### The three-key lookup the runtime does at startup

When `ns run` starts, Neuro-SAN:

1. Reads the HOCON — finds `"class": "coded_tools.llmwiki.wiki_query_tool.WikiQueryTool"`
2. Does a Python import: `from coded_tools.llmwiki.wiki_query_tool import WikiQueryTool`
3. Instantiates the class — at this point `WikiQueryTool.FUNCTION` reads the env var
4. Registers the instance under the HOCON `"name"` so the LLM can call it by that name

If step 2 fails (wrong path, typo in `"class"`) — **Neuro-SAN crashes at startup**, not at
runtime when the tool is first called. This is useful: you know immediately if the binding
is broken, before any user sends a message.

---

## Adding a New Step Tomorrow — Exact Procedure

Say you need to add a new tool `SLABreachDetector` that calls a new Lambda
`llmwiki-skill-sla-breach`. Here is the exact sequence of changes required.

### Step 1 — Deploy (or confirm) the Lambda first

Before touching any HOCON or Python, the Lambda must exist and be callable.
Test it manually:

```bash
aws lambda invoke \
  --function-name llmwiki-skill-sla-breach \
  --payload '{"skill":"SLABreachSkill","inputs":{"problem_id":"PRB0042","customer_id":"QNXT"}}' \
  --cli-binary-format raw-in-base64-out \
  response.json && cat response.json
```

Confirm the response shape. You need to know the exact keys the Lambda returns
before writing the Python tool that reads them.

---

### Step 2 — Write the Python CodedTool

Create `code/neuro_san/coded_tools/llmwiki/sla_breach_tool.py`:

```python
import os
from neuronsai.coded_tool import CodedTool
from coded_tools.llmwiki.llmwiki_base_tool import LLMWikiBaseTool

class SLABreachDetectorTool(CodedTool, LLMWikiBaseTool):

    FUNCTION = os.environ.get("SK07_FUNCTION", "llmwiki-skill-sla-breach")

    async def async_invoke(self, args: dict, sly_data: dict) -> dict:
        ctx = self._extract_sly(sly_data)

        # Read args using the EXACT same field names as in HOCON "parameters" schema
        problem_id   = args.get("problem_id", "")
        severity     = args.get("severity", "")
        breach_window = args.get("breach_window_hours", 4)

        payload = {
            "skill":      "SLABreachSkill",
            "version":    "1.0",
            "invoked_by": "pm-neuro-san-agent",
            "inputs": {
                "problem_id":          problem_id,
                "severity":            severity,
                "breach_window_hours": breach_window,
                "customer_id":         ctx["customer_id"],  # always from sly_data
            }
        }

        result = self._invoke_skill(self.FUNCTION, payload)

        return {
            "skill_id":       "SK-07",
            "breached":       result.get("breached", False),
            "breach_time_utc": result.get("breach_time_utc", ""),
            "sla_target_hrs":  result.get("sla_target_hrs", 0),
            "latency_ms":      result.get("latency_ms", 0),
        }
```

---

### Step 3 — Register the tool in the HOCON file

Open `code/registries/llmwiki/uc_pm_problem_management.hocon`.

Inside the `"tools"` array of `UCPMProblemManagementAgent`, add:

```hocon
{
    "name": "SLABreachDetector",
    "function": ${aaosa_call} {
        "description": """
            Checks whether the current problem has breached or is about to breach
            its SLA commitment. Call this after ProblemClassifier whenever severity
            is P1 or P2. Returns: breached (bool), breach_time_utc, sla_target_hrs.
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "problem_id": {
                    "type": "string",
                    "description": "The problem record ID, e.g. PRB0042"
                },
                "severity": {
                    "type": "string",
                    "description": "Severity level: P1, P2, P3, P4"
                },
                "breach_window_hours": {
                    "type": "number",
                    "description": "Hours from now within which a breach is considered imminent"
                }
            },
            "required": ["problem_id", "severity"]
        }
    },
    "class": "coded_tools.llmwiki.sla_breach_tool.SLABreachDetectorTool"
}
```

---

### Step 4 — Update the FrontMan instructions

In the same HOCON file, find the `UCPMProblemManagementAgent` `"instructions"` block
and add the new step at the right position. Example — inserting after STEP 1:

```
STEP 1b  If severity is P1 or P2, immediately call SLABreachDetector with
          the problem_id and severity from Step 1.
          IF breached = true: prepend a BREACH WARNING to all outputs.
          IF breach_time_utc is within 2 hours: escalate to high risk tier.
```

The instruction text is for the LLM only — it has no technical effect on Python.
Its purpose is to tell the LLM **when** to call the tool and **what to do with the result**.

---

### Step 5 — Set the environment variable

Add to your `.env` or export before `ns run`:

```bash
export SK07_FUNCTION=llmwiki-skill-sla-breach
```

Without this, the Python tool falls back to the hardcoded default
(`"llmwiki-skill-sla-breach"`) — which is fine as long as the default name
matches the actual deployed Lambda. Setting the env var explicitly is safer
because it decouples the Lambda name from the Python source code.

---

## Cautions — Where Things Go Wrong

These are the exact failure modes that are easy to miss:

### Caution 1 — Parameter name mismatch (most common mistake)

The HOCON `"parameters"` schema tells the LLM what field names to pass.
The Python `async_invoke` reads those field names from `args`. If they differ,
the tool runs silently with an empty string — no error, wrong result.

```
HOCON says:          "problem_record_id"   ← LLM passes this key
Python reads:        args.get("problem_id") ← reads different key → ""
Lambda receives:     "problem_id": ""       ← wrong
```

**Rule:** After writing the Python tool, read back the HOCON parameter names
and verify every `args.get("...")` in Python matches exactly — same spelling,
same underscore positions, same case.

---

### Caution 2 — Wrong `"class"` path crashes startup

The `"class"` field is a Python dotted import path relative to the `PYTHONPATH`
that Neuro-SAN uses. One typo = `ModuleNotFoundError` at `ns run` startup.

```
"class": "coded_tools.llmwiki.sla_breachtool.SLABreachDetectorTool"
                                    ↑ missing underscore
```

Neuro-SAN will refuse to start and print the import error. Fix the `"class"` string.
The class name at the end is case-sensitive too.

---

### Caution 3 — `"name"` in HOCON has no technical effect

The `"name"` field is what the LLM uses to refer to the tool in its reasoning.
It has zero effect on which Python class is loaded. You can rename it freely
without touching Python. Conversely, renaming the Python class or file requires
updating `"class"` — renaming `"name"` does not.

```
"name":  "SLAChecker"          ← change this freely
"class": "coded_tools.llmwiki  ← change this when you rename the file/class
          .sla_breach_tool
          .SLABreachDetectorTool"
```

---

### Caution 4 — Lambda response format must match `_raw_invoke` unwrapping

`LLMWikiBaseTool._raw_invoke()` expects the Lambda to return either:
- A plain JSON dict: `{"breached": true, "breach_time_utc": "..."}`
- Or an API Gateway-style envelope: `{"statusCode": 200, "body": "{\"breached\": true}"}`

If the Lambda returns something else (e.g. a list, a string, or double-wrapped),
`_raw_invoke` will either raise or return an unexpected structure, and `result.get(...)`
in the Python tool will silently return `None` for every field.

**Rule:** Test the Lambda directly with `aws lambda invoke` before writing the
Python tool, and confirm the response can be parsed with `result.get("key")`.

---

### Caution 5 — `customer_id` must always come from `sly_data`

Never read `customer_id` from `args` as the primary source. Always use:

```python
ctx = self._extract_sly(sly_data)
customer_id = ctx["customer_id"] or args.get("customer_id", "")
```

`sly_data` takes priority. If the LLM hallucinates a `customer_id` in `args`,
`sly_data` overrides it. This is the injection-protection mechanism. Removing
this pattern breaks security isolation between tenants.

---

### Caution 6 — Missing env var silently uses the fallback Lambda name

```python
FUNCTION = os.environ.get("SK07_FUNCTION", "llmwiki-skill-sla-breach")
```

If `SK07_FUNCTION` is not set, Python calls `"llmwiki-skill-sla-breach"` literally.
In production this is fine if the name matches. In staging where Lambda names have
a `-staging` suffix, forgetting the env var means staging code calls production Lambdas.

**Rule:** Always set the env var explicitly in every environment's configuration.
Never rely on the fallback name in non-production environments.

---

### Caution 7 — Adding to HOCON without a Python file crashes at startup

If the `"class"` path points to a file that doesn't exist yet, Neuro-SAN
crashes immediately when `ns run` loads the manifest. It does not fail lazily
at the time the tool is first called. You must have the Python file in place
**before** running with the updated HOCON.

**Rule:** Always write and test the Python tool first. Then add it to HOCON.
Then update the FrontMan instructions. Never do it in reverse.

---

### Summary — The correct order of operations

```
1. Deploy and test the Lambda manually (aws lambda invoke)
2. Write the Python CodedTool (.py file)
   - FUNCTION env var
   - async_invoke reads args with the SAME field names HOCON will declare
   - customer_id from sly_data (always)
   - payload["inputs"] keys match what the Lambda expects
3. Add the tool to the HOCON "tools" array
   - "class" matches the exact Python module.ClassName
   - "parameters" schema field names match async_invoke's args.get() calls
4. Add a STEP to FrontMan instructions
   - Tell the LLM when to call it and what to do with the result
5. Set the env var (SK_N_FUNCTION=lambda-name) in the run environment
6. Start ns run — it crashes immediately if "class" is wrong (good: fail fast)
7. Send a test message that triggers the new step
8. Check the coded tool returns the expected dict to FrontMan
```

The three things that must stay in sync at all times:

```
HOCON "parameters" field names
    ↕  must match exactly
Python async_invoke args.get("field_name")
    ↕  must match exactly
Lambda payload["inputs"]["field_name"]
```

A mismatch anywhere in this chain produces no exception — just a silent empty value.
That is the hardest class of bug in this system to diagnose because the run succeeds.

---

## AAOSA Protocol — How the FrontMan Thinks

AAOSA (Agent-to-Agent Orchestration with Sub-Agent Arbitration) is included via:

```hocon
include "registries/aaosa.hocon",
```

And appended to every sub-agent's instructions via:

```hocon
"instructions": """ ... """ ${aaosa_instructions}
```

At each turn the FrontMan LLM runs four internal phases before calling any tool:

```
D — Determine:  Which sub-agents can contribute to this step?
F — Fulfill:    Call those sub-agents. Collect their outputs.
F — Follow-up:  Do any outputs require clarification or re-calling?
C — Compile:    Synthesise all outputs into a coherent response.
```

This is invisible to the user — it is how the LLM structures its internal
reasoning before each visible message or tool call.

---

## How This Path Differs from the Harness

| Dimension | Neuro-SAN / HOCON path | PM Harness path |
|---|---|---|
| **Orchestration owner** | LLM (reads HOCON instructions) | Python code (hardcoded sequence) |
| **Sequence at runtime** | LLM decides order; can vary by context | Always Phase 1→2→3→pause→4→5→6→7→8 |
| **SME pause** | LLM pauses at Step 2 (between classify and context load) | Harness pauses at Phase 3 (after classify, before context load) |
| **RCA draft** | Written by LLM in Step 5 (free-form markdown) | Written by Claude via Bedrock.converse in Phase 5 (JSON → template) |
| **Skills called** | SK-01, SK-02, SK-03, SK-04, SK-05, SK-06 (all 6) | SK-01, SK-05, SK-06 only (3 of 6) |
| **Direct Bedrock calls** | None from Python — LLM itself is the reasoning engine | Phases 3, 5, 7 call Bedrock directly |
| **State storage** | Neuro-SAN session (in-process) | DynamoDB `llmwiki-pm-runs` (12 writes) |
| **Audit log** | OTel spans (if configured) | DynamoDB `llmwiki-log` (always written) |
| **Output to S3** | `wiki/pending/decisions/<slug>.md` only | 4 files: rca-draft.json, kedb-draft.json, HTML report, handoff.md |
| **HTML report** | Not generated | Generated in Phase 8 |
| **Failure mode** | LLM may silently skip a step or interpret instructions unexpectedly | Exception caught per phase, run marked "error" in DynamoDB |
| **Blocking gaps** | LLM stops and tells user (per HOCON instruction) | `gaps_blocking=true` sets final status to `completed_with_gaps` |

---

## Starting Neuro-SAN Locally

```bash
# From repo root
cd code

# Ensure neuro-san is installed
pip install neuro_san/neuro_san-*.whl neuro_san/nsflow-*.whl

# Set environment variables
export SK01_FUNCTION=llmwiki-skill-context-bootstrap
export SK02_FUNCTION=llmwiki-skill-wiki-query
export SK03_FUNCTION=llmwiki-skill-wiki-contribute
export SK04_FUNCTION=llmwiki-skill-artifact-resolution
export SK05_FUNCTION=llmwiki-skill-gap-detection
export SK06_FUNCTION=llmwiki-skill-problem-classifier
export AWS_REGION=us-east-1

# Run the agent network
ns run registries/llmwiki/manifest.hocon

# Or run just the PM network directly
ns run registries/llmwiki/uc_pm_problem_management.hocon

# nsflow browser UI (once ns run is active)
# http://localhost:4173
# Select: uc_pm_problem_management
# Send: "Run RCA for PRB0042, product QNXT, component Batch Processing, severity P2"
```

The manifest (`manifest.hocon`) controls which networks are served:
```
uc_pm_problem_management.hocon: true   ← the PM network
uc1_sales_to_service.hocon:     true   ← the UC1 handoff network
uc_test_hello.hocon:            true
uc_travel_booking.hocon:        true
hospital_management_system.hocon: true
```

---

*Source: `code/registries/llmwiki/uc_pm_problem_management.hocon` ·*
*`code/neuro_san/coded_tools/llmwiki/` · Last updated 2026-07-22*
