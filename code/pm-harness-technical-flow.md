# PM Harness — Full Technical Architecture & Flow

> **Use case:** W2 — Problem Management RCA (no Neuro-SAN)
> **Entry point:** `code/lambda/harness/pm_harness/handler.py`
> **Corresponding HOCON (Neuro-SAN path, not used here):** `code/registries/llmwiki/uc_pm_problem_management.hocon`

---

## Two Execution Paths for the Same Use Case

The same PM use case can run via two completely different runtimes:

```
HOCON path (Neuro-SAN)                  Lambda Harness path (this document)
──────────────────────────────────────  ─────────────────────────────────────────
uc_pm_problem_management.hocon          pm_harness/handler.py
    ↓                                       ↓
Neuro-SAN AAOSA runtime                 Plain Python — one Lambda, fixed sequence
    ↓                                       ↓
LLM reads instructions and decides      Code calls skills in a hardcoded order
what to call next                           ↓
    ↓                                   Calls skill Lambdas directly via boto3
Calls coded_tools/*.py                      ↓
    ↓                                   Same skill Lambdas, same payloads
Tools call skill Lambdas
```

The skill Lambdas (SK-01 through SK-06) are **identical** in both paths. The harness
cuts out the Neuro-SAN orchestration layer and drives them directly from Python.

---

## System Overview

```
User / Streamlit UI
        │
        │  POST  (Call 1 — fresh start)
        │  POST  (Call 2 — resume with sme_context)
        ▼
  API Gateway
        │
        ▼
  pm_harness Lambda
  handler.py :: lambda_handler()
        │
        ├── boto3.Lambda.invoke  →  llmwiki-skill-problem-classifier  (SK-06)
        ├── boto3.Lambda.invoke  →  llmwiki-skill-context-bootstrap    (SK-01)
        ├── boto3.Lambda.invoke  →  llmwiki-skill-gap-detection         (SK-05)
        ├── bedrock.converse     →  Claude (Phases 3, 5, 7)
        ├── DynamoDB r/w         →  llmwiki-pm-runs  (state per run)
        ├── DynamoDB w           →  llmwiki-log      (audit trail)
        └── S3 put_object        →  PM_WIKI_BUCKET   (drafts, reports)
```

---

## CALL 1 — Fresh Start (Phases 1 → 2 → 3, then PAUSE)

### Request

```json
POST /pm-harness
{
  "batch_id": "BATCH-001",
  "problem_id": "PRB0042",
  "product": "QNXT",
  "severity": "P2",
  "component": "Batch Processing",
  "related_record_ids": ["INC0100", "INC0101"]
}
```

### Execution flow

