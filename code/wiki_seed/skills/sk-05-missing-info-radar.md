---
title: SK-05 Missing Info Radar
skill_id: SK-05
business_name: Missing Info Radar
technical_name: GapDetectionSkill
tier: 2
version: "1.0"
status: active
lambda_function: llmwiki-skill-gap-detection
use_case_tags: [UC1, UC2, UC5, UC8, UC9, UC10]
domain: skills
deployed_date: 2026-05-14
---

# SK-05 — Missing Info Radar

**Business Name:** Missing Info Radar  
**Technical Name:** GapDetectionSkill  
**Tier:** 2 — Common (used by 6 of 10 UC agents)  
**Lambda:** `llmwiki-skill-gap-detection`

## What It Does

When the wiki cannot answer a question with sufficient confidence, the Missing Info Radar:

1. Calls Claude to classify the specific knowledge gap (what is missing and why)
2. Determines whether the gap is **blocking** (agent cannot proceed) or **informational**
3. Persists the gap to `llmwiki-gaps` DynamoDB table (visible in Streamlit Gap Dashboard)
4. For blocking gaps with SNS configured: publishes an alert so a human can fill the gap
5. Returns `human_prompt` — the exact question to ask a human to resolve each gap

## Trigger Condition

Call SK-05 when SK-02 returns `confidence: "low"`. Do NOT call SK-05 for `medium` confidence unless the question is business-critical.

## Gap Types

| Gap Type | Example |
|---|---|
| `missing-customer-history` | No prior engagement records for this customer |
| `missing-artifact` | Persona template not yet in wiki |
| `missing-standard` | No documented procedure for this customer segment |
| `missing-evidence` | Required gate evidence not in wiki |
| `unknown-configuration` | System configuration not documented |

## Invocation Contract

```json
{
  "skill": "GapDetectionSkill",
  "skill_id": "SK-05",
  "version": "1.0",
  "invoked_by": "your-agent-id",
  "inputs": {
    "question": "What is the SCAN Health Plan SLA for claims turnaround?",
    "domain": "customer-onboarding",
    "use_case": "UC1",
    "customer_id": "scan-health-plan-2026",
    "low_confidence_response": {
      "confidence": "low",
      "gaps_detected": [],
      "answer": "The wiki does not have specific SLA information..."
    }
  }
}
```

## Output Contract

```json
{
  "skill": "GapDetectionSkill",
  "business_name": "Missing Info Radar",
  "skill_id": "SK-05",
  "status": "success",
  "outputs": {
    "gaps": [
      {
        "gap_id": "uuid",
        "gap_type": "missing-customer-history",
        "slug": "scan-health-plan-sla-claims",
        "title": "SCAN Health Plan — Claims Turnaround SLA",
        "blocking": false,
        "escalated": false,
        "human_prompt": "Please provide the contracted SLA for claims turnaround from the SOW Section 4.2."
      }
    ],
    "gap_count": 1,
    "blocking": false,
    "escalated": false
  },
  "latency_ms": 720,
  "wiki_pages_used": 0,
  "logged_to_gaps_table": true
}
```

## Gap Dashboard

All gaps are visible in the Streamlit UI under **Expansion Lab → Knowledge Gaps**. Business users can see in real-time what the agents are discovering the wiki doesn't know — this drives the content ingestion backlog.

## Blocking Gaps

When `blocking: true`:
- The agent MUST surface the gap to a human before proceeding
- If `GAPS_SNS_TOPIC_ARN` is configured, an SNS notification is sent automatically
- The human_prompt is displayed in the Streamlit UI as an action item

## Used By

UC1 (S2S), UC2 (ENV), UC5 (DM), UC8 (CUT), UC9 (PTO), UC10 (HC)
