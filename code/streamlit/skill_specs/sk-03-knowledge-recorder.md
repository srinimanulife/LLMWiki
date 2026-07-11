---
title: SK-03 Knowledge Recorder
skill_id: SK-03
business_name: Knowledge Recorder
technical_name: WikiContributeSkill
tier: 1
version: "1.0"
status: active
lambda_function: llmwiki-skill-wiki-contribute
use_case_tags: [UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10]
domain: skills
deployed_date: 2026-05-14
---

# SK-03 — Knowledge Recorder

**Business Name:** Knowledge Recorder  
**Technical Name:** WikiContributeSkill  
**Tier:** 1 — Universal (used by all 10 UC agents)  
**Lambda:** `llmwiki-skill-wiki-contribute`

## What It Does

Saves agent-generated knowledge back to the wiki so the next agent in the lifecycle can read it. Wraps the Contribute Lambda (`llmwiki-contribute`) with:

- **Human-review routing** — `decisions/` and `evidence/` page types are automatically staged in `wiki/pending/` for approval; other types index immediately
- **Invocation audit** — every contribution is recorded in `llmwiki-contributions` DynamoDB with `agent_id`, `timestamp`, `page_type`
- **Skill contract wrapping** — returns standard `{skill, status, outputs, latency_ms}` so orchestrators can verify contribution success

## When to Call

- **At the END of every agent session** — write the handoff brief, summary decisions, or customer context the next agent needs
- **Mid-session for partial contributions** — if a milestone is reached (e.g., BOM signed off), write it immediately rather than waiting for session end

## High-Risk Page Types (always human-reviewed)

| Page Type | Routed To | Why |
|---|---|---|
| `decisions` | `wiki/pending/` | Gate decisions (G0–G6) require human approval |
| `evidence` | `wiki/pending/` | Compliance evidence must be verified before indexing |

All other types (`customers`, `artifacts`, `runbooks`, `sops`) index immediately.

## Invocation Contract

```json
{
  "skill": "WikiContributeSkill",
  "skill_id": "SK-03",
  "version": "1.0",
  "invoked_by": "your-agent-id",
  "inputs": {
    "page_type": "customers",
    "page_slug": "customer-name-2026-handoff",
    "content": "---\ntitle: ...\n---\n\n# Customer Handoff...",
    "agent_id": "your-agent-id",
    "customer_id": "customer-name-2026",
    "use_case": "UC1",
    "human_review_required": false
  }
}
```

## Output Contract

```json
{
  "skill": "WikiContributeSkill",
  "business_name": "Knowledge Recorder",
  "skill_id": "SK-03",
  "status": "success",
  "outputs": {
    "status": "indexed",
    "page_slug": "customer-name-2026-handoff",
    "s3_uri": "s3://llmwiki-bucket/wiki/customers/customer-name-2026-handoff.md",
    "human_review_required": false,
    "_skill_note": "Indexed immediately and KB sync triggered"
  },
  "latency_ms": 320,
  "wiki_pages_used": 0
}
```

## The Knowledge Compounding Effect

When SK-03 writes a page and triggers a Bedrock KB sync, that page becomes immediately available to:
- The **next agent in the same session** (via SK-02 query)
- **Any future UC agent** for this or another customer
- **Human reviewers** via the Streamlit wiki UI

This is how knowledge compounds: each agent leaves the wiki richer than it found it.

## Used By

All 10 UC agents: UC1 through UC10