```
lambda_handler()
    │
    ├─ Parse body, validate required fields
    │  (batch_id, problem_id, product, severity, component are all required)
    ├─ Build run_id = "BATCH-001#PRB0042"
    │
    ├──► _init_run()                                         [DB WRITE 1]
    │        Table:  llmwiki-pm-runs
    │        Key:    run_id="BATCH-001#PRB0042", batch_id="BATCH-001"
    │        Writes: status="running", current_phase=1,
    │                phase_results={}, created_at, expires_at (TTL 30 days)
    │
    ├──► Phase 1: _phase1_load_records()
    │        Pure Python — no external calls
    │        Builds structured dict from the related_record_ids in the request
    │        Returns: { problem_record{}, related_records[], records_loaded }
    │
    ├──► _save_phase(phase=1, result=phase1)                 [DB WRITE 2]
    │        Table:  llmwiki-pm-runs
    │        Update: phase_results={"1": phase1}, current_phase=1
    │
    ├──► Phase 2: _phase2_classify()
    │        Builds payload:
    │        {
    │          "inputs": {
    │            "problem_id":      "PRB0042",
    │            "product":         "QNXT",
    │            "component":       "Batch Processing",
    │            "severity":        "P2",
    │            "problem_summary": "Problem record PRB0042 for QNXT / Batch Processing",
    │            "related_records": [ ... ]
    │          },
    │          "invoked_by": "pm-harness"
    │        }
    │        │
    │        └──► boto3.lambda_client.invoke(
    │                 FunctionName="llmwiki-skill-problem-classifier",  [SK-06]
    │                 InvocationType="RequestResponse",
    │                 Payload=json.dumps(payload)
    │             )
    │             │
    │             └──► llmwiki-skill-problem-classifier Lambda
    │                      Classifies the problem record:
    │                      - Assigns normalized_category (Batch Processing,
    │                        Integration, Workflow, etc.)
    │                      - Assigns recurrence_type: "unique" or "repeated"
    │                      - Assigns risk_tier: "high" / "medium" / "low"
    │                      - Fires SNS ops alert if risk_tier = "high"
    │                      Returns: { normalized_category, recurrence_type,
    │                                 risk_tier, classification_confidence,
    │                                 alert_sent }
    │
    ├──► _save_phase(phase=2, result=phase2)                 [DB WRITE 3]
    │
    ├──► Phase 3: _phase3_generate_questions()
    │        Builds prompt from phase1 + phase2 (missing records, confidence,
    │        component, recurrence type)
    │        │
    │        └──► bedrock.converse(                          [BEDROCK CALL 1]
    │                 modelId="us.anthropic.claude-sonnet-4-6",
    │                 messages=[{"role":"user", "content":[{"text": prompt}]}],
    │                 inferenceConfig={"maxTokens": 300}
    │             )
    │             Claude returns up to 3 targeted SME questions as JSON array
    │
    ├──► _update_run(                                        [DB WRITE 4]
    │        status="paused", current_phase=3,
    │        phases_completed=[1, 2],
    │        phase3_questions=json.dumps(questions)
    │    )
    │
    └──► HTTP 200 response returned to caller:
         {
           "run_id":        "BATCH-001#PRB0042",
           "status":        "paused",
           "current_phase": 3,
           "message":       "Workflow paused at Step 3 — SME input required...",
           "questions":     ["What is the known behaviour of Batch Processing...", ...],
           "classification": {
             "normalized_category":       "Batch Processing",
             "recurrence_type":           "unique",
             "risk_tier":                 "medium",
             "classification_confidence": "high"
           }
         }
```

**The user reads the questions, provides answers, and submits Call 2.**

---

## CALL 2 — Resume (Phases 4 → 5 → 6 → 7 → 8, COMPLETE)

### Request

Same body as Call 1, plus:

```json
{
  "batch_id": "BATCH-001",
  "problem_id": "PRB0042",
  "product": "QNXT",
  "severity": "P2",
  "component": "Batch Processing",
  "sme_context": "Batch job started at 2am. Memory leak detected in claim processor. Similar issue seen in Mar 2025 but never documented."
}
```

### Execution flow

