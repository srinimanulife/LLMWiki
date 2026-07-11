# LLMWiki Agentic Architecture Design

**Version:** 1.0  
**Date:** 2026-05-13  
**Status:** Architecture / Pre-Implementation  
**Scope:** LLMWiki as a shared knowledge fabric for a fleet of business agents across the TriZetto Managed Cloud Services implementation lifecycle

---

## 1. Executive Summary

LLMWiki today answers questions for **humans**. This document upgrades it to answer questions for **agents**.

The shift is architectural: instead of a UI and a `/query` endpoint that returns prose, LLMWiki exposes a **Business Knowledge API** — domain-scoped, context-aware, structured-response endpoints that other agents can call to get authoritative, cited answers and act on them without further interpretation.

The catalyst is the **Sales-to-Service Agent** — the first consuming agent, triggered when a customer signs a SOW and transitions from contracting to delivery. But this is not a one-off integration. The AI Handbook Workbook defines **10 implementation lifecycle use cases**, each of which has documented AI opportunities. LLMWiki becomes the **shared knowledge substrate** that all 10 use-case agents draw from.

**What changes in LLMWiki:**

| Before (Phase 1) | After (Agentic) |
|---|---|
| Human types a question in Streamlit UI | Agent calls a business API with structured context |
| Returns prose answer | Returns structured JSON: answer + citations + action_items + confidence + gaps |
| Single `/query` endpoint | Domain-scoped endpoints per use case + universal `ask` endpoint |
| Wiki pages for humans to read | Wiki pages enriched with `use_case_tags`, `artifacts`, `action_items` |
| Agent calls LLMWiki | Agent fleet registers, contributes, and queries collaboratively |

**The central insight:** Every agent in the lifecycle needs the same body of knowledge — SOW context, provisioning standards, configuration rules, runbooks, test patterns, customer history. LLMWiki builds that body of knowledge once from source documents and serves it authoritatively to every agent, on every invocation, with citations.

---

## 2. The Knowledge Fabric Vision

```
┌─────────────────────────────────────────────────────────────────────┐
│                   AI Handbook Lifecycle                             │
│                                                                     │
│  UC1       UC2        UC3       UC4       UC5                       │
│ Sales→  Environment   IAM     Business   Data                       │
│ Service Provisioning Onboarding Config  Migration                   │
│   │          │          │        │         │                        │
│  UC6       UC7        UC8       UC9      UC10                       │
│  SIT       E2E      Cutover    PTO/   Hypercare                     │
│ Testing  Testing   Planning  Handover  Stabilize                    │
│   │          │          │        │         │                        │
└───┴──────────┴──────────┴────────┴─────────┴────────────────────────┘
                              │
                  (all agents call down to)
                              │
         ┌────────────────────▼──────────────────────┐
         │        LLMWiki Business Knowledge API      │
         │   domain-aware · cited · structured · fast │
         └────────────────────┬──────────────────────┘
                              │
         ┌────────────────────▼──────────────────────┐
         │          LLMWiki Knowledge Fabric          │
         │                                            │
         │  S3 wiki/         DynamoDB index           │
         │  ├── sources/     ├── wiki-index           │
         │  ├── entities/    ├── wiki-log             │
         │  ├── concepts/    └── source-registry      │
         │  ├── runbooks/                             │
         │  ├── customers/    Bedrock KB              │
         │  ├── decisions/    (wiki/ prefix)           │
         │  ├── artifacts/                            │
         │  ├── sops/         API Gateway             │
         │  └── evidence/     (Business API Layer)    │
         └───────────────────────────────────────────┘
```

---

## 3. Use Case Map — LLMWiki Touch Points

The AI Handbook Workbook defines 10 use cases across the TriZetto implementation lifecycle. Each maps to specific wiki domains and generates specific queries that agents will ask LLMWiki.

### 3.1 Use Case Summary

