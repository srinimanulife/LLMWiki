---
title: SK-01 Customer Briefing Loader
skill_id: SK-01
business_name: Customer Briefing Loader
technical_name: ContextBootstrapSkill
tier: 1
version: "1.0"
status: active
lambda_function: llmwiki-skill-context-bootstrap
use_case_tags: [UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10]
domain: skills
deployed_date: 2026-05-14
---

# SK-01 — Customer Briefing Loader

**Business Name:** Customer Briefing Loader  
**Technical Name:** ContextBootstrapSkill  
**Tier:** 1 — Universal (used by all 10 UC agents)  
**Lambda:** `llmwiki-skill-context-bootstrap`

## What It Does

Instantly loads everything the agent needs to know before it starts working:
- The customer's full history from the wiki (`wiki_get_customer`)
- The step-by-step implementation playbook for the current use case (`wiki_get_playbook`)

Both calls run **in parallel**, so the agent is ready in ~500ms regardless of how much customer history exists.

## When to Call

> Call SK-01 **first, always** — before any other skill or action.

If the agent skips this skill, it risks:
- Repeating work a prior agent already completed
- Missing customer-specific constraints that change the approach
- Writing wiki pages that conflict with existing customer context

## Invocation Contract

```json
{
  "skill": "ContextBootstrapSkill",
  "skill_id": "SK-01",
  "version": "1.0",
  "invoked_by": "your-agent-id",
  "inputs": {
    "customer_id": "customer-name-2026",
    "use_case": "UC1",
    "agent_id": "your-agent-id"
  }
}
```

## Output Contract

```json
{
  "skill": "ContextBootstrapSkill",
  "business_name": "Customer Briefing Loader",
  "skill_id": "SK-01",
  "version": "1.0",
  "status": "success",
  "outputs": {
    "customer_status": "new|existing",
    "customer_context": { "overview": "...", "key_facts": [], "products_in_scope": [] },
    "prior_contributions": ["wiki/customers/prior-page.md"],
    "playbook": { "steps": [], "required_artifacts": [], "decision_gates": [] },
    "pages_loaded": 3
  },
  "latency_ms": 480,
  "wiki_pages_used": 3
}
```

## Telemetry

Every invocation writes a record to `llmwiki-log` DynamoDB table with:
`skill_id`, `agent_id`, `customer_id`, `use_case`, `latency_ms`, `pages_used`, `customer_status`

## Used By

All 10 UC agents: UC1 (S2S), UC2 (ENV), UC3 (IAM), UC4 (CFG), UC5 (DM), UC6 (SIT), UC7 (E2E), UC8 (CUT), UC9 (PTO), UC10 (HC)
