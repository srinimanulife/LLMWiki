# LLMWiki — Benefit Configuration Comparison Use Case

> **Use case:** Annual benefit plan comparison — extract structured differences
> between two years of Evidence of Coverage (EOC) PDFs and produce a
> business-ready change report equivalent to a hand-authored analyst XLSX.
>
> **Source files:**
> - `beneiftconfig/2024EOCChaptor4.pdf` — 2024 EOC Chapter 4 (Medical Benefits Chart)
> - `beneiftconfig/2025EOCChaptor4.pdf` — 2025 EOC Chapter 4 (Medical Benefits Chart)
> - `beneiftconfig/2024vs2025-overall-differences.xlsx` — ground-truth diff (eval target)
>
> **Plan:** AARP® Medicare Advantage from UHC UT-0003 (HMO-POS), Utah

---

## What the Excel File Tells Us (Ground Truth)

The xlsx (`2024vs2025-overall-differences.xlsx`) is what a human analyst produced after reading
both EOCs. It has exactly this structure:

| Column | Purpose |
|---|---|
| `Chapter` | Which chapter the change is in |
| `Section/Category` | The specific benefit or topic |
| `2024 Details` | Exact 2024 value / rule |
| `2025 Details` | Exact 2025 value / rule |
| `Summary of Change` | Plain-English business summary |

**23 differences identified across 12 chapters.** Key changes found by the analyst:

| Category | 2024 | 2025 | Change |
|---|---|---|---|
| Plan premium | $33.00/month | $32.00/month | -$1.00 |
| Chiropractic services | $15 copay | $20 copay | +$5 |
| Routine Dental Annual Max | $1,500 | $1,000 | -$500 |
| Emergency care | $120 copay | $125 copay | +$5 |
| Inpatient hospital (days 1-6) | $325/day | $350/day | +$25 |
| Inpatient psychiatric (days 1-6) | $325/day | $350/day | +$25 |
| Outpatient rehab (PT/ST/OT) | $25 copay | $30 copay | +$5 |
| Outpatient surgery (ASC) | $225 copay | $250 copay | +$25 |
| Outpatient surgery (hospital) | $325 copay | $350 copay | +$25 |
| Specialist visit | $25 copay | $30 copay | +$5 |
| Podiatry services | $25 copay | $30 copay | +$5 |
| Additional routine foot care | $25 copay | $30 copay | +$5 |
| Urgently needed services | $40 copay | $55 copay | +$15 |
| Routine eyewear frequency | Every year | Every 2 years | Worse for member |
| Part D deductible | $0 | $340 (Tier 3-5) | New deductible |
| Part D initial coverage limit | $5,030 | $2,000 | Significantly lower |
| Catastrophic Stage threshold | $8,000 OOP | $2,000 OOP | Much lower (better) |
| Appeal deadline | 60 days | 65 days | +5 days |
| Quality Improvement Org (Utah) | KEPRO | ACENTRA | Org change |

**This is the output LLMWiki must reproduce automatically from just the two PDFs.**

---

## Why This Is Hard Without LLMWiki

Without LLMWiki:
1. An analyst reads both 100+ page PDFs manually
2. Builds a comparison spreadsheet by hand
3. Spends 2-4 hours per plan per year
4. A health plan with 50 products × 2 states × annual update = 200+ analyst-hours/year
5. Human error risk — easy to miss a $5 copay change buried on page 73
6. No audit trail — no way to prove the comparison is complete

With LLMWiki:
- Both PDFs are uploaded once, indexed in the knowledge base
- A single agent query produces the structured diff table
- Output is reproducible, auditable, and versioned in S3
- Same pipeline works for any EOC chapter, any year, any plan

---

## System Architecture — What Needs to Be Built

```
beneiftconfig/
├── 2024EOCChaptor4.pdf  ──► S3 uploads/ ──► Textract ──► raw/paper/2024-eoc-chapter4.md
├── 2025EOCChaptor4.pdf  ──► S3 uploads/ ──► Textract ──► raw/paper/2025-eoc-chapter4.md
│
│   (Bedrock KB syncs raw/ → vector index)
│
└── Comparison agent
        │
        ├── WikiQuery(2024 benefit values)    → SK-02
        ├── WikiQuery(2025 benefit values)    → SK-02
        ├── Claude diff synthesis             → direct Bedrock call
        └── WikiContribute(diff table draft)  → SK-03 → S3 wiki/pending/
```

