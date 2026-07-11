---
title: "Bring Your Skill to Production — Business User Guide"
type: guide
audience: business-users
domain: all
version: "1.0"
author: "LLMWiki Platform Team"
---

# Bring Your Skill to Production
### How to Turn a Business Idea Into a Running AWS Agent — No Code Required

---

## What This Guide Is

You have a manual business process — an email chain, a spreadsheet review, a
multi-step approval — that you want to automate with an AI agent.

This guide shows you exactly how to write it down in plain English so our
platform converts it into a production-grade AWS Lambda agent automatically.

You will leave with:
- A spec file the generator can read
- Test cases you can write yourself that prove the agent works
- A clear picture of what happens between your .md file and a deployed Lambda

**You do not write code. You write English.**

---

## The Big Picture: Three Documents, One Agent

Every production agent in LLMWiki starts with three plain-English documents.
Think of them as three levels of zoom:

```
LEVEL 1 — UC Brief         ← "Here's the business problem" (1 page)
    │                         Written by: Business Owner / Process Expert
    │
LEVEL 2 — Workflow Spec    ← "Here are the exact steps" (3-5 pages)
    │                         Written by: Process Expert + Platform Team
    │
LEVEL 3 — Skill Spec(s)    ← "Here is one specific capability" (1-2 pages each)
                              Written by: Business Analyst / Platform Team

         ↓  (generator reads all three)

    AWS Lambda + DynamoDB + S3 + Terraform + Tests
```

You don't have to write all three yourself. The Level 1 brief is enough to
start a conversation. The platform team co-authors Levels 2 and 3 with you.

---

## Real Example: The UC1 Sales-to-Service Handoff

Everything below uses a real agent we built. Use it as your model.

**The business problem (what the Account Manager told us):**

> "When a deal closes we spend 3 days emailing back and forth to brief the
> delivery team. Half the time delivery starts the kickoff call without the
> full picture. We want an agent that does this automatically."

That one paragraph became a 1,063-line production Lambda. Here's how.

---

## Step 1 — Write a UC Brief (Level 1)

The UC Brief is the starting document. It has five sections. You write
everything in plain English — no technical terms required.

### UC Brief Template

```markdown
---
use_case_id: UCnn          ← Ask the platform team for the next number
title: "Your Process Name"
domain: your-domain        ← e.g. customer-onboarding, claims, provisioning
---

# UCnn — Your Process Name

## What Is This?
Two paragraphs. Describe the manual problem you have today and
what the agent should do instead. Who uses it? What does it replace?
How much time does it save?

## What Do You Need to Start?
Bullet list: the minimum data a user must provide to kick off the workflow.
Example: Customer ID, contract number, product name.

## What Does the Agent Do? (Steps in plain English)
One paragraph per step. For each step describe:
- What the agent looks at or does
- What decision it makes
- What happens if it fails (stop? continue? alert someone?)

## What Does the Output Look Like?
Describe what the end user sees or downloads when the agent finishes.

## What Are the Rules?
Any business rules that must always be enforced.
Examples: "Step 3 always pauses for human approval."
         "Never process government claims automatically."

## What Skills Does This Use?
If you know, list which capabilities the agent needs.
If you don't know, leave this blank — the platform team fills it in.
```

### Real Example — UC1 Brief (abridged)

```markdown
---
use_case_id: UC1
title: "Sales-to-Service Handoff"
domain: customer-onboarding
---

## What Is This?
When a deal closes, the agent reads everything the wiki knows about
the customer, asks the sales team 3 targeted questions, detects what
the wiki doesn't know, and produces a business-ready handoff report.

Who uses it: Account Managers, Delivery Managers
What it replaces: Manual handoff email chain, SOW summary spreadsheet
Time saved: From 3 days to under 30 minutes

## What Do You Need to Start?
- Customer name — e.g. "BlueCross BlueShield Minnesota"
- Customer ID — e.g. "bcbs-mn-001"
- Product(s) sold
- SOW Reference number

## What Does the Agent Do? (8 steps)

### Step 1 — Look Up the Customer
Searches the wiki for everything known about this customer.
If the customer is new → proceeds with a clean slate, flags as new.
If this fails → STOP. We need to know if this is a known customer.

### Step 3 — Ask the Sales Team (PAUSES HERE)
Generates 3 targeted questions based on the risk tier and complexity.
Waits until the sales team submits answers, then continues automatically.

### Step 8 — Write the Handoff Report
Writes a wiki page and a downloadable HTML report.
The report goes directly to the delivery team before the kickoff call.
```

