---
title: "How to Build a New Use Case with Skill Builder, Skill Hub, and Skill Studio"
audience: "Business Analysts, Problem Coordinators, Delivery Managers"
difficulty: "No coding required"
time_to_first_run: "~2 hours"
reference_example: "UC-PM Problem Management (reverse-engineered walkthrough)"
---

# How to Build a New AI Use Case — Business User Guide

This guide walks you through building a new automated use case using the three LLMWiki
workbenches: **Skill Hub**, **Skill Builder**, and **Skill Studio**.
No coding is required. The Problem Management use case (UC-PM) is used throughout
as a worked example so you can see every decision in reverse.

---

## Overview: The Three Workbenches

| Workbench | What You Do | Output |
|---|---|---|
| **Skill Hub** | Discover and test skills that already exist | Reuse decisions |
| **Skill Builder** | Design a new skill from a plain-English spec | New Lambda + spec file |
| **Skill Studio** (Spec Studio) | Wire skills into an 8-phase workflow | Full harness + new agent in the UI |

Think of it as: Hub → Builder → Studio → Done.

---

## Step 1 — Define Your Use Case (15 min)

Before touching any tool, answer four questions:

1. **What problem does a human do today that takes too long?**
   > *Example: Problem Coordinators spend 4–6 hours manually writing RCA documents after each P1 incident.*

2. **What data already exists that an AI could use?**
   > *Example: Incident records, application logs, prior RCA pages in the wiki, KEDB entries.*

3. **What is the human judgment step that should NEVER be automated?**
   > *Example: Approving the final RCA before publication. An AI drafts, a human approves.*

4. **What is the final deliverable?**
   > *Example: A draft RCA document + KEDB entry stored in the wiki, plus an HTML summary report.*

Write these answers in a one-page brief. See `pm-uc-brief.md` for the Problem Management example.

---

## Step 2 — Check the Skill Hub First (10 min)

Go to the **Skills Hub** page in the LLMWiki app.

You will see all deployed skills with live "Try It" buttons:

| Skill | What it does | When to reuse |
|---|---|---|
| SK-01 Customer Briefing Loader | Loads customer history + playbook | Any use case that needs context about the customer |
| SK-02 Knowledge Finder | Searches the wiki for answers | Any use case that needs prior knowledge |
| SK-03 Knowledge Recorder | Saves output to the wiki | Any use case that writes back to the wiki |
| SK-04 Template Auto-Fill | Fills standard document templates | Any use case that produces a structured document |
| SK-05 Missing Info Radar | Identifies what information is missing | Any use case where gaps block the AI |
| SK-06 Problem Classifier | Classifies problems by type and risk | Any problem management or incident use case |

**Decision rule:** If a skill covers your need with 80% fit — reuse it. Don't build a new skill for a minor variation. Use the skill's inputs/outputs as-is and handle any adaptation in your harness logic.

**UC-PM Example:**
- SK-02 (Knowledge Finder) → reused for Step 5 RCA search
- SK-05 (Missing Info Radar) → reused for Step 6 gap detection
- SK-04 (Template Auto-Fill) → reused for Step 7 document population
- SK-03 (Knowledge Recorder) → reused for Step 8 wiki write
- SK-01 (Customer Briefing Loader) → reused for Step 4 prior knowledge
- **SK-06 (Problem Classifier) → NEW — built because no existing skill classified problems**

---

## Step 3 — Build a New Skill (if needed) — Skill Builder (30 min)

Only build a new skill if the Skill Hub doesn't cover your need.

### 3a. Write the Skill Spec

Copy an existing spec from the `problem-mgnt/` folder as a starting point:
```
pm-skill-spec-sk06-problem-classifier.md
```

Replace these sections with your use case:

**What It Does** — 2 sentences max. What action does this skill perform?
> *SK-06: Classifies a problem record into a normalized category and sends an alert for critical severity.*

**What It Needs (Inputs)** — list each field with type and whether it's required
> *problem_id (string, required), severity (string, required), related_records (list, required)*

**What It Produces (Outputs)** — list each output field
> *normalized_category, recurrence_type, risk_tier, classification_confidence, alert_sent*

**Business Rules** — the "if/then" logic in plain English
> *If severity is P1 or High → send SNS alert immediately*
> *If related records contain the word "Repeated" → set recurrence_type = "repeated"*

