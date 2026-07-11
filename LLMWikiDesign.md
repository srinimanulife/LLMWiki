# LLMWiki on AWS AgentCore — System Design

**Version:** 2.0  
**Date:** 2026-05-14  
**Status:** Design / Active Implementation  

---

## 1. Executive Summary

LLMWiki is a persistent, compounding knowledge base where a large language model incrementally builds and maintains interlinked wiki pages from raw source documents. Unlike RAG (which re-derives answers on every query from raw documents), LLMWiki extracts, cross-references, and synthesizes knowledge once into structured wiki pages — then keeps those pages current as new sources arrive. The wiki gets richer with every ingestion cycle.

This document describes the full system design for deploying LLMWiki on AWS, using AWS AgentCore as the agent runtime, with source ingestion from configurable locations (SharePoint, S3, web URLs, and others), and a **Search Wiki Agent** that can operate standalone or be composed into a larger agentic workflow.

**Key design goals:**
- Configurable source connectors (SharePoint, S3, web, Confluence, email)
- Fully cloud-native — no desktop tools, no local dependencies
- Search Wiki Agent deployable as a callable sub-agent in AgentCore multi-agent flows
- Docker-based, ECS Fargate–deployable containers
- Wiki knowledge persists across agent sessions via S3 + OpenSearch + DynamoDB
- LLM-owned wiki pages; humans only direct the process
- **Reusable agent skills** composable across all 10 use-case agents in the AI lifecycle

---

## 2. Architecture Overview

The system is organized into six horizontal layers, each with well-defined responsibilities and clear interfaces between them:

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 6: Interface & Composition                                │
│  AgentCore Search Wiki Agent endpoint                            │
│  API Gateway (REST) · Cognito/IAM auth                          │
│  Multi-agent composition (supervisor ↔ wiki sub-agent)          │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LAYER 5: Agent Runtime (AWS AgentCore)                          │
│  Skill Registry (SK-01 to SK-09) · UC Agent Fleet (UC1–UC10)    │
│  Search Wiki Agent · Ingest Agent · Gap Analysis Agent           │
│  MCP Tool Registry · Agent Memory (AgentCore Memory Store)      │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LAYER 4: Wiki Storage & Search                                  │
│  S3 (wiki pages, raw/, output/, todos/) · DynamoDB (index, log) │
│  Amazon OpenSearch Service (vector + full-text search)           │
│  Amazon Neptune (knowledge graph, entity relationships)          │
│  Amazon Bedrock Knowledge Bases (semantic retrieval)             │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LAYER 3: Processing Pipeline                                    │
│  AWS Step Functions (pipeline orchestration)                     │
│  Amazon Bedrock Claude (summarization, extraction, synthesis)    │
│  Lambda (chunking, embedding, index updates)                     │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LAYER 2: Document Conversion                                    │
│  Amazon Textract (PDF → structured text)                         │
│  Amazon Transcribe (audio/video → transcript)                    │
│  Lambda (HTML/DOCX/EPUB → Markdown via Pandoc)                  │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LAYER 1: Source Ingestion Connectors                            │
│  SharePoint · S3 (cross-account) · Web URLs · Confluence        │
│  Email (SES) · YouTube/Podcast · Database exports               │
│  Landing Zone: S3 raw/ bucket (versioned, immutable)            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Principles

These principles govern all design decisions, adapted from the LLMWiki methodology for the cloud/enterprise context:

1. **The LLM writes the wiki; humans direct it.** Source connectors, schema configuration, and query prompts are the only human-controlled inputs. All wiki page creation and maintenance is LLM-owned.

2. **Raw sources are immutable.** The `raw/` S3 prefix is write-once, never modified by the processing pipeline. Ingest agents read it; they never overwrite it.

3. **Acquire and Process are separate operations.** Source collection (Layer 1-2) and wiki page generation (Layer 3) run independently, on different cadences, and fail independently. This is architecturally enforced by the Step Functions pipeline design.

4. **Knowledge compounds.** Good query answers are filed back into the wiki as new pages. Each ingestion cycle increases the depth of cross-references and synthesis.

5. **The wiki is the source of truth for agents.** Agents query the wiki — not raw documents — for answers. This keeps context windows small, latency low, and answers consistent.

6. **The Search Wiki Agent is a composable unit.** It must be callable as a sub-agent in any larger AgentCore workflow without modification, via a stable MCP tool interface.

7. **Configuration drives behavior.** Schema (what page types exist, what conventions apply, what sources to monitor) lives in AWS Systems Manager Parameter Store and S3 config objects — not hardcoded in containers.

8. **Skills are composable, not duplicated.** Each UC agent cherry-picks from a shared Skill Registry. Common behavior — context bootstrap, knowledge query, contribution, gap detection — is written once and versioned independently of the agents that use it.

---

## 4. Layer 1 — Source Ingestion Connectors

### 4.1 Connector Architecture

Each connector is a standalone ECS task (Docker container) that pulls from an external source and deposits converted documents into the S3 `raw/` prefix. Connectors are:

- **Independently schedulable** via Amazon EventBridge Scheduler
- **Independently configurable** via Parameter Store (credentials, paths, filters)
- **Source-type aware** — they determine the correct `raw/` subfolder (papers/, articles/, notes/, youtube/, etc.)
- **Idempotent** — re-running a connector does not duplicate documents (checked via an S3 object existence check using a deterministic key derived from source identity)

### 4.2 Supported Source Types

| Source | Connector Mechanism | Credential Store | Target raw/ prefix |
|--------|--------------------|-----------------|--------------------|
| **SharePoint Online** | Microsoft Graph API via Lambda or AppFlow | Secrets Manager (OAuth client credentials) | raw/articles/ or raw/notes/ |
| **AWS S3 (same/cross-account)** | S3 replication rule or EventBridge + Lambda copy | IAM role (cross-account assumed role) | raw/ (type by extension) |
| **Web URLs (batch)** | Lambda + WebFetch / BeautifulSoup headless | None / Parameter Store for auth headers | raw/articles/ |
| **Confluence Cloud** | Confluence REST API v2 via Lambda | Secrets Manager (API token) | raw/articles/ or raw/notes/ |
| **Email (SES + S3)** | SES inbound rule → S3 → Lambda parse | IAM | raw/communications/ |
| **YouTube / Podcast** | yt-dlp + Amazon Transcribe (audio→transcript) | Parameter Store (yt-dlp options) | raw/youtube/ |
| **Google Drive** | Google Drive API via Lambda | Secrets Manager (service account JSON) | raw/notes/ |
| **Database export** | Lambda + JDBC/API → CSV/JSON → Markdown | Secrets Manager (DB credentials) | raw/data/ |
| **RSS / News feeds** | Lambda + feedparser on schedule | Parameter Store (feed URLs) | raw/articles/ |
| **Direct S3 drop** | S3 Event Notification → processing trigger | IAM | raw/ (detected by extension) |

### 4.3 Amazon Kendra for SharePoint (Alternative)

Amazon Kendra has a native SharePoint connector that can index SharePoint content directly. For enterprise deployments, Kendra can serve as both the SharePoint ingestion mechanism and the full-text search layer simultaneously, bypassing the need for a custom connector and the raw/ landing step for SharePoint specifically.

### 4.4 AWS AppFlow for SaaS Sources

For sources supported by AppFlow (Salesforce, Slack, ServiceNow, Google Analytics, Marketo, etc.), AppFlow handles the authentication, scheduling, and S3 landing automatically. The LLMWiki processing pipeline treats AppFlow-delivered files the same as any other raw/ file.

### 4.5 Source Registry

A DynamoDB table (`wiki-source-registry`) tracks every source ever added:

- Source ID (hash of origin URL or file path)
- Source type (sharepoint, s3, web, etc.)
- Last ingested timestamp
- Raw/ S3 key
- Processing status (raw / converted / wiki-page-created)
- Connector used

This registry prevents re-ingestion of unchanged sources and provides the inventory for Phase 9 (PROCESS).

---

## 5. Layer 2 — Document Conversion

All source documents must be converted to Markdown before landing in the `raw/` S3 prefix. The processing pipeline cannot operate on PDFs, audio files, or HTML directly — only Markdown. Conversion is a one-time operation per source; the converted `.md` file is the canonical input to all downstream processing.

### 5.1 Conversion Services

| Input Format | Conversion Service | Output | Notes |
|---|---|---|---|
| PDF | Amazon Textract (DetectDocumentText + AnalyzeDocument) | Structured Markdown | Tables, headers, and figures preserved. Original PDF kept in raw/assets/ |
| Audio / Video | Amazon Transcribe (batch or streaming) | Transcript Markdown | Speaker diarization enabled where useful |
| YouTube URL | Transcribe (via yt-dlp download → Transcribe) or Transcribe Media URL | Transcript Markdown | Caption tracks used if available, fallback to Transcribe |
| HTML / Web page | Lambda function (Pandoc or html2text or Readability.js) | Clean Markdown | Strips nav, ads, and boilerplate |
| DOCX / ODT | Lambda (Pandoc) | Markdown | Track changes stripped |
| EPUB | Lambda (Pandoc, per-chapter split) | One .md per chapter | Chapter boundaries preserved |
| PPTX | Lambda (python-pptx → slide-per-section Markdown) | Markdown with slide breaks | Speaker notes included |
| Images (OCR) | Amazon Textract | Text Markdown | For scanned documents or screenshots |
| CSV / JSON | Lambda (custom formatter) | Markdown table or YAML block | For data/metrics sources |

### 5.2 Conversion Orchestration

An AWS Step Functions state machine (`wiki-conversion-pipeline`) handles each incoming raw document:

```
[Detect Format] → [Route to Converter] → [Convert] → [Validate Output]
       ↓                                                      ↓
  [Log Failure]                                    [Write .md to raw/prefix/]
                                                          ↓
                                               [Update Source Registry]
                                                          ↓
                                          [Emit S3 Event → Processing Trigger]
```

Conversion failures are logged to CloudWatch and the source registry is updated with status `conversion-failed`. A dead-letter queue holds failed items for manual review.

---

## 6. Layer 3 — Processing Pipeline (raw/ → wiki/)

This layer reads converted Markdown files from `raw/` and produces or updates structured wiki pages in `wiki/`. It is the core intelligence layer — all LLM calls happen here.

### 6.1 Processing Pipeline State Machine

A Step Functions Express Workflow (`wiki-ingest-pipeline`) executes per source document:

```
[Check if already processed] 
         ↓ (unprocessed)
[Read source .md from S3]
         ↓
[Bedrock: Generate source summary]
         ↓
[Bedrock: Extract entities (people, orgs, concepts, products)]
         ↓
[For each entity: Check if wiki page exists in DynamoDB index]
         ↓
    ┌────┴────┐
[Create new  [Update existing
 entity page] entity page]
    └────┬────┘
         ↓
[Bedrock: Generate/update concept pages for key ideas]
         ↓
[Bedrock: Detect contradictions with existing wiki pages]
         ↓
[Bedrock: Update overview.md if source is significant]
         ↓
[Write all new/updated pages to S3 wiki/]
         ↓
[Update DynamoDB index (new pages, updated pages)]
         ↓
[Append to DynamoDB log table]
         ↓
[Upsert all pages into OpenSearch (full-text + vector)]
         ↓
[Update Neptune knowledge graph (entity nodes + relationships)]
         ↓
[Update Source Registry: status = wiki-page-created]
```

### 6.2 Bedrock Integration

All LLM calls use **Amazon Bedrock** with **Claude** (Sonnet or Opus, configurable per task type):

- **Source summary generation:** Claude Sonnet (speed/cost optimized)
- **Entity extraction:** Claude Sonnet with structured JSON output (tool use)
- **Concept page synthesis:** Claude Opus (quality-critical, cross-source synthesis)
- **Contradiction detection:** Claude Opus (reasoning-heavy)
- **Overview updates:** Claude Opus (high-level synthesis)

Model selection per task is stored in Parameter Store and hot-swappable without container redeployment.