The architecture is a **Lambda Harness** (not Neuro-SAN) because:
- The comparison sequence is fixed and deterministic
- Output is a structured table, not a conversation
- We need a PDF/XLSX report at the end, not a chat thread
- Auditable run state in DynamoDB is required for enterprise use

---

## Phase-by-Phase Technical Flow

### Call 1 — Ingest trigger (already existing — Converter Lambda)

Both PDFs are uploaded to `S3/uploads/`. The existing Converter Lambda
(`code/lambda/converter/handler.py`) fires automatically via EventBridge:

```
2024EOCChaptor4.pdf → start_document_text_detection() → poll → get all LINE blocks
                    → wrap in YAML frontmatter → s3.put_object()
                    → raw/paper/2024-eoc-chapter4.md
                    → DynamoDB REGISTRY_TABLE: status="converted"

2025EOCChaptor4.pdf → same path
                    → raw/paper/2025-eoc-chapter4.md
```

No new code needed here — the existing Converter Lambda handles PDFs already.

After conversion, Bedrock KB sync runs (triggered or scheduled) and both
Markdown files become queryable via SK-02.

---

### Call 1 of comparison — Start

```
POST /harness/benefitconfig
{
  "action": "start",
  "plan_id": "UHC-UT-0003",
  "year_a": "2024",
  "year_b": "2025",
  "chapters": ["chapter-4"],           ← optional: scope to specific chapters
  "customer_id": "UHC",
  "engagement_id": "BC-001"
}
```

**Phase 1 — Validate inputs (Python only)**
```
Check year_a and year_b docs are in DynamoDB REGISTRY_TABLE (status="converted")
If not found → HTTP 400 "Documents not yet indexed — run /ingest first"
Confirm chapter scope or default to "all chapters"
Write run record: status="running", current_phase=1
```

**Phase 2 — Extract year_a benefit values via WikiQuery (SK-02)**
```python
payload_a = {
  "skill": "WikiQuerySkill",
  "inputs": {
    "question": """
      List ALL benefit line items from the 2024 EOC Chapter 4 Medical Benefits Chart
      for plan UHC-UT-0003. For each line item provide:
      - Service category (exact name)
      - Copayment amount or coinsurance percentage
      - Any annual maximum, limit, or frequency rule
      - Whether it requires prior authorization
      Format as a structured list with exact dollar amounts.
    """,
    "domain": "benefit-configuration",
    "customer_id": "UHC",
    "year_filter": "2024",
    "use_case": "UC-BC"
  }
}
→ SK-02 Lambda → Bedrock KB semantic search → Claude synthesis
→ Returns: structured list of ~60-80 benefit line items with values
→ Save to phase_results["2"]
```

**Phase 3 — Extract year_b benefit values via WikiQuery (SK-02)**
```python
# Same query, different year_filter
payload_b = { ...same... "year_filter": "2025" }
→ SK-02 Lambda
→ Returns: structured list for 2025
→ Save to phase_results["3"]
```

**Phase 4 — Identify differences via direct Bedrock call**
```python
prompt = f"""
You are a healthcare benefit analyst comparing two years of Medicare Advantage plan benefits.

YEAR A (2024) BENEFIT VALUES:
{phase_results["2"]["answer"]}

YEAR B (2025) BENEFIT VALUES:
{phase_results["3"]["answer"]}

Instructions:
1. Compare every benefit line item side by side.
2. Identify ALL differences — copayment changes, coinsurance changes,
   annual maximum changes, frequency changes, new benefits, removed benefits.
3. Ignore formatting differences — focus only on value/rule changes.
4. For each difference, produce a JSON object with:
   {{
     "chapter": "Chapter N: <name>",
     "section_category": "<exact service name>",
     "year_a_value": "<exact 2024 value/rule>",
     "year_b_value": "<exact 2025 value/rule>",
     "change_direction": "increase | decrease | new | removed | changed",
     "dollar_impact": <number or null>,
     "summary": "<one plain-English sentence a member would understand>"
   }}
5. Return a JSON array of all differences. Include EVERY change, no matter how small.

Return ONLY the JSON array. No explanation.
"""
→ bedrock.converse(modelId=CLAUDE_SONNET, messages=[...], inferenceConfig={"maxTokens": 8192})
→ Parse JSON response
→ Save to phase_results["4"]
```

**PAUSE — return to caller**
```json
{
  "run_id": "BC-UHC-UT-0003-2024-2025-abc123",
  "status": "paused",
  "message": "Preliminary comparison complete. Found N differences. Call resume to generate report.",
  "differences_found": N,
  "phase": 4
}
```