```
lambda_handler()
    │
    ├─ Detects: sme_context present AND existing run has status="paused"
    ├─ Restores phase1, phase2 from DynamoDB phase_results
    ├─ Calls _resume_workflow()
    │
    ├──► _update_run(status="running", current_phase=4)      [DB WRITE 5]
    │
    │
    ├──► Phase 4: _phase4_prior_knowledge()
    │        Builds payload:
    │        {
    │          "inputs": {
    │            "customer_id":  "QNXT",
    │            "domain":       "problem-management",
    │            "use_case":     "UC-PM",
    │            "component":    "Batch Processing",
    │            "category":     "Batch Processing",
    │            "recurrence":   "unique"
    │          },
    │          "invoked_by": "pm-harness"
    │        }
    │        │
    │        └──► boto3.lambda_client.invoke(
    │                 FunctionName="llmwiki-skill-context-bootstrap",   [SK-01]
    │                 InvocationType="RequestResponse",
    │                 Payload=json.dumps(payload)
    │             )
    │             │
    │             └──► llmwiki-skill-context-bootstrap Lambda
    │                      Queries the LLMWiki S3 / Bedrock KB for:
    │                      - Prior RCA records for this product/component
    │                      - KEDB entries matching the category
    │                      - Implementation playbook for UC-PM
    │                      Returns: { prior_contributions[], playbook{},
    │                                 customer_status, key_facts }
    │
    │        Returns: { prior_rcas[], kedb_entries[], playbooks[],
    │                   prior_knowledge_confidence }
    │
    ├──► _save_phase(phase=4, result=phase4)                 [DB WRITE 6]
    │
    │
    ├──► Phase 5: _phase5_rca_draft()
    │        Builds a large prompt combining ALL context:
    │          - phase1: problem_record, related_records
    │          - phase2: normalized_category, risk_tier, recurrence
    │          - sme_context: user's answers from Call 2
    │          - phase4: prior_rcas, kedb_entries
    │        │
    │        └──► bedrock.converse(                          [BEDROCK CALL 2]
    │                 modelId="us.anthropic.claude-sonnet-4-6",
    │                 messages=[RCA draft prompt],
    │                 inferenceConfig={"maxTokens": 1500}
    │             )
    │             Claude returns structured RCA JSON:
    │             {
    │               "root_cause_statement": "Memory leak in claim processor...",
    │               "contributing_factors": ["High volume overnight batch", ...],
    │               "timeline": [{"timestamp":"02:00","description":"batch started"},...],
    │               "pattern_detected": true,
    │               "pattern_description": "Matches Mar 2025 incident pattern",
    │               "linked_problem_ids": [],
    │               "corrective_actions": [
    │                 {"type":"workaround","description":"Restart processor","owner":"Ops"},
    │                 {"type":"permanent_fix","description":"Patch memory pool","owner":"Dev"}
    │               ],
    │               "rca_confidence": "medium"
    │             }
    │
    ├──► _save_phase(phase=5, result=phase5)                 [DB WRITE 7]
    │
    │
    ├──► Phase 6: _phase6_gap_detection()
    │        Builds question from phase5:
    │          "Review this RCA for PRB0042 (QNXT).
    │           Root cause: Memory leak in claim processor...
    │           RCA confidence: medium
    │           Corrective actions: [...]
    │           Identify knowledge gaps: missing evidence, incomplete root cause
    │           chains, missing permanent fix details, missing monitoring steps."
    │        │
    │        Builds payload:
    │        {
    │          "inputs": {
    │            "question":    "Review this RCA for PRB0042...",
    │            "domain":      "problem-management",
    │            "use_case":    "UC-PM",
    │            "customer_id": "QNXT",
    │            "low_confidence_response": {"confidence": "medium"}
    │          },
    │          "invoked_by": "pm-harness"
    │        }
    │        │
    │        └──► boto3.lambda_client.invoke(
    │                 FunctionName="llmwiki-skill-gap-detection",        [SK-05]
    │                 InvocationType="RequestResponse",
    │                 Payload=json.dumps(payload)
    │             )
    │             │
    │             └──► llmwiki-skill-gap-detection Lambda
    │                      Classifies knowledge gaps in the RCA:
    │                      - gap_type: "entity" | "concept" | "question"
    │                      - blocking: true if gap prevents RCA completion
    │                      - Records gaps with status="suggested" in DynamoDB
    │                      Returns: { gaps[], gap_count, blocking }
    │
    │        Returns: { gaps[], gap_count, gaps_blocking }
    │
    ├──► _save_phase(phase=6, result=phase6)                 [DB WRITE 8]
    │
    │
    ├──► Phase 7: _phase7_template_fill()
    │        Builds prompt from all phases combined:
    │          problem_id, product, category, risk_tier,
    │          root_cause, contributing_factors, timeline,
    │          corrective_actions, gaps
    │        │
    │        └──► bedrock.converse(                          [BEDROCK CALL 3]
    │                 modelId="us.anthropic.claude-sonnet-4-6",
    │                 messages=[template fill prompt],
    │                 inferenceConfig={"maxTokens": 1500}
    │             )
    │             Claude returns two filled templates as JSON:
    │             {
    │               "rca_document": {
    │                 "title":               "RCA - PRB0042",
    │                 "problem_id":          "PRB0042",
    │                 "product":             "QNXT",
    │                 "category":            "Batch Processing",
    │                 "risk_tier":           "medium",
    │                 "root_cause":          "...",
    │                 "contributing_factors": [...],
    │                 "timeline":            [...],
    │                 "corrective_actions":  [...],
    │                 "status":              "Draft"
    │               },
    │               "kedb_entry": {
    │                 "title":                   "KEDB - PRB0042",
    │                 "known_error_description": "...",
    │                 "workaround":              "Restart claim processor",
    │                 "permanent_fix":           "Patch memory pool allocator",
    │                 "status":                  "Draft"
    │               },
    │               "unfilled_fields": ["root_cause_evidence — SME input required"]
    │             }
    │
    ├──► _save_phase(phase=7, result=phase7)                 [DB WRITE 9]
    │
    │
    ├──► Phase 8: _phase8_write_and_report()
    │        No LLM call. Pure assembly + storage.
    │        │
    │        ├──► s3.put_object(                             [S3 WRITE 1]
    │        │        Bucket: PM_WIKI_BUCKET
    │        │        Key:    wiki/pm/drafts/PRB0042/rca-draft.json
    │        │        Body:   phase7.rca_document (JSON)
    │        │    )
    │        │
    │        ├──► s3.put_object(                             [S3 WRITE 2]
    │        │        Bucket: PM_WIKI_BUCKET
    │        │        Key:    wiki/pm/drafts/PRB0042/kedb-draft.json
    │        │        Body:   phase7.kedb_entry (JSON)
    │        │    )
    │        │
    │        ├──► _build_report_html()
    │        │        Pure Python. Assembles full HTML report from all phases.
    │        │        Includes: problem summary table, root cause, timeline,
    │        │        corrective actions, KEDB entry, gaps, evidence pack,
    │        │        prior related problems. Status banner: DRAFT.
    │        │
    │        ├──► s3.put_object(                             [S3 WRITE 3]
    │        │        Bucket: PM_WIKI_BUCKET
    │        │        Key:    wiki/pm/reports/BATCH-001_PRB0042-report.html
    │        │        ContentType: text/html
    │        │    )
    │        │
    │        ├──► _build_session_handoff_md()
    │        │        Pure Python. Builds human-readable Markdown:
    │        │        classification, root cause, next best step,
    │        │        open items/gaps, corrective actions.
    │        │
    │        ├──► s3.put_object(                             [S3 WRITE 4]
    │        │        Bucket: PM_WIKI_BUCKET
    │        │        Key:    sessions/BATCH-001/2026-07-22-handoff.md
    │        │        ContentType: text/markdown
    │        │    )
    │        │
    │        ├──► s3.generate_presigned_url(HTML report, expiry=86400s)
    │        └──► s3.generate_presigned_url(handoff.md,  expiry=86400s)
    │
    ├──► _save_phase(phase=8, result=phase8)                 [DB WRITE 10]
    │
    ├──► _write_session_wrapup()                             [DB WRITE 11]
    │        Table:  llmwiki-log
    │        Key:    log_date="session#pm-harness#2026-07-22"
    │                timestamp_id="{iso_now}#BATCH-001#PRB0042"
    │        Writes: phases_completed=[1,2,3,4,5,6,7,8],
    │                outcome="success" (or "partial" if gaps_blocking),
    │                artifacts=[rca_key, kedb_key, report_key, handoff_key],
    │                handoff { next_best_step, open_items, risk_flags,
    │                           confidence },
    │                agent_id="UC-PM-ProblemMgmtAgent",
    │                TTL = now + 90 days
    │
    ├──► _update_run(                                        [DB WRITE 12]
    │        status="completed",         (or "completed_with_gaps")
    │        current_phase=8,
    │        phases_completed=[1,2,3,4,5,6,7,8],
    │        report_download_url,
    │        wiki_rca_page_id, wiki_kedb_page_id,
    │        total_latency_ms
    │    )
    │
    └──► HTTP 200 full summary response:
         {
           "run_id":              "BATCH-001#PRB0042",
           "status":              "completed",
           "phases_completed":    [1,2,3,4,5,6,7,8],
           "total_latency_ms":    ...,
           "report_download_url": "https://s3.presigned...",
           "handoff_md_url":      "https://s3.presigned...",
           "wiki_rca_page_id":    "wiki/pm/drafts/PRB0042/rca-draft.json",
           "wiki_kedb_page_id":   "wiki/pm/drafts/PRB0042/kedb-draft.json",
           "summary": {
             "normalized_category":  "Batch Processing",
             "recurrence_type":      "unique",
             "risk_tier":            "medium",
             "root_cause_statement": "Memory leak in claim processor...",
             "pattern_detected":     true,
             "gap_count":            2,
             "gaps_blocking":        false
           }
         }
```