**What you write in Step N is exactly what the generator uses to name the
phase function and its error-handling behavior.** "If this fails → STOP"
becomes a `_PhaseError`. "If this fails → continue" becomes a try/except
that logs and proceeds.

---

## Step 2 — Write a Workflow Spec (Level 2)

The Workflow Spec turns your brief into a precise implementation blueprint.
The generator reads this to build the entire Lambda skeleton.

The key additions vs. the brief are:

1. **Input field names** (exact snake_case names the Lambda will accept)
2. **Skill mapping** (which existing skill handles each step)
3. **Gating rules** (when a step is allowed to run)
4. **Output field names** (what each step produces that the next step consumes)
5. **Report sections** (what appears in the HTML output)

### Workflow Spec Template (key sections)

```markdown
---
workflow_id: WF-UCnn
use_case: UCnn
business_name: "..."
requires_human_input: true | false
human_input_phase: N         ← Which step number pauses for a human
harness_lambda: llmwiki-harness-ucnn
---

## Harness Inputs (what the user provides at start)

| Field        | Type   | Required | Description            |
|--------------|--------|----------|------------------------|
| customer_id  | string | yes      | Unique customer code   |
| ...          |        |          |                        |

## Workflow Steps

### Step N: [Name]

| Field       | Value                                       |
|-------------|---------------------------------------------|
| Skill       | SK-02 (Knowledge Finder)                    |
| Type        | llm_agent                                   |
| Input from  | harness: customer_id; Step N-1: risk_tier   |
| Output to   | Step N+1, Step 8 (report)                   |
| Gating rule | Step N-1 must complete successfully         |
| On failure  | skip (continue with empty result)           |

What this step does: [plain English]

Output fields:
- `confidence` — "high" / "medium" / "low"
- `answer` — plain-English result text

Decision logic:
- If confidence == "high" → skip Step N+1
- If confidence == "low" → run Step N+1

## Report Sections

| # | Section Title | Data Source       | Render As         |
|---|---------------|-------------------|-------------------|
| 1 | Customer Info | phase1.overview   | Paragraph         |
| 2 | Risk Tier     | phase2.risk_tier  | Colored badge     |
```

### The Four Step Types — Plain English

| Type | Means | Example |
|---|---|---|
| `programmatic` | A direct API call, no AI reasoning | Load customer record, write wiki page |
| `llm_single` | One call to Claude, structured JSON out | Classify risk tier based on context |
| `llm_agent` | Claude searches the wiki and reasons | "What are the delivery risks for this customer?" |
| `llm_human_input` | Workflow pauses — human answers a question | Sales team provides executive sponsor info |

### The Three Failure Modes — Plain English

| On failure value | Means in code |
|---|---|
| `abort_workflow` | Raise `_PhaseError` — entire run stops, status = "error" |
| `skip` | Catch the exception, log a warning, continue with an empty result |
| `alert` | Catch the exception, send an SNS notification, continue |

---

## Step 3 — Write a Skill Spec (Level 3)

A Skill Spec describes one reusable capability. Write one when your workflow
needs something the five existing skills cannot do.

**Check existing skills first:**

| Skill | Does what | Use it when... |
|---|---|---|
| SK-01 Customer Briefing Loader | Loads customer history + playbooks | Step 1 of almost every workflow |
| SK-02 Knowledge Finder | Answers a question from the wiki | "What does the wiki know about X?" |
| SK-03 Knowledge Recorder | Writes new content to the wiki | Recording a result, saving a report |
| SK-04 Template Auto-Fill | Fills a template with real data | Populating a form or checklist |
| SK-05 Missing Info Radar | Finds and logs what the wiki doesn't know | After a low-confidence answer |

