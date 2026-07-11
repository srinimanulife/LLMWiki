---
skill_id: SK-06
business_name: "Problem Classifier"
technical_name: "ProblemClassifierSkill"
tier: 3
domain: problem-management
use_case_tags: [UC-PM]
platforms: [QNXT, TCS, EAM, EDM]
version: "1.0"
---

# SK-06 — Problem Classifier

## What It Does

Classifies a problem record into a normalized issue category, determines whether the problem is a repeated occurrence or a unique event, assigns a risk tier, and triggers an SNS alert for high-severity problems. This classification drives the RCA workflow — repeated problems get pattern analysis, high-risk problems get immediate notification.

## When to Call

Call this skill at Step 2 of the Problem Management workflow, after Step 1 has successfully loaded the problem record and related incident/log records. Must NOT be called before the problem record is loaded. Must complete before the SME question generation in Step 3.

## What It Needs (Inputs)

- `problem_id` (string, required) — primary problem record ID, e.g. `PRB-1001`
- `product` (string, required) — platform name: `QNXT`, `TCS`, `EAM`, or `EDM`
- `component` (string, required) — affected module or process, e.g. `Member Update API`
- `severity` (string, required) — `P1`, `P2`, `P3`, `High`, `Medium`, or `Low`
- `problem_summary` (string, required) — summary title from the problem record
- `related_records` (list of objects, required) — each object has: `source_type` (string), `summary_title` (string), `raw_excerpt` (string), `solution` (string), `normalized_issue_category` (string)
- `ingest_batch_id` (string, required) — batch traceability ID, e.g. `PM-QNXT-001`

## What It Produces (Outputs)

- `normalized_category` — one of: `Batch Processing`, `Integration`, `Workflow`, `Logging`, `Authentication`, `Eligibility`, `Correspondence`, `Encounter`, `Status`; the category that best describes the primary failure mode
- `recurrence_type` — `"repeated"` if multiple related records share the same root pattern, `"unique"` if the issue appears for the first time
- `risk_tier` — `"high"` if severity is P1 or High; `"medium"` if P2 or Medium; `"low"` if P3 or Low
- `classification_confidence` — `"high"` if records clearly point to one category, `"medium"` if partially ambiguous, `"low"` if insufficient evidence
- `alert_sent` — boolean, `true` if an SNS alert was dispatched (only for risk_tier = "high")
- `classification_notes` — short explanation of why this category and recurrence type were chosen

## Business Rules

- If `severity` is `P1` or `High` → set `risk_tier` = `"high"` AND publish an SNS alert to the operations team immediately. Do not wait for any other step.
- If two or more related records share the same `normalized_issue_category` AND the `solution` field on any record contains the word "Repeated" → set `recurrence_type` = `"repeated"`.
- If all related records are unique (no shared category, no "Repeated" indicator) → set `recurrence_type` = `"unique"`.
- If `product` is not one of `QNXT`, `TCS`, `EAM`, `EDM` → return error immediately with status 400.
- If `related_records` is empty → set `classification_confidence` = `"low"` and `recurrence_type` = `"unique"`; do not abort.
- Maximum 50 records in `related_records` per call. If exceeded → return error with status 400.

## What It Calls (Backend)

- `llm_single` — calls Claude via Bedrock to reason over the records and produce normalized_category, recurrence_type, and classification_notes
- `sns_publish` — to alert the operations team when risk_tier = "high" (topic: llmwiki-pm-high-severity-alerts)
- `dynamodb_write` — to persist the classification result (table: llmwiki-pm-classifications)

## Error Handling

- Soft failure: Claude returns a category not in the allowed list → map to closest allowed value and set classification_confidence = "low"
- Hard failure: `problem_id` is missing or empty → return HTTP 400 error, message: "problem_id is required"
- Hard failure: `product` is not one of the four allowed values → return HTTP 400 error, message: "product must be QNXT, TCS, EAM, or EDM"
- Hard failure: `related_records` exceeds 50 items → return HTTP 400 error, message: "related_records exceeds maximum of 50"
- Hard failure: SNS publish fails 3 times for a P1/High problem → return HTTP 500 error and log; do not silently continue
- Soft failure: DynamoDB write fails → log warning, return classification result to caller without persisting

## Example: Happy Path

**Scenario:** QNXT eligibility timeout — repeated problem, P1 severity

