---
workflow_id: WF-UC1
use_case: UC1
business_name: "Sales-to-Service Handoff"
domain: customer-onboarding
version: "1.0"
requires_human_input: true
human_input_phase: 3
harness_lambda: llmwiki-harness-uc1
harness_table: llmwiki-harness-runs
workspace_table: llmwiki-workspace-files
report_bucket_prefix: wiki/reports
wiki_page_prefix: customers
---

# Sales-to-Service Handoff Workflow

## Business Goal

Automates the 3-day manual Sales-to-Service handoff into a 30-minute
human-in-the-loop workflow. Given a customer ID and SOW reference, the agent
loads all known customer history, classifies the engagement, pauses for
a single targeted sales-team Q&A, performs risk analysis and gap detection,
attempts template population, and writes a business-ready HTML handoff report
and a wiki knowledge page.

**Who uses it:** Account Managers, Delivery Managers, Sales Operations  
**What it replaces:** Manual handoff email chain, SOW summary spreadsheet  
**Output:** Downloadable HTML report + wiki page + DynamoDB gap log

---

## Harness Inputs (provided at workflow start)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| customer_id | string | yes | Canonical customer identifier, e.g. "bcbs-mn-001" |
| customer_name | string | yes | Customer legal name for the report header |
| product | string | yes | Product(s) sold, plain English |
| sow_reference | string | yes | Contract reference number |
| human_context | string | no | Sales team answer (empty on first call — harness pauses at Phase 3) |

---

## Workflow Steps

### Step 1: Customer Wiki Lookup

| Field | Value |
|-------|-------|
| Skill | SK-01 (ContextBootstrapSkill) |
| Type | programmatic |
| Lambda call | PLAYBOOK_FUNCTION, action=get_customer |
| Input from | harness: customer_id |
| Output to | Step 2, Step 4, Step 8 |
| Gating rule | None — always runs first |
| On failure | abort_workflow (raise _PhaseError) |

**What this step does:**
Calls the playbook Lambda with `action=get_customer` to retrieve everything
the wiki knows about this customer: prior engagements, known issues, products
used, key contacts, and any existing overview text.

**Output fields used downstream:**
- `customer_status` — "active", "new", "no-history" (→ Phase 2 context)
- `pages_found` — count of wiki pages found
- `key_facts` — list of important bullet points from customer history
- `overview` — synthesized text overview of the customer
- `products_in_scope` — list of known products

**Decision logic:**
- If `pages_found == 0` → customer is new; Step 2 defaults to risk_tier=HIGH

---

### Step 2: Engagement Classification

| Field | Value |
|-------|-------|
| Skill | bedrock_claude (direct call, no skill Lambda) |
| Type | llm_single |
| Input from | Step 1 output (full JSON summary) |
| Output to | Step 3, Step 7, Step 8 |
| Gating rule | Step 1 must complete |
| On failure | abort_workflow |

**What this step does:**
Single Bedrock call. Feeds Phase 1 output as context, asks Claude to classify
the engagement. Returns exactly this JSON:

```json
{
  "customer_type": "payer|provider|pharmacy|government",
  "products": ["list of products in scope"],
  "risk_tier": "HIGH|MEDIUM|LOW",
  "go_live_urgency": "HIGH|MEDIUM|LOW",
  "implementation_complexity": "HIGH|MEDIUM|LOW",
  "rationale": "2-3 sentence explanation of risk classification"
}
```

**Business rules:**
- If no prior history (Phase 1 pages_found=0) → default risk_tier=HIGH
- New customers are always HIGH complexity until proven otherwise

---

### Step 3: Human Input — Sales Team Q&A

| Field | Value |
|-------|-------|
| Skill | built-in (pause/resume) |
| Type | llm_human_input |
| Input from | Step 2 output: risk_tier, implementation_complexity, products |
| Output to | Step 5, Step 7, Step 8 |
| Gating rule | Step 2 must complete |
| On failure | N/A — human either answers or run stays paused |

**What this step does:**
On first invocation (human_context empty): Generates exactly 3 targeted
questions for the sales team based on the risk tier and complexity, then
PAUSES the workflow and returns `status=paused` with the questions.

On resume invocation (human_context filled): Records the human answer and
continues to Step 4.

**Question generation rules:**
- Always ask about executive sponsor and decision authority
- Always ask about go-live timeline commitments and contract constraints
- If risk_tier=HIGH: ask about prior implementation attempts and lessons learned
- If complexity=HIGH: ask about data migration constraints and legacy system dependencies

**Pause state persisted to DynamoDB:**
- `status=paused`, `current_phase=3`, `phase3_question` (the generated questions text)

**How answers flow forward:**
- Full human answer stored as `summary` in phase3 result
- Passed to Phase 5 risk query as `Customer context: {summary}`
- Passed to Phase 7 available_context as `human_context`