**Only write a new skill spec if none of the above covers it.**

### Skill Spec Template

```markdown
---
skill_id: SK-NN             ← Next available number after SK-05
business_name: "..."        ← Plain English, 3-5 words
technical_name: "...Skill"  ← CamelCase
tier: 3                     ← 1=universal, 2=common, 3=domain-specific
domain: your-domain
use_case_tags: [UC1, UC5]
---

## What It Does
One or two sentences. What business task does this skill perform?

## When to Call
When in a workflow should this run? What must have happened before?
What must NOT have happened yet?

## What It Needs (Inputs)
- input_name (type, required/optional) — what it is, where it comes from
- customer_id (string, required) — from SK-01 output.customer_id
- claim_lines (list, required) — user provides at workflow start

## What It Produces (Outputs)
- output_name — what it contains, how downstream steps use it
- status (string) — "ready" / "blocked" / "not_applicable"
- blocking_issues (list) — list of problems the human team must resolve

## Business Rules
Rules the skill MUST enforce. The generator turns these into if-guards.
- If customer_type == "government" → return not_applicable immediately
- If amount > 50000 AND no prior auth → flag as blocking issue
- Maximum 500 claim lines per call

## What It Calls (Backend)
Name the backends you need. The generator wires them automatically.
- wiki_query — to check if prior authorization exists
- dynamodb_write — to persist blocking issues (table: llmwiki-claim-issues)
- sns_publish — to alert the claims team if any blocking issue is found

## Error Handling
- Soft failure: wiki_query returns low confidence → treat as "no prior auth"
- Hard failure: claim_lines is empty → stop immediately, return error
- Hard failure: DynamoDB write fails 3 times → stop immediately

## Example: Happy Path
Walk through ONE concrete example with realistic test data.
Input → what the skill does step by step → Output.
(This becomes your first unit test automatically.)

## Example: Edge Case
One unusual or incomplete input case.
What happens? What does the output look like?

## Telemetry Fields
Extra fields to log beyond the standard ones:
- claim_batch_id — correlate logs to a batch
- lines_checked — volume tracking
```

### Real Example — SK-06 Claim Readiness Validator (abridged)

```markdown
## Business Rules
- If customer_type == "government" → return status: not_applicable immediately
- A claim is BLOCKING if: diagnosis_code is missing
- A claim is BLOCKING if: amount > 50000 AND no prior auth in the wiki
- A claim is a WARNING if: service_date is more than 90 days ago
- Maximum 500 claim lines per call

## Example: Happy Path

Inputs:
  customer_id: "bcbs-mn-001"
  claim_batch_id: "BATCH-2026-0519-001"
  claim_lines:
    - {claim_id: "CLM-001", diagnosis_code: "Z00.00", amount: 450.00}
    - {claim_id: "CLM-003", diagnosis_code: "M54.5",  amount: 75000.00}
  customer_type: "payer"

What the skill does:
  1. CLM-001 passes all checks (valid code, amount under threshold)
  2. CLM-003 has amount > 50000 → calls wiki to check prior auth
     wiki returns: "Prior auth PA-2026-0115 found" → CLM-003 passes

Output:
  status: "ready"
  readiness_score: 100
  blocking_issues: []
  lines_checked: 2
  lines_ready: 2
```

---

## Step 4 — Writing Test Cases (The Most Important Section)

**This is where most business users stop too early. Don't.**

The generator uses your examples to create test stubs — but YOU need to make
those examples precise enough to catch real bugs. Here is the principle:

> One test case = one claim you make about how the agent behaves.
> If you can state it as "WHEN [condition] THEN [result]", it's a test case.

### The Four Tests You Must Always Write

Write these four for every skill or workflow spec you submit:

---

**Test 1 — The Happy Path**
The normal case. Everything is provided. What should come back?

```
WHEN: all required inputs are present and valid
THEN: status = "success" (or "ready" / "completed")
AND:  the key output field is present and non-empty
AND:  the skill_id in the response matches "SK-NN"
```