Input:
```
problem_id: "PRB-1001"
product: "QNXT"
component: "Member Update API"
severity: "P1"
ingest_batch_id: "PM-QNXT-001"
problem_summary: "Recurring timeout pattern in eligibility processing"
related_records:
  - source_type: "Log"
    summary_title: "Member eligibility update timeout"
    raw_excerpt: "Timeout while writing eligibility update to core tables"
    solution: "Repeated problem – increase connection timeout, add retry"
    normalized_issue_category: "Logging"
  - source_type: "Incident"
    summary_title: "Eligibility update failed for large group batch"
    raw_excerpt: "Batch update failed after partial commit in same API path"
    solution: "Repeated problem – same corrective action as PRB-1001 plus batch chunking"
    normalized_issue_category: "Batch Processing"
  - source_type: "ProblemRecord"
    summary_title: "Recurring timeout pattern in eligibility processing"
    raw_excerpt: "Problem review identified same timeout pattern across multiple incidents"
    solution: "Repeated problem – create RCA page and known-error entry for timeout pattern"
    normalized_issue_category: "Workflow"
```

What the skill does:
1. Detects P1 severity → sets risk_tier = "high", sends SNS alert
2. Scans solution fields → all three contain "Repeated problem" → sets recurrence_type = "repeated"
3. Calls Claude → reasons that the primary failure mode is a timeout across batch and API layers → normalizes to "Batch Processing" (most specific category across records)
4. Sets classification_confidence = "high" (three records all agree on the pattern)
5. Writes classification to DynamoDB

Output:
```
normalized_category: "Batch Processing"
recurrence_type: "repeated"
risk_tier: "high"
classification_confidence: "high"
alert_sent: true
classification_notes: "Three records share the same timeout pattern in the Member Update API.
  Solutions on all records indicate this is a known repeated problem. SNS alert sent for P1 severity."
```

## Example: Edge Case

**Scenario:** EDM unique problem, empty related_records

Input:
```
problem_id: "PRB-4002"
product: "EDM"
component: "Submission Generator"
severity: "P1"
ingest_batch_id: "PM-EDM-001"
problem_summary: "Submission generation stalled on one large batch"
related_records: []
```

What the skill does:
1. Detects P1 severity → sets risk_tier = "high", sends SNS alert
2. related_records is empty → sets recurrence_type = "unique", classification_confidence = "low"
3. Calls Claude with only the problem summary → Claude infers "Batch Processing" from "large batch" context
4. Sets classification_confidence = "low" (no evidence records to corroborate)
5. Writes result to DynamoDB; returns result with confidence warning

Output:
```
normalized_category: "Batch Processing"
recurrence_type: "unique"
risk_tier: "high"
classification_confidence: "low"
alert_sent: true
classification_notes: "No related records provided. Category inferred from problem summary only.
  Confidence is low — recommend SME review of classification in Step 3."
```

## Business-Readable Tests

### T1 — Happy path: repeated P1 problem classified correctly
```
Input:
  problem_id: "PRB-1001"
  product: "QNXT"
  component: "Member Update API"
  severity: "P1"
  ingest_batch_id: "PM-QNXT-001"
  problem_summary: "Recurring timeout pattern in eligibility processing"
  related_records: (3 records as shown in Happy Path above)
Expected output:
  normalized_category: "Batch Processing"
  recurrence_type: "repeated"
  risk_tier: "high"
  classification_confidence: "high"
  alert_sent: true
```

### T2 — Missing problem_id returns 400
```
Input:
  product: "QNXT"
  component: "Member Update API"
  severity: "P1"
  ingest_batch_id: "PM-QNXT-001"
  problem_summary: "Recurring timeout"
  related_records: []
  (no problem_id)
Expected output:
  HTTP 400 error
  error message contains "problem_id"
```

### T3 — Invalid product value returns 400
```
Input:
  problem_id: "PRB-9999"
  product: "SAP"
  component: "Unknown"
  severity: "P2"
  ingest_batch_id: "PM-TEST-001"
  problem_summary: "Test"
  related_records: []
Expected output:
  HTTP 400 error
  error message contains "product must be QNXT, TCS, EAM, or EDM"
```

### T4 — More than 50 related_records returns 400
```
Input:
  problem_id: "PRB-5000"
  product: "EDM"
  component: "Submission Generator"
  severity: "P2"
  ingest_batch_id: "PM-EDM-TEST"
  problem_summary: "Large batch"
  related_records: (51 items)
Expected output:
  HTTP 400 error
  error message contains "related_records exceeds maximum of 50"
```

## Telemetry Fields

Extra fields to log beyond the standard skill response fields:
- `ingest_batch_id` — correlate classification logs to the source batch
- `records_evaluated` — count of related_records passed in
- `repeated_indicators_found` — count of records whose solution field contained "Repeated"
- `alert_sent` — boolean for SNS audit trail
