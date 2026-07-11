---
workflow_id: WF-UC-PM
use_case: UC-PM
business_name: "Problem Management RCA Workflow"
domain: problem-management
platforms: [QNXT, TCS, EAM, EDM]
requires_human_input: true
human_input_phase: 3
harness_lambda: llmwiki-harness-uc-pm
version: "1.0"
---

# WF-UC-PM — Problem Management RCA Workflow Spec

## Harness Inputs (what the user provides at start)

| Field | Type | Required | Description |
|---|---|---|---|
| batch_id | string | yes | Ingest batch identifier, e.g. `PM-QNXT-001` |
| product | string | yes | Platform: `QNXT`, `TCS`, `EAM`, or `EDM` |
| problem_id | string | yes | Primary problem record ID, e.g. `PRB-1001` |
| related_record_ids | list of strings | yes | Incident and log IDs linked to this problem, e.g. `["INC-QNXT-1042", "APPLOG-0001"]` |
| severity | string | yes | `P1`, `P2`, `P3`, `High`, `Medium`, or `Low` |
| component | string | yes | Affected module or process, e.g. `Member Update API` |
| sme_context | string | optional | SME answers submitted on resume call; absent on first call |

---

## Workflow Steps

---

### Step 1: Problem Record Load

| Field | Value |
|---|---|
| Skill | Programmatic |
| Type | programmatic |
| Input from | harness: batch_id, problem_id, related_record_ids, product |
| Output to | Step 2, Step 5 |
| Gating rule | batch_id and problem_id must be present |
| On failure | abort_workflow |

What this step does: Loads the primary problem record and all linked incident and log records from the input batch. Validates that the problem_id exists. Returns a consolidated record set.

Output fields:
- `problem_record` — full problem record object (id, product, component, summary, severity, timestamp)
- `related_records` — list of linked incident and log objects (id, source_type, summary, raw_excerpt, solution)
- `records_loaded` — integer count of records successfully loaded
- `records_missing` — list of any related_record_ids that could not be loaded

Decision logic:
- If problem_id not found → abort_workflow
- If related_record_ids partially missing → log warning, continue with available records

---

### Step 2: Problem Classification

| Field | Value |
|---|---|
| Skill | SK-06 Problem Classifier |
| Type | llm_single |
| Input from | Step 1: problem_record, related_records; harness: severity, component |
| Output to | Step 3, Step 5, Step 8 (report) |
| Gating rule | Step 1 must complete successfully |
| On failure | skip (continue with unclassified result) |

What this step does: Classifies the problem by normalized issue category, recurrence type (repeated vs. unique), affected product domain, and risk tier. If severity is P1 or High, sends an SNS alert to the operations team.

Output fields:
- `normalized_category` — one of: `Batch Processing`, `Integration`, `Workflow`, `Logging`, `Authentication`, `Eligibility`, `Correspondence`, `Encounter`, `Status`
- `recurrence_type` — `"repeated"` or `"unique"`
- `risk_tier` — `"high"` / `"medium"` / `"low"`
- `classification_confidence` — `"high"` / `"medium"` / `"low"`
- `alert_sent` — boolean, true if SNS alert was triggered

Decision logic:
- If severity is P1 or High → send SNS alert, set risk_tier = "high"
- If recurrence_type == "repeated" → Step 5 will include pattern detection pass
- If classification_confidence == "low" → include flag in Step 8 report

---

### Step 3: SME Context Collection (HUMAN INPUT — WORKFLOW PAUSES HERE)

| Field | Value |
|---|---|
| Skill | Human Input (harness built-in) |
| Type | llm_human_input |
| Input from | Step 1: records_missing; Step 2: classification_confidence, normalized_category; harness: component |
| Output to | Step 5 |
| Gating rule | Steps 1 and 2 must complete |
| On failure | skip (continue without SME context if resume call has empty sme_context) |

What this step does: Generates up to 3 targeted questions for the Problem Coordinator or SME. Questions are based on: any records that could not be loaded (Step 1), low-confidence classification areas (Step 2), and component-specific knowledge gaps. The workflow pauses and returns status = "paused" with the questions. On the resume call the user submits answers in the `sme_context` field and the workflow continues from Step 4.

Output fields:
- `questions` — list of up to 3 question strings presented to the SME
- `sme_context` — the SME's submitted answers (populated on resume call)

---

### Step 4: Load Prior Knowledge