---

### Call 2 — Resume

```
POST /harness/benefitconfig
{
  "action": "resume",
  "run_id": "BC-UHC-UT-0003-2024-2025-abc123"
}
```

**Phase 5 — Gap detection via SK-05**
```
Check: are there benefit categories in year_a not found in year_b?
Check: are there benefit categories in year_b not found in year_a?
Call GapDetection SK-05:
  question = "Are there benefit categories present in 2024 but missing from 2025 index?"
  domain = "benefit-configuration"
→ Returns gap list (benefits that couldn't be compared due to missing index coverage)
→ Save to phase_results["5"]
```

**Phase 6 — Categorise and rank differences via Bedrock**
```python
prompt = f"""
Given this list of benefit differences:
{phase_results["4"]}

Categorise each change for business impact:
- COST_INCREASE: member pays more
- COST_DECREASE: member pays less
- COVERAGE_REDUCTION: less covered / stricter limits
- COVERAGE_EXPANSION: more covered / relaxed limits
- ADMINISTRATIVE: org name changes, deadline changes, etc.
- NEW_BENEFIT: net new coverage
- REMOVED_BENEFIT: coverage eliminated

Also add a severity: HIGH / MEDIUM / LOW based on dollar impact and member visibility.
Return the full differences array with "category" and "severity" added to each object.
"""
→ bedrock.converse()
→ Save to phase_results["6"]
```

**Phase 7 — Write structured diff to wiki (SK-03)**
```python
# Build Markdown table from categorised differences
diff_table = build_markdown_table(phase_results["6"])

payload = {
  "skill": "WikiContributeSkill",
  "inputs": {
    "page_type": "decisions",          ← triggers HITL routing (human must review)
    "page_slug": f"benefitconfig-{plan_id}-{year_a}-vs-{year_b}",
    "content": diff_table,
    "agent_id": "llmwiki-benefitconfig-harness",
    "customer_id": "UHC",
    "use_case": "UC-BC",
    "human_review_required": True
  }
}
→ SK-03 Lambda → S3 wiki/pending/decisions/benefitconfig-UHC-UT-0003-2024-vs-2025.md
```

**Phase 8 — Generate HTML report + XLSX + presigned URLs**
```
Build HTML report:
  - Executive summary (N changes, cost trend, severity breakdown)
  - Changes grouped by chapter
  - Member impact section (plain English — "Your specialist copay went up $5")
  - Data quality notes (any gaps detected in Phase 5)

Build XLSX:
  - Sheet "Summary": totals by category and severity
  - Sheet "All Changes": full diff table (same 5 columns as ground-truth xlsx)
  - Sheet "Member Impact": HIGH severity items only, plain English

Write to S3:
  wiki/benefitconfig/reports/{run_id}/
    benefitconfig-2024vs2025-report.html
    benefitconfig-2024vs2025-differences.xlsx
    benefitconfig-2024vs2025-member-summary.md

Generate presigned URLs (7-day expiry) for all 3 outputs.

Write audit record to DynamoDB llmwiki-log:
  log_date: "session#benefitconfig#2026-07-23"
  plan_id: "UHC-UT-0003"
  year_a: "2024", year_b: "2025"
  differences_found: N
  high_severity: N
  artifacts: [html_url, xlsx_url, summary_url]
  TTL: 90 days
```

**Return to caller**
```json
{
  "run_id": "BC-UHC-UT-0003-2024-2025-abc123",
  "status": "completed",
  "differences_found": 23,
  "high_severity_count": 8,
  "artifacts": {
    "html_report":     "https://s3.presigned.../benefitconfig-2024vs2025-report.html",
    "xlsx_report":     "https://s3.presigned.../benefitconfig-2024vs2025-differences.xlsx",
    "member_summary":  "https://s3.presigned.../benefitconfig-2024vs2025-member-summary.md",
    "wiki_draft":      "s3://llmwiki-bucket/wiki/pending/decisions/benefitconfig-UHC-UT-0003-2024-vs-2025.md"
  }
}
```

---

## Files to Create

```
code/
└── lambda/
    └── harness/
        └── benefitconfig_harness/
            └── handler.py          ← new harness (same pattern as pm_harness)

code/
└── registries/
    └── llmwiki/
        └── uc_benefit_config.hocon ← optional: Neuro-SAN path for conversational use

beneiftconfig/
└── llmwiki-benefitconfig.md        ← this document
```