---

## All Database and Storage Writes

| # | Write | Table / Bucket | Key pattern | When |
|---|---|---|---|---|
| DB 1 | Init run record | `llmwiki-pm-runs` | `run_id` + `batch_id` | Start of Call 1 |
| DB 2 | Phase 1 result | `llmwiki-pm-runs` | same key | After Phase 1 |
| DB 3 | Phase 2 result | `llmwiki-pm-runs` | same key | After Phase 2 |
| DB 4 | Pause state + questions | `llmwiki-pm-runs` | same key | End of Call 1 |
| DB 5 | Resume — set running | `llmwiki-pm-runs` | same key | Start of Call 2 |
| DB 6 | Phase 4 result | `llmwiki-pm-runs` | same key | After Phase 4 |
| DB 7 | Phase 5 result | `llmwiki-pm-runs` | same key | After Phase 5 |
| DB 8 | Phase 6 result | `llmwiki-pm-runs` | same key | After Phase 6 |
| DB 9 | Phase 7 result | `llmwiki-pm-runs` | same key | After Phase 7 |
| DB 10 | Phase 8 result | `llmwiki-pm-runs` | same key | After Phase 8 |
| DB 11 | Session audit log | `llmwiki-log` | `session#pm-harness#<date>` | End of Call 2 |
| DB 12 | Final status + URLs | `llmwiki-pm-runs` | same key | Very end |
| S3 1 | RCA draft JSON | `PM_WIKI_BUCKET` | `wiki/pm/drafts/<id>/rca-draft.json` | Phase 8 |
| S3 2 | KEDB draft JSON | `PM_WIKI_BUCKET` | `wiki/pm/drafts/<id>/kedb-draft.json` | Phase 8 |
| S3 3 | HTML report | `PM_WIKI_BUCKET` | `wiki/pm/reports/<run>-report.html` | Phase 8 |
| S3 4 | Handoff markdown | `PM_WIKI_BUCKET` | `sessions/<batch>/<date>-handoff.md` | Phase 8 |