| Field | Value |
|---|---|
| Skill | SK-01 Customer Briefing Loader |
| Type | llm_agent |
| Input from | harness: product, component; Step 2: normalized_category, recurrence_type |
| Output to | Step 5 |
| Gating rule | Step 3 must complete (resume call received) |
| On failure | skip (continue with empty prior-knowledge set) |

What this step does: Queries the wiki for prior RCA pages, KEDB entries, and operational playbooks related to the same product, component, and issue category. Returns any previously recorded workarounds and permanent fixes.

Output fields:
- `prior_rcas` — list of prior RCA wiki pages found (id, title, summary, fix_applied)
- `kedb_entries` — list of known-error entries found (id, title, workaround, permanent_fix)
- `playbooks` — list of relevant playbook pages found
- `prior_knowledge_confidence` — `"high"` / `"medium"` / `"low"` / `"none"`

Decision logic:
- If prior_knowledge_confidence == "none" → Step 5 proceeds with no prior context; note this in report
- If prior_rcas contains entries where recurrence_type == "repeated" → Step 5 links this problem to the pattern

---

### Step 5: RCA Draft and Pattern Detection

| Field | Value |
|---|---|
| Skill | SK-02 Knowledge Finder |
| Type | llm_agent |
| Input from | Step 1: problem_record, related_records; Step 2: normalized_category, recurrence_type, risk_tier; Step 3: sme_context; Step 4: prior_rcas, kedb_entries |
| Output to | Step 6, Step 7, Step 8 (report) |
| Gating rule | Step 4 must complete |
| On failure | abort_workflow |

What this step does: Drafts the structured RCA narrative using the loaded problem records, SME context, and prior wiki knowledge. Identifies whether this problem is part of a known recurring pattern. Produces the root cause statement, contributing factors, timeline, and initial corrective action recommendations.

Output fields:
- `root_cause_statement` — 1–3 sentence root cause narrative
- `contributing_factors` — list of contributing factor strings
- `timeline` — ordered list of events (timestamp, record_id, description)
- `pattern_detected` — boolean
- `pattern_description` — description of the recurring pattern if detected, else empty
- `linked_problem_ids` — list of prior problem IDs this relates to (from prior_rcas)
- `corrective_actions` — list of objects: `{type: "workaround"|"permanent_fix", description: string, owner: string}`
- `rca_confidence` — `"high"` / `"medium"` / `"low"`

Decision logic:
- If rca_confidence == "low" → Step 6 must run to identify gaps; flag in report
- If pattern_detected == true → include pattern_description and linked_problem_ids in Step 8 report section

---

### Step 6: Knowledge Gap Detection

| Field | Value |
|---|---|
| Skill | SK-05 Missing Info Radar |
| Type | llm_agent |
| Input from | Step 5: root_cause_statement, contributing_factors, corrective_actions, rca_confidence |
| Output to | Step 7, Step 8 (report) |
| Gating rule | Step 5 must complete |
| On failure | skip (continue with empty gap list) |

What this step does: Reviews the RCA draft for missing evidence, incomplete root cause chains, missing permanent fix details, and missing monitoring or prevention steps. Produces a gap list with recommendations for what the Problem Coordinator should investigate further.

Output fields:
- `gaps` — list of gap objects: `{area: string, description: string, recommended_action: string}`
- `gap_count` — integer
- `gaps_blocking` — boolean, true if any gap makes the RCA unpublishable without resolution

Decision logic:
- If gap_count == 0 → Step 7 proceeds with a complete RCA
- If gaps_blocking == true → Step 8 report marks the RCA as "Draft — Incomplete" and lists blocking gaps

---

### Step 7: Template Fill — RCA and KEDB

| Field | Value |
|---|---|
| Skill | SK-04 Template Auto-Fill |
| Type | llm_single |
| Input from | Step 2: normalized_category, risk_tier; Step 5: root_cause_statement, contributing_factors, timeline, corrective_actions, pattern_description; Step 6: gaps |
| Output to | Step 8 |
| Gating rule | Step 6 must complete |
| On failure | skip (use raw Step 5 output in report if template fill fails) |

What this step does: Populates the standard RCA document template and the KEDB entry template. Any field that cannot be filled from available data is marked "Pending — requires SME input."

Output fields:
- `rca_document` — fully structured RCA object with all template sections populated
- `kedb_entry` — fully structured KEDB entry object
- `unfilled_fields` — list of field names that were marked "Pending"

---

### Step 8: Write Draft and Produce Report

