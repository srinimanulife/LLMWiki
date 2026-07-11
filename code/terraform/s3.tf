resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ── Main wiki bucket ──────────────────────────────────────────────
resource "aws_s3_bucket" "wiki" {
  bucket = "llmwiki-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_versioning" "wiki" {
  bucket = aws_s3_bucket.wiki.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "wiki" {
  bucket = aws_s3_bucket.wiki.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "wiki" {
  bucket                  = aws_s3_bucket.wiki.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Seed sample documents ─────────────────────────────────────────
resource "aws_s3_object" "sample_pdf_text" {
  bucket       = aws_s3_bucket.wiki.id
  key          = "raw/papers/cloud-strategy-2026.md"
  content_type = "text/markdown"
  content      = <<-EOT
    # Cloud Strategy 2026

    ## Executive Summary
    This document outlines the organization's cloud strategy for 2026. Our primary goal is to migrate 80%
    of workloads to AWS by Q4 2026, reducing infrastructure costs by 35% while improving system reliability
    to 99.99% uptime.

    ## Key Initiatives
    1. **Lift and Shift Phase**: Move 40 legacy applications to EC2 with minimal changes by Q2 2026.
    2. **Modernization Phase**: Re-architect top 10 business-critical apps to use serverless and containers.
    3. **Data Platform Consolidation**: Unify 6 disparate data warehouses into a single AWS data lake on S3
       with Athena and Glue for querying.
    4. **Security Posture Improvement**: Implement AWS Security Hub, GuardDuty, and zero-trust networking
       across all workloads by Q3 2026.

    ## Budget
    Total cloud budget for 2026: $4.2M
    - Compute and storage: $2.1M
    - Data services: $800K
    - Security and compliance: $600K
    - Professional services and training: $700K

    ## Risks and Mitigations
    - **Vendor lock-in risk**: Mitigated by using Terraform for IaC and avoiding proprietary managed services
      where open alternatives exist.
    - **Skills gap**: 60% of engineering team lacks AWS certification. Training program budgeted for H1 2026.
    - **Compliance**: PCI-DSS and SOC2 audits scheduled for Q3. Security Hub findings must be remediated
      before go-live.

    ## Success Metrics
    - Migration velocity: 5 applications per sprint
    - Cost per workload: 30% reduction vs on-prem baseline
    - MTTR: from 4 hours to under 30 minutes
    - Deployment frequency: from monthly to daily
  EOT
}

resource "aws_s3_object" "sample_notes" {
  bucket       = aws_s3_bucket.wiki.id
  key          = "raw/notes/team-meeting-2026-05-01.md"
  content_type = "text/markdown"
  content      = <<-EOT
    # Team Meeting Notes — 2026-05-01

    **Attendees**: Sarah Chen (CTO), Marcus Obi (Cloud Architect), Priya Nair (Security Lead),
    James Park (DevOps Lead)

    ## Discussion Points

    ### Cloud Migration Status
    - Q1 target of 10 apps met: 12 apps successfully migrated to EC2
    - Modernization track behind: only 2 of 10 target apps re-architected (was expecting 4 by now)
    - Root cause: underestimated complexity of legacy Oracle database dependencies
    - Decision: engage AWS Professional Services for Oracle to Aurora migration playbook

    ### Security Findings
    - GuardDuty flagged 3 high-severity findings in the dev account last week
    - All related to overly permissive IAM roles created by a contractor in 2024
    - Priya to remediate by EOW, implementing least-privilege IAM policy review process
    - Security Hub score improved from 42% to 67% since January

    ### Budget Review
    - Q1 actual spend: $890K vs $1.05M budgeted (15% under budget)
    - Savings from Reserved Instance purchases for EC2 fleet
    - Reallocating $160K savings to accelerate the data lake project

    ### Action Items
    - Marcus: finalize Terraform modules for VPC and ECS by 2026-05-15
    - Priya: remediate IAM findings and update runbook
    - James: set up CloudWatch dashboards for migration KPIs
    - Sarah: schedule AWS Professional Services engagement

    ## Next Meeting: 2026-05-15
  EOT
}

resource "aws_s3_object" "sample_article" {
  bucket       = aws_s3_bucket.wiki.id
  key          = "raw/articles/generative-ai-enterprise-trends.md"
  content_type = "text/markdown"
  content      = <<-EOT
    # Generative AI in the Enterprise: 2026 Trends

    Source: Internal research summary, compiled 2026-04-20

    ## Overview
    Enterprise adoption of generative AI has accelerated dramatically in 2025-2026. Key findings from
    a survey of 500 enterprise technology leaders:

    - 73% have at least one generative AI system in production (up from 31% in 2024)
    - Average investment per enterprise: $2.3M in 2026, up 180% from 2024
    - Top use cases: document summarization (68%), code generation (61%), customer service automation (54%)

    ## Technology Landscape
    The market is dominated by three LLM providers: Anthropic (Claude), OpenAI (GPT series), and
    Google (Gemini). Enterprises increasingly deploy through cloud-provider APIs (AWS Bedrock, Azure OpenAI,
    Google Vertex AI) rather than direct API access, citing security, compliance, and data residency needs.

    ## Key Challenges Reported
    1. **Hallucination and accuracy**: 71% of respondents cited accuracy as their top concern. RAG
       (Retrieval-Augmented Generation) architectures are now the dominant mitigation approach.
    2. **Data security**: 65% worried about proprietary data leaking to model providers. On-premises
       and VPC-deployed models are growing in adoption.
    3. **Cost management**: Token costs at scale are significant. Prompt caching and smaller specialist
       models are emerging cost strategies.
    4. **Skills gap**: Only 28% of enterprises have sufficient internal AI engineering talent.

    ## Emerging Pattern: Knowledge Wikis
    A new architectural pattern gaining traction is the "LLM-maintained knowledge wiki" — where AI
    agents continuously process organizational documents and maintain a structured, searchable knowledge
    base. Unlike pure RAG (which queries raw documents on every request), wiki-based architectures
    pre-process documents once into structured pages, dramatically reducing query latency and improving
    answer consistency. Early adopters report 60% reduction in analyst research time.

    ## Forecast
    By end of 2026, 90% of Fortune 500 companies will have at least one production generative AI system.
    The shift from experimentation to operationalization will drive demand for MLOps, AI governance, and
    enterprise-grade agent platforms.
  EOT
}

resource "aws_s3_object" "sample_data" {
  bucket       = aws_s3_bucket.wiki.id
  key          = "raw/notes/infrastructure-metrics-q1-2026.md"
  content_type = "text/markdown"
  content      = <<-EOT
    # Infrastructure Metrics Q1 2026

    ## Compute
    | Resource | Count | Monthly Cost |
    |----------|-------|--------------|
    | EC2 instances (on-demand) | 42 | $18,400 |
    | EC2 instances (reserved) | 28 | $6,200 |
    | ECS Fargate tasks (avg) | 12 | $2,100 |
    | Lambda invocations (M) | 340 | $680 |

    ## Storage
    | Resource | Volume | Monthly Cost |
    |----------|--------|--------------|
    | S3 (standard) | 48 TB | $1,104 |
    | S3 (IA) | 120 TB | $1,560 |
    | EBS volumes | 18 TB | $1,800 |
    | RDS (Aurora) | 6 TB | $2,400 |

    ## Availability
    - Overall uptime: 99.94% (target: 99.9%)
    - Incidents: 2 P1, 4 P2, 11 P3
    - Mean Time to Recovery (P1): 47 minutes (target: 30 min — needs improvement)
    - Deployments: 143 production deployments, 0 rollbacks

    ## Cost Trend
    - Q1 2026 total: $890K
    - Q4 2025 total: $1.02M
    - Reduction: 12.7% QoQ (primary driver: RI purchases and S3 lifecycle policy implementation)

    ## Recommendations
    1. Migrate remaining on-demand EC2s to reserved instances — estimated savings: $4,200/month
    2. Enable S3 Intelligent-Tiering for 48TB standard bucket — estimated savings: $1,800/month
    3. Right-size 8 oversized EC2 instances identified in Compute Optimizer report
    4. MTTR reduction: implement automated runbooks for top 5 incident types
  EOT
}

resource "aws_s3_object" "sample_presentation" {
  bucket       = aws_s3_bucket.wiki.id
  key          = "raw/articles/agentcore-architecture-overview.md"
  content_type = "text/markdown"
  content      = <<-EOT
    # AWS AgentCore Architecture Overview

    Source: Internal architecture review presentation, 2026-04-15

    ## What is AgentCore?
    AWS AgentCore is a fully managed runtime for deploying and operating AI agents at enterprise scale.
    It provides: agent hosting, tool (MCP) registry, session memory, multi-agent orchestration, and
    built-in observability — without requiring teams to manage the underlying infrastructure.

    ## Core Components

    ### Agent Runtime
    Hosts agent logic in isolated execution environments. Supports Python and TypeScript. Agents are
    defined by: (1) a system prompt, (2) a set of MCP tools, (3) an optional memory store, and
    (4) a supervisor/sub-agent hierarchy.

    ### MCP Tool Registry
    Model Context Protocol (MCP) is the standard for agent tool definitions. AgentCore's registry
    allows tools to be registered once and discovered/called by any agent in the fleet. This is the
    key enabler for multi-agent composition — agents call each other's tools without bespoke integration.

    ### Agent Memory Store
    Persistent, session-scoped memory that survives across multiple turns of a conversation. Agents
    can read and write to memory, enabling context accumulation across sessions.

    ### Multi-Agent Orchestration
    AgentCore supports supervisor-worker hierarchies: a top-level orchestrator agent routes requests
    to specialist sub-agents. Each sub-agent operates independently and returns structured results
    to the supervisor. This enables decomposing complex tasks into parallel, independently scalable units.

    ## Integration with LLMWiki
    The LLMWiki Search Wiki Agent is deployed as an AgentCore agent. It exposes wiki_search,
    wiki_get_page, and wiki_get_overview as MCP tools. Any other agent in the AgentCore fleet can
    call these tools, making the LLMWiki knowledge base a shared substrate for the entire agent ecosystem.

    ## Pricing
    AgentCore is priced per agent-session-second. For a wiki system handling 1,000 queries/day
    with average 5-second session duration: approximately $0.05/hour at baseline load.
  EOT
}

# S3 bucket notification is defined in lambda.tf (single resource covers both
# raw/ ingest trigger and uploads/ converter trigger).

# ── Problem Management wiki bucket ────────────────────────────────
# Separate bucket so PM testing data stays isolated from the main
# Sales-to-Service wiki content.
resource "aws_s3_bucket" "pm" {
  bucket = "llmwiki-problem-mgnt-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_versioning" "pm" {
  bucket = aws_s3_bucket.pm.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pm" {
  bucket = aws_s3_bucket.pm.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "pm" {
  bucket                  = aws_s3_bucket.pm.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
