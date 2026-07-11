---
title: SK-02 Knowledge Finder
skill_id: SK-02
business_name: Knowledge Finder
technical_name: WikiQuerySkill
tier: 1
version: "1.0"
status: active
lambda_function: llmwiki-skill-wiki-query
use_case_tags: [UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10]
domain: skills
deployed_date: 2026-05-14
---

# SK-02 — Knowledge Finder

**Business Name:** Knowledge Finder  
**Technical Name:** WikiQuerySkill  
**Tier:** 1 — Universal (used by all 10 UC agents)  
**Lambda:** `llmwiki-skill-wiki-query`

## What It Does

Searches the company knowledge base and returns a cited, structured answer with concrete action items. Wraps the Business Query Lambda (`llmwiki-business-query`) with:

- **Automatic intent detection** — classifies the question as checklist/artifact/entity/narrative before querying
- **Retry on low confidence** — if domain-scoped search returns low confidence, automatically retries with a broader scope
- **Structured telemetry logging** — every question, confidence level, and answer is logged to `llmwiki-log` for analytics

## When to Call

Call SK-02 any time the agent needs to look something up before acting. Common question patterns:
- "What are the steps for [process]?"
- "What artifacts are required for [phase]?"
- "Who is responsible for [activity]?"
- "What does the wiki say about [topic] for this customer?"

## Invocation Contract

```json
{
  "skill": "WikiQuerySkill",
  "skill_id": "SK-02",
  "version": "1.0",
  "invoked_by": "your-agent-id",
  "inputs": {
    "question": "What are the key steps in the Sales-to-Service handoff process?",
    "domain": "customer-onboarding",
    "customer_id": "customer-name-2026",
    "use_case": "UC1",
    "max_results": 5
  }
}
```

## Output Contract

```json
{
  "skill": "WikiQuerySkill",
  "business_name": "Knowledge Finder",
  "skill_id": "SK-02",
  "status": "success",
  "outputs": {
    "answer": "Synthesized, cited answer...",
    "confidence": "high|medium|low",
    "action_items": ["Concrete action 1", "Concrete action 2"],
    "artifacts_referenced": [{"name": "template", "s3_key": "wiki/artifacts/..."}],
    "evidence_required": [],
    "gaps_detected": [],
    "sources": [{"page_slug": "...", "relevance_score": 0.87}],
    "wiki_page_count": 5
  },
  "latency_ms": 2100,
  "wiki_pages_used": 5
}
```

## Confidence Guidance

| Confidence | Meaning | Agent Action |
|---|---|---|
| `high` | 3+ strong sources agree | Trust the answer and act |
| `medium` | 1–2 relevant sources | Use the answer, flag to human if critical |
| `low` | Weak or no sources | Call SK-05 (Missing Info Radar) before proceeding |

## Retry Behaviour

If `confidence == "low"` and `domain` was set, SK-02 automatically retries without the domain filter. If the broader query returns `medium` or `high`, the broader result is returned with a `_note` field explaining the fallback.

## Used By

All 10 UC agents: UC1 through UC10