Example for UC1 harness:
```
WHEN: customer_id="bcbs-mn-001", customer_name="BlueCross MN",
      product="Care Management Platform", sow_reference="SOW-2026-001"
THEN: status = "paused"  (it pauses to ask the sales team 3 questions)
AND:  current_phase = 3
AND:  the response contains a "question" field
```

---

**Test 2 — Missing Required Input**
Leave out the most important field. What should happen?

```
WHEN: customer_id is missing (empty event sent)
THEN: status = "error"
AND:  the error message mentions "customer_id"
AND:  no data is written to DynamoDB or S3
```

---

**Test 3 — The Government / Not-Applicable Rule**
If your skill has a "skip this type of customer" rule, test it explicitly.

```
WHEN: customer_type = "government"
THEN: status = "not_applicable"
AND:  no wiki_query call is made
AND:  no DynamoDB write is made
```

---

**Test 4 — The Hard Failure**
The most dangerous input. What should cause a full stop?

```
WHEN: claim_lines = []  (empty list)
THEN: the skill returns an error immediately
AND:  status code is 400
AND:  error message mentions "claim_lines"
AND:  SNS alert is sent to the claims team
```

---

### How to Write Tests in the Spec (for the Generator)

Add a section to your skill spec called `## Business-Readable Tests`.
Write them in the format below — the generator uses these to produce
`test_claim_readine.py` automatically.

```markdown
## Business-Readable Tests

### T1 — Happy path: all claims pass
Input:
  customer_id: "bcbs-mn-001"
  claim_batch_id: "BATCH-TEST-001"
  claim_lines: [{claim_id:"CLM-001", diagnosis_code:"Z00.00", amount:450.00}]
  customer_type: "payer"
Expected output:
  status: "ready"
  readiness_score: 100
  blocking_issues: []

### T2 — Missing customer_id
Input:
  claim_batch_id: "BATCH-TEST-001"
  claim_lines: [{claim_id:"CLM-001", diagnosis_code:"Z00.00", amount:450.00}]
  (no customer_id)
Expected output:
  HTTP 400 error
  error message contains "customer_id"

### T3 — Government customer is not applicable
Input:
  customer_id: "medicaid-state-001"
  customer_type: "government"
  claim_batch_id: "BATCH-TEST-001"
  claim_lines: [{claim_id:"CLM-001", diagnosis_code:"Z00.00", amount:450.00}]
Expected output:
  status: "not_applicable"

### T4 — Empty claim_lines is a hard failure
Input:
  customer_id: "bcbs-mn-001"
  claim_batch_id: "BATCH-TEST-001"
  claim_lines: []
Expected output:
  HTTP 400 error
  error message contains "claim_lines is empty"
```

These four lines — Input, Expected output — are read directly by the
test runner. No Python knowledge required.

---

### Harness-Level Test Cases (for multi-step workflows)

For a full workflow spec (Level 2), you need one additional test type:

**Test H1 — First call pauses at human-input step**
```
WHEN: first call with customer_id, product, sow_reference (no human_context)
THEN: status = "paused"
AND:  current_phase = 3
AND:  a question is returned asking for sales team context
AND:  DynamoDB run record has status = "paused"
```

**Test H2 — Resume with human context completes the run**
```
WHEN: second call with same customer_id + human_context = "Executive sponsor
      is Jane Smith. Go-live Q3 2026. No prior attempts."
THEN: status = "completed"
AND:  phases_completed = 8
AND:  report_url is a valid presigned S3 URL
AND:  DynamoDB run record has status = "completed"
```

**Test H3 — poll for status mid-run**
```
WHEN: action = "get_status", engagement_id = "bcbs-mn-001"
THEN: status is one of: "running" / "paused" / "completed" / "error"
AND:  current_phase is a number between 1 and 8
```

---

## Step 5 — The Full Generation Command

Once your spec files are in `wiki_seed/skills/`, run one command:

```bash
# Generate and test a single skill
python3 scripts/generate_skill_lambda.py \
    --spec wiki_seed/skills/sk-06-claim-readiness.md

# Generate and test a full workflow harness
python3 scripts/generate_harness.py \
    --spec wiki_seed/skills/wf-UC1-sales-to-service.md

# Generate EVERYTHING from a UC brief (skills + harness + tests)
python3 scripts/generate_pipeline.py \
    --brief wiki_seed/skills/uc-01-brief.md \
    --region us-east-1

# Generate + deploy immediately to AWS
python3 scripts/generate_pipeline.py \
    --brief wiki_seed/skills/uc-01-brief.md \
    --deploy
```

What the generator does in order:

```
1. Read your spec → extract inputs, outputs, rules, examples
2. Load reference code from existing skills (SK-01 to SK-05 as examples)
3. Call Claude via AWS Bedrock → generate handler.py
4. Validate Python syntax with ast.parse()
   → If syntax error: automatically ask Claude to fix and retry (up to 2×)
5. Write lambda/skills/{slug}/handler.py
6. Write test_*.py from your "Business-Readable Tests" section
7. Run tests immediately (no AWS required — all AWS calls are mocked)
8. Write Terraform resource block to terraform/lambda_skills_generated.tf
9. If --deploy: zip + push to AWS Lambda
```

Steps 4 and 7 are the safety net. If the generator produces broken code,
you see it immediately — before anything reaches AWS.

---

## Step 6 — How to Read the Test Results

After `generate_pipeline.py` runs you will see output like this:

```
============================================================
RESULTS: 25 passed / 0 failed / 25 total
============================================================

Testing: lambda/skills/claim_readine/handler.py
  ✓ claim_readine:happy_path
  ✓ claim_readine:missing_inputs
  ✓ claim_readine:contract_fields
  ✓ claim_readine:government_not_applicable

Testing: lambda/harness/uc1_harness/handler.py
  ✓ uc1_harness:requires_customer_id
  ✓ uc1_harness:get_status
  ✓ uc1_harness:first_invocation
  ✓ uc1_harness:report_html_structure
```

**What each test label means:**

| Test label | What it checks | How your spec controls it |
|---|---|---|
| `happy_path` | Your Test 1 example → skill returns success | Your "Example: Happy Path" section |
| `missing_inputs` | Empty event → 400 error | Your "required" field markings |
| `contract_fields` | Response has skill_id, status, outputs | Built into every skill automatically |
| `government_not_applicable` | customer_type=government → not_applicable | Your "Business Rules" section |
| `requires_customer_id` | Empty harness event → error | Harness input table, Required=yes |
| `first_invocation` | Fresh customer → status=paused | `human_input_phase: 3` in front matter |
| `report_html_structure` | HTML report has all required sections | Your "Report Sections" table |

If a test fails, the output shows exactly what came back vs. what was expected.
You fix the spec, rerun the generator, and the test re-runs automatically.

---

## Anatomy of a Spec File — What Each Section Generates

Here is the direct mapping so you understand what each line you write
turns into in production code:

```
Spec section                    → What it generates
────────────────────────────────────────────────────────────
skill_id: SK-06                 → Lambda function name: llmwiki-skill-sk06-*
                                  SSM parameter: /llmwiki/skills/sk-06/arn
                                  CloudWatch log group: /aws/lambda/llmwiki-skill-sk06-*

tier: 3                         → Lambda memory: 256 MB / timeout: 60s
                                  (tier 1 gets 512 MB / 300s)

use_case_tags: [UC5]            → DynamoDB skill registry entry for UC5

What It Needs: customer_id      → body.get("inputs", {}).get("customer_id", "").strip()
  (required)                      if not customer_id: return _respond(400, error)

What It Needs: customer_type    → body.get("inputs", {}).get("customer_type", "payer")
  (optional, default "payer")

Business Rule:                  → if customer_type == "government":
  "If government → not_applicable"   return _skill_response(version, "not_applicable", ...)

Business Rule:                  → if len(claim_lines) > 500:
  "Maximum 500 claim lines"          raise _SkillError("claim_lines exceeds maximum", 400)

Error Handling:                 → try:
  "Soft failure: wiki_query           result = wiki_query(...)
   low confidence → treat as          if result.get("confidence") == "low":
   no prior auth"                         warnings.append("low confidence...")
                                           prior_auth_found = False

Error Handling:                 → except _SkillError as e:
  "Hard failure: empty claim_lines"       return _respond(e.status_code, {"error": str(e)})

What It Calls: dynamodb_write   → dynamodb = boto3.resource("dynamodb")
                                  + IAM policy: dynamodb:PutItem, dynamodb:UpdateItem
                                  + Terraform: aws_iam_role_policy attachment

What It Calls: sns_publish      → sns = boto3.client("sns")
                                  + IAM policy: sns:Publish
                                  + env var: SNS_TOPIC_ARN

Example: Happy Path             → def test_happy_path(): event = {your example input}
                                  assert result["status"] == "ready"

requires_human_input: true      → pause/resume logic in lambda_handler
human_input_phase: 3              status="paused" + question returned on first call
                                  status="completed" on resume call

Report Sections table           → _build_report_html() with exactly those sections
                                  in that order, with colored KPI badges
```