| # | Use Case | Vector | LLMWiki Domain | Primary Agent Queries |
|---|---|---|---|---|
| **1** | Sales → Service | V1, V2 | `customer-onboarding` | "What do I know about this customer?", "What is the standard handoff checklist?", "What personas apply to this customer's product?" |
| **2** | Environment Provisioning | V1, V2, V3 | `provisioning` | "What is the BOM template for Product X?", "What are the ARB security requirements?", "What design standards apply to this environment?" |
| **3** | IAM Onboarding | V1, V2 | `identity-access` | "What is the RBAC matrix for this customer type?", "What least-privilege policies apply for role X?", "What access review cadence is required?" |
| **4** | Business Configuration | V1, V2, V3 | `configuration` | "What configuration rules apply for this workflow?", "What are the known dependency risks?", "What validation tests are required post-config?" |
| **5** | Data Migration | V1, V2 | `data-migration` | "What is the standard source-to-target mapping for this data type?", "What DQ checks are required?", "What exception handling patterns apply?" |
| **6** | SIT | V1, V2 | `testing` | "What test scenarios exist for this feature area?", "What automation patterns apply?", "What sign-off evidence is required?" |
| **7** | E2E Testing | V1, V2 | `testing` | "What are the E2E scenario definitions for batch validation?", "What business process health checks are required?" |
| **8** | Cutover Planning | V1, V2, V3 | `cutover` | "What is the cutover runbook for this product?", "What rollback criteria apply?", "What decision gates are required before go-live?" |
| **9** | PTO / Handover | V1, V2 | `handover` | "What SOPs should be handed to the ops team?", "What does the customer education pack include?", "What readiness checklist applies?" |
| **10** | Hypercare Stabilization | V1, V2 | `hypercare` | "What monitoring thresholds trigger escalation?", "What business-process health checks are required?", "What does the hypercare exit checklist require?" |

### 3.2 LLMWiki Wiki Page Domains (New S3 Structure)

The existing `wiki/sources/`, `wiki/entities/`, `wiki/concepts/` structure is extended with use-case-aligned domain prefixes:

```
s3://llmwiki-bucket/
  wiki/
    sources/        ← unchanged: one page per ingested source document
    entities/       ← unchanged: people, orgs, systems, products
    concepts/       ← unchanged: ideas, frameworks, methodologies
    runbooks/       ← NEW: step-by-step operational procedures per use case
    customers/      ← NEW: customer-specific context (SOW summaries, personas, history)
    artifacts/      ← NEW: document templates, BOMs, checklists, configuration patterns
    decisions/      ← NEW: architecture decisions, ARB outcomes, design choices
    sops/           ← NEW: standard operating procedures for ops/support teams
    evidence/       ← NEW: compliance evidence templates and audit trail patterns
    index.md
    overview.md
```

Each new page type has an enriched frontmatter schema that enables domain-filtered retrieval (see Section 5).

---

## 4. Multi-Agent Topology

```
                    ┌─────────────────────────────────────────┐
                    │        External Systems & Humans         │
                    │  ServiceNow · SharePoint · SOW portal   │
                    └───────────────┬─────────────────────────┘
                                    │ documents / triggers
                    ┌───────────────▼─────────────────────────┐
                    │          LLMWiki Ingest Pipeline         │
                    │  S3 raw/ → Lambda Ingest → Bedrock KB   │
                    │  (auto-builds wiki pages from sources)   │
                    └───────────────┬─────────────────────────┘
                                    │ structured wiki
                    ┌───────────────▼─────────────────────────┐
                    │      LLMWiki Business Knowledge API      │
                    │  (API Gateway + Business Query Lambda)   │
                    │                                         │
                    │  POST /wiki/ask          (universal)     │
                    │  POST /wiki/query/{domain}               │
                    │  GET  /wiki/playbook/{use-case}          │
                    │  GET  /wiki/customer/{id}                │
                    │  GET  /wiki/artifact/{type}              │
                    │  POST /wiki/contribute   (write-back)    │
                    └─────────────────┬───────────────────────┘
                                      │
          ┌────────────────────────────────────────────────────────────┐
          │                  Consuming Agent Fleet                     │
          │                                                            │
          │  ┌──────────────────┐      ┌──────────────────────────┐   │
          │  │ Sales-to-Service │      │  Environment Provisioning│   │
          │  │ Agent            │      │  Agent                   │   │
          │  │ (UC1 — First)    │      │  (UC2)                   │   │
          │  └──────────────────┘      └──────────────────────────┘   │
          │                                                            │
          │  ┌──────────────────┐      ┌──────────────────────────┐   │
          │  │ IAM Onboarding   │      │ Business Config Agent     │   │
          │  │ Agent (UC3)      │      │ (UC4)                    │   │
          │  └──────────────────┘      └──────────────────────────┘   │
          │                                                            │
          │  ┌──────────────────┐      ┌──────────────────────────┐   │
          │  │ Data Migration   │      │ SIT / E2E Testing         │   │
          │  │ Agent (UC5)      │      │ Agent (UC6, UC7)          │   │
          │  └──────────────────┘      └──────────────────────────┘   │
          │                                                            │
          │  ┌──────────────────┐      ┌──────────────────────────┐   │
          │  │ Cutover Planning │      │ PTO Handover Agent        │   │
          │  │ Agent (UC8)      │      │ (UC9)                    │   │
          │  └──────────────────┘      └──────────────────────────┘   │
          │                                                            │
          │  ┌──────────────────┐                                      │
          │  │ Hypercare        │                                      │
          │  │ Stabilization    │                                      │
          │  │ Agent (UC10)     │                                      │
          │  └──────────────────┘                                      │
          └────────────────────────────────────────────────────────────┘
                                      │
                              (agents write back)
                    ┌─────────────────▼───────────────────────┐
                    │      LLMWiki Contribution Pipeline       │
                    │  Agent outputs → wiki/customers/ pages  │
                    │  Agent decisions → wiki/decisions/       │
                    │  Agent evidence → wiki/evidence/         │
                    └─────────────────────────────────────────┘
```