Bedrock calls use **Prompt Caching** (Anthropic's system prompt caching) for the wiki schema instructions and existing wiki context, significantly reducing token costs on repeated operations.

### 6.3 Wiki Page Types

The processing pipeline generates and maintains these page types in `wiki/`:

| Page Type | S3 Prefix | Description |
|---|---|---|
| Source summaries | wiki/sources/ | One page per raw source — summary, key takeaways, quotes, links to entity pages |
| Entity pages | wiki/entities/ | People, organizations, products, systems — accumulated from all sources mentioning them |
| Concept pages | wiki/concepts/ | Ideas, theories, frameworks — synthesized from all sources discussing them |
| Comparison pages | wiki/comparisons/ | Auto-generated when ≥2 entities of the same type exist |
| Timeline pages | wiki/timelines/ | When chronological data is detected in sources |
| Question pages | wiki/questions/ | Open research questions surfaced during processing |
| Synthesis pages | wiki/synthesis/ | Cross-source analysis, argument pages, original analysis |
| **Runbook pages** | wiki/runbooks/ | Step-by-step operational procedures per use case (UC1–UC10) |
| **Customer pages** | wiki/customers/ | Customer-specific context: SOW summaries, personas, handoff notes |
| **Artifact pages** | wiki/artifacts/ | Document templates: BOM, checklists, persona templates, test plans |
| **Decision pages** | wiki/decisions/ | Architecture decisions, ARB outcomes, scope decisions |
| **SOP pages** | wiki/sops/ | Standard operating procedures for ops and support teams |
| **Evidence pages** | wiki/evidence/ | Compliance evidence templates and audit trail patterns |
| Index | wiki/index.md | Master catalog of all wiki pages |
| Overview | wiki/overview.md | High-level summary of everything in the wiki |
| Log | wiki/log.md (+ DynamoDB) | Append-only record of all operations |

### 6.4 Batch vs. Event-Driven Processing

**Event-driven mode:** S3 Event Notification triggers the pipeline immediately when a new file lands in `raw/`. Suitable for low-volume wikis or time-sensitive updates.

**Batch mode:** EventBridge Scheduler triggers the pipeline on a cron schedule (e.g., nightly). Processes all unprocessed `raw/` files in a single Step Functions map state. More cost-efficient for high-volume ingestion.

Both modes are configurable via Parameter Store. The source registry ensures no document is processed twice in either mode.

---

## 7. Layer 4 — Wiki Storage & Search

### 7.1 Amazon S3 — Wiki Page Store

The primary storage for all wiki content:

```
s3://wiki-bucket/
  raw/                     # Immutable source documents (converted .md)
    papers/
    articles/
    notes/
    youtube/
    assets/                # Original PDFs, audio files (non-processed)
  wiki/                    # LLM-generated pages
    sources/
    entities/
    concepts/
    comparisons/
    timelines/
    questions/
    synthesis/
    runbooks/              # UC-tagged procedures
    customers/             # Customer-specific context
    artifacts/             # Document templates
    decisions/             # Architecture decisions (HITL gate)
    sops/                  # Standard operating procedures
    evidence/              # Compliance evidence (HITL gate)
    pending/               # Staged for human review (not in KB)
    index.md
    overview.md
    log.md
  output/                  # Query answers, analysis reports, gap analyses
  todos/                   # Research priority files
  config/                  # AGENTS.md schema, wiki configuration
  infranodus/              # Knowledge graph ontology files
```

S3 versioning is enabled on the `wiki/` prefix — every LLM write creates a new version, providing a complete edit history without a separate git repository. S3 Lifecycle policies archive older versions to S3 Glacier after 90 days.

### 7.2 Amazon DynamoDB — Index and Metadata

Two DynamoDB tables:

**`wiki-index` table:** The machine-readable equivalent of `wiki/index.md`
- Partition key: `page_type` (entity, concept, source, etc.)
- Sort key: `page_slug` (kebab-case page name)
- Attributes: S3 key, title, tags, source_count, last_updated, status, wikilinks (list of related page slugs)
- GSI on `last_updated` for recency queries
- GSI on `status` for finding stale or incomplete pages

**`wiki-log` table:** Append-only operation log
- Partition key: `date` (YYYY-MM-DD)
- Sort key: `timestamp#operation_id`
- Attributes: operation type (ingest/update/lint/query), source processed, pages created/updated, contradictions flagged, duration

### 7.3 Amazon OpenSearch Service — Search Layer

Replaces Obsidian's graph view and InfraNodus's text analysis for **search and discovery**:

- **Full-text search** across all wiki pages (BM25)
- **Semantic/vector search** using k-NN with embeddings from Amazon Titan Embeddings or Cohere Embed (via Bedrock)
- **Hybrid search** (BM25 + k-NN combined scoring) for best relevance
- **Faceted search** by page type, tags, date range, source count
- **Wikilink traversal** — OpenSearch stores wikilink relationships, enabling "find pages linked from this page" queries

Each wiki page is indexed with:
- Full text content
- YAML frontmatter fields (title, tags, source_count, status)
- Dense vector embedding
- Sparse vector (for BM25)
- `wikilinks` array (linked page slugs)
- `page_type` facet

OpenSearch is deployed in **Serverless** mode for variable workloads, or **managed domain** for predictable traffic.

### 7.4 Amazon Bedrock Knowledge Bases — Semantic Retrieval

A Bedrock Knowledge Base is configured over the `wiki/` S3 prefix, providing:

- Automatic re-chunking and re-embedding when wiki pages are updated
- Native integration with Bedrock Agents (the Search Wiki Agent can use KB retrieve as a built-in action)
- Citations returned with every retrieval (which wiki page, which passage)
- Metadata filtering (filter by page_type, tags, date range)

The Knowledge Base uses S3 Vectors as its vector store backend.

### 7.5 Amazon Neptune — Knowledge Graph

Neptune stores the entity relationship graph:

- **Nodes:** Every wiki entity, concept, and source page
- **Edges:** Typed relationships extracted by the LLM (isA, causes, contradicts, relatedTo, mentionedIn, supersedes, etc.)
- **Properties:** Confidence score, source count, first/last seen timestamps

Neptune enables:
- Knowledge gap detection: disconnected subgraphs = research gaps
- Shortest path queries: "how is concept A related to concept B?"
- Cluster analysis: which topics are most densely connected?
- Orphan detection: nodes with no edges = incomplete wiki pages

Neptune is accessed via the Gremlin API (property graph) from Lambda functions in the processing pipeline and from the Gap Analysis Agent.

---

## 8. Layer 5 — Agent Runtime (AWS AgentCore)

### 8.1 Agent Inventory

Five platform agents are deployed in AgentCore, plus the UC agent fleet (Section 20):

| Agent | Role | Trigger | AgentCore Type |
|---|---|---|---|
| **Search Wiki Agent** | Answers queries against the wiki | API call / sub-agent invocation | Inline agent or supervisor-managed sub-agent |
| **Ingest Agent** | Orchestrates raw/ → wiki/ processing | S3 event / scheduled / API call | Event-driven agent |
| **Gap Analysis Agent** | Analyzes Neptune graph for research gaps, generates todos | Scheduled / API call | Scheduled agent |
| **Lint Agent** | Finds contradictions, orphans, stale pages | Scheduled (weekly or on-demand) | Scheduled agent |
| **Wiki Orchestrator** | Routes user requests to the right sub-agent | API call / user-facing | Supervisor agent |

### 8.2 Search Wiki Agent — Detailed Design

This is the primary consumer-facing agent and the one exposed for multi-agent composition.

**Tools available to the Search Wiki Agent:**

| Tool Name | Description | Backing Service |
|---|---|---|
| `search_wiki` | Semantic + full-text search across all wiki pages | OpenSearch + Bedrock KB |
| `get_wiki_page` | Retrieve full content of a specific wiki page | S3 GetObject |
| `get_entity_context` | Get all wiki knowledge about a named entity | DynamoDB index + S3 |
| `traverse_wikilinks` | Follow wikilink graph from a starting page | OpenSearch wikilinks field |
| `get_wiki_overview` | Return the current wiki overview.md | S3 GetObject |
| `list_pages_by_type` | List all pages of a given type | DynamoDB query |
| `find_related_concepts` | Neptune shortest-path query between two concepts | Neptune Gremlin |
| `get_recent_changes` | Return recently updated pages | DynamoDB log query |
| `answer_and_file` | Generate a synthesized answer and optionally save it as a wiki output page | Bedrock + S3 |

**Search Wiki Agent behavior:**
1. Receives a natural language query
2. Uses `search_wiki` to find top-k relevant wiki pages
3. Reads full page content for top results via `get_wiki_page`
4. Synthesizes a cited answer using Claude (via Bedrock, not a separate call — done in the agent's own generation step)
5. Optionally saves the answer to `output/` via `answer_and_file`
6. Returns: synthesized answer + list of source wiki pages with S3 URIs

**AgentCore Memory:** The Search Wiki Agent uses AgentCore's built-in Memory Store to retain session context — so follow-up questions within a session build on prior answers without re-retrieving the same pages.

### 8.3 Ingest Agent — Detailed Design

**Tools available to the Ingest Agent:**

| Tool Name | Description | Backing Service |
|---|---|---|
| `list_unprocessed_sources` | Check source registry for raw files without wiki pages | DynamoDB source-registry |
| `trigger_processing_pipeline` | Start Step Functions execution for a source | Step Functions StartExecution |
| `check_pipeline_status` | Poll Step Functions execution status | Step Functions DescribeExecution |
| `update_wiki_schema` | Read/write AGENTS.md config from S3 | S3 GetObject/PutObject |
| `flag_contradiction` | Add a contradiction notice to a wiki page | S3 GetObject/PutObject + DynamoDB |

### 8.4 Gap Analysis Agent — Detailed Design

Replaces InfraNodus gap analysis with Neptune + Claude:

**Workflow:**
1. Query Neptune for disconnected subgraph clusters (potential research gaps)
2. Query Neptune for low-degree nodes (entities with few connections = under-explored)
3. Read `wiki/questions/` pages for open research questions
4. Read DynamoDB index for page types with low source_count
5. Run Bedrock Claude analysis: "Given these graph statistics and wiki page counts, what are the top research priorities?"
6. Generate todo files in `output/todos/` and S3 `todos/` prefix
7. Return gap analysis report

**Gap types detected:**
- Disconnected clusters (no path between two topic areas)
- Under-explored entities (entity page exists but only 1-2 sources)
- Missing synthesis (multiple sources reference a concept but no synthesis page exists)
- Empty page types (e.g., no timeline pages despite temporal data in sources)
- Orphan pages (no inbound wikilinks)

### 8.5 Wiki Orchestrator — Multi-Agent Routing

The Orchestrator is the top-level agent exposed to end users or external calling agents. It:

- Receives natural language instructions
- Classifies intent: search query / ingest request / gap analysis / lint / plan
- Routes to the appropriate sub-agent
- Composes multi-step operations (e.g., "ingest these URLs and then tell me what gaps remain")
- Maintains conversation context across sub-agent calls via AgentCore session state

---

## 9. Layer 6 — Interface & Multi-Agent Composition

### 9.1 Amazon API Gateway

REST API exposing the wiki operations:

| Endpoint | Method | Agent | Description |
|---|---|---|---|
| `/wiki/ask` | POST | Business Query Lambda | Structured JSON query for agent consumption |
| `/wiki/query/{domain}` | POST | Business Query Lambda | Domain-scoped query |
| `/wiki/playbook/{uc}` | GET | Playbook Lambda | Step-by-step use-case playbook |
| `/wiki/customer/{id}` | GET | Playbook Lambda | All context for a specific customer |
| `/wiki/artifact/{type}` | GET | Playbook Lambda | Retrieve artifact template |
| `/wiki/contribute` | POST | Contribute Lambda | Agent write-back to wiki |
| `/wiki/query` | POST | Search Wiki Agent | Natural language query against the wiki |
| `/wiki/ingest` | POST | Ingest Agent | Trigger ingestion of new sources |
| `/wiki/gaps` | GET | Gap Analysis Agent | Get current gap analysis report |
| `/wiki/status` | GET | Orchestrator | Wiki health summary |

Authentication: AWS IAM SigV4 for agent-to-agent calls; Cognito user pools for human users.

### 9.2 AgentCore Sub-Agent Interface

The Search Wiki Agent is exposed as an AgentCore-callable agent with a stable contract:

**Input schema (AgentCore invoke):**
```
action: search | get_page | get_overview | list_gaps | answer_and_file
query: string (natural language, required for search and answer_and_file)
filters: { page_type?, tags?, date_from?, date_to? } (optional)
save_answer: boolean (whether to persist to output/, default false)
```

**Output schema:**
```
answer: string (synthesized response)
sources: [ { page_slug, page_type, s3_uri, relevance_score } ]
confidence: low | medium | high
gaps_detected: [ string ] (optional, populated if answer is incomplete)
```

### 9.3 MCP Tool Registry

The Search Wiki Agent's tools are registered in AgentCore's MCP Tool Registry, making them discoverable and callable by other AgentCore-hosted agents without going through the REST API:

- `wiki_search(query, filters)` — semantic wiki search
- `wiki_get_page(slug)` — retrieve page
- `wiki_get_context(entity_name)` — get all context for an entity
- `wiki_get_gaps()` — get current research gaps
- `wiki_get_overview()` — get wiki summary

---

## 10. Container Architecture (Docker + ECS Fargate)

### 10.1 Container Inventory

| Container | ECS Launch Type | Scaling | Purpose |
|---|---|---|---|
| `wiki-source-connector` | Fargate (scheduled task) | N/A (run-to-completion) | Source ingestion from all connectors |
| `wiki-converter` | Fargate (event-driven task) | Per-document scaling | Document format conversion |
| `wiki-processor` | Fargate (event-driven task) | Per-batch scaling | raw/ → wiki/ LLM processing |
| `wiki-indexer` | Fargate (event-driven task) | Per-batch scaling | OpenSearch + Neptune updates |
| `wiki-agent-runtime` | Fargate (long-running service) | Auto-scaling (target tracking) | AgentCore agent hosting |
| `wiki-api` | Fargate (long-running service) | Auto-scaling | API Gateway integration |
| `wiki-gap-analyzer` | Fargate (scheduled task) | N/A (run-to-completion) | Gap analysis and todo generation |

### 10.2 Container Configuration

Each container is configured entirely through environment variables drawn from:
- **AWS Systems Manager Parameter Store** — non-sensitive config (S3 bucket names, table names, model IDs, batch sizes)
- **AWS Secrets Manager** — sensitive config (external API keys, SharePoint credentials, database passwords)
- **IAM Task Role** — AWS service access (no credentials in environment for AWS services)

This means the same Docker image runs in dev, staging, and prod with different Parameter Store paths injected at task launch time.

### 10.3 Container Registry

Amazon Elastic Container Registry (ECR) hosts all container images:
- Image scanning on push (ECR enhanced scanning with Inspector)
- Immutable tags for production images (no `latest` in production)
- Lifecycle policy: keep last 10 images per repository

### 10.4 Networking

All containers run in **private subnets** within a dedicated VPC:
- No public IP addresses on ECS tasks
- Outbound internet access via NAT Gateway (for Bedrock, external connectors)
- VPC endpoints for S3, DynamoDB, SQS, ECR, Secrets Manager, Parameter Store (eliminates NAT for AWS services)
- Security groups: each container type has its own SG with least-privilege rules
- The `wiki-api` container is the only one fronted by an Application Load Balancer (in public subnets)

---

## 11. Configuration Management (Schema Layer)

The wiki schema (equivalent to `CLAUDE.md` / `AGENTS.md` in the local LLMWiki) is stored in AWS and loaded by agents and pipeline workers at runtime.

### 11.1 Schema Storage

**S3 config object:** `s3://wiki-bucket/config/AGENTS.md`
- The full wiki schema document: page templates, ingest workflow, conventions, page type definitions
- Versioned in S3 — every schema update is a new S3 version (full history preserved)
- Read by: all Bedrock Claude prompts (injected as system prompt), all agents, all pipeline workers

**Parameter Store hierarchy:**
```
/wiki/{env}/
  connector/sharepoint/tenant_id
  connector/sharepoint/site_url
  connector/sharepoint/folder_path
  connector/s3_source/bucket
  connector/s3_source/prefix
  processing/llm_model_summary       (e.g., us.anthropic.claude-sonnet-4-6)
  processing/llm_model_synthesis     (e.g., us.anthropic.claude-opus-4-7)
  processing/batch_size
  processing/auto_create_entities    (true/false)
  search/opensearch_endpoint
  search/index_name
  wiki/bucket_name
  wiki/tier                          (light/medium/heavy)
  agent/search_agent_id
  agent/ingest_agent_id
  skills/registry_version            (e.g., 1.2)
  skills/context_bootstrap_arn       (Lambda ARN for SK-01)
  skills/gap_detection_arn           (Lambda ARN for SK-05)
  skills/gate_validation_arn         (Lambda ARN for SK-06)
```

### 11.2 Schema Hot-Reload

The wiki schema (AGENTS.md) can be updated without redeploying containers:
- All agents and pipeline workers re-read the schema from S3 at the start of each execution
- Schema changes take effect on the next run (no restart required)
- A schema version number in the document enables auditing which schema was used for a given ingestion run (stored in the DynamoDB log)

---

## 12. Security Architecture

### 12.1 IAM — Least Privilege

Each ECS task and Lambda function has a dedicated IAM role with only the permissions it needs. **Deployed IAM roles (POC):**

| Component | IAM Role | Key Permissions |
|---|---|---|
| Source connector tasks | `llmwiki-connector-task` | S3:PutObject (raw/ prefix only), DynamoDB:PutItem (source-registry), Secrets Manager:GetSecretValue |
| Processing pipeline (Step Functions + Lambda) | `llmwiki-pipeline-lambda` | S3:GetObject (raw/), S3:PutObject (wiki/), DynamoDB:PutItem/UpdateItem (index, log), Bedrock:InvokeModel |
| Streamlit ECS task | `llmwiki-streamlit-task` | lambda:InvokeFunction (skill-*, uc1-*, gatekeeper, uc1-harness), DynamoDB:GetItem/Query/Scan (harness + index tables), S3:GetObject (wiki/reports/*) |
| All skill Lambdas + harness Lambdas | `llmwiki-skills-lambda-role` | lambda:InvokeFunction (llmwiki-skill-* + downstream), DynamoDB full access (wiki_log, gaps, wiki_index, harness_runs, workspace_files), S3:PutObject/GetObject (wiki/reports/*), Bedrock:InvokeModel *, SNS:Publish *, CloudWatch:Logs |
| Search Wiki / Gap Analysis agents | `llmwiki-agent-role` | S3:GetObject (wiki/, output/), DynamoDB:GetItem/Query (index, log), Bedrock:RetrieveAndGenerate |

S3 bucket policies enforce that the `raw/` prefix has no `PutObject` permission for processing tasks (only connector tasks write there). The `wiki/reports/` prefix is accessible only to skill/harness Lambdas and Streamlit — not to agents or connector tasks.

**Principle of least privilege gaps to address for production:**
- Bedrock:InvokeModel `*` → scope to specific model ARNs
- SNS:Publish `*` → scope to specific topic ARNs
- `llmwiki-skills-lambda-role` is shared across all 5 skill Lambdas + 2 harness Lambdas — split into per-function roles in production

### 12.2 Encryption

- **At rest:** S3 SSE-S3 (POC default). Upgrade to SSE-KMS with wiki-specific KMS key for production. DynamoDB SSE enabled (`server_side_encryption { enabled = true }`) on all tables including harness_runs and workspace_files. Neptune and OpenSearch encryption at rest.
- **In transit:** TLS 1.2+ on all service endpoints. VPC endpoints for DynamoDB and S3 eliminate internet transit for Lambda/ECS → AWS service calls.
- **Secrets:** No credentials in environment variables or code. API keys and third-party credentials in Secrets Manager. SSM Parameter Store used for non-secret ARN discovery only (`/llmwiki/harness/*`).

### 12.3 Data Residency

All AWS services in `us-east-1`. S3 bucket Block Public Access enabled. No public S3 URLs — all access via presigned URLs (1-hour TTL) or IAM-authenticated API calls. Harness workspace files (DynamoDB) and reports (S3) have 30-day TTL to avoid indefinite storage of potentially sensitive engagement data.

### 12.4 API Authentication

- **Human users → API Gateway:** Cognito User Pool authorizer (JWT). POC dev only: IP allowlist.
- **Agent-to-agent calls → AgentCore:** IAM-based SigV4 signing. AgentCore S2S role (`llmwiki-agentcore-s2s-role`) grants `execute-api:Invoke` on Business API resource policy.
- **External systems → API Gateway:** API Gateway usage plans with API keys (rate-limited).
- **Streamlit → Lambda:** IAM role attached to ECS task — no credentials in application code.

### 12.5 AI Governance

- **Model approval:** Only `us.anthropic.claude-sonnet-4-6-v1:0` used across all Lambdas and harness phases. Model ID is env-configurable but defaulted in Terraform.
- **Agent contributions tagged:** All SK-03 wiki contributions include `contributing_agent` frontmatter with `agent_id` (e.g. `uc1-harness`). High-risk page types (`decisions/`, `evidence/`) default to `human_review_required: true`.
- **Audit trail:** CloudTrail enabled. DynamoDB `llmwiki-log` records every contribution with `agent_id`, `timestamp`, `page_slug`. `llmwiki-harness-runs` records every harness execution with full `phase_results` JSONB — permanent audit log of what each phase produced.
- **Hallucination guardrail:** `confidence` field in every SK-02 response. Low confidence triggers Phase 6 gap detection rather than silently proceeding. Agents are instructed: "If the wiki does not have an answer, report it as a knowledge gap — do not infer."
- **Human-in-the-loop gate:** Phase 3 of the hard harness is a mandatory human input gate. The system cannot proceed to risk analysis (Phase 5) without a human response — this is enforced by the state machine, not by prompting.

### 12.6 Compliance Considerations (POC → Production)

| Control | POC Status | Production Requirement |
|---|---|---|
| PHI/PII in wiki pages | ❌ Prohibited in POC — test data only | Bedrock Guardrails to detect and block PHI in contributions |
| HIPAA BAA with AWS | ✅ Standard for AWS customers | Confirm BAA covers Bedrock, DynamoDB, S3 in scope |
| Data classification tagging | ⬜ Not implemented | Tag S3 objects and DynamoDB items with data classification |
| Engagement data retention | 30-day DynamoDB/workspace TTL | Review with legal — may need longer for SOW-related data |
| Model output logging | ⬜ CloudWatch only | Bedrock model invocation logging to S3 for audit |
| Vulnerability scanning | ECR scan-on-push enabled | Add Snyk/Inspector2 in CI/CD pipeline |

---

## 13. Observability

### 13.1 Amazon CloudWatch

- **Structured logging:** All Lambda functions and ECS tasks emit to CloudWatch Logs. **Deployed log groups (POC):** `/aws/lambda/llmwiki-skill-*` (14-day retention), `/aws/lambda/llmwiki-gatekeeper` (14-day), `/aws/lambda/llmwiki-uc1-harness` (14-day), `/ecs/llmwiki-streamlit` (7-day).
- **Custom metrics:** Each pipeline stage emits metrics:
  - `WikiPagesCreated` / `WikiPagesUpdated` per run
  - `SourcesIngested` per connector per run
  - `BedrockTokensConsumed` (cost tracking)
  - `SearchLatencyP99` (Search Wiki Agent)
  - `SkillInvocationCount` by skill ID — `skill_id` dimension
  - `SkillLatencyP99` by skill ID — from `latency_ms` in skill response
  - `HarnessPhaseLatency` by phase number — from `phase_results` stored in DynamoDB
  - `HarnessGapsDetected` per run — from `phase6.gap_count`
  - `HarnessCompletionRate` (completed vs error vs paused)
- **Dashboards:** CloudWatch dashboard: wiki health (total pages, sources, last ingest, search latency, gap count, error rate), skill breakdown (invocations/latency by SK-01…SK-09), harness telemetry (phases completed, gaps per run, latency distribution).
- **Alarms:** Ingestion failure (SNS → email), search latency P99 > 10s, Bedrock throttling, harness Lambda error rate > 5%.

### 13.2 AWS X-Ray

Distributed tracing across the full ingest pipeline and harness execution. Each skill invocation is traceable end-to-end: `UC1HarnessLambda → SK-02:WikiQuerySkill → BedrockKB → Claude → response`. X-Ray segments annotated with `skill_id`, `phase_num`, `engagement_id` for cross-phase correlation.

### 13.3 Wiki Health Report

The Gap Analysis Agent generates a weekly `output/wiki-health-report.md` containing:
- Total pages by type
- Sources ingested this week vs. all-time
- Orphan page count
- Open research questions count
- Top knowledge gaps
- Bedrock cost breakdown
- Search query volume and top queries
- Skill invocation breakdown: which skills were called, by which agents, success/failure rates

---

## 14. Deployment Architecture

### 14.1 Infrastructure as Code

All infrastructure defined in **Terraform** (HCL):
- One Terraform root module, decomposed into child modules:
  - `modules/wiki-storage` — S3, DynamoDB, KMS keys
  - `modules/wiki-search` — OpenSearch, Neptune, Bedrock Knowledge Base
  - `modules/wiki-pipeline` — Step Functions, Lambda, EventBridge rules
  - `modules/wiki-containers` — ECR, ECS Cluster, Task Definitions, Services
  - `modules/wiki-agents` — AgentCore agent definitions, MCP tool registrations
  - `modules/wiki-skills` — Skill Registry Lambda functions, skill IAM roles (new)
  - `modules/wiki-api` — API Gateway, Cognito, ALB
  - `modules/wiki-network` — VPC, subnets, security groups, VPC endpoints
- Environment-specific `tfvars` files (`dev.tfvars`, `staging.tfvars`, `prod.tfvars`)
- Remote state in S3 + DynamoDB state lock table
- Terraform workspace or separate state files per environment

### 14.2 Deployment Pipeline

GitHub Actions → Terraform:

```
[Source: GitHub PR / merge to main]
         ↓
[CI: GitHub Actions]
  - terraform fmt --check
  - terraform validate
  - tflint (lint HCL)
  - docker build + push to ECR (all containers)
  - Unit tests (Lambda functions + skill Lambdas)
         ↓
[Plan: terraform plan -var-file=dev.tfvars]
  - Plan output posted as PR comment
         ↓
[Deploy: Dev environment]
  - terraform apply -var-file=dev.tfvars -auto-approve
  - Integration smoke test (ingest one test doc, run one search query, invoke SK-01)
         ↓
[Manual Approval Gate]
         ↓
[Deploy: Production environment]
  - terraform apply -var-file=prod.tfvars
  - Blue/green ECS deployment via aws_codedeploy_deployment_group resource
```

### 14.3 Environment Promotion

Three environments: `dev`, `staging`, `prod`. Each environment has:
- Its own S3 bucket (separate wiki data)
- Its own Parameter Store hierarchy (`/wiki/dev/`, `/wiki/prod/`)
- Shared ECR (same images, different configs)
- Separate AgentCore agents (dev agents do not share memory with prod)
- **Shared Skill Registry version** — skills are promoted from dev → prod as a versioned unit

### 14.4 Blue/Green Deployments for ECS Services

`wiki-agent-runtime` and `wiki-api` use ECS blue/green deployment via CodeDeploy:
- New task definition deployed to green target group
- Smoke tests run against green
- Traffic shifted 10% → 50% → 100% over configurable intervals
- Auto-rollback on alarm breach

---

## 15. Data Flow — End-to-End Scenarios

### 15.1 "Ingest a SharePoint folder" flow

```
1. EventBridge Scheduler fires (e.g., daily at 2 AM)
2. ECS task wiki-source-connector starts
3. Connector authenticates to SharePoint via Graph API (creds from Secrets Manager)
4. Fetches new/modified files since last run (delta query)
5. Writes files to s3://wiki-bucket/raw/articles/ (PDFs go to raw/assets/ + trigger conversion)
6. Updates wiki-source-registry in DynamoDB (status: raw)
7. S3 Event Notification fires for each new raw file
8. Step Functions wiki-conversion-pipeline starts
9. Textract converts PDFs → Markdown; Lambda converts HTML → Markdown
10. Converted .md files written to raw/articles/
11. Source registry updated (status: converted)
12. S3 event fires for each converted .md
13. Step Functions wiki-ingest-pipeline starts (one execution per source)
14. Bedrock Claude generates source summary → written to wiki/sources/
15. Bedrock Claude extracts entities → entity pages created/updated in wiki/entities/
16. Concept pages created/updated in wiki/concepts/
17. All pages indexed in OpenSearch, embeddings stored
18. Neptune updated with new entity nodes and relationships
19. DynamoDB index and log updated
20. Source registry updated (status: wiki-page-created)
21. Ingest Agent notified of completion → sends summary to CloudWatch + SNS
```

### 15.2 "UC1 agent answers a customer question" flow (via Skill)

```
1. UC1 Sales-to-Service Agent triggered by EventBridge (SOW upload event)
2. Agent calls SK-01 ContextBootstrapSkill(customer_id="scan-001", use_case="UC1")
   → skill calls wiki_get_customer + wiki_get_playbook in parallel
   → returns: {customer_context, uc1_playbook, prior_pages}
3. Agent calls SK-02 WikiQuerySkill(domain="customer-onboarding", question="...", customer_id="scan-001")
   → calls wiki_ask → KB retrieve → Claude synthesis
   → returns: {answer, confidence, action_items, artifacts_referenced, gaps_detected}
4. Agent calls SK-04 ArtifactResolutionSkill(artifact_type="persona-template", customer_id="scan-001")
   → calls wiki_get_artifact → Claude populates template with customer data
   → returns: {artifact_content, populated_fields, missing_fields}
5. Agent synthesizes handoff brief (Claude reasoning over prior skill outputs)
6. If gaps_detected: Agent calls SK-05 GapDetectionSkill → SNS escalation if blocking
7. Agent calls SK-03 WikiContributeSkill(page_type="customers", content="...", customer_id="scan-001")
   → validates → writes S3 → updates DynamoDB → triggers KB sync
   → returns: {status: "indexed", page_slug: "...", s3_uri: "..."}
8. Downstream agents (UC2+) call SK-01 ContextBootstrapSkill for same customer → get UC1 output
```

### 15.3 "Detect and plan for knowledge gaps" flow

```
1. Gap Analysis Agent triggered (weekly schedule or manual)
2. Neptune Gremlin query: find disconnected graph components
3. Neptune query: find nodes with degree < 2 (under-explored entities)
4. DynamoDB query: find page types with source_count < 3
5. S3 read: wiki/questions/*.md for open questions
6. Bedrock Claude: "Given these gaps, generate prioritized research todos"
7. Todo files written to s3://wiki-bucket/todos/
8. CloudWatch metric: GapCount (trend tracking)
9. Gap analysis report written to s3://wiki-bucket/output/gap-analysis-{date}.md
10. SNS notification sent with summary (if configured)
```

---

## 16. AWS Service Summary

| Category | AWS Service | Role in LLMWiki |
|---|---|---|
| **LLM** | Amazon Bedrock (Claude) | All wiki page generation, summarization, synthesis, skill reasoning |
| **Agent Runtime** | AWS AgentCore | UC agent fleet, Search Wiki Agent, Skill Registry sub-agents |
| **Object Storage** | Amazon S3 | Raw sources, wiki pages, outputs, todos, config |
| **Metadata Store** | Amazon DynamoDB | Wiki index, operation log, source registry, contributions audit |
| **Search** | Amazon OpenSearch Service | Full-text + vector semantic search over wiki pages |
| **Semantic Retrieval** | Amazon Bedrock Knowledge Bases | Native Bedrock agent retrieval over wiki pages |
| **Knowledge Graph** | Amazon Neptune | Entity relationship graph, gap analysis, orphan detection |
| **PDF Extraction** | Amazon Textract | PDF → structured Markdown conversion |
| **Audio/Video** | Amazon Transcribe | Audio/video → transcript Markdown |
| **SaaS Connectors** | Amazon AppFlow | Managed ingestion from Salesforce, Slack, etc. |
| **Enterprise Search** | Amazon Kendra | Native SharePoint connector; alternative search layer |
| **Pipeline Orchestration** | AWS Step Functions | Conversion pipeline, ingest pipeline state machines |
| **Event Routing** | Amazon EventBridge | S3 events → pipeline triggers; UC agent triggers; scheduled jobs |
| **Scheduling** | EventBridge Scheduler | Source connector cron, gap analysis cron |
| **Container Registry** | Amazon ECR | Docker image storage |
| **Container Runtime** | Amazon ECS Fargate | All container workloads (serverless, no EC2 management) |
| **API Layer** | Amazon API Gateway | REST API for external access to wiki + Business API for agents |
| **Auth (human)** | Amazon Cognito | User authentication for API Gateway |
| **Config (non-secret)** | AWS Systems Manager Parameter Store | Wiki configuration, model IDs, S3 paths, skill ARNs |
| **Config (secret)** | AWS Secrets Manager | External API keys, SharePoint credentials |
| **Encryption** | AWS KMS | Encryption keys for S3, DynamoDB, OpenSearch |
| **Networking** | Amazon VPC | Private network for all compute |
| **IaC** | Terraform | All infrastructure defined as code (HCL modules, remote S3 state) |
| **CI/CD** | GitHub Actions | Build, test, plan, and apply pipeline with PR plan comments |
| **Logging** | Amazon CloudWatch Logs | Structured logs from all components |
| **Metrics** | Amazon CloudWatch Metrics | Wiki health metrics, cost tracking, latency, skill telemetry |
| **Tracing** | AWS X-Ray | Distributed tracing across pipeline stages and skill invocations |
| **Notifications** | Amazon SNS | Ingestion completion, error alerts, gap escalation, HITL review |
| **Async Queuing** | Amazon SQS | Dead-letter queues for failed ingestions |

---

## 17. Phase-to-AWS-Service Mapping

| LLMWiki Phase | AWS Implementation | Skills / Harness |
|---|---|---|
| **DISCOVER / SCOPE / STRUCTURE / SCHEMA** | One-time setup via Terraform + AGENTS.md → S3 config/ + SSM Parameter Store | — |
| **WORKFLOWS** | Step Functions state machine definitions + EventBridge rules | — |
| **SCAFFOLD** | `terraform apply`: S3 prefixes, DynamoDB tables, OpenSearch index mappings, DynamoDB harness tables | Skill Lambda deployments via `terraform/lambda_skills.tf` + `lambda_harness.tf` |
| **ACQUIRE** | Source Connector containers (ECS Fargate) + AppFlow + Textract + Transcribe | — |
| **PROCESS** | Ingest Pipeline Step Functions + Bedrock Claude + Indexer Lambda | — |
| **QUERY** | Search Wiki Agent (AgentCore) + Bedrock KB | **SK-01** ContextBootstrap, **SK-02** WikiQuery |
| **CONTRIBUTE** | Wiki Contribute Lambda + DynamoDB log | **SK-03** WikiContribute (human_review_required gate) |
| **ARTIFACT RESOLUTION** | Artifact store S3 + DynamoDB | **SK-04** ArtifactResolution |
| **LINT / GAP ANALYSIS** | Gap Analysis Agent + Neptune + Bedrock Claude + S3 todos/ | **SK-05** GapDetection (batch sub-agents in harness) |
| **UC1 HARNESS** | `llmwiki-gatekeeper` + `llmwiki-uc1-harness` + DynamoDB `harness_runs` + `workspace_files` | All 5 POC skills orchestrated across 8 phases |
| **PLAN** | Gap Analysis Agent + Neptune queries + S3 todos/ | SK-05 GapDetectionSkill |

---

## 18. Key Design Decisions and Trade-offs

### 18.1 OpenSearch vs. Kendra for Search

**OpenSearch:** More flexible, cheaper at scale, supports hybrid search, supports vector similarity. Requires more operational setup. Best for wikis queried programmatically by agents.

**Kendra:** Enterprise-grade, native SharePoint/S3 connectors, better out-of-box relevance for document Q&A. More expensive (fixed pricing). Best when human users search the wiki via a UI. Kendra can replace the OpenSearch layer entirely for wikis with heavy SharePoint sourcing.

**Recommendation:** Use OpenSearch as the primary agent-facing search layer (lower latency, more flexible, vector-native). Add Kendra as an optional overlay for human-facing enterprise search needs.

### 18.2 Neptune vs. Bedrock for Gap Analysis

Neptune provides precise, queryable graph structure — disconnected components are mathematically identified. Bedrock Claude provides nuanced qualitative gap analysis ("conceptually, source X and concept Y are related but no wiki page connects them"). Use both: Neptune for structural gaps, Bedrock for semantic gaps.

### 18.3 Bedrock Knowledge Bases vs. Direct OpenSearch

Bedrock KB provides the cleanest integration path for agents using Bedrock Agents natively (one API call for retrieval + generation). Direct OpenSearch queries give more control over ranking, filtering, and hybrid scoring. The design uses both: KB for the Search Wiki Agent's primary retrieval (simplicity), OpenSearch for the indexer and any custom search operations (flexibility).

### 18.4 Step Functions vs. EventBridge Pipes for Pipeline

Step Functions Express Workflows provide visibility (each execution has a traceable history), retry logic, error handling, and parallel map states for batch processing. EventBridge Pipes are simpler but lack the branching and error handling needed for a multi-stage conversion + ingest pipeline. Step Functions is the correct choice for pipeline orchestration at this complexity level.

### 18.5 ECS Fargate vs. Lambda for Processing

The LLM processing tasks (calling Bedrock Claude multiple times per document, writing multiple S3 objects, updating DynamoDB and OpenSearch) can run for 3-10 minutes per document at scale. Lambda's 15-minute max is sufficient for most cases, but ECS Fargate task duration is unlimited, making it more appropriate for large documents or batch operations. Use Lambda for lightweight event routing and index updates; use ECS Fargate tasks for the heavy LLM processing.

### 18.6 Skills as Lambdas vs. AgentCore Sub-Agents

Deterministic skills (context bootstrap, contribution, gate validation) are implemented as Lambdas — they have predictable inputs and outputs with no multi-step reasoning. Non-deterministic skills (artifact resolution, test orchestration, compliance evidence) require LLM reasoning over multiple data sources and are better as AgentCore sub-agents where the model controls the execution flow. See Section 20 for the full decision matrix.

---

## 19. Extensibility Points

The design is intentionally open at these points for future extension:

1. **New source connectors:** Add a new ECS task definition + Parameter Store config. No changes to the processing pipeline (connector outputs are format-agnostic Markdown in `raw/`).

2. **New wiki page types:** Add a new entry to AGENTS.md (the S3 config object) and a new DynamoDB page_type value. Processing pipeline reads page types from config — no code change.

3. **New LLM models:** Change the Parameter Store model ID. All Bedrock calls are model-agnostic at the code level.

4. **Additional agents in the AgentCore fleet:** Any new agent can register `wiki_search` as an MCP tool and call the Search Wiki Agent as a sub-agent. The wiki becomes a shared knowledge substrate for the entire agent fleet.

5. **Human review workflow:** Insert an SNS notification + SQS queue + human-approval Lambda between the processing pipeline and the wiki write step. Pages requiring human review are held in a staging S3 prefix until approved.

6. **Multi-wiki support:** The entire system is parameterized by wiki name / environment path. Multiple independent wikis can run in the same AWS account (different S3 prefixes, DynamoDB tables, OpenSearch indexes, AgentCore agents) by varying the Terraform `tfvars` configuration — no module changes required.

7. **New skills:** Add a new skill Lambda or AgentCore sub-agent, register it in the Skill Registry (Parameter Store + DynamoDB skills table), update the skill-to-UC matrix. Existing agents adopt it by updating their system prompts — no infrastructure rebuild.

---

## 20. Reusable Skill Architecture

### 20.1 What Is a Skill?

A **skill** is a composable, versioned unit of agent behavior that sits between the atomic MCP tools (raw API calls) and the full UC agents (complete use-case workflows). Skills:

- Have a **single well-defined business capability** ("load customer context", "detect knowledge gaps")
- **Compose one or more MCP tools** with their own reasoning logic
- **Have a standard invocation contract** — every skill accepts `{skill, version, inputs}` and returns `{skill, status, outputs, latency_ms, wiki_pages_used}`
- Are **registered and versioned independently** — a skill update benefits every agent that uses it without requiring agent redeployment
- Are **cherry-picked** by each UC agent from the Skill Registry — an agent declares which skills it needs in its system prompt

**The three layers:**

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: UC Agents (use-case orchestrators)                    │
│  UC1 through UC10 — each cherry-picks skills from registry     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ call
┌──────────────────────────────▼──────────────────────────────────┐
│  LAYER 2: Skill Registry (SK-01 to SK-09)                       │
│  Composable behaviors — implement patterns shared across UCs   │
│  Tier 1: Universal (all 10 UCs)                                 │
│  Tier 2: Common (5+ UCs)                                        │
│  Tier 3: Domain-Specific (2–4 UCs)                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │ invoke
┌──────────────────────────────▼──────────────────────────────────┐
│  LAYER 1: MCP Tools (atomic API calls)                          │
│  wiki_ask · wiki_get_customer · wiki_get_playbook               │
│  wiki_get_artifact · wiki_contribute · wiki_get_gaps            │
└─────────────────────────────────────────────────────────────────┘
```

---

### 20.1a Skill Business Names

Each skill has a **technical name** (code and invocation contracts) and a **business-friendly name** (stakeholder communications, Streamlit UI, and slide decks):

| Skill ID | Business-Friendly Name | Technical Name | What It Does in Plain English |
|---|---|---|---|
| SK-01 | **Customer Briefing Loader** | ContextBootstrapSkill | Instantly loads everything the agent knows about a customer and their current project phase before it starts working |
| SK-02 | **Knowledge Finder** | WikiQuerySkill | Searches the company knowledge base and returns a cited, structured answer with concrete action items |
| SK-03 | **Knowledge Recorder** | WikiContributeSkill | Saves agent-generated insights, decisions, and customer pages back to the shared knowledge base for the next agent |
| SK-04 | **Template Auto-Fill** | ArtifactResolutionSkill | Finds the right template or checklist and pre-populates it with available customer data — no manual copying |
| SK-05 | **Missing Info Radar** | GapDetectionSkill | Detects when the knowledge base doesn't have enough information and alerts the team to fill the gap before proceeding |
| SK-06 | **Readiness Gate Checker** | DecisionGateValidationSkill | Verifies all required approvals and evidence are in place before the project advances to the next phase |
| SK-07 | **Test Scenario Builder** | TestOrchestrationSkill | Generates tailored test scenarios from proven patterns and maps each to available automation approaches |
| SK-08 | **Evidence Bundle Assembler** | ComplianceEvidenceSkill | Collects, validates, and packages compliance evidence for AI Handbook gate reviews — routes to human approval |
| SK-09 | **Setup Checklist Validator** | ProvisioningChecklistSkill | Validates infrastructure, security, and configuration checklists against current standards — flags every gap |

---

### 20.1b Full Skill Architecture Diagram

The following diagram shows all three layers of the skill architecture: the UC agent fleet, the tiered Skill Registry, and the MCP tool layer. Each UC agent cherry-picks the skills it needs at system-prompt declaration time — no code changes required.

```
╔══════════════════════════════════════════════════════════════════════╗
║           LLMWIKI REUSABLE SKILL ARCHITECTURE                       ║
║        "Build once · Register once · Cherry-pick everywhere"        ║
╚══════════════════════════════════════════════════════════════════════╝

  ┌──────────────────── UC AGENT FLEET ──────────────────────────────┐
  │                                                                   │
  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                  │
  │  │UC1 ★ │ │ UC2  │ │ UC3  │ │ UC4  │ │ UC5  │   ★ = POC        │
  │  │ S2S  │ │ ENV  │ │ IAM  │ │ CFG  │ │  DM  │                  │
  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘                  │
  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                  │
  │  │ UC6  │ │ UC7  │ │ UC8  │ │ UC9  │ │ UC10 │                  │
  │  │ SIT  │ │ E2E  │ │ CUT  │ │ PTO  │ │  HC  │                  │
  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘                  │
  │  Each agent declares which skills it needs in its system prompt. │
  └──────────────────────────┬───────────────────────────────────────┘
                             │ cherry-pick from Skill Registry
                             ▼
  ┌──────── SKILL REGISTRY  (DynamoDB: llmwiki-skill-registry) ──────┐
  │                                                                   │
  │  ┌───────────────────────────────────────────────────────────┐   │
  │  │ TIER 1 — UNIVERSAL  ·  ALL 10 UC agents use these         │   │
  │  │                                                            │   │
  │  │  SK-01  Customer Briefing Loader   (ContextBootstrapSkill) │   │
  │  │  SK-02  Knowledge Finder           (WikiQuerySkill)        │   │
  │  │  SK-03  Knowledge Recorder         (WikiContributeSkill)   │   │
  │  └───────────────────────────────────────────────────────────┘   │
  │                                                                   │
  │  ┌───────────────────────────────────────────────────────────┐   │
  │  │ TIER 2 — COMMON  ·  5–8 UC agents use these              │   │
  │  │                                                            │   │
  │  │  SK-04  Template Auto-Fill         (ArtifactResolution)    │   │
  │  │  SK-05  Missing Info Radar         (GapDetectionSkill)     │   │
  │  │  SK-06  Readiness Gate Checker     (DecisionGateValidation)│   │
  │  └───────────────────────────────────────────────────────────┘   │
  │                                                                   │
  │  ┌───────────────────────────────────────────────────────────┐   │
  │  │ TIER 3 — DOMAIN-SPECIFIC  ·  2–4 UC agents use these     │   │
  │  │                                                            │   │
  │  │  SK-07  Test Scenario Builder      (TestOrchestrationSkill)│   │
  │  │  SK-08  Evidence Bundle Assembler  (ComplianceEvidenceSkill│   │
  │  │  SK-09  Setup Checklist Validator  (ProvisioningCheckSkill)│   │
  │  └───────────────────────────────────────────────────────────┘   │
  └──────────────────────────┬───────────────────────────────────────┘
                             │ skills invoke atomic tools
                             ▼
  ┌──────────────────── MCP TOOL LAYER ──────────────────────────────┐
  │  wiki_ask  ·  wiki_get_customer  ·  wiki_get_playbook            │
  │  wiki_get_artifact  ·  wiki_contribute  ·  wiki_get_gaps         │
  └──────────────────────────────────────────────────────────────────┘
```

---

### 20.2 Skill Taxonomy — Full Catalogue

#### Tier 1 — Universal Skills (used by all 10 UC agents)

---

**SK-01 · ContextBootstrapSkill**

> Load everything the agent needs to know before acting: customer history from the wiki + the current playbook for this use case. Called at the START of every UC agent session.

| Property | Value |
|---|---|
| Implementation | Lambda function (`lambda/skills/context_bootstrap/`) |
| MCP tools composed | `wiki_get_customer` + `wiki_get_playbook` (parallel) |
| Inputs | `customer_id`, `use_case` (UC1–UC10), `agent_id` |
| Outputs | `customer_context`, `playbook_steps`, `prior_agent_contributions`, `pages_loaded`, `customer_status` (new/existing) |
| Latency | ~500ms (two parallel API calls) |
| Used by | UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10 |

```json
// Invocation example
{
  "skill": "ContextBootstrapSkill",
  "version": "1.0",
  "inputs": {
    "customer_id": "scan-health-plan-2026",
    "use_case": "UC1",
    "agent_id": "sales-to-service-agent-v1"
  }
}

// Output structure
{
  "skill": "ContextBootstrapSkill",
  "status": "success",
  "outputs": {
    "customer_status": "new",          // "new" | "existing"
    "customer_context": { ... },       // from wiki_get_customer
    "prior_contributions": [],         // prior agent-contributed pages
    "playbook": { "steps": [...] },    // from wiki_get_playbook
    "pages_loaded": 3
  },
  "latency_ms": 480
}
```

---

**SK-02 · WikiQuerySkill**

> Ask a domain-scoped, customer-aware business question to the wiki. The core intelligence call — returns structured answer, confidence, and action items. Called whenever the agent needs to know something.

| Property | Value |
|---|---|
| Implementation | MCP tool group (thin wrapper around `wiki_ask`) |
| MCP tools composed | `wiki_ask` |
| Inputs | `question`, `domain`, `customer_id`, `use_case`, `intent` (optional) |
| Outputs | `answer`, `confidence`, `action_items`, `artifacts_referenced`, `evidence_required`, `gaps_detected`, `sources` |
| Latency | ~1–3s (KB retrieve + Claude synthesis) |
| Used by | UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10 |

The SK-02 wrapper adds: automatic intent detection from question text, retry on low-confidence with broadened query, and structured logging of all questions/answers to the `wiki-log` DynamoDB table for analytics.

---

**SK-03 · WikiContributeSkill**

> Write agent-generated knowledge back to the wiki. Validates content, selects correct page type, applies human-review staging for high-risk types, writes to S3, and triggers Bedrock KB sync. Called at the END of every UC agent session (and mid-session for incremental contributions).

| Property | Value |
|---|---|
| Implementation | Lambda function (`lambda/skills/wiki_contribute/`) |
| MCP tools composed | `wiki_contribute` + DynamoDB audit write |
| Inputs | `page_type`, `page_slug`, `content` (Markdown), `customer_id`, `use_case`, `agent_id`, `human_review_required` |
| Outputs | `status` (indexed/pending), `page_slug`, `s3_uri`, `kb_sync_triggered`, `review_required` |
| Latency | ~300ms (S3 write + DynamoDB + Bedrock KB trigger) |
| Used by | UC1, UC2, UC3, UC4, UC5, UC6, UC7, UC8, UC9, UC10 |

The skill automatically sets `human_review_required: true` for `decisions/` and `evidence/` page types (routes to `wiki/pending/`). For `customers/`, `runbooks/`, `sops/`, and `artifacts/` it indexes immediately.

---

#### Tier 2 — Common Skills (used by 5 or more UC agents)

---

**SK-04 · ArtifactResolutionSkill**

> Retrieve a named artifact template from the wiki and populate it with available customer and project data. Returns a partially or fully populated document that the agent can review, complete, or contribute back.

| Property | Value |
|---|---|
| Implementation | AgentCore sub-agent (`skill-artifact-resolution-v1`) |
| MCP tools composed | `wiki_get_artifact` + `wiki_ask` (domain-scoped for context) + Bedrock Claude (populate) |
| Inputs | `artifact_type`, `customer_id`, `available_context` (dict), `use_case` |
| Outputs | `artifact_content` (populated Markdown), `populated_fields` (list), `missing_fields` (list), `s3_key` |
| Latency | ~2–4s (S3 read + Claude population) |
| Used by | UC1 (persona-template), UC2 (bom-template, arb-checklist), UC3 (rbac-matrix), UC5 (data-mapping-template), UC6 (sit-test-scenarios), UC7 (e2e-scenarios), UC8 (cutover-runbook), UC9 (pto-checklist) |

The sub-agent uses Claude to map available customer context to template fields. It identifies which fields it can populate from `available_context` and which require human input, then returns `missing_fields` so the UC agent can request them from a human or flag as a gap.

---

**SK-05 · GapDetectionSkill**

> When the wiki cannot answer a question with sufficient confidence, identify, classify, and record the knowledge gap. If the gap is blocking (confidence = "low" and action is required), escalate to human via SNS. Records gaps in the `llmwiki-gaps` DynamoDB table for the Streamlit UI gap dashboard.

| Property | Value |
|---|---|
| Implementation | Lambda function (`lambda/skills/gap_detection/`) |
| MCP tools composed | `wiki_get_gaps` + Bedrock Claude (classify) + SNS (escalate) |
| Inputs | `question`, `domain`, `use_case`, `customer_id`, `low_confidence_response` (from SK-02) |
| Outputs | `gaps` (list of `{gap_type, slug, title, blocking, escalated, human_prompt}`) |
| Latency | ~800ms (Claude classify + DynamoDB write + optional SNS) |
| Used by | UC1, UC2, UC5, UC8, UC9, UC10 |

Gap types: `missing-customer-history`, `missing-artifact`, `missing-standard`, `missing-evidence`, `unknown-configuration`. Blocking gaps (where the agent cannot proceed without the information) trigger SNS → Streamlit notification.

---

**SK-06 · DecisionGateValidationSkill**

> Verify that current evidence in the wiki satisfies the AI Handbook decision gate required for the current project phase (G0–G6). Returns gate status, a list of satisfied and missing evidence items, and whether the gate is blocking. Prevents agents from contributing evidence pages that assert gate passage without the required artifacts.

| Property | Value |
|---|---|
| Implementation | Lambda function (`lambda/skills/gate_validation/`) |
| MCP tools composed | `wiki_ask` (domain: governance) + DynamoDB read (evidence table) |
| Inputs | `decision_gate` (G0–G6), `customer_id`, `use_case`, `agent_id` |
| Outputs | `gate`, `satisfied` (bool), `satisfied_evidence` (list), `missing_evidence` (list), `blocking` (bool) |
| Latency | ~600ms (wiki query + evidence table scan) |
| Used by | UC1 (G0), UC2 (G1, G2), UC3 (G2), UC8 (G5), UC9 (G5), UC10 (G6) |

The gate validation is called before any `wiki_contribute` call that writes `decisions/` or `evidence/` page types. If `blocking: true`, the contribute is rejected and the agent must escalate to a human before proceeding.

---

#### Tier 3 — Domain-Specific Skills (used by 2–4 UC agents)

---

**SK-07 · TestOrchestrationSkill**

> Generate test scenarios from wiki-sourced test patterns, map each scenario to available automation approaches, collect sign-off evidence, and structure results for wiki contribution. Shared between SIT (UC6) and E2E Testing (UC7) agents.

| Property | Value |
|---|---|
| Implementation | AgentCore sub-agent (`skill-test-orchestration-v1`) |
| MCP tools composed | `wiki_ask` (domain: testing), `wiki_get_artifact` (test templates), `wiki_contribute` (results) |
| Inputs | `test_type` (sit/e2e), `feature_area`, `customer_id`, `product`, `use_case` |
| Outputs | `test_scenarios` (list), `automation_mapping`, `sign_off_criteria`, `evidence_s3_keys` |
| Latency | ~3–6s (multi-step reasoning over test patterns) |
| Used by | UC6 (SIT testing), UC7 (E2E testing) |

---

**SK-08 · ComplianceEvidenceSkill**

> Assemble a compliance evidence bundle for AI Handbook gates. Queries the wiki for required evidence patterns, scans existing evidence pages for the current customer, identifies gaps, and structures the bundle for human review via the HITL workflow. All outputs routed to `wiki/pending/` for approval.

| Property | Value |
|---|---|
| Implementation | AgentCore sub-agent (`skill-compliance-evidence-v1`) |
| MCP tools composed | `wiki_ask` (domain: governance), `wiki_get_artifact` (evidence templates), `wiki_contribute` (HITL-flagged) |
| Inputs | `decision_gate` (G4–G6), `customer_id`, `product`, `evidence_type` |
| Outputs | `evidence_bundle` (list of page slugs), `missing_items`, `review_url`, `gate_readiness_pct` |
| Latency | ~4–8s (multi-step evidence assembly) |
| Used by | UC8 (Cutover gate G5), UC9 (Handover gate G5), UC10 (Hypercare exit gate G6) |

---

**SK-09 · ProvisioningChecklistSkill**

> Validate a technical provisioning checklist (BOM, ARB security checklist, IAM policy review, business configuration validation) against current standards in the wiki. Returns checklist completion status, validation failures, and remediation steps. Used across environment, identity, and configuration use cases.

| Property | Value |
|---|---|
| Implementation | Lambda function (`lambda/skills/provisioning_checklist/`) |
| MCP tools composed | `wiki_ask` (domain-specific: provisioning / identity-access / configuration), `wiki_get_artifact` (checklist templates) |
| Inputs | `checklist_type` (bom/arb/iam/config), `customer_id`, `submitted_values` (dict of checklist responses) |
| Outputs | `checklist_status` (pass/fail/partial), `passed_items` (list), `failed_items` (list), `remediation_steps` (list) |
| Latency | ~1–2s (wiki lookup + deterministic validation) |
| Used by | UC2 (BOM + ARB), UC3 (IAM policy), UC4 (business config validation) |

---

### 20.3 Skill-to-Use-Case Matrix

The following matrix shows which skills are used by each of the 10 UC agents. `✅` = used in this use case, `–` = not applicable.

```
                        UC1  UC2  UC3  UC4  UC5  UC6  UC7  UC8  UC9 UC10
                        S2S  ENV  IAM  CFG  DM   SIT  E2E  CUT  PTO  HC
──────────────────────────────────────────────────────────────────────────
SK-01 ContextBootstrap   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
SK-02 WikiQuery          ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
SK-03 WikiContribute     ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
──────────────────────────────────────────────────────────────────────────
SK-04 ArtifactResolution ✅   ✅   ✅   –    ✅   ✅   ✅   ✅   ✅   –
SK-05 GapDetection       ✅   ✅   –    –    ✅   –    –    ✅   ✅   ✅
SK-06 GateValidation     ✅   ✅   ✅   –    –    –    –    ✅   ✅   ✅
──────────────────────────────────────────────────────────────────────────
SK-07 TestOrchestration  –    –    –    –    –    ✅   ✅   –    –    –
SK-08 ComplianceEvidence –    –    –    –    –    –    –    ✅   ✅   ✅
SK-09 ProvisioningCheck  –    ✅   ✅   ✅   –    –    –    –    –    –
──────────────────────────────────────────────────────────────────────────
Total skills per agent:   5    6    5    4    4    5    5    7    7    6
POC skills (UC1 subset):  ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
                         (all 5 POC skills are reused in every future UC)
```

**Key insight:** The 3 Tier-1 skills (SK-01, SK-02, SK-03) are used by all 10 agents with zero modification. The 3 Tier-2 skills built for UC1 POC (SK-04, SK-05, SK-06) cover 8 of 10 future agents. Building 6 skills in the POC yields near-complete coverage across the entire fleet.

---

### 20.4 Skill Registry — Implementation

Skills are registered in a DynamoDB table (`llmwiki-skill-registry`) and their ARNs stored in Parameter Store:

**`llmwiki-skill-registry` DynamoDB table:**

| Attribute | Type | Description |
|---|---|---|
| `skill_id` (PK) | String | e.g., `SK-01` |
| `version` (SK) | String | e.g., `1.0` |
| `name` | String | `ContextBootstrapSkill` |
| `tier` | Number | 1, 2, or 3 |
| `implementation_type` | String | `lambda` or `agentcore-sub-agent` |
| `lambda_arn` | String | ARN if Lambda |
| `agent_id` | String | AgentCore agent ID if sub-agent |
| `input_schema` | Map | JSON Schema for inputs |
| `output_schema` | Map | JSON Schema for outputs |
| `used_by_ucs` | List | [UC1, UC2, ...] |
| `status` | String | `active` / `deprecated` |
| `deployed_date` | String | ISO 8601 |

**UC Agent System Prompt declares skills:**

```
You are the UC2 Environment Provisioning Agent. You have the following skills available:
- SK-01 ContextBootstrapSkill — call first, always
- SK-02 WikiQuerySkill — for all provisioning domain questions
- SK-03 WikiContributeSkill — for all wiki write-backs
- SK-04 ArtifactResolutionSkill — for BOM and ARB checklist population
- SK-05 GapDetectionSkill — when wiki confidence is low
- SK-06 DecisionGateValidationSkill — before writing decisions/ pages
- SK-09 ProvisioningChecklistSkill — for BOM/ARB validation

Do not implement checklist logic yourself. Call the appropriate skill.
```

This means adding a new skill to an existing agent requires only a system prompt update — no infrastructure change.

---

### 20.5 Skill Versioning and Lifecycle

Skills are versioned independently of the agents that use them. When a skill is updated (e.g., SK-05 GapDetectionSkill adds a new gap type), all agents using it get the improved behavior at their next invocation with no redeployment:

```
Skill version lifecycle:
v1.0 → ACTIVE (deployed with UC1 POC)
v1.1 → ACTIVE (minor fix — available to all agents immediately)
v2.0 → ACTIVE (breaking change — agents opt-in via system prompt version pin)
v1.0 → DEPRECATED (after 30-day migration window)
```

Agents pin to a skill version in their system prompt:
```
- SK-05 GapDetectionSkill v1.x — use latest patch version
```

This allows breaking skill changes without coordinating agent redeployment, while still protecting agents that need a stable interface.

---

### 20.6 Standard Skill Invocation Contract

All skills use this exact contract, regardless of implementation type:

**Request:**
```json
{
  "skill": "GapDetectionSkill",
  "skill_id": "SK-05",
  "version": "1.0",
  "invoked_by": "sales-to-service-agent-v1",
  "inputs": {
    "question": "What is the SCAN Health Plan SLA for claims turnaround?",
    "domain": "customer-onboarding",
    "use_case": "UC1",
    "customer_id": "scan-health-plan-2026",
    "low_confidence_response": { "confidence": "low", "gaps_detected": [] }
  }
}
```

**Response:**
```json
{
  "skill": "GapDetectionSkill",
  "skill_id": "SK-05",
  "version": "1.0",
  "status": "success",
  "outputs": {
    "gaps": [
      {
        "gap_type": "missing-customer-history",
        "slug": "scan-health-plan-sla-claims",
        "title": "SCAN Health Plan — Claims Turnaround SLA",
        "blocking": false,
        "escalated": false,
        "human_prompt": "Please provide the contracted SLA for claims turnaround from the SOW Section 4.2."
      }
    ]
  },
  "latency_ms": 720,
  "wiki_pages_used": [],
  "logged_to_gaps_table": true
}
```

---

### 20.7 Skill Wiki Pages — Living Documentation

Each skill has a corresponding **wiki page** stored in `wiki/skills/` — a Markdown file that documents the skill's contract, usage, outputs, and telemetry. These pages are:

- Indexed by Bedrock KB so agents can query "how do I use SK-04?" via SK-02
- Displayed in the Streamlit UI under a "Skills" tab
- The authoritative reference for all teams building new UC agents

| Skill | Wiki Page | Location |
|---|---|---|
| SK-01 Customer Briefing Loader | `sk-01-customer-briefing-loader.md` | `wiki_seed/skills/` → `wiki/skills/` |
| SK-02 Knowledge Finder | `sk-02-knowledge-finder.md` | `wiki_seed/skills/` → `wiki/skills/` |
| SK-03 Knowledge Recorder | `sk-03-knowledge-recorder.md` | `wiki_seed/skills/` → `wiki/skills/` |
| SK-04 Template Auto-Fill | `sk-04-template-auto-fill.md` | `wiki_seed/skills/` → `wiki/skills/` |
| SK-05 Missing Info Radar | `sk-05-missing-info-radar.md` | `wiki_seed/skills/` → `wiki/skills/` |

Upload skill pages to S3 after deploy:
```bash
aws s3 cp wiki_seed/skills/ s3://<wiki-bucket>/wiki/skills/ --recursive --profile tzg-sandbox
```

The skill pages use the same frontmatter schema as all other wiki pages, with additional fields: `skill_id`, `business_name`, `tier`, `lambda_function`.

---

### 20.7a Skill Implementation — Code Structure

Each skill is a standalone Lambda function in `lambda/skills/`:

```
lambda/skills/
├── context_bootstrap/       # SK-01 Customer Briefing Loader
│   ├── handler.py
│   └── requirements.txt
├── wiki_query/              # SK-02 Knowledge Finder
│   ├── handler.py
│   └── requirements.txt
├── wiki_contribute/         # SK-03 Knowledge Recorder
│   ├── handler.py
│   └── requirements.txt
├── artifact_resolution/     # SK-04 Template Auto-Fill
│   ├── handler.py
│   └── requirements.txt
├── gap_detection/           # SK-05 Missing Info Radar
│   ├── handler.py
│   └── requirements.txt
└── uc1_orchestrator/        # UC1 demo: all 5 skills in sequence
    ├── handler.py
    └── requirements.txt

wiki_seed/skills/            # Wiki documentation pages for each skill
├── sk-01-customer-briefing-loader.md
├── sk-02-knowledge-finder.md
├── sk-03-knowledge-recorder.md
├── sk-04-template-auto-fill.md
└── sk-05-missing-info-radar.md

terraform/
├── lambda_skills.tf         # 5 skill Lambdas + UC1 orchestrator + SSM ARN params
└── iam_skills.tf            # Shared IAM role for all skills

scripts/
└── test_skills_e2e.sh       # 9-test E2E validation of all 5 skills + UC1 flow
```

Terraform deploys all skill Lambdas and writes their ARNs to SSM Parameter Store under `/llmwiki/skills/sk*_arn` — so AgentCore can discover them at runtime without hardcoded ARNs.

---

### 20.8 Skill Deployment — Terraform Module

Skills are deployed via a dedicated Terraform module `modules/wiki-skills`:

```hcl
# modules/wiki-skills/main.tf

# Tier 1 — Lambda skills (deterministic)
resource "aws_lambda_function" "sk01_context_bootstrap" {
  function_name = "llmwiki-skill-context-bootstrap"
  handler       = "handler.lambda_handler"
  ...
}

resource "aws_lambda_function" "sk03_wiki_contribute" {
  function_name = "llmwiki-skill-wiki-contribute"
  ...
}

resource "aws_lambda_function" "sk05_gap_detection" {
  function_name = "llmwiki-skill-gap-detection"
  ...
}

resource "aws_lambda_function" "sk06_gate_validation" {
  function_name = "llmwiki-skill-gate-validation"
  ...
}

resource "aws_lambda_function" "sk09_provisioning_checklist" {
  function_name = "llmwiki-skill-provisioning-checklist"
  ...
}

# Tier 2–3 — AgentCore sub-agents (reasoning-heavy skills)
# SK-04, SK-07, SK-08 are registered as AgentCore agents via Console/CLI
# Their agent IDs are stored in Parameter Store:
resource "aws_ssm_parameter" "sk04_agent_id" {
  name  = "/llmwiki/skills/sk04_artifact_resolution_agent_id"
  type  = "String"
  value = var.sk04_agent_id   # set after AgentCore agent creation
}

# Skill Registry DynamoDB table
resource "aws_dynamodb_table" "skill_registry" {
  name         = "llmwiki-skill-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "skill_id"
  range_key    = "version"
  ...
}
```

---

### 20.8 POC Skill Scope vs. Full Fleet

The UC1 POC deploys and validates exactly 5 skills. These 5 skills are reused without modification by UC2–UC10:

| Phase | Skills Added | Cumulative Total | UCs Unlocked |
|---|---|---|---|
| **POC (UC1)** | SK-01, SK-02, SK-03, SK-04, SK-05 | 5 | UC1 |
| **Phase 3a (UC2–UC3)** | SK-06, SK-09 | 7 | UC2, UC3 |
| **Phase 3b (UC4–UC7)** | SK-07 | 8 | UC4, UC5, UC6, UC7 |
| **Phase 3c (UC8–UC10)** | SK-08 | 9 | UC8, UC9, UC10 |

Building 5 skills in the POC unlocks the infrastructure for all 10 use cases. The remaining 4 skills (SK-06, SK-07, SK-08, SK-09) are incremental additions that extend the registry without touching existing skill code.

---

### 20.9 UC Agent ↔ Skill Wiring Diagram

The following diagram shows the explicit wiring between each UC agent and the skills it uses:

```
UC AGENT                     SKILLS WIRED IN
─────────────────────────────────────────────────────────────────────

UC1 Sales-to-Service    ──── SK-01 Customer Briefing Loader
 (★ POC Target)         ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill        [persona]
                        └─── SK-05 Missing Info Radar

UC2 Environment         ──── SK-01 Customer Briefing Loader
 Provisioning           ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill       [BOM, ARB]
                        ├─── SK-05 Missing Info Radar
                        ├─── SK-06 Readiness Gate Checker    [G1, G2]
                        └─── SK-09 Setup Checklist Validator [BOM/ARB]

UC3 Identity &          ──── SK-01 Customer Briefing Loader
 Access Management      ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill       [RBAC]
                        ├─── SK-06 Readiness Gate Checker    [G2]
                        └─── SK-09 Setup Checklist Validator [IAM]

UC4 Business            ──── SK-01 Customer Briefing Loader
 Configuration          ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        └─── SK-09 Setup Checklist Validator [config]

UC5 Data Migration      ──── SK-01 Customer Briefing Loader
                        ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill  [data-mapping]
                        └─── SK-05 Missing Info Radar

UC6 SIT Testing         ──── SK-01 Customer Briefing Loader
                        ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill  [test-scenarios]
                        └─── SK-07 Test Scenario Builder    [SIT]

UC7 E2E Testing         ──── SK-01 Customer Briefing Loader
                        ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill   [e2e-scenarios]
                        └─── SK-07 Test Scenario Builder    [E2E]

UC8 Cutover             ──── SK-01 Customer Briefing Loader
                        ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill  [cutover-runbook]
                        ├─── SK-05 Missing Info Radar
                        ├─── SK-06 Readiness Gate Checker    [G5]
                        └─── SK-08 Evidence Bundle Assembler [G5]

UC9 Handover &          ──── SK-01 Customer Briefing Loader
 Post-Go-Live Support   ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-04 Template Auto-Fill      [PTO checklist]
                        ├─── SK-05 Missing Info Radar
                        ├─── SK-06 Readiness Gate Checker    [G5]
                        └─── SK-08 Evidence Bundle Assembler [G5]

UC10 Hypercare          ──── SK-01 Customer Briefing Loader
                        ├─── SK-02 Knowledge Finder
                        ├─── SK-03 Knowledge Recorder
                        ├─── SK-05 Missing Info Radar
                        ├─── SK-06 Readiness Gate Checker    [G6]
                        └─── SK-08 Evidence Bundle Assembler [G6 exit]
```

**Reading the diagram:** UC1 (the POC) wires SK-01 through SK-05. Every subsequent agent adds 1–2 domain-specific skills to that foundation. No existing skill is ever modified when a new UC agent is onboarded.

---

### 20.10 Why Skill Architecture Is Better

#### What The Alternatives Look Like

| Alternative | Description | The Problem |
|---|---|---|
| **Monolithic agents** | Each UC agent contains all its own logic — context loading, KB queries, artifact retrieval, gap detection — in its system prompt | When SK-02 improves (e.g., better retry logic), all 10 agents must be updated individually. 10× deployment risk per improvement. |
| **Per-agent Lambda duplicates** | Each UC agent has its own copy of the knowledge query logic in its Lambda | A bug in the domain-filter fallback must be patched in 10 places. Bug surfaces in UC6 four weeks after it was fixed in UC1. |
| **Direct MCP tool calls in agent logic** | Agent system prompt calls `wiki_ask` directly, re-implementing retry/logging/gap-detection inline | The agent has to re-implement error handling, intent detection, analytics logging, and fallback behavior on every direct call. Multi-step reasoning duplicated across agents. |
| **Sub-agent per use case** | Build a custom AgentCore sub-agent for every use case | 10 full agents to deploy, manage, update, and monitor — instead of 10 lightweight agents each calling 5–7 shared skills. |

#### Why the Skill Registry Approach Wins

**1. Write once, improve everywhere.** When the Customer Briefing Loader (SK-01) is updated to load additional context fields, all 10 UC agents get the improvement automatically at their next invocation — with zero redeployment. A single change propagates across the entire fleet in seconds.

**2. Test once, trust everywhere.** Each skill has its own unit tests and integration tests. When SK-05 (Missing Info Radar) passes its test suite, every agent that uses it inherits that confidence. A skill is not "working in UC1" and "untested in UC8" — it works or it doesn't, fleet-wide.

**3. Skills deploy before agents need them.** The POC builds SK-01 through SK-05. When the UC2 agent is built in Phase 3, SK-01, SK-02, SK-03, SK-04, SK-05 are already deployed, tested, and proven at production scale from UC1. UC2 wires them at system prompt time — no Lambda deployment required for the first five skills.

**4. Granular versioning without agent redeployment.** Agents pin to `SK-05 v1.x` (latest patch). A non-breaking improvement rolls out silently. A breaking change releases as `v2.0` and agents opt in on their own schedule. This is impossible with monolithic agents where logic and version are fused.

**5. Skill metrics surface cross-agent patterns.** Because all knowledge queries flow through SK-02 (Knowledge Finder), CloudWatch dashboards show question patterns, confidence distributions, and gap rates across all 10 use cases in a single view. With monolithic agents, each agent's telemetry is siloed.

**6. Smaller agent surface area reduces hallucination risk.** Each UC agent's system prompt is shorter and more focused: "You are UC2. Call these 7 skills. Do not implement checklist logic yourself." When the agent prompt is smaller, there are fewer opportunities for the LLM to reason off-track. The skills provide the structure; the agent provides the orchestration.

**7. New UC agents are mostly wiring declarations.** A new UC agent in Phase 3 is a system prompt that lists which 4–7 existing skills it needs, plus domain-specific instructions unique to that UC. The core capabilities are inherited from the registry. First UC8 engineering task is "which skills does UC8 need?" — not "build gap detection from scratch."

#### The Compounding Effect Visualized

```
POC (Week 7):   5 skills built  ──→  1 agent working
Phase 3a (Wk 18): +2 skills ──→  3 agents working  (UC2, UC3 added)
Phase 3b (Wk 22): +1 skill  ──→  7 agents working  (UC4–UC7 added)
Phase 3c (Wk 26): +1 skill  ──→ 10 agents working  (UC8–UC10 added)

Each increment: ~2–3 weeks of work → 3–4 new agents.
Without skill reuse: each new agent would be 4–6 weeks of logic
duplication — the fleet would take 60 weeks, not 19.
```

**The business case:** The skill architecture reduces the Phase 3 fleet build from ~60 weeks of duplicated engineering to ~19 weeks of incremental wiring. The POC investment in 5 skills yields a 10× acceleration on every subsequent use case.

---

## 21. Engagement Harness Architecture

### 21.1 The Long-Running Agent Problem

Anthropic's research on long-running agents (["Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), Nov 2025) identifies a fundamental challenge: agents work in discrete sessions, and each new session starts with **no memory of what came before**. Without a harness to bridge sessions, three failure modes emerge:

| Failure Mode | What Happens | Impact on LLMWiki |
|---|---|---|
| **One-shotting** | Agent tries to complete all deliverables at once, exhausts context mid-way, leaves work half-done | UC1 orchestrator produces an incomplete handoff brief — UC2 reads garbage |
| **Premature victory** | Agent sees some progress already done and declares the job complete | UC1 marks `status=complete` even though persona template was never populated |
| **Cold-start disorientation** | New session has no idea what was done, wastes tokens re-discovering state | Each skill invocation re-fetches customer context that was already loaded |

The Anthropic solution uses two components:
1. **Initializer Agent** — runs once, creates a structured environment (feature list, progress file, init script)
2. **Coding Agent** — every session reads progress + history, picks ONE incomplete item, does it, commits, marks complete

**LLMWiki is the ideal harness substrate.** The wiki is already a durable, queryable state store. The insight is to use it not just as a knowledge base for agent answers, but as the **harness environment itself** — storing deliverable registries, progress notes, and health state in structured wiki pages.

---

### 21.2 Harness Component Mapping

| Anthropic Harness Component | LLMWiki Equivalent | AWS Service |
|---|---|---|
| `feature_list.json` — all deliverables, `"passes": false` | `wiki/engagements/{id}/deliverable-registry.json` | S3 (wiki bucket) |
| `claude-progress.txt` — what each session did | `wiki/engagements/{id}/progress.json` | S3 (wiki bucket) |
| `init.sh` — verify app is healthy before starting | SK-01 enhanced with S3 existence checks on prior outputs | Lambda (SK-01) |
| Initializer Agent — runs once on project start | **UC0 Engagement Initializer Lambda** — fires on SOW signed | Lambda + EventBridge |
| Coding Agent reads progress + picks ONE item | Each UC orchestrator reads deliverable registry, picks first `"complete": false` | Step Functions |
| Agent marks feature `"passes": true` only after E2E test | SK-03 marks deliverable `"complete": true` only after SK-02 confirms with `confidence=high` | Lambda (SK-02 + SK-03) |
| Git commit + progress update at session end | SK-03 write + `progress.json` append | Lambda (SK-03) |
| Blocking gap → human input required | SK-05 blocking gap → Step Functions `.waitForTaskToken` | Step Functions + SNS |

---

### 21.3 UC0 Engagement Initializer

The **UC0 Engagement Initializer** is a new Lambda that fires once when a SOW is signed, before any UC agent runs. It is the LLMWiki equivalent of the Anthropic Initializer Agent.

**Trigger:** EventBridge rule matching `source="llmwiki"`, `detail-type="SOWIngested"`

**Output — deliverable-registry.json:**
```json
{
  "engagement_id": "bcbs-mn-001",
  "customer_name": "BlueCross BlueShield Minnesota",
  "product": "TriZetto QNXT",
  "sow_reference": "SOW-2026-BCBS-MN-001",
  "initialized_at": "2026-05-14T10:00:00Z",
  "deliverables": [
    {"id": "D-01", "uc": "UC1", "name": "Customer Handoff Brief",         "wiki_key": "wiki/customers/bcbs-mn-001-handoff-2026.md", "complete": false},
    {"id": "D-02", "uc": "UC1", "name": "Persona Template Populated",     "wiki_key": "wiki/artifacts/bcbs-mn-001-persona.md",      "complete": false},
    {"id": "D-03", "uc": "UC1", "name": "Knowledge Gaps Recorded",        "wiki_key": "llmwiki-gaps table",                         "complete": false},
    {"id": "D-04", "uc": "UC2", "name": "Environment Provisioned",        "wiki_key": "wiki/decisions/bcbs-mn-001-bom-approved.md", "complete": false},
    {"id": "D-05", "uc": "UC3", "name": "IAM Setup Documented",           "wiki_key": "wiki/decisions/bcbs-mn-001-iam-setup.md",    "complete": false},
    {"id": "D-06", "uc": "UC4", "name": "Business Config Documented",     "wiki_key": "wiki/runbooks/bcbs-mn-001-biz-config.md",    "complete": false},
    {"id": "D-07", "uc": "UC5", "name": "Data Migration Plan Written",    "wiki_key": "wiki/runbooks/bcbs-mn-001-data-migration.md","complete": false},
    {"id": "D-08", "uc": "UC6", "name": "SIT Results Recorded",           "wiki_key": "wiki/evidence/bcbs-mn-001-sit-results.md",   "complete": false},
    {"id": "D-09", "uc": "UC7", "name": "E2E Test Report Written",        "wiki_key": "wiki/evidence/bcbs-mn-001-e2e-results.md",   "complete": false},
    {"id": "D-10", "uc": "UC8", "name": "Cutover Runbook Generated",      "wiki_key": "wiki/runbooks/bcbs-mn-001-cutover.md",       "complete": false},
    {"id": "D-11", "uc": "UC9", "name": "PTO Handover Pack Written",      "wiki_key": "wiki/customers/bcbs-mn-001-handover.md",     "complete": false},
    {"id": "D-12", "uc": "UC10","name": "Hypercare Exit Report Written",   "wiki_key": "wiki/evidence/bcbs-mn-001-hypercare-exit.md","complete": false}
  ]
}
```

**Output — progress.json:**
```json
{
  "engagement_id": "bcbs-mn-001",
  "sessions": [
    {
      "session_id": "uc0-init-001",
      "uc": "UC0",
      "timestamp": "2026-05-14T10:00:00Z",
      "agent": "engagement-initializer-v1",
      "action": "Initialized engagement harness. Created deliverable-registry.json with 12 deliverables. All marked incomplete.",
      "deliverables_completed": [],
      "next_agent": "UC1 Sales-to-Service Agent"
    }
  ]
}
```

Both files are written to the wiki bucket at:
- `wiki/engagements/{engagement_id}/deliverable-registry.json`
- `wiki/engagements/{engagement_id}/progress.json`

---

### 21.4 Harness-Aware Skill Enhancements

#### SK-01 Enhanced: Health Check on Session Start

The Anthropic article's "init.sh" pattern — verify the app is healthy before starting new work — maps directly to an enhanced SK-01 that checks prior session outputs exist before proceeding.

```
SK-01 Enhanced Flow:
  1. Load deliverable-registry.json for this engagement
  2. Load progress.json (last session's summary)
  3. For each PRIOR UC's completed deliverables:
       → check S3 key exists (not just "marked complete")
       → if missing: create blocking gap via SK-05 before proceeding
  4. THEN load current customer context + playbook (existing SK-01 logic)
  5. Return: {prior_sessions, completed_deliverables, health_check_passed, ...existing outputs}
```

This eliminates cold-start disorientation: the agent reads `progress.json` and knows *exactly* what was done in the last session, which deliverables are remaining, and whether any prior outputs are in a broken state.

#### SK-03 Enhanced: Deliverable Completion Verification

The Anthropic article's hardest lesson: **never mark a feature complete without testing it**. The equivalent in LLMWiki is that SK-03 should not mark a deliverable complete just because it wrote a page — it should verify the page is queryable.

```
SK-03 Enhanced Flow (when deliverable_id is provided):
  1. Write page to wiki (existing SK-03 logic)
  2. Wait for KB sync (poll llmwiki-index DynamoDB until page appears, max 30s)
  3. Invoke SK-02: "Does {wiki_key} contain {expected_content_signal}?"
  4. IF SK-02 returns confidence=high:
       → mark deliverable "complete": true in deliverable-registry.json
       → append session summary to progress.json
     ELSE:
       → mark deliverable "needs-verification" (not complete)
       → log warning to progress.json
  5. Return standard SK-03 response + verification_status
```

---

### 21.5 Step Functions Engagement State Machine

The harness runtime is an **AWS Step Functions Standard Workflow** — one state machine execution per engagement. This replaces direct Lambda-to-Lambda calls from the UC1 orchestrator, enabling durable checkpointing, human-approval gates, and resumable execution across sessions.

```
┌─────────────────────────────────────────────────────────────────────┐
│              LLMWiki Engagement State Machine                        │
│                   (one execution per engagement_id)                  │
│                                                                      │
│  EventBridge (SOW signed)                                            │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────┐                                                │
│  │ UC0: Initialize  │  → writes deliverable-registry.json            │
│  │  Harness         │    + progress.json to wiki                     │
│  └────────┬─────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ UC1: Load Context│  → SK-01 (health check + customer context)     │
│  │  (SK-01)         │                                                │
│  └────────┬─────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ UC1: Query Wiki  │  → SK-02 (handoff process risks)               │
│  │  (SK-02)         │                                                │
│  └────────┬─────────┘                                                │
│           │                                                          │
│    ┌──────▼──────┐                                                   │
│    │ confidence  │                                                    │
│    │  == "low"?  │                                                    │
│    └──┬──────┬───┘                                                   │
│    Yes│      │No                                                      │
│       ▼      ▼                                                       │
│  ┌─────────┐ │                                                       │
│  │SK-05:   │ │  → classify + persist gaps                            │
│  │Gap Radar│ │                                                        │
│  └────┬────┘ │                                                       │
│       │      │                                                       │
│   blocking?  │                                                       │
│    ┌──▼──┐   │                                                       │
│    │Wait │   │  ← .waitForTaskToken (SNS → human fills gap           │
│    │Token│   │     → sends task token back → execution resumes)      │
│    └──┬──┘   │                                                       │
│       └──────┘                                                       │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ UC1: Fill        │  → SK-04 (persona template + available context)│
│  │  Template (SK-04)│                                                │
│  └────────┬─────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ UC1: Write +     │  → SK-03 (write + verify + mark D-01 complete) │
│  │  Verify (SK-03)  │                                                │
│  └────────┬─────────┘                                                │
│           │                                                          │
│    ┌──────▼──────┐                                                   │
│    │ All UC1     │                                                    │
│    │ deliverables│                                                    │
│    │ complete?   │                                                    │
│    └──┬──────┬───┘                                                   │
│    No │      │ Yes                                                    │
│       │      ▼                                                       │
│       │  ┌──────────────────┐                                        │
│       │  │ Trigger UC2      │  → EventBridge: "UC1Complete"          │
│       │  └──────────────────┘                                        │
│       │                                                              │
│       └──────► (loop back to UC1: Load Context)                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Step Functions features used:**

| Feature | Purpose |
|---|---|
| **Standard Workflow** | Durable execution history — survives Lambda restarts, supports re-drives |
| **`.waitForTaskToken`** | Pauses on blocking gap until human fills it via SNS callback |
| **Error handling + retry** | Lambda failures retry with exponential back-off before escalating |
| **Choice state** | Route on `confidence` level and deliverable completion status |
| **Map state** (Phase 3) | Run UC2–UC10 sequentially, each reading prior agent outputs |
| **Execution history** | Full audit trail of every skill invocation, decision, and timing |

---

### 21.6 Progress Tracking in the Wiki

Every skill invocation that completes a deliverable appends an entry to `progress.json`. This is the direct LLMWiki equivalent of `claude-progress.txt` — the file that lets each new session get oriented without spending tokens re-discovering state.

```json
{
  "engagement_id": "bcbs-mn-001",
  "sessions": [
    {
      "session_id": "uc1-run-001",
      "uc": "UC1",
      "timestamp": "2026-05-14T10:05:00Z",
      "agent": "sales-to-service-agent-v1",
      "skills_invoked": ["SK-01","SK-02","SK-05","SK-04","SK-03"],
      "action": "Loaded customer context (new customer, no history). Queried delivery risks — confidence=medium. No blocking gaps. Populated persona template at 72% completion. Wrote handoff brief to wiki/customers/bcbs-mn-001-handoff-2026.md. Verified via SK-02 — confidence=high. Marked D-01 complete.",
      "deliverables_completed": ["D-01"],
      "deliverables_remaining": ["D-02","D-03","D-04","D-05","D-06","D-07","D-08","D-09","D-10","D-11","D-12"],
      "next_session_note": "D-02 Persona Template needs re-run with full SOW context — completion was 72%, target is 90%+. Trigger UC2 when D-01 and D-02 both complete."
    }
  ]
}
```

SK-01 reads this file at the start of every session. The `next_session_note` field is the exact equivalent of the Anthropic article's progress note — written by one agent session to orient the next.

---

### 21.7 Four Failure Modes — LLMWiki Solutions

Mapping the Anthropic article's failure modes table to the LLMWiki harness:

| Failure Mode | Anthropic Solution | LLMWiki Harness Solution |
|---|---|---|
| **Agent one-shots and runs out of context** | Feature list + one-feature-per-session rule | Deliverable registry + Step Functions — each state handles ONE skill, not the whole engagement |
| **Agent declares victory prematurely** | Feature `"passes": false` until E2E tested | Deliverable `"complete": false` until SK-02 confirms the page is queryable with `confidence=high` |
| **Agent can't get up to speed in new session** | `claude-progress.txt` + git log | `progress.json` in wiki + SK-01 reads it at session start before doing any work |
| **App left in broken state between sessions** | `init.sh` health check + smoke test | SK-01 health check verifies all prior deliverables' S3 keys exist before proceeding; creates blocking gap if any are missing |

---

### 21.8 AWS Service Architecture — Full Harness

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLMWiki Engagement Harness                    │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐ │
│  │ EventBridge │───►│  Step Functions Standard Workflow        │ │
│  │ SOW Signed  │    │  (one execution per engagement_id)       │ │
│  └─────────────┘    └───────────────────┬─────────────────────┘ │
│                                         │                        │
│         ┌───────────────────────────────▼────────────────────┐  │
│         │              S3 Wiki Bucket                         │  │
│         │  wiki/engagements/{id}/deliverable-registry.json   │  │
│         │  wiki/engagements/{id}/progress.json               │  │
│         │  wiki/customers/{id}-handoff.md                    │  │
│         │  wiki/artifacts/{id}-persona.md                    │  │
│         │  ... (all UC1–UC10 deliverable pages)              │  │
│         └────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  SK-01   │  │  SK-02   │  │  SK-05   │  │  SK-03       │   │
│  │ Briefing │  │Knowledge │  │  Gap     │  │ Recorder     │   │
│  │ Loader   │  │ Finder   │  │  Radar   │  │ + Verifier   │   │
│  │(+health  │  │          │  │(.waitFor │  │(+marks       │   │
│  │ check)   │  │          │  │ Token)   │  │ complete)    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│                                                                  │
│  ┌────────────────┐   ┌──────────────┐   ┌───────────────────┐ │
│  │  DynamoDB      │   │     SNS      │   │  CloudWatch       │ │
│  │  llmwiki-log   │   │  Blocking    │   │  Step Functions   │ │
│  │  llmwiki-gaps  │   │  Gap Alerts  │   │  Execution Logs   │ │
│  └────────────────┘   └──────────────┘   └───────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

### 21.9 Harness vs. Skill Architecture — How They Work Together

The harness and skill architectures are complementary layers, not alternatives:

```
┌────────────────────────────────────────────────────────┐
│                  HARNESS LAYER                          │
│  Step Functions + UC0 + deliverable-registry.json      │
│  "What needs to be done? What is done? What's next?"   │
│                        │                               │
│              ┌─────────▼──────────┐                    │
│              │    SKILL LAYER      │                    │
│              │  SK-01..SK-09      │                    │
│              │  "How to do it"    │                    │
│              └─────────┬──────────┘                    │
│                        │                               │
│              ┌─────────▼──────────┐                    │
│              │    WIKI LAYER       │                    │
│              │  S3 + Bedrock KB   │                    │
│              │  "What we know"    │                    │
│              └────────────────────┘                    │
└────────────────────────────────────────────────────────┘
```

- The **wiki layer** stores knowledge and deliverable state
- The **skill layer** executes discrete capabilities against the wiki
- The **harness layer** orchestrates skills in the right order, tracks progress, handles failures, and ensures agents stay oriented across sessions

Without the harness, skills are called in a single Lambda and the engagement state lives only in the Lambda's execution context — lost if the function times out or the agent is re-triggered. With the harness, engagement state is durable in S3 and execution state is durable in Step Functions.

---

### 21.10 Implementation Phases

| Component | Phase | Effort |
|---|---|---|
| UC0 Engagement Initializer Lambda | Phase 2 POC | 1 day |
| `deliverable-registry.json` schema + S3 write | Phase 2 POC | 0.5 days |
| `progress.json` append in SK-03 | Phase 2 POC | 0.5 days |
| SK-01 health check (S3 existence check) | Phase 2 POC | 0.5 days |
| SK-03 deliverable verification (SK-02 confirmation query) | Phase 2 POC | 1 day |
| Step Functions state machine (replaces UC1 orchestrator Lambda) | Phase 3 | 2 days |
| `.waitForTaskToken` for blocking gaps | Phase 3 | 1 day |
| Multi-UC state machine (UC1→UC10 in sequence) | Phase 3 | 3 days |
| progress.json surfaced in Streamlit UI | Phase 2 POC | 0.5 days |

---

## 22. Hard Harness — Domain-Specific Workflow Enforcement

### 22.1 The Insight: Soft Harness vs. Hard Harness

Section 21 describes the **Engagement Harness** — a soft harness where LLMWiki acts as the durable state store and skills are orchestrated via Step Functions. This is powerful but still partially LLM-controlled: the agent decides what to call next, can skip steps, and can declare victory early.

Three sources converge on a stronger pattern:

1. **Stripe Minions** (Feb 2026) — Stripe's internal coding agents merged >1,000 PRs/week using a "legal plugin" architecture: a conversational **Gatekeeper LLM** validates prerequisites before any action, then a deterministic **Locked Plan Panel** drives execution phase by phase. The LLM executes *within* each phase but cannot reorder or skip phases. Real-time SSE events stream phase transitions to the UI.

2. **Anthropic Harness Research** (Nov 2025, Section 21) — Initializer sets structured environment; coding agent reads progress file, picks ONE item, works, commits.

3. **AI Automators Ep 6 Agent Harness** — Formalises the architecture as two explicit layers: *Deep Mode (soft harness, LLM-controlled)* vs *Harness Engine (hard harness, system-controlled state machine)*. Five deterministic phase types. Contract review demo: 8 phases, batched parallel sub-agents, human-in-the-loop, DOCX output.

**The key insight (from Ep 6):**
> *"The model is commoditized. Structured enforcement of process is the moat."*

A hard harness guarantees every phase completes and validates before advancing. The LLM cannot decide to skip due diligence. This is the difference between a demo and a production-grade system.

---

### 22.2 Hard Harness vs. Soft Harness — LLMWiki Context

| Dimension | Soft Harness (Section 21) | Hard Harness (Section 22) |
|---|---|---|
| **Who controls flow** | LLM (UC1 orchestrator) | System (Step Functions state machine) |
| **Phase skipping** | LLM can decide to skip SK-05 | Engine enforces every phase completes |
| **Validation** | Deliverable marked complete when SK-02 confirms | Pydantic-validated structured output per phase before advance |
| **Prerequisites** | None — fires immediately on SOW ingest | Gatekeeper LLM validates all inputs present before launch |
| **Phase context** | Full agent system prompt all the time | 5–15 line focused prompt per phase + curated tools only |
| **Human pause** | Blocking gap via SNS | `llm_human_input` phase type — conversational mid-task pause |
| **UI** | Skill execution log in Streamlit | Real-time phase panel with locked plan (LLM cannot modify) |
| **Deliverables** | S3 markdown pages | S3 markdown + structured JSON + downloadable DOCX reports |
| **Parallelism** | Sequential skills | `llm_batch_agents` — configurable concurrent sub-agents per item |

---

### 22.3 Five Phase Types — Mapped to LLMWiki

Borrowed from the Ep 6 Harness Engine spec:

| Phase Type | Description | LLMWiki Usage |
|---|---|---|
| `programmatic` | Pure Python, no LLM — document extraction, parsing | SOW PDF parsing, customer entity extraction, BOM parsing |
| `llm_single` | Single LLM call, Pydantic-validated structured JSON output | Classification (contract type, risk tier), gap prioritisation |
| `llm_agent` | Multi-round agent loop with curated tool set | Playbook RAG discovery, delivery risk analysis |
| `llm_batch_agents` | N parallel sub-agents per item, configurable concurrency | Clause-by-clause risk scoring, multi-domain gap analysis |
| `llm_human_input` | Pauses harness, generates informed question, waits for reply | Blocking gap → human fills context → harness resumes |

---

### 22.4 UC1 Hard Harness — 8 Phases

Mapping the Stripe/Ep6 contract review pattern to the UC1 Sales-to-Service engagement:

```
┌─────────────────────────────────────────────────────────────────────────┐
│              UC1 Hard Harness — Sales-to-Service Agent                   │
│                     (replaces UC1 Orchestrator Lambda)                   │
│                                                                          │
│  GATEKEEPER LLM (pre-harness, conversational)                            │
│  "I can see the SOW for BlueCross BlueShield MN has been uploaded.       │
│   Do you want me to begin the Sales-to-Service handoff workflow?"        │
│  → User confirms → [TRIGGER_HARNESS] sentinel → harness starts          │
│                                                                          │
│  ┌─────┬────────────────────────────┬──────────────────┬─────────────┐  │
│  │Phase│ Name                       │ Type             │ Output      │  │
│  ├─────┼────────────────────────────┼──────────────────┼─────────────┤  │
│  │  1  │ SOW Intake & Extraction    │ programmatic     │ sow-text.md │  │
│  │  2  │ Customer Classification    │ llm_single       │ classif.md  │  │
│  │  3  │ Gather Handoff Context     │ llm_human_input  │ context.md  │  │
│  │  4  │ Load Delivery Playbook     │ llm_agent (SK-01)│ playbook.md │  │
│  │  5  │ Risk & Gap Analysis        │ llm_agent (SK-02)│ risks.md    │  │
│  │  6  │ Gap Detection & Recording  │ llm_batch_agents │ gaps.md     │  │
│  │     │   (1 sub-agent per gap)    │ (SK-05 × N)      │             │  │
│  │  7  │ Template Population        │ llm_agent (SK-04)│ persona.md  │  │
│  │  8  │ Write Handoff + Summary    │ llm_single+SK-03 │ handoff.md  │  │
│  │     │   → DOCX report generation │ + DOCX           │ + .docx     │  │
│  └─────┴────────────────────────────┴──────────────────┴─────────────┘  │
│                                                                          │
│  POST-HARNESS LLM (conversational)                                       │
│  "The handoff brief for BCBS-MN is complete. 3 delivery risks flagged.  │
│   Persona template is 84% complete. Full report in wiki/handoffs/..."   │
│  → Reverts to normal agent mode for follow-up questions                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 22.5 Gatekeeper LLM Pattern

Borrowed from Stripe Minions — a prerequisite-validating conversational agent runs *before* any harness phase begins:

```
User uploads SOW PDF
         │
         ▼
Gatekeeper LLM (no tools — conversational only)
  Checks:
  • SOW file is present in workspace
  • customer_id is determinable from filename or prior context
  • No active harness run already exists for this engagement
  
  If prerequisites met:
    "SOW for BlueCross BlueShield MN uploaded ✓. 
     Ready to begin Sales-to-Service handoff workflow (8 phases, ~4 mins).
     Shall I proceed?"
    User: "Yes"
    → Response ends with [TRIGGER_HARNESS] sentinel
    → Harness engine starts Phase 1 in the same SSE stream

  If prerequisites not met:
    "I can see you've started the workflow, but I need the signed SOW 
     document before I can begin. Please upload the PDF."
    → Multi-turn conversation until prerequisites satisfied
```

**Why this matters for LLMWiki:** Without a gatekeeper, the UC1 agent fires immediately on EventBridge and proceeds even if the SOW PDF failed to ingest, the customer entity page wasn't created, or the KB sync is still pending. The gatekeeper absorbs all of these edge cases in a user-friendly conversational layer before any deterministic work begins.

---

### 22.6 Locked Plan Panel — UI Pattern

From Stripe Minions: the Locked Plan Panel is the UI's visual contract with the user. The agent cannot modify the plan (locked icon). The user sees exactly what phases are coming, which is running now, and what has completed.

```
┌─────────────────────────────────────────────────────────┐
│  🔒 UC1 Sales-to-Service Handoff                         │
│  BCBS Minnesota · SOW-2026-BCBS-MN-001                   │
├─────────────────────────────────────────────────────────┤
│  ✅ Phase 1  SOW Intake & Extraction          0.4s       │
│  ✅ Phase 2  Customer Classification          2.1s       │
│  ✅ Phase 3  Gather Handoff Context           —          │
│             (waiting for your input)                     │
│  🔵 Phase 4  Load Delivery Playbook         [running]    │
│  ⬜ Phase 5  Risk & Gap Analysis             —           │
│  ⬜ Phase 6  Gap Detection & Recording       —           │
│  ⬜ Phase 7  Template Population             —           │
│  ⬜ Phase 8  Write Handoff + Report          —           │
├─────────────────────────────────────────────────────────┤
│  🔒 This plan is system-enforced and cannot be modified. │
└─────────────────────────────────────────────────────────┘
```

**Real-time behaviour via SSE:** Each phase transition emits `harness_phase_start` / `harness_phase_complete` events. The Streamlit UI updates the panel status without a page reload. Sub-agent spawns in Phase 6 emit `harness_sub_agent_start` / `harness_sub_agent_complete` per gap, showing a progress counter: "Analysing gap 3 of 7…"

---

### 22.7 Human-in-the-Loop — Phase 3 Context Gathering

Phase 3 (`llm_human_input`) implements the Stripe/Ep6 pattern for mid-harness human input. Unlike the SK-05 SNS escalation (a blocking notification), this is a *conversational* pause that generates an informed question using what Phase 1 and 2 already discovered:

```
Phase 2 Output (Classification):
  {
    "customer_type":   "Healthcare Payer",
    "products":        ["TriZetto QNXT"],
    "go_live_target":  "2026-Q4",
    "risk_tier":       "HIGH",
    "contract_value":  "Enterprise"
  }

Phase 3 generates (informed by Phase 2):
  "I've classified this as a high-risk, enterprise healthcare payer 
   implementation targeting Q4 go-live. Before I analyse the delivery 
   risks, can you tell me:
   1. Has this customer implemented TriZetto products before?
   2. Are there any known data migration constraints from legacy systems?
   3. Who is the designated Delivery Lead?
   
   Your answers will be used to prioritise the risk analysis in Phase 5."

User responds → written to workspace as context.md → Phase 4 begins
```

---

### 22.8 Batched Parallel Sub-Agents — Phase 6

Phase 6 (Gap Detection) uses `llm_batch_agents` to analyse multiple gaps in parallel, instead of running SK-05 once for all gaps sequentially:

```
Phase 5 Output: 7 identified risk areas (from SK-02 analysis)

Phase 6 Engine:
  batch_size = 3  (3 concurrent sub-agents)
  
  Batch 1 (concurrent):
    Sub-agent A: Analyses gap "No TriZetto QNXT implementation history"
    Sub-agent B: Analyses gap "Missing claims turnaround SLA documentation"  
    Sub-agent C: Analyses gap "No data migration playbook for QNXT"
  
  Batch 2 (concurrent):
    Sub-agent D: Analyses gap "No healthcare payer persona template"
    Sub-agent E: Analyses gap "Missing go-live checklist for Q4 target"
    Sub-agent F: Analyses gap "No known escalation contacts documented"
  
  Batch 3 (single):
    Sub-agent G: Analyses gap "No prior BCBS implementation evidence"
  
  Each sub-agent calls SK-05 with its specific gap + writes result to workspace
  Results aggregated → gaps.md written → Phase 7 begins
```

**UI:** Progress counter in the phase panel — "Analysing gap 3 of 7…" — gives the user real-time visibility into a parallel workload that would otherwise feel like a black box.

---

### 22.9 AWS Components — Hard Harness vs. Soft Harness Delta

The hard harness uses the same core AWS services but adds and changes several:

| Component | Soft Harness (§21) | Hard Harness Delta |
|---|---|---|
| **Orchestration** | Step Functions Standard Workflow | Step Functions **Express Workflow** (lower latency) + Map state for batch phases |
| **Phase state** | deliverable-registry.json in S3 | `harness_runs` DynamoDB table (per-thread state machine status, phase results JSONB) |
| **Human pause** | `.waitForTaskToken` (SNS-based) | Step Functions `.waitForTaskToken` via **AppSync** (real-time UI callback) or API Gateway WebSocket |
| **Sub-agents** | Single Lambda per skill | **Lambda concurrency** reserved per harness type × batch_size (e.g., 5 concurrent SK-05 invocations) |
| **Structured output** | JSON response from skills | Bedrock **response schemas** (tool_choice forced structured JSON) + Pydantic validation in Lambda |
| **Phase output store** | S3 wiki pages | S3 wiki pages **+** DynamoDB phase_results JSONB (for fast UI queries without S3 reads) |
| **Real-time UI** | Streamlit polling (DynamoDB scan) | **API Gateway WebSocket** or **SSE endpoint** → Streamlit `st.write_stream()` |
| **DOCX generation** | Not in scope | Lambda Layer with `python-docx` + S3 presigned URL for download |
| **Gatekeeper** | None | New Lambda: `llmwiki-gatekeeper` — conversational prereq validation |
| **Post-harness** | None | Bedrock call after all phases complete → summary message in UI |

---

### 22.10 Streamlit UI — Agentic Steps Visualisation

The current Streamlit Agent Demo uses a step-by-step button progression. The hard harness pattern enables a richer real-time UI that shows agents thinking and phases completing without any button clicks:

```
┌─────────────────────────────────────────────────────────────────────┐
│  🤖 UC1 Sales-to-Service Agent — Live Execution                      │
│  Customer: BCBS Minnesota · SOW-2026-BCBS-MN-001                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  GATEKEEPER  ─────────────────────────────────────────────────────  │
│  💬 "SOW uploaded ✓. Ready to begin 8-phase handoff workflow."       │
│  💬 User: "Go ahead"                                                 │
│                                                                      │
│  LOCKED PLAN  🔒 ─────────────────────────────────────────────────  │
│  ✅ 1. SOW Intake          0.4s    📄 sow-text.md                    │
│  ✅ 2. Classification      2.1s    📋 Healthcare Payer / HIGH risk   │
│  ✅ 3. Gather Context      —       💬 Human provided context         │
│  🔵 4. Load Playbook       3.2s…   🔍 Querying wiki (SK-01+SK-02)   │
│       └─ Searching: "UC1 onboarding playbook" ████░░░░              │
│  ⬜ 5. Risk Analysis       —                                         │
│  ⬜ 6. Gap Detection       —       (7 gaps · 3 parallel agents)      │
│  ⬜ 7. Template Fill       —                                         │
│  ⬜ 8. Handoff Report      —       📄 .md + 📥 .docx                 │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│  TELEMETRY  ──────────────────────────────────────────────────────  │
│  Phases done: 3/8  │  Skills invoked: 4  │  Gaps found: 0 so far   │
└─────────────────────────────────────────────────────────────────────┘
```

**Implementation approach for Streamlit:**
- Use `st.status()` containers (Streamlit 1.28+) — each phase becomes a collapsible status block that auto-expands when running and collapses to a checkmark when complete
- `st.progress()` bar per batch phase showing sub-agent completion
- `st.chat_message()` for the gatekeeper conversational exchange
- `st.download_button()` for the DOCX report at Phase 8
- Backend publishes phase events to DynamoDB; frontend polls every 2s and rerenders only changed phases using `st.fragment` (Streamlit 1.37+)

---

### 22.11 Why This Architecture Is Better — Summary Comparison

| Dimension | Direct Lambda calls (Phase 1) | Skill Architecture (§20) | Soft Harness (§21) | Hard Harness (§22) |
|---|---|---|---|---|
| Agent can skip steps | Yes | Yes | Yes (LLM decides) | **No — system enforced** |
| Agent declares victory early | Yes | Yes | No (deliverable verification) | **No — gated phases** |
| Prerequisites validated | No | No | No | **Yes — gatekeeper** |
| Human input | SNS notification | SK-05 blocking gap | waitForTaskToken | **Conversational mid-phase** |
| Per-phase tool scope | All tools always | All tools always | All tools always | **5–15 line prompt + curated tools** |
| Parallel processing | No | No | No | **Batch sub-agents** |
| UI visibility | Progress bar | Skill execution log | Deliverable registry | **Real-time locked plan panel** |
| Output format | Markdown only | Markdown only | Markdown + JSON | **Markdown + JSON + DOCX** |
| New harness = new UC | Full rebuild | Skill wiring | New Step Functions def | **Register harness file + done** |

---

### 22.12 Deployed POC — AWS Resources

All hard harness components are deployed and smoke-tested in account `392568849512` (us-east-1).

| Resource | Name | Key Config |
|---|---|---|
| Lambda — Gatekeeper | `llmwiki-gatekeeper` | 30s / 256MB · validates prereqs · generates Bedrock greeting · returns 8-phase manifest |
| Lambda — UC1 Harness | `llmwiki-uc1-harness` | 900s / 1024MB · 8-phase state machine · `get_status` polling action · async-safe resume |
| DynamoDB — Harness Runs | `llmwiki-harness-runs` | PAY_PER_REQUEST · GSIs: `status_index`, `engagement_status_index` · TTL 30 days |
| DynamoDB — Workspace Files | `llmwiki-workspace-files` | PAY_PER_REQUEST · GSI: `phase_index` (numeric ordering) · TTL 30 days |
| Streamlit Page | `/harness_demo` | Two-column layout: chat (60%) + locked plan (40%) · async polling every 3s |
| IAM | `llmwiki-streamlit-skills-invoke` | Streamlit ECS task invokes gatekeeper + uc1_harness + reads harness tables |
| SSM | `/llmwiki/harness/gatekeeper_arn`, `/llmwiki/harness/uc1_harness_arn` | ARN discovery |

---

### 22.13 Async Polling Pattern (implemented)

The naive implementation blocked Streamlit for 30–60 seconds with a spinning cursor. The production-ready pattern:

```
1. UI fires  lambda.invoke(InvocationType="Event")  ← <100ms, fire and forget
2. Lambda runs phases 4–8, writing DynamoDB after every phase
3. UI calls  get_status  every 3s (DynamoDB.get_item, ~100ms)
4. Phase tiles animate live: ⬜ → 🔵 (running) → ✅ (complete)
5. When status=completed → fetch full phase_results → render completion + download
```

**DynamoDB writes per phase:**
- Before phase: `current_phase=N`, `current_phase_name="..."` (for live display)
- After phase: `current_phase=N+1`, `phase_results=<updated JSON blob>`
- Final: `status=completed`, `total_latency_ms`, `completed_at`

**Resilience:**
- Browser close mid-run → state in DynamoDB; polling resumes on reopen
- Double-resume prevented by `status=running` set atomically at resume start
- Partial phase_results returned on Lambda timeout — UI shows what completed

---

### 22.14 Phase-by-Phase Latency Budget (observed POC)

| Phase | Type | Typical Latency | Bottleneck |
|---|---|---|---|
| 1 — SOW Intake | programmatic | 300–500ms | DynamoDB + Lambda |
| 2 — Classification | llm_single | 2–4s | Bedrock Claude |
| 3 — Human Input (question gen) | llm_human_input | 3–5s | Bedrock Claude |
| 4 — Load Playbook | llm_agent (SK-01) | 300ms–8s | Bedrock KB query |
| 5 — Risk Analysis | llm_agent (SK-02) | 10–40s | KB vector search + synthesis |
| 6 — Gap Detection | llm_batch_agents (SK-05×3) | 10–30s | 3 sequential SK-05 calls |
| 7 — Template Fill | llm_agent (SK-04) | 100–500ms | Template lookup |
| 8 — Handoff Report | llm_single (SK-03) | 1–3s | S3 write + presigned URL |
| **Total phases 4–8** | | **~30–90s** | Phase 5 dominates (~60%) |

Phase 5 (SK-02 with Bedrock KB vector search) is the primary optimisation target in production: response caching, KB pre-warming, or streaming delivery.

---

### 22.15 Error Handling Contract

Each phase is wrapped in `try/except _PhaseError`. On failure:
1. `status=error` written to DynamoDB with `failed_phase=N`
2. Partial `phase_results` (up to failed phase) returned — still useful to delivery team
3. UI shows `❌ Error at Phase N: <message>` in the locked plan panel

**Non-fatal failures** (harness continues):
- `_write_workspace` DynamoDB write → logged, harness proceeds
- S3 report upload → logged as warning, `report_uploaded=false` in Phase 8 result
- `_init_harness_run` → logged, harness runs without persistence

This contract means the business user always knows exactly which phase failed and which phases succeeded — not just "something went wrong."

---

*End of LLMWiki AWS AgentCore System Design v2.1*
*Updated 2026-05-15 — Sections 22.12–22.15: deployed POC details, async polling, latency budget, error contract*
*AWS Account: 392568849512 | Region: us-east-1 | Model: us.anthropic.claude-sonnet-4-6*
