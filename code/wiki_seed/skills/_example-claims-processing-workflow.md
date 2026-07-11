---
workflow_id: WF-UC5
use_case: UC5
business_name: "Claims Batch Processing"
domain: claims-processing
version: "1.0"
requires_human_input: true
human_input_phase: 3
---

# Claims Batch Processing Workflow

## Business Goal

When a new batch of healthcare claims arrives from the provider, this workflow
automatically validates readiness, checks for known issues in the wiki, pauses to
let the claims team confirm any blockers are resolved, then processes and records
the outcome. It replaces a 3-day manual email chain between sales, delivery, and
the provider team with a 20-minute automated + human-in-the-loop workflow.

**Who uses it:** Claims Operations Lead, Delivery Manager  
**What it replaces:** Manual claim intake checklist + email to provider team  
**Output:** Processed batch record indexed to wiki + issue log in DynamoDB

---

## Workflow Steps

### Step 1: Load Customer Context

| Field | Value |
|---|---|
| Skill | SK-01 |
| Type | programmatic |
| Input from | harness: `customer_id` |
| Output to | Step 2, Step 3, Step 4 |
| Gating rule | None — always runs first |
| On failure | abort_workflow |

**What this step does:**
Loads the customer's full history from the wiki and the UC5 delivery playbook in parallel.
The agent now knows: customer type, products in scope, any prior claims incidents,
escalation contacts, and the standard processing checklist for UC5.

---

### Step 2: Claim Readiness Validation

| Field | Value |
|---|---|
| Skill | SK-06 (Claim Readiness Validator) |
| Type | llm_agent |
| Input from | harness: `claim_batch_id`, `claim_lines`; Step 1 output: `customer_context.customer_type` |
| Output to | Step 3 (blocking_issues), Step 5 (readiness_score) |
| Gating rule | Step 1 must be complete |
| On failure | alert + abort_workflow |

**What this step does:**
Validates every claim line in the batch: checks for missing diagnosis codes, amounts
requiring prior auth, and stale service dates. Returns a readiness score and a list
of issues the human team must resolve.

**Decision logic:**
- If `status == "not_applicable"` (government payer) → skip Steps 3–4, jump to Step 5 using the alternative government processing path
- If `status == "ready"` → skip Step 3 human pause, jump directly to Step 4
- If `status == "blocked"` → proceed to Step 3 (human confirmation)

---

### Step 3: Human Confirmation of Blocking Issues ⏸️

| Field | Value |
|---|---|
| Skill | built-in (human input) |
| Type | llm_human_input |
| Input from | Step 2 output: `blocking_issues` |
| Output to | Step 4 |
| Gating rule | Only runs if Step 2 status == "blocked" |
| On failure | N/A — human either confirms or cancels |

**What this step does:**
Pauses the workflow and presents the blocking issues to the Claims Operations Lead.
The agent has already loaded the customer context (Step 1) and knows the issue details
(Step 2), so it asks specific, pre-populated questions instead of generic ones.

**Questions to ask the human:**

For each blocking issue in Step 2 output, generate this question:
> "CLM-{claim_id}: {issue_type} — {description}. {resolution_hint}. Has this been resolved? (yes / no / escalate)"

Plus one summary question:
> "Are there any additional constraints on this batch I should know about before processing?"

**How the answers flow forward:**
- If any claim line answer is "no" → that line is marked `excluded_by_human` and removed from the processing batch
- If any answer is "escalate" → SK-05 Gap Detection runs on that line before continuing
- Human's free-text answer to the summary question is stored as `human_context` and passed to Step 4

---

### Step 4: Wiki Risk Check

| Field | Value |
|---|---|
| Skill | SK-02 |
| Type | llm_agent |
| Input from | Step 1 output: `customer_context`; Step 3 output: `human_context` (if present) |
| Output to | Step 5 |
| Gating rule | Steps 1 and 3 (if it ran) must be complete |
| On failure | skip (log warning, continue with low-confidence flag) |

**What this step does:**
Queries the wiki for any known processing risks specific to this customer and claim type.

Question template:
> "What are the known issues or edge cases for processing {diagnosis_code} claims for a {customer_type} payer? Customer: {customer_id}. Human context: {human_context}"

**Decision logic:**
- If `confidence == "low"` → run SK-05 (Gap Detection) to log what the wiki is missing; add `wiki_gaps` to Step 5 input
- If `confidence == "high"` → skip SK-05

---

### Step 5: Record Processing Outcome

| Field | Value |
|---|---|
| Skill | SK-03 |
| Type | llm_single |
| Input from | Steps 1–4 outputs |
| Output to | wiki + S3 report |
| Gating rule | All prior required steps complete |
| On failure | retry once, then alert |

**What this step does:**
Writes the batch processing record to the wiki under `wiki/customers/{customer_id}-claims-batch-{date}.md`.
Also writes a plain-text summary report to `wiki/reports/{customer_id}-claims-{batch_id}-{date}.txt`.

---

## Human Input Step — Full Detail

**When it fires:** After Step 2 (only if blocking issues found)

**What the agent knows by this point:**
- Customer history (Step 1): products, prior incidents, contacts
- Batch issues (Step 2): exact claim IDs and issue descriptions with resolution hints

**UI behaviour:**
- Show a table of blocking issues with claim ID, type, description, resolution hint
- For each issue: "Resolved? Yes / No / Escalate" radio
- Free text: "Any additional context before I proceed?"
- Button: "Confirm and continue processing"

**How the answers flow forward:**
- "Yes" answers → claim line stays in the batch
- "No" answers → claim line removed, added to `excluded_lines` in output
- "Escalate" answers → SK-05 runs for that claim line before Step 4

---

## Output / Deliverable

**Wiki page written:** `wiki/customers/{customer_id}-claims-batch-{batch_id}.md`  
Contains: batch summary, readiness score, issues found, human decisions, risk notes from wiki

**S3 report:** `wiki/reports/{customer_id}-claims-{batch_id}-{date}.html`  
Business-friendly HTML report with KPIs: lines processed, lines excluded, readiness score, gaps logged

**DynamoDB:** Each blocking issue written to `llmwiki-claim-issues`

**Downstream:** Output wiki page becomes input for UC8 (Cutover readiness check)

---

## Composition Notes

**Skill sequence:** SK-01 → SK-06 → (human) → SK-02 → (SK-05 if low confidence) → SK-03

**Optional skills:**
- SK-05 only runs if SK-02 confidence < high, or if human answers "Escalate" on a claim line

**New skills this workflow needs:**
- SK-06: Claim Readiness Validator — see `_example-claim-validation-skill.md`

**Skills NOT needed:** SK-04 (no template to populate in this workflow)