---

## Skill Lambda Invocations

| Phase | Lambda name | Skill | Purpose |
|---|---|---|---|
| 2 | `llmwiki-skill-problem-classifier` | SK-06 | Normalise category, risk tier, fire SNS if P1 |
| 4 | `llmwiki-skill-context-bootstrap` | SK-01 | Load prior RCAs, KEDB entries, UC-PM playbook |
| 6 | `llmwiki-skill-gap-detection` | SK-05 | Classify + record knowledge gaps in the RCA |

Phases 3, 5, 7 call **Bedrock directly** — no Lambda hop, no skill wrapper.  
Phase 8 makes **no LLM or Lambda call** — pure report assembly + S3 writes.  
Phases 1 is **pure Python** — no external call of any kind.

---

## Bedrock Calls Summary

| Call | Phase | Prompt purpose | Max tokens | Output |
|---|---|---|---|---|
| 1 | Phase 3 | Generate 3 SME questions from classification | 300 | JSON array of question strings |
| 2 | Phase 5 | Draft full RCA narrative + timeline + actions | 1500 | JSON object (rca_confidence, root_cause, etc.) |
| 3 | Phase 7 | Populate RCA template + KEDB entry template | 1500 | JSON object (rca_document, kedb_entry, unfilled_fields) |

---

## Key Design Decisions