**Error Handling** — what should fail hard vs. soft
> *Hard: missing problem_id → return 400. Soft: LLM returns unknown category → map to closest + low confidence*

### 3b. Open Skill Builder in the App

Go to **Skill Builder** in the LLMWiki app.

1. Paste your spec into the text area
2. Click **"Map to Existing Skills"** — it will tell you if any existing skill already covers it
3. If no match, click **"Generate Skill"** — this creates the Lambda handler from your spec template
4. The built-in tester appears — paste a sample input and click **Run**
5. Check the output matches your spec. If not, edit the Business Rules in the spec and click **Regenerate**
6. Click **Deploy** when you're satisfied

The skill is now live. It appears in the Skill Hub for the next person to discover.

---

## Step 4 — Design Your 8-Phase Workflow — Skill Studio (45 min)

Every LLMWiki use case follows the same 8-phase locked structure:

| Phase | Type | Always does |
|---|---|---|
| 1 | Programmatic | Load / validate input data |
| 2 | LLM Single | Classify or analyse the input |
| 3 | **Human Input** | **ALWAYS pauses here for human review** |
| 4 | LLM Agent | Load prior knowledge from wiki |
| 5 | LLM Agent | Main AI reasoning / draft |
| 6 | LLM Agent | Detect gaps or validate |
| 7 | LLM Single | Fill output template |
| 8 | Programmatic | Write output, generate report |

### 4a. Assign Skills to Phases

For each phase, decide: which skill handles it, or is it programmatic (no LLM)?

**UC-PM Example:**

| Phase | Name | Skill | Input From | Output To |
|---|---|---|---|---|
| 1 | Problem Record Load | Programmatic | batch_id, problem_id, related_record_ids | Phase 2, 5 |
| 2 | Problem Classification | **SK-06** (new) | Phase 1 records, severity | Phase 3, 5, 8 |
| 3 | SME Context Collection | Human Pause | Phase 1+2 outputs → questions | Phase 5 |
| 4 | Load Prior Knowledge | **SK-01** (reuse) | product, component, category | Phase 5 |
| 5 | RCA Draft | **SK-02** (reuse) | Phase 1+2+3+4 | Phase 6, 7, 8 |
| 6 | Gap Detection | **SK-05** (reuse) | Phase 5 RCA outputs | Phase 7, 8 |
| 7 | Template Fill | **SK-04** (reuse) | Phase 2+5+6 | Phase 8 |
| 8 | Write Draft + Report | **SK-03** (reuse) | All phases | Final output |

5 reused skills + 1 new skill = full 8-phase workflow with 30 min of new build work.

### 4b. Define the Harness Inputs

What does the user (or calling system) provide at the start?

**UC-PM inputs:**
| Field | Description |
|---|---|
| batch_id | Ingest batch (e.g. PM-QNXT-001) |
| problem_id | Problem record ID (e.g. PRB-1001) |
| product | Platform: QNXT, TCS, EAM, or EDM |
| severity | P1 / P2 / P3 / High / Medium / Low |
| component | Affected module (e.g. Member Update API) |
| related_record_ids | List of linked incident/log IDs |

### 4c. Define the Run ID and State

Every harness needs a unique run identifier for DynamoDB tracking:

```
UC-PM: run_id = f"{batch_id}#{problem_id}"
UC1:   run_id = f"{customer_id}#{timestamp}"
```

Your run ID should combine the primary entity ID + the batch or date so runs are unique and queryable.

### 4d. Open Spec Studio in the App

Go to **Spec Studio** in the LLMWiki app.

1. Click **"New Use Case"** and choose a template (clone UC-PM for a problem-type workflow)
2. Fill in: use case name, harness lambda name, DynamoDB table name, S3 output bucket prefix
3. For each of the 8 phases: pick the skill from the dropdown or mark as "programmatic"
4. Set the human pause phase (almost always Phase 3)
5. Set severity-based alert rules (which severity levels trigger SNS)
6. Set output rules (draft-only? auto-publish? report format?)
7. Click **"Generate Workflow"** — this creates:
   - The harness Lambda handler
   - The DynamoDB table Terraform resource
   - The `workflow-spec.md` YAML file
   - A new entry in the Streamlit AGENTS registry
8. Click **"Deploy"** — terraform apply runs automatically