**Key architectural principle:** Every agent is both a **consumer** (reads from LLMWiki) and a **contributor** (writes back decisions, completed checklists, customer context). The wiki compounds in value across the full lifecycle.

---

## 5. LLMWiki Business Knowledge API Design

This is the core enhancement. The current `POST /query` endpoint returns prose for humans. The Business Knowledge API returns **structured, actionable JSON for agents**.

### 5.1 Universal Agent Query — `POST /wiki/ask`

The primary endpoint for all consuming agents. Agents provide context and intent; LLMWiki returns structured, domain-filtered knowledge.

**Request:**
```json
{
  "question": "What are the standard ARB requirements for a new TriZetto environment provisioning?",
  "intent": "retrieve-checklist",
  "domain": "provisioning",
  "context": {
    "customer_id": "BCBS-MN-001",
    "project_phase": "environment-provisioning",
    "use_case": "UC2",
    "agent_id": "provisioning-agent-v1"
  },
  "response_format": "structured",
  "max_results": 5,
  "include_action_items": true
}
```

**Response:**
```json
{
  "answer": "ARB requirements for TriZetto environment provisioning include: (1) completed BOM with approved capacity sizing [[artifact/bom-template]], (2) High-Level Design with Security review sign-off [[runbook/arb-security-checklist]], (3) Control Tower guardrails enabled [[concept/control-tower-guardrails]], and (4) Audit Manager evidence pack initialized [[sop/evidence-pack-setup]].",
  "confidence": "high",
  "domain": "provisioning",
  "sources": [
    {
      "page_slug": "arb-security-checklist",
      "page_type": "runbooks",
      "s3_uri": "s3://llmwiki-bucket/wiki/runbooks/arb-security-checklist.md",
      "relevance_score": 0.94,
      "excerpt": "ARB requires: BOM approval, HLD sign-off, Security controls verification..."
    }
  ],
  "action_items": [
    "Complete BOM spreadsheet using wiki/artifacts/bom-template",
    "Submit HLD to ARB for security review",
    "Initialize Audit Manager evidence pack"
  ],
  "artifacts_referenced": [
    {"name": "BOM Template", "s3_key": "wiki/artifacts/bom-template.md"},
    {"name": "ARB Checklist", "s3_key": "wiki/runbooks/arb-security-checklist.md"}
  ],
  "gaps_detected": [],
  "wiki_page_count": 3,
  "use_case_tags": ["UC2"]
}
```

### 5.2 Domain-Scoped Query — `POST /wiki/query/{domain}`

Agents that know their domain can call directly without specifying it in the body. Domains: `customer-onboarding`, `provisioning`, `identity-access`, `configuration`, `data-migration`, `testing`, `cutover`, `handover`, `hypercare`.

```
POST /wiki/query/customer-onboarding
POST /wiki/query/provisioning
POST /wiki/query/testing
POST /wiki/query/cutover
```

Request body is the same as `/wiki/ask` minus the `domain` field.

### 5.3 Customer Context Retrieval — `GET /wiki/customer/{customer_id}`

Returns everything LLMWiki knows about a specific customer, synthesized from all ingested sources (SOW, persona docs, handoff notes, decisions made).

```
GET /wiki/customer/BCBS-MN-001
```

**Response:**
```json
{
  "customer_id": "BCBS-MN-001",
  "customer_name": "BlueCross BlueShield Minnesota",
  "overview": "Healthcare payer organization implementing TriZetto QNXT...",
  "key_facts": [...],
  "active_projects": [...],
  "products_in_scope": ["QNXT", "TriZetto Claims"],
  "personas": {...},
  "open_decisions": [...],
  "related_pages": [...],
  "last_updated": "2026-05-10"
}
```

### 5.4 Use Case Playbook — `GET /wiki/playbook/{use-case}`

Returns the complete, current playbook for a specific implementation lifecycle use case, assembled from all relevant wiki pages (runbooks, artifacts, decisions, SOPs).

```
GET /wiki/playbook/UC1   → Sales-to-Service playbook
GET /wiki/playbook/UC8   → Cutover playbook
GET /wiki/playbook/UC10  → Hypercare playbook
```

