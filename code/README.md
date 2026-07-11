# LLMWiki — AWS AgentCore Knowledge Wiki

Phase 0 + Phase 1 implementation. Automatically builds a wiki from documents via Bedrock Claude.

## Prerequisites

- AWS SSO session: `aws sso login --profile tzg-sandbox`
- Terraform >= 1.5
- Docker (for Streamlit image)
- Python 3.12
- AWS CLI with S3 Vectors support (aws-cli >= 2.22 / boto3 >= 1.36)

## Quick Start

```bash
# 1. Login
aws sso login --profile tzg-sandbox

# 2. Deploy everything (Terraform + Docker build + push)
cd code
./scripts/deploy.sh --profile tzg-sandbox --region us-east-1

# 3. Test end-to-end
./scripts/test_e2e.sh --profile tzg-sandbox

# 4. Open Streamlit UI (URL printed by deploy.sh)
```

## Cost Management

```bash
# Stop Streamlit to save ~$0.02/hr when not demoing
./scripts/shutdown.sh --profile tzg-sandbox

# Resume Streamlit
./scripts/startup.sh --profile tzg-sandbox

# DESTROY everything (irreversible)
./scripts/destroy.sh --profile tzg-sandbox
```

## Architecture

```
uploads/          → Converter Lambda (Textract PDF / Bedrock Office)
                         ↓
raw/              → Ingest Lambda (Bedrock Claude Sonnet 4.6)
                         ↓
wiki/sources/     → S3 wiki pages (Markdown)
wiki/entities/
wiki/concepts/
                         ↓
Bedrock KB        → S3 Vectors index (semantic search)
                         ↓
Query Lambda      → API Gateway POST /query
                         ↓
Streamlit UI      → Browse, upload, ask questions
```

## Architecture Decision: S3 Vectors, not OpenSearch Serverless

**We use Amazon S3 Vectors as the Bedrock Knowledge Base vector store.**

We evaluated OpenSearch Serverless first and rejected it:

| Factor | OpenSearch Serverless | S3 Vectors |
|---|---|---|
| Minimum cost (idle) | ~$11–12/day (2 OCU always-on) | ~$0/day (pay per request) |
| Deploy complexity | Separate index creation with SigV4 signing, collection warm-up delays | Single `aws s3vectors` CLI call |
| Terraform support | Native resource exists | CLI via `null_resource` (provider support in progress) |
| Fit for this workload | Designed for high-throughput search | Right-sized for tens–hundreds of wiki pages |

LLMWiki is **not a RAG system over raw documents**. The ingest pipeline pre-processes documents into structured wiki pages (sources, entities, concepts), which are already well-organized and small in number. Semantic search over ~50–200 wiki pages does not justify the operational cost or complexity of OpenSearch Serverless.

S3 Vectors is the right default for this scale. If the wiki grows to tens of thousands of pages and query latency becomes a concern, migrating to OpenSearch Serverless is a one-config change in `bedrock_kb.tf`.

## Sample Questions to Ask

After deploy, the 5 pre-loaded documents enable these questions:

- "What are the key risks in our cloud migration strategy?"
- "What was Q1 2026 infrastructure spend?"
- "Who attended the team meeting and what were the action items?"
- "What are the enterprise generative AI adoption trends for 2026?"
- "How does AWS AgentCore work?"
- "What action items were assigned to Marcus and Priya?"

## Directory Layout

```
code/
  terraform/     — All AWS infrastructure (Terraform HCL)
  lambda/
    ingest/      — S3 trigger → Bedrock → wiki pages
    query/       — Bedrock KB retrieval + synthesis
    converter/   — Textract PDF + Office → Markdown
  streamlit/     — Web UI (Docker, ECS Fargate)
  config/        — AGENTS.md wiki schema
  scripts/       — deploy, startup, shutdown, destroy, test
```

## AWS Resources Created (all prefixed llmwiki-)

| Resource | Name | Cost when idle |
|---|---|---|
| S3 bucket (wiki) | llmwiki-{random} | ~$0.023/GB/month |
| S3 Vectors bucket | llmwiki-vectors-{random} | ~$0/month at demo scale |
| DynamoDB (3 tables) | llmwiki-index, llmwiki-log, llmwiki-source-registry | $0 |
| Lambda (3 functions) | llmwiki-ingest, llmwiki-query, llmwiki-converter | $0 |
| API Gateway | llmwiki-api | $0 |
| Bedrock KB | llmwiki-knowledge-base | $0 |
| ECS Fargate | llmwiki-streamlit | $0 when desired_count=0 |
| ECR | llmwiki-streamlit | ~$0.10/GB/month |
| ALB | llmwiki-alb | ~$0.008/hr |
| VPC | llmwiki-vpc | $0 |
| CloudWatch Logs | /aws/lambda/llmwiki-* | ~$0.50/GB ingested |

**Estimated cost running (1 ECS task):** ~$0.50–1/day
**Estimated cost stopped (0 tasks, no queries):** ~$0.20/day (ALB only)

*(Dropped from ~$12–13/day by removing OpenSearch Serverless.)*