Your use case is now live in the Hard Harness Demo dropdown.

---

## Step 5 — Seed Your Use Case Bucket (5 min)

Each use case gets its own S3 bucket for outputs and reference documents. Only put use-case-specific files in it — no cross-use-case content.

**UC-PM bucket:** `llmwiki-problem-mgnt-278e7e22`

Files seeded:
```
specs/pm-uc-brief.md              ← the one-pager you wrote in Step 1
specs/pm-workflow-spec.md         ← generated by Skill Studio
specs/pm-skill-spec-sk06.md       ← generated by Skill Builder
docs/pm-harness-overview.md       ← how the harness works
raw/pm-ingest-templates.xlsx      ← sample data for demos
```

No S2S files. No generic wiki content. Clean separation means future agents looking in this bucket only find PM content.

---

## Step 6 — Test End to End (20 min)

Go to **Hard Harness Demo** in the LLMWiki app and select your new agent from the dropdown.

### Test Script

**Test 1 — First call (phases 1–3, should pause):**
1. Enter your Batch ID, Component, Product, and Problem ID in the sidebar
2. Click **Start Harness**
3. Expected: "paused" status, 3 SME questions displayed
4. Verify: classification looks correct for your domain

**Test 2 — Resume (phases 4–8, should complete):**
1. Answer the 3 questions in the text area
2. Click **Submit answers & run phases 4–8**
3. Expected: all 8 phases tick green, report URL appears
4. Click **Download Report** — verify the HTML report has all 10 sections

**Test 3 — Edge cases:**
- Submit with a missing required field → should get a 400 error message
- Submit with an invalid product value → should get a validation error
- Resume when no paused run exists → should start fresh

**UC-PM Test Results (reference):**
- Phase 1+2: ~11 seconds
- Phase 4-8: ~47–70 seconds depending on LLM response time
- Total wall clock: under 90 seconds for a complete 8-phase RCA

---

## Step 7 — Add to Production (optional, coordinator only)

When the use case is validated:

1. Email the workflow spec (`workflow-spec.md`) to the Platform team
2. They will add SNS email subscriptions for the alert topic
3. They will set up IAM access for the production role
4. They will move the S3 bucket to production with versioning enabled

You do not need to do anything else — the platform is already production-ready.

---

## Quick Reference: What Code Lives Where

```
lambda/
├── common/                  ← Shared utilities (Bedrock, DynamoDB, S3 helpers)
│   ├── llmwiki_common.py    ← All handlers can import from here
│   └── harness_common.py    ← Shared harness state management
│
├── apps/
│   ├── s2s/                 ← UC1 Sales-to-Service (your reference example)
│   └── problem_mgnt/        ← UC-PM Problem Management (this use case)
│       ├── harness/pm_harness/    ← The 8-phase workflow engine
│       └── skills/problem_classifier/  ← SK-06 (use-case-specific skill)
│
└── skills_shared/           ← SK-01 through SK-05 (reused by all apps)
```

When you build a new use case, you only need to create a new `apps/<your_uc>/` folder.
Everything in `skills_shared/` and `common/` is already there for you to use.

---

## FAQ

**Q: Does every use case need all 8 phases?**
A: Yes. The 8-phase structure is locked. If a phase isn't meaningful for your use case,
mark it as "pass-through" — it runs instantly and produces an empty result. The lock
ensures that every agent in the platform is auditable and the human-in-the-loop is
never skipped.

**Q: Can I have more than one human pause?**
A: Phase 3 is always the human pause. If you need a second review point, add a
Phase 3b question or increase the scope of Phase 3's questions. Do not move the
pause to a different phase number.

**Q: Can the AI automatically publish the RCA to the wiki?**
A: No. All output is always draft status. A human coordinator must review and
explicitly publish. This is not a configurable setting — it is a governance rule.

**Q: What if I need a skill that isn't in the Hub and doesn't fit the existing patterns?**
A: Build it using Skill Builder. Follow the same spec template. The only constraint
is that every skill must follow the standard contract:
`{skill, version, inputs} → {skill, status, outputs, latency_ms}`.
This contract is what makes skills composable — any harness can call any skill.

**Q: How do I handle a use case that spans multiple products (QNXT + TCS)?**
A: Add a `products` list input to your harness and run the classification phase once
per product. The run ID should include both product codes. The report consolidates
findings across both.
