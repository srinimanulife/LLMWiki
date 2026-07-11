# LLMWiki Schema — AGENTS.md

## Project Overview
This is the LLMWiki knowledge base. It automatically ingests documents from raw/ and builds
a structured, interlinked wiki of Markdown pages organized by page type. The LLM owns all
wiki/ pages. Humans upload source documents; the LLM maintains all knowledge pages.

## Directory Structure
- `raw/papers/`    — Academic papers and formal reports (converted to .md from PDF)
- `raw/articles/`  — Web articles, blog posts, overviews
- `raw/notes/`     — Meeting notes, personal notes, informal documents
- `raw/sows/`      — Statements of Work and customer contracts
- `raw/youtube/`   — Video and podcast transcripts
- `raw/assets/`    — Original PDFs and binary files (not processed)
- `wiki/sources/`  — One summary page per source document
- `wiki/entities/` — Pages for people, organizations, systems, products
- `wiki/concepts/` — Pages for ideas, frameworks, methodologies, terms
- `wiki/questions/`— Open research questions surfaced during ingestion
- `wiki/runbooks/` — Step-by-step operational procedures per use case (UC1–UC10)
- `wiki/customers/`— Customer-specific context: SOW summaries, personas, handoff notes
- `wiki/artifacts/`— Document templates: BOM, checklists, persona template, test plans
- `wiki/decisions/`— Architecture decisions, ARB outcomes, scope decisions
- `wiki/sops/`     — Standard operating procedures for ops and support teams
- `wiki/evidence/` — Compliance evidence templates and audit trail patterns
- `wiki/pending/`  — Agent contributions awaiting human review (not indexed in KB)
- `wiki/index.md`  — Auto-generated master catalog of all wiki pages
- `wiki/overview.md` — High-level synthesis of the entire knowledge base
- `output/`        — Query answers and analysis reports
- `config/`        — This file and other configuration

## Page Templates

### Source Summary Page (wiki/sources/<slug>.md)
```yaml
---
title: <Document Title>
date: <YYYY-MM-DD>
tags: [<tag1>, <tag2>]
source_count: 1
source_file: <raw/ path>
source_type: <paper|article|note|transcript>
status: active
---

# <Title>

## Summary
<2-3 paragraph summary of the document's key content>

## Key Takeaways
- <Takeaway 1>
- <Takeaway 2>
- <Takeaway 3>

## Key Entities
- [[entity-slug-1]] — <brief description>
- [[entity-slug-2]] — <brief description>

## Key Concepts
- [[concept-slug-1]] — <brief description>

## Quotes
> <Notable direct quote from the source>

## Questions Raised
- <Open question this source raises>
```

### Entity Page (wiki/entities/<slug>.md)
```yaml
---
title: <Entity Name>
date: <YYYY-MM-DD>
tags: [entity, <entity-type>]
source_count: <number>
status: active
---

# <Entity Name>

## Overview
<1 paragraph description synthesized from all sources>

## Key Facts
- <Fact from source A>
- <Fact from source B>

## Relationships
- [[related-entity]] — <relationship type>

## Sources
- [[source-slug-1]]
- [[source-slug-2]]
```

### Concept Page (wiki/concepts/<slug>.md)
```yaml
---
title: <Concept Name>
date: <YYYY-MM-DD>
tags: [concept]
source_count: <number>
status: active
---

# <Concept Name>

## Definition
<Clear definition synthesized from sources>

## How It Works
<Explanation of the concept>

## Applications / Examples
- <Example from source A>

## Related Concepts
- [[related-concept]] — <relationship>

## Sources
- [[source-slug-1]]
```

## Ingest Workflow
When a new .md file lands in raw/:
1. Read the source document fully
2. Generate a source summary page in wiki/sources/
3. For each key entity mentioned: create or update wiki/entities/<slug>.md
4. For each key concept: create or update wiki/concepts/<slug>.md
5. Update wiki/index.md to include all new/updated pages
6. Append an entry to the DynamoDB log table
7. Flag any contradictions with existing wiki pages in the summary

## Conventions
- File naming: kebab-case only (e.g., cloud-strategy-2026.md)
- Wikilinks: [[page-slug]] style (no extension, no path)
- Date format: ISO 8601 (YYYY-MM-DD)
- Tone: professional and objective
- Uncertainty: use "According to [source]..." when claims are source-specific
- Contradictions: note them explicitly with "CONTRADICTION: source A says X, source B says Y"
- Cross-references: always link entities and concepts mentioned in any page
- Entity page rule: only create if entity is mentioned in 2+ distinct passages
- Concept page rule: create for any idea that has its own definition or framework

## Agentic Page Types (new in Phase 2)

When ingesting documents that are SOWs, customer briefs, or TriZetto implementation documents,
generate ADDITIONAL page types beyond sources/entities/concepts:

### Runbook Page (wiki/runbooks/<slug>.md)
```yaml
---
title: <Runbook Title>
date: <YYYY-MM-DD>
tags: [runbook, <use-case-tag>]
use_case_tags: [UC1]        # which use cases this runbook serves
domain: customer-onboarding # domain for KB filtering
artifact_type: runbook
decision_gate: G0            # G0–G6 if applicable
action_items:
  - "Step 1 action"
evidence_required:
  - "Evidence item"
status: active
---
```

### Customer Page (wiki/customers/<slug>.md)
```yaml
---
title: <Customer Name> — <Context>
date: <YYYY-MM-DD>
tags: [customer, <customer-name>]
customer_id: <customer-id>
use_case_tags: [UC1]
domain: customer-onboarding
contributing_agent: <agent-id-if-agent-created>
human_review_required: false
status: active
---
```

### Artifact Template Page (wiki/artifacts/<slug>.md)
```yaml
---
title: <Template Name>
date: <YYYY-MM-DD>
tags: [artifact, template]
artifact_type: <persona-template|bom|checklist|sop>
use_case_tags: [UC1, UC2]
domain: <domain>
status: active
---
```

## Frontmatter Rule for Agentic Pages
All wiki pages that could be queried by an AI agent MUST include:
- `use_case_tags`: list of UC1–UC10 tags indicating which use cases benefit from this page
- `domain`: one of customer-onboarding | provisioning | identity-access | configuration |
  data-migration | testing | cutover | handover | hypercare
- `action_items`: machine-parseable list of concrete actions (empty list if none)

## Model
- All generation uses Claude Sonnet 4.6 (us.anthropic.claude-sonnet-4-6-v1:0)
- Max context per page generation: 8,000 tokens source + 8,192 tokens output