### Why hardcoded phase sequence instead of LLM orchestration?

The PM harness is a **deterministic workflow**, not a reasoning exercise. The phase order is always:

```
Load records → Classify → SME questions (pause) → Prior knowledge → RCA draft → Gaps → Template → Write
```

This order is contractual — it cannot be safely reordered. A Neuro-SAN LLM could
theoretically call GapDetection before ProblemClassifier, which would produce wrong
results. The harness eliminates that risk.

### Why PAUSE at Phase 3?

SME context (what actually happened, what changed, what workarounds were tried) is
irreplaceable. It cannot be inferred from the problem record alone. The pause forces
a human into the loop before any LLM writes to the knowledge base. No draft is ever
produced from Phase 1+2 alone.

### Why are RCA outputs always DRAFT?

The HITL constraint is hardcoded in Phase 8 — all S3 writes go to
`wiki/pm/drafts/` not `wiki/pm/live/`. The HTML report carries a "DRAFT — NOT
PUBLISHED" banner. A Problem Coordinator must manually review and promote. This
cannot be bypassed by any input or instruction.

### Why does Phase 8 write to S3 instead of via SK-03?

SK-03 (`llmwiki-skill-wiki-contribute`) is the standard wiki indexing path.
The PM harness writes directly to S3 because:
- RCA drafts must go to `wiki/pm/drafts/` — a separate S3 prefix not managed by SK-03
- The HTML report is a binary artifact, not a Markdown wiki page
- Direct S3 gives the harness full control over the HITL routing

### run_id format

`run_id = f"{batch_id}#{problem_id}"`

This composite key lets a status poll (`action=get_status`) reconstruct both parts from
a single string. The `#` separator is chosen because neither `batch_id` nor `problem_id`
contains it.

---

## What Makes This "Not Neuro-SAN" — Side-by-Side

| Dimension | Neuro-SAN (HOCON path) | PM Harness (Lambda path) |
|---|---|---|
| **Who decides what to call next?** | The LLM — reads `instructions:` in HOCON | Python code — fixed function call sequence |
| **Sequence changeable at runtime?** | Yes — LLM can reorder based on reasoning | No — hardcoded Phase 1→2→3→pause→4→5→6→7→8 |
| **Human pause point** | Wherever STEP 2 in HOCON says "wait for user" | Always Phase 3, always before `sme_context` |
| **State between calls** | Neuro-SAN session memory | `llmwiki-pm-runs` DynamoDB table |
| **Skill Lambdas called?** | Yes — via `coded_tools/*.py` → `LLMWikiBaseTool._invoke_skill()` | Yes — directly via `_invoke_skill()` in handler.py |
| **Which Lambdas?** | SK-01, SK-02, SK-03, SK-04, SK-05, SK-06 | SK-01, SK-05, SK-06 only |
| **Bedrock calls** | Inside coded_tools + any LLM reasoning | Phases 3, 5, 7 directly in handler.py |
| **Auditability** | Neuro-SAN logs + OTel spans | Every phase result in DynamoDB + llmwiki-log |
| **Failure mode** | LLM can skip a step or hallucinate a step | Exception caught per phase, run set to "error" |

---

## Environment Variables

| Variable | Default | Used for |
|---|---|---|
| `PM_RUNS_TABLE` | `llmwiki-pm-runs` | Run state storage |
| `PM_WIKI_BUCKET` | *(required)* | S3 destination for drafts and reports |
| `LOG_TABLE` | `llmwiki-log` | Session audit log |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | Bedrock model for all three direct calls |
| `SK01_FUNCTION` | `llmwiki-skill-context-bootstrap` | Phase 4 Lambda name |
| `SK05_FUNCTION` | `llmwiki-skill-gap-detection` | Phase 6 Lambda name |
| `SK06_FUNCTION` | `llmwiki-skill-problem-classifier` | Phase 2 Lambda name |
| `AWS_REGION` | `us-east-1` | All boto3 clients |

---

*Source: `code/lambda/harness/pm_harness/handler.py` · Last updated 2026-07-22*
