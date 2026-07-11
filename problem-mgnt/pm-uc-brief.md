---
use_case_id: UC-PM
title: "Problem Management — AI-Assisted RCA and Knowledge Capture"
domain: problem-management
platforms: [QNXT, TCS, EAM, EDM]
---

# UC-PM — Problem Management: AI-Assisted RCA and Knowledge Capture

## What Is This?

Trizetto platforms — TCS, QNXT, EAM, and EDM — experience recurring incidents and operational disruptions.
Today, Root Cause Analysis (RCA) is written manually by operations staff, known-error reuse is weak, and insights stay siloed inside individual problem records. This means the same underlying issues surface repeatedly, each time consuming time that could be avoided.

This agent takes a set of problem records, related incidents, and supporting logs for a given batch, retrieves everything the wiki knows about similar prior issues, and produces a structured RCA draft, a Known Error Database (KEDB) entry, and a list of corrective actions — ready for human review and approval. After approval the outputs are written back to the wiki so future problems can build on them.

Who uses it: Operations Managers, Problem Coordinators, Platform SMEs  
What it replaces: Manual RCA writing, ad-hoc email chains, spreadsheet-based KEDB  
Time saved: From 1–3 days of manual RCA effort to a reviewed draft in under 2 hours

## What Do You Need to Start?

- `batch_id` — the ingest batch identifier, e.g. `PM-QNXT-001`
- `product` — the platform being analyzed: `QNXT`, `TCS`, `EAM`, or `EDM`
- `problem_id` — the primary problem record ID, e.g. `PRB-1001`
- `related_record_ids` — list of incident and log record IDs linked to this problem, e.g. `["INC-QNXT-1042", "APPLOG-0001"]`
- `severity` — overall severity level: `P1`, `P2`, `P3`, or `High`, `Medium`, `Low`
- `component` — the affected module or process, e.g. `Member Update API`, `Claims Pricing Batch`

## What Does the Agent Do? (Steps in plain English)

### Step 1 — Load Problem Records
The agent loads the problem record, all linked incidents, and supporting log entries identified by the batch ID and record IDs provided.
If the problem ID is not found → STOP. We cannot proceed without the primary record.
If related records are partially missing → continue with what is available and flag what is missing.

### Step 2 — Classify and Prioritize
The agent classifies the problem by severity, affected component, normalized issue category (e.g. Batch Processing, Integration, Workflow), and whether the issue is a repeated occurrence or unique.
If classification cannot be determined → continue with "Unknown" category and flag for human review.

### Step 3 — SME Context (PAUSES HERE)
The agent generates up to 3 targeted questions for the Problem Coordinator or SME — focused on information gaps found in Steps 1 and 2 (e.g. missing workaround details, unclear recurrence pattern, unknown change that preceded the incident).
The workflow pauses until the SME submits answers, then continues automatically.

### Step 4 — Load Prior Knowledge
The agent queries the wiki for prior RCA pages, KEDB entries, and playbooks related to the same component, issue category, and product. It retrieves any previously recorded workarounds or permanent fixes.
If the wiki returns nothing → continue with an empty prior-knowledge set.

### Step 5 — Draft RCA and Detect Patterns
Using the problem records, SME context, and retrieved wiki knowledge, the agent drafts a structured RCA. It identifies whether this problem is part of a known recurring pattern across products or time periods.
If pattern confidence is low → include a note in the RCA flagging uncertainty.

### Step 6 — Identify Knowledge Gaps
The agent checks the drafted RCA for missing root cause evidence, missing permanent fix details, and missing monitoring or prevention steps. It produces a gap list.
If no gaps are found → this step produces an empty gap list and continues.

### Step 7 — Fill RCA and KEDB Templates
The agent populates the standard RCA template and the KEDB entry template using the drafted content from Steps 5 and 6.
If a template field cannot be filled → mark it as "Pending — requires SME input" and continue.

### Step 8 — Write and Route for Review
The agent writes the completed RCA page and KEDB entry to the wiki in draft status.
It produces a summary report for the Problem Coordinator showing: RCA draft, KEDB entry, corrective action recommendations, evidence pack, and gap list.
The output is NOT published until a human approves it. Approval triggers a status change from "draft" to "published" in the wiki.

## What Does the Output Look Like?

A downloadable HTML report and a wiki-stored draft containing:
1. Problem summary (product, component, severity, recurrence type)
2. Root cause analysis narrative
3. Timeline of linked incidents and logs
4. Pattern analysis (repeated vs. unique; links to prior similar problems)
5. KEDB entry (short-form known-error record)
6. Corrective action recommendations (workaround + permanent fix)
7. Gap list (what is still unknown or missing)
8. Evidence pack (list of source records used)

## What Are the Rules?

- Step 3 always pauses for human (SME) input before RCA drafting begins.
- RCA and KEDB outputs are always written in draft status — never auto-published.
- A problem record that spans multiple products must be run once per product (one `product` value per invocation).
- If a problem is classified as `P1` or `High` severity, an SNS alert is sent to the operations team at Step 2.
- The agent must never overwrite an existing published RCA page. A new draft version is created instead.
- Maximum 50 related records per invocation. Larger batches must be split.

## What Skills Does This Use?

| Phase | Skill Used |
|---|---|
| Step 1 — Load Problem Records | Programmatic (direct data load) |
| Step 2 — Classify and Prioritize | SK-06 Problem Classifier (new) |
| Step 3 — SME Context | Human Input (built into harness) |
| Step 4 — Load Prior Knowledge | SK-01 Customer Briefing Loader |
| Step 5 — Draft RCA and Detect Patterns | SK-02 Knowledge Finder |
| Step 6 — Identify Knowledge Gaps | SK-05 Missing Info Radar |
| Step 7 — Fill RCA and KEDB Templates | SK-04 Template Auto-Fill |
| Step 8 — Write and Route for Review | SK-03 Knowledge Recorder |

SK-06 (Problem Classifier) is a new skill required for this use case. Specs for SK-06 are in `pm-skill-spec-sk06-problem-classifier.md`.