**Response:**
```json
{
  "use_case": "UC1",
  "title": "Sales to Service — Customer Onboarding Playbook",
  "current_as_of": "2026-05-13",
  "steps": [
    {"step": 1, "title": "SOW Review", "wiki_page": "runbooks/sow-review-checklist", "action_items": [...]},
    {"step": 2, "title": "Persona Generation", "wiki_page": "sops/persona-generation-sop", "action_items": [...]},
    {"step": 3, "title": "Knowledge Transfer Session", "wiki_page": "runbooks/handoff-session-guide", "action_items": [...]}
  ],
  "required_artifacts": [...],
  "decision_gates": ["G0"],
  "evidence_required": [...]
}
```

### 5.5 Artifact Retrieval — `GET /wiki/artifact/{type}`

Returns a specific reusable artifact template (BOM, checklist, SOP, runbook, test template).

```
GET /wiki/artifact/bom-template
GET /wiki/artifact/cutover-runbook
GET /wiki/artifact/pto-checklist
GET /wiki/artifact/hypercare-exit-criteria
```

### 5.6 Agent Contribution — `POST /wiki/contribute`

Agents write back knowledge they generate. This is the compounding mechanism.

**Request:**
```json
{
  "agent_id": "sales-to-service-agent-v1",
  "use_case": "UC1",
  "customer_id": "BCBS-MN-001",
  "contribution_type": "customer-context",
  "page_type": "customers",
  "page_slug": "bcbs-mn-001-onboarding-2026",
  "content": "# BCBS-MN Onboarding 2026\n\n## Customer Context\n...",
  "tags": ["customer-onboarding", "BCBS-MN", "2026"],
  "human_review_required": false
}
```

**Effect:** Creates or updates `wiki/customers/bcbs-mn-001-onboarding-2026.md` in S3, updates DynamoDB index, triggers KB sync. Future agents querying for BCBS-MN context get this page as a retrieval result.

### 5.7 API Gateway Route Table

```
POST /wiki/ask                      → Business Query Lambda (domain-aware, structured)
POST /wiki/query/{domain}           → Business Query Lambda (domain-prefixed)
GET  /wiki/playbook/{use-case}      → Playbook Assembly Lambda
GET  /wiki/customer/{customer-id}   → Customer Context Lambda
GET  /wiki/artifact/{type}          → S3 GetObject proxy (via Lambda)
POST /wiki/contribute               → Agent Contribution Lambda
GET  /wiki/status                   → existing (no change)
GET  /wiki/gaps                     → existing (no change)
POST /query                         → existing (no change, human UI backward compat)
```

---

## 6. Sales-to-Service Agent — First Use Case Deep Dive

UC1 is the first agent to consume LLMWiki. Its purpose: when a customer signs a SOW, ensure that all customer context — product scope, personas, key contacts, known constraints, historical decisions — is automatically surfaced to the delivery team.

### 6.1 Trigger and Flow

```
1. Sales team uploads SOW + Sales-to-Service deck to SharePoint
        │
        ▼ (SharePoint connector OR manual S3 drop)
2. LLMWiki Ingest Lambda fires
        │
        ▼ Bedrock Claude processes SOW
3. LLMWiki creates:
   • wiki/customers/{customer-slug}.md  ← customer entity page
   • wiki/sources/{sow-slug}.md         ← source summary
   • wiki/decisions/{initial-scope}.md  ← scope decisions extracted from SOW
        │
        ▼
4. Sales-to-Service Agent is triggered (EventBridge or SNS notification)
        │
        ▼
5. Agent calls LLMWiki Business API:
   GET  /wiki/customer/{customer-id}    ← everything known about this customer
   POST /wiki/ask  {domain: "customer-onboarding",
                    question: "What are the key delivery risks for this customer?",
                    context: {customer_id: ..., sow_ref: ...}}
   GET  /wiki/playbook/UC1             ← current onboarding playbook
        │
        ▼
6. Agent synthesizes:
   • Customer Persona document (V1 output)
   • Handoff summary with risk flags (V2 output)
   • Knowledge gaps identified (e.g., "No prior history for this customer in wiki")
        │
        ▼
7. Agent calls POST /wiki/contribute:
   • Writes wiki/customers/{customer-slug}-2026-handoff.md
   • Includes: persona, risks, decisions made, open questions
        │
        ▼
8. Next agent in chain (e.g., Environment Provisioning Agent) calls
   GET /wiki/customer/{customer-id} and gets the Sales-to-Service output
   as part of the customer context → seamless handoff
```

### 6.2 What the Sales-to-Service Agent Gets from LLMWiki