---

## Common Mistakes (and How to Avoid Them)

**Mistake 1 — Inputs too vague**

Bad:
```
## What It Needs
- customer info
- claim data
```

Good:
```
## What It Needs
- customer_id (string, required) — from SK-01 output.customer_id
- claim_batch_id (string, required) — user provides at workflow start
- claim_lines (list of objects, required) — each has claim_id, service_date,
  diagnosis_code (string), amount (float)
```

The generator needs exact names and types to produce correct code.

---

**Mistake 2 — Business rules that are too general**

Bad:
```
## Business Rules
- Handle high-value claims differently
```

Good:
```
## Business Rules
- If amount > 50000 AND prior auth cannot be confirmed → add as BLOCKING issue
- If amount > 50000 AND wiki_query returns confidence=high confirming auth → pass
```

Rules become `if` guards in the code. "Differently" doesn't compile.

---

**Mistake 3 — Happy path example with fake or trivial data**

Bad:
```
## Example: Happy Path
Input: { "customer_id": "test", "claim_lines": [] }
Output: { "status": "success" }
```

Good:
```
## Example: Happy Path
Input:
  customer_id: "bcbs-mn-001"
  claim_batch_id: "BATCH-2026-0519-001"
  claim_lines:
    - {claim_id:"CLM-001", service_date:"2026-05-01",
       diagnosis_code:"Z00.00", amount:450.00}
Output:
  status: "ready"
  readiness_score: 100
  blocking_issues: []
  lines_checked: 1
  lines_ready: 1
```

The test runner literally runs your example as a test. Empty claim_lines
triggers the hard-failure path, not the happy path.

---

**Mistake 4 — Forgetting the edge case**

Every skill needs at least one case where the input is unusual or incomplete.
This is where bugs hide. The most valuable edge cases are:

- The "not applicable" exemption (government, test, cancelled)
- An input that exceeds a limit (500 claim lines, 90-day cutoff)
- A required downstream service returning low confidence or an error
- The human-input step receiving an empty or one-word answer

---

**Mistake 5 — Writing a new skill for something SK-02 already does**

If your step is "look up whether X exists in our knowledge base" → use SK-02,
not a new skill. The generator will call the existing `wiki_query` Lambda.
Only write a new skill when the logic after the lookup is custom.

---

## Quick Reference: File Naming and Location

```
wiki_seed/skills/
│
├── uc-01-brief.md             ← Level 1: UC Brief (start here)
├── wf-UC1-sales-to-service.md ← Level 2: Workflow Spec
├── sk-01-*.md through sk-05-* ← Existing skills (do not modify)
├── sk-06-claim-readiness.md   ← Level 3: Your new skill spec
└── bringyourskill_harness.md  ← This guide
```

File naming rules:
- UC Brief: `uc-NN-short-name.md` (NN = use case number)
- Workflow Spec: `wf-UCNN-workflow-name.md`
- Skill Spec: `sk-NN-skill-name.md` (NN = next available after SK-05)

---

## Checklist Before You Hand Off a Spec

Use this checklist to review your spec before running the generator.
Every checked box is a test that will pass automatically.