No new skill Lambdas needed. The harness reuses:
- SK-01 (context-bootstrap) — load prior year comparisons if available
- SK-02 (wiki-query) — extract benefit values from indexed EOC
- SK-03 (wiki-contribute) — write diff draft to wiki/pending/
- SK-05 (gap-detection) — flag benefit categories that couldn't be compared

---

## S3 Upload — Uploading PDFs for Eval

The llmwiki wiki bucket (`llmwiki-{suffix}`) is the target. Two upload paths:

**Path A — Via Streamlit UI (production)**
```
Knowledge Hub → Upload Documents
Select: 2024EOCChaptor4.pdf, 2025EOCChaptor4.pdf
Category: benefit-config
Customer: UHC
```
Converter Lambda fires automatically on S3 ObjectCreated.

**Path B — Direct S3 upload for local dev/eval**
```bash
# Find the deployed bucket name
BUCKET=$(aws s3 ls | grep llmwiki | awk '{print $3}' | head -1)

# Upload both PDFs
aws s3 cp beneiftconfig/2024EOCChaptor4.pdf s3://$BUCKET/uploads/benefit-config/2024EOCChaptor4.pdf
aws s3 cp beneiftconfig/2025EOCChaptor4.pdf s3://$BUCKET/uploads/benefit-config/2025EOCChaptor4.pdf

# Verify Converter Lambda fired (check DynamoDB REGISTRY_TABLE)
aws dynamodb scan --table-name llmwiki-document-registry \
  --filter-expression "contains(source_key, :bc)" \
  --expression-attribute-values '{":bc":{"S":"benefit-config"}}' \
  --query "Items[*].[source_id.S, status.S]" --output table
```

**Note on current account state:** The llmwiki bucket has a random suffix
(`llmwiki-{random_id.hex}`) generated at Terraform apply time. The bucket
name is not yet known in this account — Terraform must be applied first.
The `aipocuhg` bucket currently visible is a separate project. Once
`terraform apply` runs in `code/terraform/`, the correct bucket name
will be in Terraform state output as `wiki_bucket_name`.

---

## Eval Plan — Using the XLSX as Ground Truth

The xlsx file is the **eval golden set**. Here is how to use it to measure
whether the harness output is correct.

### Eval schema

```python
# Each row in the xlsx = one expected finding
EXPECTED_DIFFS = [
    {
        "chapter": "Chapter 4: Medical Benefits Chart",
        "section_category": "Chiropractic services",
        "year_a_value": "$15 copayment per visit.",
        "year_b_value": "$20 copayment per visit.",
        "summary_of_change": "Copayment increased by $5."
    },
    # ... 22 more rows
]
```

### Eval dimensions