| API Call | LLMWiki Returns | Agent Uses It To |
|---|---|---|
| `GET /wiki/customer/{id}` | All prior history, existing pages | Build context for the delivery team |
| `POST /wiki/ask` (domain: onboarding) | Onboarding best practices, risk patterns from past projects | Generate risk-aware handoff summary |
| `GET /wiki/playbook/UC1` | Step-by-step onboarding checklist with artifacts | Drive the agent's execution plan |
| `GET /wiki/artifact/persona-template` | Customer persona template | Pre-populate with extracted SOW data |
| `POST /wiki/contribute` | (writes back) | Persist customer context for downstream agents |

### 6.3 Knowledge Gap Detection for UC1

When the agent calls `/wiki/ask` and the wiki returns low-confidence results (new customer, no prior history), LLMWiki automatically:
1. Identifies the gap ("No customer profile exists for BCBS-MN")
2. Creates a stub page in `wiki/customers/`
3. Returns the gap in the response so the agent can prompt a human to fill it
4. Records it in the gaps table for the Streamlit UI

---

## 7. Agent-to-Agent Handoff via LLMWiki

The wiki is the **handoff mechanism** between use cases. Instead of each agent passing a payload to the next agent, each agent **writes to the wiki** and the next agent **reads from the wiki**. This is the compounding mechanism.

```
UC1 Sales-to-Service Agent
  └─── POST /wiki/contribute → wiki/customers/{id}-handoff.md
                                         │
UC2 Provisioning Agent                   │ reads
  └─── GET /wiki/customer/{id} ──────────┘
  └─── POST /wiki/ask (domain: provisioning)
  └─── POST /wiki/contribute → wiki/decisions/{id}-bom-approved.md
                                         │
UC3 IAM Onboarding Agent                 │ reads
  └─── GET /wiki/customer/{id} ──────────┘
  └─── POST /wiki/query/identity-access
  └─── POST /wiki/contribute → wiki/decisions/{id}-iam-setup.md
                                         │
... (continues through UC4 → UC10)       │
                                         │
UC10 Hypercare Agent                     │ reads
  └─── GET /wiki/customer/{id} ──────────┘  (full lifecycle context)
  └─── POST /wiki/query/hypercare
  └─── POST /wiki/contribute → wiki/evidence/{id}-hypercare-exit.md
```

Each agent in the chain reads the **accumulated context** from all prior agents. The Hypercare agent, for instance, can ask LLMWiki "What provisioning decisions were made for this customer?" and get the answer from what the Provisioning agent wrote — without any direct inter-agent messaging.

---

## 8. LLMWiki Enhancements Required

### 8.1 New Lambda: Business Query Lambda

The current `query/handler.py` returns prose answers. A new **Business Query Lambda** wraps it with:

- **Domain routing**: routes the question to domain-filtered KB retrieval
- **Intent classification**: detects if the agent wants a checklist, narrative, template, or entity context
- **Structured response builder**: assembles `action_items`, `artifacts_referenced`, `use_case_tags`
- **Agent context injection**: uses `customer_id` and `project_phase` from request context to prioritize retrieval

New Lambda: `lambda/business_query/handler.py`
New API Gateway route: `POST /wiki/ask`, `POST /wiki/query/{domain}`

### 8.2 New Lambda: Playbook Assembly Lambda

`GET /wiki/playbook/{use-case}` assembles a playbook dynamically from:
1. DynamoDB query for pages tagged with `use_case_tags` containing the requested UC
2. S3 reads for each relevant page
3. Bedrock Claude synthesis: "Assemble a step-by-step playbook for UC{N} from these wiki pages"
4. Returns structured JSON with steps, artifacts, and decision gates

New Lambda: `lambda/playbook/handler.py`

### 8.3 New Lambda: Agent Contribution Lambda

`POST /wiki/contribute` validates, writes, and triggers KB sync:
1. Validates contribution schema (agent_id, page_type, content)
2. Writes wiki page to S3 under the appropriate domain prefix
3. Updates DynamoDB index with `contributing_agent` and `use_case_tags`
4. Triggers Bedrock KB ingestion job
5. Returns `{status: "indexed", page_slug: "...", s3_uri: "..."}`

New Lambda: `lambda/contribute/handler.py`

### 8.4 Wiki Page Schema Enhancement

All new wiki pages include extended frontmatter for domain filtering:

```yaml
---
title: ARB Security Checklist for Environment Provisioning
date: 2026-05-13
tags: [runbook, provisioning, security, arb]
use_case_tags: [UC2, UC8]          # NEW: which use cases this page supports
domain: provisioning               # NEW: primary domain
artifact_type: checklist           # NEW: for artifact retrieval endpoint
contributing_agent: provisioning-agent-v1  # NEW: if written by an agent
customer_id: ""                    # NEW: customer-specific pages
decision_gate: G1                  # NEW: alignment to AI Handbook decision gates
vector_alignment: [V1, V2]         # NEW: Cognizant AI vector alignment
action_items:                      # NEW: machine-parseable action list
  - "Complete BOM with approved capacity sizing"
  - "Submit HLD to ARB for security review"
evidence_required:                 # NEW: compliance evidence this page produces
  - "ARB checklist completed"
  - "BOM approval record"
source_count: 3
status: active
---
```

### 8.5 AGENTS.md Schema Extension

The `config/AGENTS.md` wiki schema (read by all Bedrock prompts) is extended with the new page types and enriched frontmatter templates so that both the ingest pipeline and agent contributions generate pages with the correct agent-friendly metadata.

### 8.6 Terraform: New Lambda + API Gateway Resources

Three new Lambdas + new API Gateway resources + IAM roles. The existing infrastructure is not modified — additions only.

---

## 9. S3 Layout — Agent-Readable Wiki Corpus

```
s3://llmwiki-bucket/
  config/
    AGENTS.md              ← wiki schema (extended with new page types)
    domain-registry.json   ← NEW: maps domain → s3 prefix, use_case_tags
    agent-registry.json    ← NEW: registered consuming agents + permissions

  raw/                     ← unchanged (source documents, immutable)
    papers/
    articles/
    notes/
    meetings/
    assets/

  wiki/                    ← LLM-generated pages (all indexed in Bedrock KB)
    sources/               ← one page per ingested source document
    entities/              ← people, orgs, systems, products
    concepts/              ← ideas, frameworks, methodologies
    runbooks/              ← NEW: operational procedures per use case
    customers/             ← NEW: customer-specific context and history
    artifacts/             ← NEW: document templates, BOMs, checklists
    decisions/             ← NEW: architecture and design decisions
    sops/                  ← NEW: standard operating procedures
    evidence/              ← NEW: compliance evidence patterns + audit trails
    questions/             ← stub pages for knowledge gaps (existing)
    index.md               ← master catalog (existing)
    overview.md            ← high-level synthesis (existing)

  output/                  ← query answers, analysis reports (existing)
  todos/                   ← gap analysis todo files (existing)
```

The **single Bedrock Knowledge Base** indexes the entire `wiki/` prefix. Domain filtering is achieved via KB metadata filters on the `domain` and `use_case_tags` frontmatter fields, which are indexed as KB metadata attributes.

---

## 10. MCP Tool Definitions for AgentCore Consumption

All consuming agents deployed in AWS AgentCore access LLMWiki via registered MCP tools. No agent calls the REST API directly — they call tools.

```json
{
  "tools": [
    {
      "name": "wiki_ask",
      "description": "Ask a business question to the LLMWiki knowledge base. Returns a structured answer with citations, action items, and confidence score.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "question": {"type": "string"},
          "domain": {"type": "string", "enum": ["customer-onboarding","provisioning","identity-access","configuration","data-migration","testing","cutover","handover","hypercare"]},
          "customer_id": {"type": "string"},
          "use_case": {"type": "string", "description": "UC1 through UC10"},
          "include_action_items": {"type": "boolean", "default": true}
        },
        "required": ["question"]
      }
    },
    {
      "name": "wiki_get_customer",
      "description": "Retrieve all knowledge about a specific customer from the wiki — SOW context, personas, decisions, history.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "customer_id": {"type": "string"}
        },
        "required": ["customer_id"]
      }
    },
    {
      "name": "wiki_get_playbook",
      "description": "Get the current step-by-step playbook for a specific implementation lifecycle use case (UC1–UC10).",
      "inputSchema": {
        "type": "object",
        "properties": {
          "use_case": {"type": "string", "description": "e.g. UC1, UC8, UC10"}
        },
        "required": ["use_case"]
      }
    },
    {
      "name": "wiki_get_artifact",
      "description": "Retrieve a specific artifact template (BOM, checklist, runbook, SOP, test template).",
      "inputSchema": {
        "type": "object",
        "properties": {
          "artifact_type": {"type": "string", "description": "e.g. bom-template, cutover-runbook, pto-checklist"}
        },
        "required": ["artifact_type"]
      }
    },
    {
      "name": "wiki_contribute",
      "description": "Write knowledge back to the wiki. Agents call this to persist decisions, completed checklists, customer context, and evidence — making it available to downstream agents.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "page_type": {"type": "string", "enum": ["customers","decisions","artifacts","evidence","sops"]},
          "page_slug": {"type": "string"},
          "content": {"type": "string", "description": "Full Markdown content with YAML frontmatter"},
          "customer_id": {"type": "string"},
          "use_case": {"type": "string"},
          "human_review_required": {"type": "boolean", "default": false}
        },
        "required": ["page_type", "page_slug", "content"]
      }
    },
    {
      "name": "wiki_get_gaps",
      "description": "Return current knowledge gaps — topics that agents tried to query but the wiki couldn't answer. Use to prioritize what documents to ingest.",
      "inputSchema": {"type": "object", "properties": {}}
    }
  ]
}
```