| Field | Value |
|---|---|
| Skill | SK-03 Knowledge Recorder |
| Type | programmatic |
| Input from | harness: product, problem_id, batch_id; Step 2: normalized_category, recurrence_type; Step 5: root_cause_statement, corrective_actions, pattern_detected; Step 6: gaps, gaps_blocking; Step 7: rca_document, kedb_entry |
| Output to | Final output (report + wiki) |
| Gating rule | Step 7 must complete |
| On failure | alert |

What this step does: Writes the RCA document and KEDB entry to the wiki in **draft** status (never auto-published). Generates the HTML summary report. The report is stored in S3 and a presigned URL is returned to the caller. An SNS notification is sent to the Problem Coordinator with a link to the report.

Output fields:
- `wiki_rca_page_id` — the wiki page ID of the saved RCA draft
- `wiki_kedb_page_id` — the wiki page ID of the saved KEDB entry draft
- `report_url` — presigned S3 URL to the HTML summary report (valid 24 hours)
- `status` — `"completed"` or `"completed_with_gaps"`

Decision logic:
- If gaps_blocking == true → status = "completed_with_gaps"; report prominently shows blocking gap list
- If alert On failure → SNS notification sent to ops team; run record saved with status = "error"

---

## Report Sections

| # | Section Title | Data Source | Render As |
|---|---|---|---|
| 1 | Problem Summary | harness inputs + Step 2 outputs | Table with colored severity badge |
| 2 | Root Cause Statement | Step 5: root_cause_statement | Paragraph |
| 3 | Contributing Factors | Step 5: contributing_factors | Bulleted list |
| 4 | Incident Timeline | Step 5: timeline | Ordered list with timestamps |
| 5 | Recurrence Pattern | Step 5: pattern_detected, pattern_description, linked_problem_ids | Paragraph + links; hidden if pattern_detected = false |
| 6 | Corrective Actions | Step 5: corrective_actions | Table: Type / Description / Owner |
| 7 | KEDB Entry | Step 7: kedb_entry | Formatted block |
| 8 | Knowledge Gaps | Step 6: gaps | Warning block; hidden if gap_count = 0 |
| 9 | Evidence Pack | Step 1: related_records | Table: Record ID / Source Type / Summary |
| 10 | Prior Related Problems | Step 4: prior_rcas | List of links; hidden if empty |

---

## DynamoDB Run Record

Each harness invocation writes and updates a run record in DynamoDB table `llmwiki-pm-runs`:

| Field | Value |
|---|---|
| `run_id` | `{batch_id}#{problem_id}` |
| `product` | from harness input |
| `status` | `"running"` / `"paused"` / `"completed"` / `"completed_with_gaps"` / `"error"` |
| `current_phase` | integer 1–8 |
| `phases_completed` | list of completed phase numbers |
| `report_url` | presigned S3 URL (set at Step 8) |
| `created_at` | ISO timestamp |
| `updated_at` | ISO timestamp |

---

## Business-Readable Tests

### H1 — First call pauses at Step 3 for SME input
```
WHEN: first call with batch_id="PM-QNXT-001", product="QNXT", problem_id="PRB-1001",
      related_record_ids=["INC-QNXT-1042","APPLOG-0001"], severity="P1", component="Member Update API"
      (no sme_context)
THEN: status = "paused"
AND:  current_phase = 3
AND:  response contains "questions" field with 1–3 items
AND:  DynamoDB run record has status = "paused"
```

### H2 — Resume with SME context completes the run
```
WHEN: second call with same batch_id, problem_id, AND sme_context = "Same timeout seen in April.
      No change deployed. Root cause suspected to be connection pool exhaustion under peak load."
THEN: status = "completed" or "completed_with_gaps"
AND:  phases_completed includes all 8 phases
AND:  report_url is a valid presigned S3 URL
AND:  DynamoDB run record has status = "completed" or "completed_with_gaps"
AND:  wiki_rca_page_id is non-empty
```

### H3 — Poll for status mid-run
```
WHEN: action = "get_status", run_id = "PM-QNXT-001#PRB-1001"
THEN: status is one of: "running" / "paused" / "completed" / "completed_with_gaps" / "error"
AND:  current_phase is an integer between 1 and 8
```

### H4 — Missing required field returns error
```
WHEN: first call with problem_id missing (all other fields present)
THEN: status = "error"
AND:  HTTP 400 response
AND:  error message mentions "problem_id"
AND:  no DynamoDB record is written
```