**UC Brief (Level 1)**
- [ ] Business problem is explained in one paragraph — no jargon
- [ ] Every step has an explicit failure mode: "stop" or "continue" or "alert"
- [ ] The step that pauses for human input is clearly identified
- [ ] The output (what the user sees/downloads) is described

**Workflow Spec (Level 2)**
- [ ] Every input field has a name (snake_case), type, and required/optional
- [ ] Every step has a `Gating rule` and `On failure` value
- [ ] The `Output fields` from each step list the exact field names
- [ ] Decision logic (if confidence=high → skip step N) is explicit
- [ ] Report Sections table is complete with data source per section

**Skill Spec (Level 3)**
- [ ] `Business Rules` section has at least 3 explicit if-then rules
- [ ] Happy Path example has realistic data (not "test"/"foo")
- [ ] Happy Path example output lists all key output fields with real values
- [ ] Edge Case example covers the "not applicable" or over-limit case
- [ ] `Business-Readable Tests` section has T1 through T4
- [ ] Every required input is marked `required`; optional inputs have defaults

**Test Cases**
- [ ] T1 Happy path: normal inputs → expected success output
- [ ] T2 Missing input: no required field → 400 error with field name
- [ ] T3 Not-applicable rule: exempt customer type → not_applicable
- [ ] T4 Hard failure: dangerous input (empty list, invalid type) → error + alert

---

## End-to-End Timeline

| When | Who | What happens |
|---|---|---|
| Day 0 | Business Owner | Writes Level 1 UC Brief (1 hour) |
| Day 0 | Platform Team | Reviews brief, identifies skills needed |
| Day 1 | Business Owner + Platform | Co-authors Level 2 Workflow Spec |
| Day 1 | Business Analyst | Writes Level 3 Skill Specs for any new skills |
| Day 1 | Platform | Runs `generate_pipeline.py` — code + tests generated |
| Day 1 | Business Owner | Reviews test results against their test cases |
| Day 2 | Platform | Fixes any spec gaps, reruns generator |
| Day 2 | Business Owner | Signs off on test results |
| Day 2 | Platform | Runs `--deploy` — Lambda is live in AWS |
| Day 3 | Business Owner | Runs the agent end-to-end in the Spec Studio UI |

From spec to live agent: **2 working days**.
From change-your-spec to re-deployed agent: **under 1 hour**.

---

## The Change Loop: Modifying a Spec After Deployment

This is the key promise of the system: **change the .md, not the code.**

```
You edit wf-UC1-sales-to-service.md
    ↓
Add a new step, or change a business rule, or add a report section
    ↓
python3 scripts/generate_harness.py --spec wiki_seed/skills/wf-UC1-sales-to-service.md --deploy
    ↓
New Lambda is deployed in ~5 minutes
All tests re-run automatically against the new code
```

What you should change in the spec vs. what you should call the platform for:

| Change | Do it yourself in the .md | Call the platform |
|---|---|---|
| Add a report section | Yes | No |
| Change a business rule (amount threshold, customer type) | Yes | No |
| Add a new input field | Yes | No |
| Change which step pauses for human input | Yes | No |
| Add a new skill call within an existing step | Yes | No |
| Add a completely new skill (new Lambda) | Write sk-NN spec | Platform deploys infra |
| Change DynamoDB table structure | No | Yes |
| Change IAM permissions | No | Yes |

---

## Getting Help

**To start a new use case:** Drop your UC Brief in `wiki_seed/skills/` and
open a pull request. The platform team will review within 24 hours.

**To run the generator yourself:**
```bash
# 1. Make sure you have AWS SSO active
aws sts get-caller-identity --profile tzg-sandbox

# 2. Generate from your spec
python3 scripts/generate_pipeline.py \
    --brief wiki_seed/skills/uc-NN-your-brief.md \
    --region us-east-1 \
    --profile tzg-sandbox

# 3. Review the test results — all should be green before deploying
```

**To see the Spec Studio UI** (edit specs in a browser, click Generate/Test/Deploy):
```bash
streamlit run streamlit/pages/spec_studio.py
```

**If tests are failing:** Read the error — it will say exactly which of your
test cases failed and what the agent returned instead. Nine times out of ten,
the fix is in the Business Rules section of your spec.