---

### Step 4: Load Delivery Playbook

| Field | Value |
|-------|-------|
| Skill | SK-01 (ContextBootstrapSkill) |
| Type | programmatic |
| Lambda call | PLAYBOOK_FUNCTION, action=get_playbook |
| Input from | harness: use_case="UC1" |
| Output to | Step 8 |
| Gating rule | Step 3 must complete |
| On failure | skip (log warning, continue with playbook_steps=0) |

**What this step does:**
Loads the UC1 delivery playbook: structured step-by-step guide for this type
of implementation. Returns a `steps` list and `pages_loaded` count.

**Business rule:**
- If wiki has no UC1 playbook pages → `playbook_steps=0`; report shows "Playbook not yet seeded"
- Non-blocking — a missing playbook does not stop the workflow

---

### Step 5: Risk Analysis

| Field | Value |
|-------|-------|
| Skill | SK-02 (WikiQuerySkill) |
| Type | llm_agent |
| Lambda call | SK02_FUNCTION |
| Input from | Step 3 output: summary; harness: customer_id, product |
| Output to | Step 6, Step 7, Step 8 |
| Gating rule | Step 4 must complete |
| On failure | skip (confidence=low, empty answer, continue to Step 6) |

**What this step does:**
Queries the wiki with: "What are the key delivery risks and success factors for
a new {product} implementation for a healthcare payer? Customer context: {phase3_summary}"

Domain filter: `customer-onboarding`

**Output fields:**
- `confidence` — "high", "medium", "low"
- `answer` — plain-English risk analysis text
- `action_items` — list of recommended actions for delivery team
- `wiki_page_count` — number of wiki pages consulted

**Decision logic:**
- If `confidence == "high"` → skip Step 6
- If `confidence in ("medium", "low")` → proceed to Step 6

---

### Step 6: Knowledge Gap Detection

| Field | Value |
|-------|-------|
| Skill | SK-05 (GapDetectionSkill) |
| Type | llm_agent (0-3 sub-invocations) |
| Lambda call | SK05_FUNCTION (called up to 3 times, once per gap question) |
| Input from | Step 5 output: confidence, answer, action_items |
| Output to | Step 7, Step 8 |
| Gating rule | Only runs if Step 5 confidence != "high" |
| On failure | skip (log warning, continue with gaps=[]) |

**What this step does:**
When the wiki's risk answer has low/medium confidence, this step derives 1-3
specific gap questions from the action items, then calls SK-05 once per
question. Each SK-05 call returns a list of gaps (what the wiki is missing)
and writes them to the DynamoDB gap log.

**Gap question derivation:**
1. If action_items contain "?" characters → use them directly as gap questions
2. Otherwise → call Bedrock to synthesize gap questions from the answer text
3. Fallback: use hardcoded questions about implementation standards and data migration

**Gap object structure:**
```json
{
  "title": "Plain-English name of the gap",
  "gap_type": "missing-artifact|missing-standard|missing-customer-history",
  "blocking": true|false,
  "human_prompt": "Exact question to ask a human to fill this gap"
}
```

**Output fields:**
- `gaps` — list of gap objects
- `gap_count` — total number of gaps
- `blocking_count` — count of gaps with blocking=true
- `sub_agents_run` — number of SK-05 invocations

---

### Step 7: Template Population

| Field | Value |
|-------|-------|
| Skill | SK-04 (ArtifactResolutionSkill) |
| Type | llm_agent |
| Lambda call | SK04_FUNCTION |
| Input from | Steps 1-6 outputs (full context bundle) |
| Output to | Step 8 |
| Gating rule | Step 6 must complete (or be skipped) |
| On failure | skip (found=false, completion_pct=0, continue) |

**What this step does:**
Builds a context bundle from all prior phases and asks SK-04 to find and
populate the `persona-template` artifact with this customer's data.

**Context bundle passed to SK-04:**
- customer_id, customer_status, key_facts, products, risk_tier, go_live_urgency
- implementation_complexity, rationale (from Phase 2)
- human_context, risk_answer, action_items (from Phases 3+5)
- gaps, blocking_gaps count (from Phase 6)

**Output fields:**
- `found` — true/false (false if no persona-template in wiki)
- `completion_pct` — 0-100
- `populated_fields` — list of field names that were filled
- `missing_fields` — list of field names still empty

---

### Step 8: Write Handoff Report

| Field | Value |
|-------|-------|
| Skill | SK-03 (WikiContributeSkill) |
| Type | programmatic |
| Lambda calls | SK03_FUNCTION (wiki index) + s3_client (report files) |
| Input from | All prior phase outputs |
| Output to | S3 HTML report + wiki page + presigned download URL |
| Gating rule | All prior required steps must be complete |
| On failure | retry once, then alert (non-blocking for report) |

