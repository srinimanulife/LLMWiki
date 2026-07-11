---
title: SK-04 Template Auto-Fill
skill_id: SK-04
business_name: Template Auto-Fill
technical_name: ArtifactResolutionSkill
tier: 2
version: "1.0"
status: active
lambda_function: llmwiki-skill-artifact-resolution
use_case_tags: [UC1, UC2, UC3, UC5, UC6, UC7, UC8, UC9]
domain: skills
deployed_date: 2026-05-14
---

# SK-04 — Template Auto-Fill

**Business Name:** Template Auto-Fill  
**Technical Name:** ArtifactResolutionSkill  
**Tier:** 2 — Common (used by 8 of 10 UC agents)  
**Lambda:** `llmwiki-skill-artifact-resolution`

## What It Does

Finds the right template or checklist in the wiki and pre-populates it with available customer and project data. No manual copying from template to document. Uses Claude to:

1. Fetch the artifact template from `wiki/artifacts/` or `wiki/runbooks/`
2. Identify every placeholder field in the template
3. Fill in every field it CAN populate from `available_context`
4. Mark fields it CANNOT fill as `[MISSING: field_name]`
5. Return `populated_fields`, `missing_fields`, and a `completion_pct`

## Supported Artifact Types (UC1 POC)

| Artifact | Page Slug | Used In |
|---|---|---|
| Customer Persona Template | `persona-template` | UC1 |
| BOM Template | `bom-template` | UC2 |
| ARB Security Checklist | `arb-checklist` | UC2 |
| RBAC Matrix Template | `rbac-matrix` | UC3 |
| Data Migration Mapping | `data-mapping-template` | UC5 |
| Test Scenario Template | `test-scenario-template` | UC6, UC7 |
| Cutover Runbook | `cutover-runbook` | UC8 |
| PTO Checklist | `pto-checklist` | UC9 |

## Invocation Contract

```json
{
  "skill": "ArtifactResolutionSkill",
  "skill_id": "SK-04",
  "version": "1.0",
  "invoked_by": "your-agent-id",
  "inputs": {
    "artifact_type": "persona-template",
    "customer_id": "customer-name-2026",
    "use_case": "UC1",
    "available_context": {
      "customer_id": "customer-name-2026",
      "handoff_summary": "...",
      "action_items": ["..."],
      "products_in_scope": ["TriZetto Facets"]
    }
  }
}
```

## Output Contract

```json
{
  "skill": "ArtifactResolutionSkill",
  "business_name": "Template Auto-Fill",
  "skill_id": "SK-04",
  "status": "success",
  "outputs": {
    "artifact_type": "persona-template",
    "found": true,
    "s3_key": "wiki/artifacts/persona-template.md",
    "artifact_content": "# Customer Persona\n\n**Customer:** customer-name-2026\n...",
    "populated_fields": ["customer_id", "date", "products"],
    "missing_fields": ["primary_contact_email", "go_live_date"],
    "completion_pct": 75
  },
  "latency_ms": 2800,
  "wiki_pages_used": 1
}
```

## When Artifact Is Not Found

If `found: false`, the agent should:
1. Log a knowledge gap via SK-05 with `gap_type: "missing-artifact"`
2. Proceed with a manually-structured brief rather than failing

The artifact will become available once the source document containing the template is ingested via `raw/`.

## Used By

UC1 (persona), UC2 (BOM, ARB), UC3 (RBAC), UC5 (data-mapping), UC6 (SIT scenarios), UC7 (E2E scenarios), UC8 (cutover-runbook), UC9 (PTO)