---

## 11. Response Contract for Agent Consumption

All `/wiki/ask` and `/wiki/query/{domain}` responses conform to this contract. Consuming agents can rely on this schema without parsing prose.

```json
{
  "answer": "string — synthesized, cited, in plain language",
  "confidence": "high | medium | low",
  "domain": "string — the domain that answered the question",
  "use_case_tags": ["UC1", "UC2"],
  "sources": [
    {
      "page_slug": "string",
      "page_type": "string",
      "s3_uri": "string",
      "relevance_score": 0.0,
      "excerpt": "string — relevant passage from this page",
      "artifact_type": "string | null",
      "decision_gate": "string | null"
    }
  ],
  "action_items": [
    "string — concrete action the agent or human should take"
  ],
  "artifacts_referenced": [
    {"name": "string", "s3_key": "string", "artifact_type": "string"}
  ],
  "evidence_required": [
    "string — compliance evidence this answer references"
  ],
  "gaps_detected": [
    {"type": "entity|concept|question", "slug": "string", "title": "string"}
  ],
  "contributing_agent_hint": "string | null — if next agent should contribute based on this answer"
}
```

**Why this matters:** A Sales-to-Service agent calling `wiki_ask` gets back not just an answer, but:
- Exactly which artifacts to use (BOM template, persona template)
- What actions to take (submit ARB, initialize evidence pack)
- What evidence to collect (for compliance gates G0–G6)
- What gaps exist (customer context missing → prompt human)

The agent can act on the response directly, without LLM re-interpretation.

---

## 12. Knowledge Compounding Mechanism

The wiki gets richer across the full lifecycle:

```
Ingest Phase (before UC1):
  wiki has: standards, procedures, artifact templates (ingested from TriZetto docs)

After UC1 (Sales-to-Service Agent):
  wiki gains: customer-specific context, persona, scope decisions, risk flags

After UC2 (Provisioning Agent):
  wiki gains: BOM decisions, HLD approvals, ARB outcomes for this customer

After UC3–UC5 (IAM, Config, Migration Agents):
  wiki gains: access patterns, config decisions, data mapping choices, exceptions

After UC6–UC7 (Testing Agents):
  wiki gains: test results, known defects, automation patterns that worked

After UC8 (Cutover Agent):
  wiki gains: actual cutover runbook used, rollback decisions made, incident log

After UC9 (PTO/Handover Agent):
  wiki gains: customer education materials, SOP approvals, DR brief

After UC10 (Hypercare Agent):
  wiki gains: monitoring thresholds that triggered, business health patterns, exit evidence

Next Customer:
  wiki has: all the above from prior implementations → richer answers, better playbooks
```

This is the compounding effect described in the LLMWiki methodology: **the wiki gets better with every agent run, for every subsequent project.**

---

## 13. Security and Governance

### 13.1 Agent Identity

Each consuming agent authenticates to the Business Knowledge API using an **API Gateway usage plan key** (Phase 1) or **IAM SigV4** (Phase 2 / AgentCore native). The `contributing_agent` frontmatter field records which agent wrote each wiki page.

### 13.2 Human-in-the-Loop for Contributions

Agent contributions with `human_review_required: true` land in `wiki/pending/` rather than `wiki/` and are not indexed in the Bedrock KB until a human approves them via the Streamlit UI. High-risk contributions (cutover runbooks, compliance evidence) default to `human_review_required: true`.

### 13.3 AI Handbook Alignment

Every wiki page contributed by an agent includes the `vector_alignment` frontmatter field ([V1], [V2], [V3]) aligned to the Cognizant 3-Vector AI model from the AI Handbook Workbook. This enables governance reporting: "How many V3 (agentic) contributions were made this quarter, and were they reviewed?"

### 13.4 Decision Gate Evidence

Wiki pages tagged with `decision_gate` (G0–G6) are the LLMWiki contributions that satisfy security approval evidence requirements. The `/wiki/ask` response's `evidence_required` field maps directly to the AI Handbook Workbook's Appendix A evidence bundles, giving agents an explicit list of what to collect at each gate.

---

## 14. Implementation Roadmap