**What this step does:**
1. Builds a Markdown handoff brief from all 7 phase outputs.
2. Calls SK-03 to index it in the wiki under `customers/{customer_id}-harness-handoff-{year}`.
3. Generates a styled HTML report and writes to S3 at `wiki/reports/{customer_id}-handoff-report-{date}.html`.
4. Generates a plain-text fallback report at `wiki/reports/{customer_id}-handoff-report-{date}.txt`.
5. Returns a presigned download URL (12-hour expiry) for the HTML report.

---

## Report Sections (HTML Output)

The generated HTML report MUST contain these sections in order:

| # | Section Title | Data Source | Render As |
|---|---------------|-------------|-----------|
| KPI | Risk Tier | phase2.risk_tier | Colored badge (RED/ORANGE/GREEN) |
| KPI | Go-Live Urgency | phase2.go_live_urgency | Colored badge |
| KPI | Complexity | phase2.implementation_complexity | Colored badge |
| KPI | Wiki Confidence | phase5.confidence | Colored badge |
| KPI | Knowledge Gaps | len(phase6.gaps) + phase6.blocking_count | "N (M blocking)" |
| KPI | Template Fill | phase7.completion_pct | "N%" |
| 1 | Customer Overview | phase1.overview + phase1.key_facts | Paragraph + bullet list |
| 2 | Engagement Classification | phase2.rationale + customer_type/risk_tier/urgency/complexity | Paragraph + metadata table |
| 3 | Sales Team Context | phase3.summary | Paragraph |
| 4 | Delivery Playbook | phase4.playbook_steps + phase4.pages_loaded | Metadata table |
| 5 | Risk Analysis | phase5.confidence + phase5.answer + phase5.action_items | Badge + paragraph + bullet list |
| 6 | Knowledge Gaps | phase6.gaps list | Data table (Gap / Type / Action Required) |
| 7 | Persona Template Status | phase7.completion_pct + populated/missing counts | Progress bar + counts |

---

## Human Input Step — Full Detail

**When it fires:** After Step 2 (always — risk classification is always needed)

**What the agent knows at pause time:**
- risk_tier, implementation_complexity, products (from Step 2)
- Optional: customer history from Step 1 if customer is known

**Questions to generate (exactly 3):**
Generate these based on risk_tier and complexity:
- If risk_tier=HIGH → "Were there any prior implementation attempts with this customer? What were the outcomes?"
- If complexity=HIGH → "What are the data migration or legacy system constraints that delivery should know about?"
- Always → "Who is the executive sponsor? Do they have full decision authority, or is there an approval committee?"
- Always → "What is the contractual go-live date, and are there penalty clauses if it's missed?"

Pick the 3 most relevant from the above based on classification.

**UI behavior:**
- Show the 3 questions as a numbered list
- Free-text area for the sales team to answer all 3
- "Submit and Continue" button triggers workflow resume

**How the answers flow forward:**
- Stored verbatim as `human_context` (first 500 chars as `summary`)
- Passed to SK-02 query in Phase 5 as customer context
- Passed to SK-04 context bundle in Phase 7

---

## Composition Notes

**Skill sequence:**
SK-01 (customer) → Bedrock direct → (human pause) → SK-01 (playbook) → SK-02 → SK-05×N → SK-04 → SK-03

**Optional skills:**
- SK-05 only runs if Phase 5 confidence != "high"
- SK-04 always runs but may return found=false (non-blocking)

**DynamoDB tables used:**
- `llmwiki-harness-runs` — run state (hash=engagement_id, range=run_id)
- `llmwiki-workspace-files` — per-phase markdown workspace (hash=engagement_id, range=file_path)
- `llmwiki-gaps` — gap log (written by SK-05)
- `llmwiki-log` — skill telemetry (written by each skill)

**S3 paths written:**
- `wiki/reports/{customer_id}-handoff-report-{date}.html` — primary report
- `wiki/reports/{customer_id}-handoff-report-{date}.txt` — plain text fallback
- `wiki/customers/{customer_id}-harness-handoff-{year}.md` — wiki knowledge page

**Downstream consumers:**
- UC2 Environment Provisioning reads the wiki knowledge page
- UC8 Cutover Readiness Check reads the gap log

---

## Output / Deliverable

**Downloadable HTML report:**
`wiki/reports/{customer_id}-handoff-report-{YYYY-MM-DD}.html`
Business-ready, print-to-PDF capable. Contains KPI bar + 7 sections.

**Wiki page:**
`wiki/customers/{customer_id}-harness-handoff-{YYYY}.md`
Indexed in Bedrock KB, searchable by future agents.

**DynamoDB run record:**
`llmwiki-harness-runs` — full phase_results JSON, status=completed, latency.

**Presigned URL:**
12-hour download link returned in the API response and stored in
`phase_results.phase8.report_download_url`.
