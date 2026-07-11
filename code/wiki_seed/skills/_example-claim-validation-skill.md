---
skill_id: SK-06
business_name: "Claim Readiness Validator"
technical_name: "ClaimReadinessSkill"
tier: 3
version: "1.0"
status: spec
use_case_tags: [UC5, UC8]
domain: claims-processing
---

# Claim Readiness Validator

## What It Does

Before the delivery team processes a batch of healthcare claims, this skill checks whether
all required supporting documents (EOB, prior auth, member eligibility confirmation) are
present and flags any claim lines that are missing mandatory data. It returns a readiness
score and a list of blocking issues the human team must resolve before processing can start.

## When to Call

Call this skill **after** SK-01 (customer context loaded) and **before** any claim
processing step. If the customer is type "government", return `not_applicable` immediately
without calling any downstream service — government payers use a separate adjudication path.

## What It Needs (Inputs)

- `customer_id` (string, required) — from SK-01 output `customer_context.customer_id`
- `claim_batch_id` (string, required) — the batch reference from the harness variable; user provides at workflow start
- `claim_lines` (list of objects, required) — each object has `claim_id`, `service_date`, `diagnosis_code`, `amount`; passed in from the harness
- `customer_type` (string, optional) — from SK-01 output `customer_context.customer_type`; defaults to "payer" if absent
- `strict_mode` (boolean, optional) — if true, treat warnings as blocking; defaults to false

## What It Produces (Outputs)

- `readiness_score` (integer 0–100) — percentage of claim lines that pass all checks
- `status` (string) — `ready` / `blocked` / `not_applicable`
- `blocking_issues` (list of objects) — each has `claim_id`, `issue_type`, `description`, `resolution_hint`
- `warnings` (list of strings) — non-blocking observations the delivery team should know
- `lines_checked` (integer) — total claim lines evaluated
- `lines_ready` (integer) — lines with no issues

## Business Rules

- If `customer_type == "government"` → return `status: not_applicable` immediately, set `readiness_score: null`
- A claim line is **blocking** if: `diagnosis_code` is missing OR `amount` > 50000 without a prior auth record in the wiki
- A claim line is a **warning** if: `service_date` is more than 90 days ago
- If `strict_mode == true` → promote all warnings to blocking issues
- Maximum 500 claim lines per invocation; return an error if exceeded

## What It Calls (Backend)

- `wiki_query` — to look up whether a prior auth record exists for claims with amount > 50000
  - Question template: "Is there a prior authorization on file for customer {customer_id} claim {claim_id}?"
  - Domain: "claims-processing"
- `bedrock_claude` — to classify ambiguous diagnosis codes (when code is present but malformed)
- `dynamodb_write` — write each blocking issue to table `llmwiki-claim-issues` with TTL 90 days
- `sns_publish` — if any blocking issue is found, send an alert to the claims team SNS topic

## Error Handling

- **Soft failure:** If `wiki_query` returns low confidence for a prior auth check, treat as "no prior auth found" (blocking), log a warning, and continue checking remaining lines
- **Soft failure:** If `bedrock_claude` fails to classify a diagnosis code, treat the line as a warning (not blocking), add `"diagnosis_code_unverified"` to warnings
- **Hard failure:** If `claim_lines` is empty, raise an error immediately — do not proceed
- **Hard failure:** If `dynamodb_write` fails 3 times, raise an error — issues must be persisted before returning
- SNS alert fires for any hard failure so the on-call team is notified

## Example: Happy Path

**Inputs:**
```json
{
  "customer_id": "bcbs-mn-001",
  "claim_batch_id": "BATCH-2026-0519-001",
  "claim_lines": [
    {"claim_id": "CLM-001", "service_date": "2026-05-01", "diagnosis_code": "Z00.00", "amount": 450.00},
    {"claim_id": "CLM-002", "service_date": "2026-05-10", "diagnosis_code": "J18.9",  "amount": 1200.00},
    {"claim_id": "CLM-003", "service_date": "2026-05-15", "diagnosis_code": "M54.5",  "amount": 75000.00}
  ],
  "customer_type": "payer"
}
```

**What the skill does:**
1. CLM-001 and CLM-002 pass all checks — valid diagnosis codes, amounts under threshold
2. CLM-003 has amount > 50000 — skill calls SK-02 asking if prior auth exists for this claim
   - SK-02 returns confidence=high, answer="Prior auth PA-2026-0115 found for patient coverage"
   - CLM-003 passes
3. No blocking issues found. `readiness_score = 100`

**Output:**
```json
{
  "status": "ready",
  "readiness_score": 100,
  "blocking_issues": [],
  "warnings": [],
  "lines_checked": 3,
  "lines_ready": 3
}
```

## Example: Edge Case

**Input:** CLM-004 has `diagnosis_code: ""` (empty) and `amount: 80000`.

**What happens:**
- Diagnosis code is missing → blocking issue added
- Amount > 50000 but no diagnosis code → skip prior auth check (can't query without context)
- `readiness_score` drops below 100

**Output includes:**
```json
{
  "blocking_issues": [
    {
      "claim_id": "CLM-004",
      "issue_type": "missing_diagnosis_code",
      "description": "Diagnosis code is required for all claim lines",
      "resolution_hint": "Contact the provider to obtain ICD-10 code before resubmitting"
    }
  ]
}
```

## Telemetry Fields

Log these extra fields to `llmwiki-log` beyond the standard fields:
- `claim_batch_id` — so you can correlate logs to a batch
- `lines_checked` — volume tracking
- `lines_ready` — pass rate over time
- `blocking_count` — trend monitoring
- `customer_type` — filter government vs payer in analytics