| Dimension | Question | How to score |
|---|---|---|
| **Recall** | Did the harness find all 23 differences? | `found_count / 23` |
| **Precision** | Are there false positives (differences that aren't real)? | `correct_found / total_found` |
| **Value accuracy** | Are the exact dollar amounts correct? | Compare `year_a_value` / `year_b_value` strings |
| **Summary quality** | Is the plain-English summary correct and clear? | LLM judge: Claude rates each summary 1-5 |
| **Chapter accuracy** | Is each difference assigned to the right chapter? | Exact match on `chapter` field |

### Eval script outline

```python
# code/eval/step_benefitconfig.py

import openpyxl, json, boto3

def load_ground_truth(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    return [
        {"chapter": r[0], "section": r[1], "val_a": r[2], "val_b": r[3], "summary": r[4]}
        for r in rows if r[0]
    ]

def call_benefitconfig_harness(plan_id, year_a, year_b):
    # POST to harness Lambda or API GW endpoint
    ...

def score_recall(ground_truth, harness_output):
    # For each ground truth row, check if harness found it
    # Match on section_category (fuzzy) + year_a_value (exact dollar)
    found = 0
    for gt in ground_truth:
        match = any(
            gt["section"].lower() in h["section_category"].lower()
            and gt["val_a"].strip() == h["year_a_value"].strip()
            for h in harness_output
        )
        if match: found += 1
    return found / len(ground_truth)

def run_eval():
    gt = load_ground_truth("beneiftconfig/2024vs2025-overall-differences.xlsx")
    harness_result = call_benefitconfig_harness("UHC-UT-0003", "2024", "2025")
    
    recall = score_recall(gt, harness_result["differences"])
    print(f"Recall: {recall:.1%}  ({int(recall * len(gt))}/{len(gt)} differences found)")
    print(f"Precision: TBD")
    print(f"False positives: {len(harness_result['differences']) - int(recall * len(gt))}")

    # Use Claude as judge for summary quality
    for diff in harness_result["differences"][:5]:  # sample
        judge_prompt = f"""
        Rate this benefit change summary on a scale of 1-5 for:
        - Accuracy (is it factually correct?)
        - Clarity (would a Medicare member understand it?)
        
        Summary: {diff['summary']}
        Context: {diff['year_a_value']} → {diff['year_b_value']}
        
        Return: {{"accuracy": N, "clarity": N, "notes": "..."}}
        """
        # Call bedrock.converse() with judge prompt
```

### Expected eval targets

| Metric | Minimum acceptable | Target |
|---|---|---|
| Recall | 85% (20/23 diffs found) | 95%+ (22/23) |
| Precision | 80% (no hallucinated diffs) | 90%+ |
| Dollar value accuracy | 95% (exact match on amounts) | 99% |
| Summary clarity (LLM judge avg) | 3.5/5 | 4.5/5 |

The 2 most likely misses:
1. **Chapter 6 changes** (Part D deductible, catastrophic stage) — these are in a different
   chapter than the PDFs you uploaded. If only Chapter 4 PDFs are indexed, the eval
   will find ~15/23 (65% recall). Upload the full EOC PDFs for full coverage.
2. **Eyewear frequency change** — the change is subtle (every year → every 2 years).
   The WikiQuery must ask explicitly about frequency rules, not just dollar amounts.

---

## DynamoDB Tables Used

| Table | When written | What is stored |
|---|---|---|
| `llmwiki-document-registry` | On PDF conversion (existing) | source_key, converted_key, status |
| `llmwiki-bc-runs` | After every phase (new) | run_id, plan_id, year_a, year_b, phase_results, status |
| `llmwiki-log` | On completion | session audit, artifact URLs, TTL 90 days |

---

## What Needs to Be Built — Checklist

```
□  Upload PDFs to S3 / confirm Converter Lambda fires and indexes both docs
□  Verify both docs appear in Bedrock KB (test a query: "What is the 2024 specialist copay?")
□  Write code/lambda/harness/benefitconfig_harness/handler.py  (8 phases, two-call pattern)
□  Add benefitconfig to terraform:
     - DynamoDB table llmwiki-bc-runs
     - IAM role for new harness Lambda
     - Lambda function + API GW route /harness/benefitconfig
□  Write code/eval/step_benefitconfig.py (recall + precision + LLM judge)
□  Run eval against ground-truth xlsx
□  Tune Phase 4 prompt until recall ≥ 95%
□  Optional: write uc_benefit_config.hocon for conversational "what changed in dental?" queries
```

---

## Conversational Add-On (Neuro-SAN / HOCON)

Once the harness produces and stores the diff in the wiki, a conversational agent
can answer targeted questions from business users without re-running the full comparison:

```
User: "What changed in dental benefits between 2024 and 2025?"

FrontMan → WikiQuery SK-02:
  question = "dental benefit changes 2024 vs 2025 UHC-UT-0003"
  domain = "benefit-configuration"

Returns: "Routine Dental Annual Maximum decreased from $1,500 to $1,000.
          Eyewear benefit changed from annual to every 2 years."
```

This reuses the stored wiki diff — no re-processing of PDFs needed.
The HOCON for this is a single-agent network with WikiQuery as the only tool.

---

## Key Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Textract misses table structure in PDF | Dollar amounts extracted as plain text, context lost | Use `AnalyzeDocument` with TABLES feature instead of `start_document_text_detection` — returns structured table cells |
| Two PDFs from different chapters (2025 PDF starts at Chapter 3) | 2025 query returns Chapter 3 content instead of Chapter 4 benefit chart | Year filter + chapter filter in WikiQuery; frontmatter tag `chapter: 4` on conversion |
| LLM hallucinates a change that doesn't exist | False positive in diff table | Add a verification pass: re-query both docs for the suspected change and confirm both values before including |
| Part D changes not in Chapter 4 PDFs | Recall limited to ~65% without full EOC | Upload full EOC PDF for both years, not just Chapter 4 |
| Dollar amount format variations ("$25.00" vs "$25") | Exact string match fails in eval | Normalise amounts in eval script before comparison |

---

*Source PDFs: `beneiftconfig/2024EOCChaptor4.pdf`, `beneiftconfig/2025EOCChaptor4.pdf`*
*Ground truth: `beneiftconfig/2024vs2025-overall-differences.xlsx`*
*Last updated: 2026-07-23*