### Phase 1 (Now — in progress): Core LLMWiki
- [x] S3 + Lambda ingest → wiki pages
- [x] Bedrock KB + query Lambda
- [x] API Gateway `/query` + `/wiki/status` + `/wiki/gaps`
- [x] Streamlit UI
- [ ] **Deploy to AWS account 392568849512 (us-east-1)**

### Phase 2 (Agent API — 2 weeks): Business Knowledge API
- [ ] New Lambda: `business_query/handler.py` — domain-aware structured query
- [ ] New Lambda: `contribute/handler.py` — agent write-back
- [ ] New Lambda: `playbook/handler.py` — use-case playbook assembly
- [ ] API Gateway: new routes (`/wiki/ask`, `/wiki/query/{domain}`, `/wiki/contribute`, `/wiki/playbook/{uc}`)
- [ ] AGENTS.md schema extension: new page types + enriched frontmatter
- [ ] Terraform: new Lambdas, API routes, IAM roles
- [ ] Initial wiki content: ingest TriZetto implementation standards docs (SOW template, BOM template, ARB checklist, PTO checklist from AIFactory directory)

### Phase 3 (Sales-to-Service Agent — 3 weeks): First Consumer
- [ ] Sales-to-Service Agent deployed in AWS AgentCore
- [ ] MCP tools registered: `wiki_ask`, `wiki_get_customer`, `wiki_contribute`
- [ ] SharePoint connector: auto-ingest SOWs from SharePoint
- [ ] End-to-end test: upload SOW → agent queries wiki → agent contributes customer page → human reviews
- [ ] Demo: Sales-to-Service Agent surfaces customer context for BCBS-MN 2026 project

### Phase 4 (Agent Fleet — 6 weeks): All 10 Use Cases
- [ ] Provisioning Agent (UC2)
- [ ] IAM Onboarding Agent (UC3)
- [ ] Configuration Agent (UC4)
- [ ] Data Migration Agent (UC5)
- [ ] SIT/E2E Testing Agents (UC6, UC7)
- [ ] Cutover Planning Agent (UC8)
- [ ] PTO/Handover Agent (UC9)
- [ ] Hypercare Agent (UC10)
- [ ] Wiki Orchestrator Agent (routes user intent to right sub-agent)
- [ ] Full lifecycle demo: BCBS-MN from SOW to hypercare exit, all wiki contributions visible

### Phase 5 (Production — 8 weeks): Full Architecture
- [ ] OpenSearch (hybrid search, domain facets)
- [ ] Neptune (knowledge gap detection across customer graph)
- [ ] GitHub Actions CI/CD
- [ ] Cognito + IAM SigV4 auth
- [ ] Multi-wiki (one wiki instance per product line: QNXT wiki, Claims wiki)

---

## 15. Why LLMWiki Is the Right Knowledge Backend for This Agent Fleet

| Alternative | Why Not |
|---|---|
| **Each agent has its own RAG** | Agents duplicate knowledge; consistency impossible; no compounding; high cost |
| **Shared document store (SharePoint/Kendra)** | Returns raw documents, not synthesized knowledge; agents must re-derive answers; no contribution mechanism |
| **Shared vector DB only** | No structure; no page types; no relationships; no gap detection; no contribution |
| **Static knowledge base (human-written)** | Goes stale; doesn't compound; requires human maintenance |
| **LLMWiki** | Pre-synthesized structured pages; domain-filtered retrieval; agents contribute back; wiki compounds across entire lifecycle; one Bedrock KB serves all agents |

The single most important property: **LLMWiki is the only approach where each agent both reads AND writes**, creating a positive feedback loop. Every SOW ingested, every agent decision contributed, every customer context page written makes the next agent run — for any use case, for any customer — more accurate.

---

## 16. Immediate Next Actions

1. **Deploy Phase 1** (current code to AWS account 392568849512): `scripts/deploy.sh`
2. **Ingest seed content**: upload TriZetto implementation docs from `AIFactory/` directory into S3 `raw/` — especially the AI Handbook Workbook, ARB checklist, BOM template, PTO checklist
3. **Build Phase 2 Business Query Lambda** (`lambda/business_query/handler.py`) — the `/wiki/ask` endpoint is the unlock for all consuming agents
4. **Define MCP tool contracts** for AgentCore (Section 10 of this document)
5. **Prioritize Sales-to-Service Agent** as the Phase 3 integration target — it is the entry point for all subsequent use cases

---

*End of LLMWiki Agentic Architecture Design v1.0*

*Related documents: `LLMWikiDesign.md` (full AWS architecture), `LLMWikiDesignMVP.md` (phase plan), `code/config/AGENTS.md` (wiki schema), `AIFactory/AI_Handbook_Workbook_Implement Phase.docx` (10 use cases)*
