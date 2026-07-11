---
use_case_id: UC1
title: "Sales-to-Service Handoff"
domain: customer-onboarding
version: "1.0"
author: "Sales Operations / Delivery Team"
---

# UC1 — Sales-to-Service Handoff

## What Is This?

When a deal closes, the sales team hands off a new customer to the delivery
(services) team. Today this is a 3-day back-and-forth of emails and spreadsheets
between sales, delivery, and the customer. Things get lost. The delivery team
starts without the full picture.

This use case automates the handoff. The agent reads everything the wiki knows
about the customer, asks the sales team 3 targeted questions, detects what the
wiki doesn't know yet, and produces a business-ready handoff report.

**Who uses it:** Account Managers, Delivery Managers, Sales Operations  
**What it replaces:** Manual handoff checklist, email chain, SOW summary doc  
**Time saved:** From 3 days to under 30 minutes  

---

## What Do You Need to Start?

To run this use case you provide:

- **Customer name** — e.g. "BlueCross BlueShield Minnesota"
- **Customer ID** — e.g. "bcbs-mn-001"
- **Product(s) in scope** — what was sold
- **SOW Reference** — contract number

That's it. The agent does the rest.

---

## What Does the Agent Do? (8 steps, in plain English)

### Step 1 — Look Up the Customer
The agent searches the wiki for everything already known about this customer:
previous engagements, prior issues, products used, key contacts.
- **If the customer is new:** Proceeds with a clean slate, flags as new.
- **If the customer has history:** Loads all known facts as context.
- **If this fails:** Stop — we need to know if this is a known customer.

### Step 2 — Classify the Engagement
The agent reads the customer context and decides: how risky is this deal?
Returns: Risk Tier (HIGH/MEDIUM/LOW), Go-Live Urgency, and Implementation Complexity.
- Uses the standard classification framework: new customers default to HIGH risk.
- **If this fails:** Stop — classification drives everything downstream.

### Step 3 — Ask the Sales Team (Human Input — PAUSES HERE)
Based on the risk tier and complexity, the agent generates exactly 3 targeted
questions for the sales team. The workflow pauses until the sales team answers.

Examples of questions it asks:
- "Were there any prior implementation attempts? If so, what went wrong?"
- "Who is the executive sponsor and do they have full decision authority?"
- "Are there any contract penalty clauses tied to the go-live date?"

Once the sales team submits answers, the workflow continues automatically.

### Step 4 — Load the Delivery Playbook
The agent loads the UC1 delivery playbook from the wiki: the standard steps,
checklists, and known pitfalls for this type of implementation.
- **If the playbook is empty:** Records "0 steps" and continues (non-blocking).

### Step 5 — Run Risk Analysis
The agent queries the wiki: "What are the key delivery risks for this customer
and product type?" It returns a confidence score (high/medium/low) and a
plain-English answer with any action items the delivery team should act on.
- **If confidence is low or answer is empty:** Triggers Step 6 (gap detection).
- **If confidence is high:** Skips Step 6.

### Step 6 — Find What the Wiki Doesn't Know (Gap Detection)
When the wiki can't answer the risk question confidently, the agent generates
specific gap questions and sends each one to the gap-detection skill. This
skill looks at what's missing, writes it to the gap log, and returns a list of
blocking issues the delivery team must resolve before go-live.
- **If confidence was high in Step 5:** Skipped entirely.
- Each gap is tagged: blocking (must resolve) or non-blocking (nice to have).

### Step 7 — Populate the Customer Template
The agent tries to fill in the standard onboarding persona template using
everything gathered so far. Returns a percentage completion and a list of
fields still missing.
- **If the template doesn't exist in the wiki:** Records 0% and continues.

### Step 8 — Write the Handoff Report
The agent writes:
1. A full handoff brief to the wiki (becomes searchable for future agents).
2. A business-ready HTML report (downloadable by the delivery manager).

The report is the key deliverable — it goes directly to the delivery team
before the kickoff call.

---

## What Does the Output Look Like?

**Handoff Report (HTML — downloaded by delivery manager)**

The report shows:
- Customer name, product, SOW reference, report date
- KPI bar: Risk Tier · Go-Live Urgency · Complexity · Wiki Confidence · Knowledge Gaps · Template Fill %
- Section 1: Customer Overview (what we know about them)
- Section 2: Engagement Classification (why this risk tier)
- Section 3: Sales Team Context (the 3 answers from the sales team)
- Section 4: Delivery Playbook (standard steps to follow)
- Section 5: Risk Analysis (what the wiki says about risks + action items)
- Section 6: Knowledge Gaps (a table of gaps with what needs to be resolved)
- Section 7: Template Status (how complete the onboarding template is)

**Wiki Page** — indexed under `customers/{customer_id}-harness-handoff-{year}.md`  
**Gap Log** — each blocking gap written to DynamoDB `llmwiki-gaps` table

---

## What Are the Rules?

1. The 8 steps always run in order. No skipping, no reordering.
2. Step 3 (human input) is the only step that pauses. The user submits an
   answer through the UI and the workflow resumes automatically.
3. Steps 1 and 2 are hard failures — if either fails, the whole workflow stops.
4. Steps 4, 5, 6, 7 are soft failures — if they fail, the report is generated
   with whatever data is available and the failure is noted.
5. All phase results are saved to DynamoDB after each step so a partial run can
   be inspected or resumed.
6. A new customer (no prior wiki history) automatically gets risk_tier = HIGH.

---

## What Skills Does This Use?

| Step | Skill | Type |
|------|-------|------|
| 1 | SK-01 Customer Briefing Loader | Programmatic |
| 2 | (Bedrock direct call) | LLM single-call |
| 3 | (Human input — built-in pause) | Human input |
| 4 | SK-01 Customer Briefing Loader | Programmatic |
| 5 | SK-02 Knowledge Finder | LLM agent |
| 6 | SK-05 Missing Info Radar | LLM agent (0-3 sub-agents) |
| 7 | SK-04 Template Auto-Fill | LLM agent |
| 8 | SK-03 Knowledge Recorder | Programmatic |

---

## What Workflow File Implements This?

See `wf-UC1-sales-to-service.md` — the detailed technical spec that the
code generator uses to produce the harness Lambda.

---

## What's Next After This?

The handoff brief written in Step 8 becomes the input for:
- **UC2** — Environment Provisioning Agent (reads the wiki page to set up accounts)
- **UC8** — Cutover Readiness Check (uses the gap log to track resolution)
