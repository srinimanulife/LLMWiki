# LLMWiki on Neuro SAN — Findings, Integration Design & AWS AgentCore Deployment

**Version:** 1.0  
**Date:** 2026-07-09  
**Status:** Architecture / Decision Document  
**Scope:** How to run the LLMWiki UC1–UC10 agent fleet using Neuro SAN Studio instead of (or alongside) raw AWS AgentCore, and the pros/cons of doing so

---

## 1. Neuro SAN Studio — What It Is (Findings)

Neuro SAN Studio is Cognizant AI Lab's open-source multi-agent orchestration framework. It is the engineering layer behind the **Cognizant Neuro® AI Multi-Agent Accelerator** — the same platform family as the Neuro AI Trust platform (discussed in Section 6).

### 1.1 Core Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  nsflow UI  (http://localhost:4173)                          │
│  Visual agent network browser + chat interface               │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP / gRPC
┌────────────────────────▼─────────────────────────────────────┐
│  Neuro SAN Server  (http://localhost:8080)                   │
│  Tornado async HTTP server · gRPC server                     │
│  AGENT_MANIFEST_FILE → loads registered agent networks       │
│  AGENT_TOOL_PATH → loads coded_tools/ Python classes         │
│  MCP endpoint: /mcp (AGENT_MCP_ENABLE=true)                  │
└────────────────────────┬─────────────────────────────────────┘
                         │ AAOSA protocol
┌────────────────────────▼─────────────────────────────────────┐
│  Agent Network (HOCON config, e.g. llmwiki_uc1.hocon)        │
│  ┌───────────┐     ┌─────────┐     ┌──────────────────────┐  │
│  │ FrontMan  │────▶│ Sub-    │────▶│ CodedTool (Python)   │  │
│  │ (UC1 Agt) │     │ Agents  │     │  wiki_ask / SK-01    │  │
│  └───────────┘     └─────────┘     └──────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 The AAOSA Protocol — How Agents Talk

AAOSA (Adaptive Agent Open System Architecture) is Neuro SAN's inter-agent communication protocol. Every agent in a network follows the same delegation loop:

```
Step 1 — Determine:
  FrontMan asks each sub-agent: "Is this inquiry relevant to you?"
  Sub-agent returns JSON: { Relevant: Yes/No, Strength: 1-10, Claim: All/Partial }

Step 2 — Fulfill:
  FrontMan sends to the most relevant sub-agents:
  "Fulfill your part of this inquiry."
  Sub-agent returns JSON: { Response: "..." }

Step 3 — Follow-up:
  FrontMan may iterate if sub-agents need more information before fulfilling.

Step 4 — Compile:
  FrontMan synthesizes all sub-agent responses into a final answer.
```

This replaces LLMWiki's current custom skill invocation pattern (SK-01 → SK-02 → SK-03 sequence) with a **declarative, self-organizing delegation graph** where agents decide their own relevance.

### 1.3 HOCON — The Configuration Language

Every agent network is a HOCON file. HOCON supports:
- **Variable substitution** (`${aaosa_instructions}`) — the AAOSA protocol is defined once in `registries/aaosa.hocon` and included in every network
- **File includes** (`include "registries/aaosa.hocon"`) — networks compose from shared building blocks
- **LLM config separation** (`include "config/llm_config.hocon"`) — model selection is a single-file change affecting all agents

Example of how a UC1 agent would look in HOCON:
```hocon
include "registries/aaosa.hocon"
include "config/llm_config.hocon"

"tools": [
  {
    "name": "UC1SalesToServiceAgent",
    "function": {
      "description": "Handles Sales-to-Service onboarding for a customer when a SOW is signed.",
      "parameters": { ... }
    },
    "instructions": """
      You are the UC1 Sales-to-Service Agent. When triggered, call your down-chain agents
      to load customer context, query the wiki, populate the persona template, and contribute
      the result back to the wiki.
    """ ${aaosa_instructions},
    "tools": ["ContextBootstrapTool", "WikiQueryTool", "ArtifactResolutionTool",
              "GapDetectionTool", "WikiContributeTool"]
  },
  {
    "name": "WikiQueryTool",
    "function": ${aaosa_call}{
      "description": "Queries the LLMWiki Business Knowledge API for domain-scoped answers."
    },
    "class": "llmwiki_tools.WikiQueryCodedTool"
  },
  ...
]
```

### 1.4 Coded Tools — The Integration Point

`coded_tools/` contains Python classes that implement the `CodedTool` interface. This is how Neuro SAN connects to external APIs. For LLMWiki, each skill (SK-01 to SK-09) would become a coded tool:

```python
# coded_tools/llmwiki_tools/wiki_query_tool.py
class WikiQueryCodedTool(CodedTool):
    def invoke(self, args: dict, sly_data: dict) -> str:
        response = requests.post(
            f"{LLMWIKI_API_URL}/wiki/ask",
            json={
                "question": args["inquiry"],
                "domain": args.get("domain"),
                "customer_id": sly_data.get("customer_id"),   # ← Sly Data: not exposed to LLM
            },
            headers={"Authorization": f"Bearer {LLMWIKI_API_KEY}"}
        )
        return response.json()["answer"]
```

**Sly Data** is a key security feature: sensitive fields (`customer_id`, `api_key`, session tokens) are passed to coded tools via a separate channel that is never exposed to the LLM's context window. This directly addresses the prompt injection risk documented in `llmwiki-security.md`.

### 1.5 Deployment Model

Neuro SAN ships with a production-ready **Docker container**:

```
deploy/Dockerfile  →  python:3.13-slim
  EXPOSE 8080
  ENV AGENT_MANIFEST_FILE  → which agent networks to serve
  ENV AGENT_TOOL_PATH      → where coded_tools/ classes live
  ENV AWS_ACCESS_KEY_ID    → Bedrock credentials
  ENV AGENT_MCP_ENABLE=true → exposes /mcp endpoint for AgentCore
  ENV LANGFUSE_ENABLED     → optional observability
```

The container runs the Neuro SAN server and exposes:
- `POST /api/v1/{agent_name}/streaming_chat` — REST API (for direct callers)
- `http://host:port/mcp` — MCP endpoint (for AgentCore to discover and call tools)

This means Neuro SAN can run as an **ECS Fargate task** in AWS — the same infrastructure model LLMWiki already uses for its skill Lambdas and wiki-agent-runtime containers.

### 1.6 Bedrock Support

Neuro SAN supports AWS Bedrock natively in `config/llm_config.hocon`:

```hocon
"llm_config": {
    "model_name": "us.anthropic.claude-sonnet-4-6-v1:0",
    "provider": "bedrock",
    "region": "us-east-1"
}
```

LLM provider is a single-file, hot-reloadable config — the same Claude model LLMWiki already uses runs inside Neuro SAN agents without code changes.

### 1.7 MCP Exposure (Key for AgentCore Integration)

With `AGENT_MCP_ENABLE=true`, the Neuro SAN server exposes every registered agent as an MCP tool at `/mcp`. AWS AgentCore can connect to this endpoint and invoke any UC agent as a registered MCP tool — exactly how LLMWiki's MCP tools (`wiki_ask`, `wiki_contribute`, etc.) are already designed to work.

---

## 2. How to Run LLMWiki Using Neuro SAN

### 2.1 Architecture Mapping — What Replaces What

| LLMWiki (current AgentCore design) | Neuro SAN equivalent |
|---|---|
| UC1–UC10 agents defined in AgentCore console | UC1–UC10 HOCON files in `registries/` |
| Skill Registry (DynamoDB + Parameter Store) | `registries/manifest.hocon` |
| SK-01 ContextBootstrapSkill (Lambda) | `coded_tools/llmwiki/context_bootstrap_tool.py` |
| SK-02 WikiQuerySkill (MCP tool wrapper) | `coded_tools/llmwiki/wiki_query_tool.py` |
| SK-03 WikiContributeSkill (Lambda) | `coded_tools/llmwiki/wiki_contribute_tool.py` |
| SK-04 ArtifactResolutionSkill (AgentCore sub-agent) | HOCON sub-agent with `wiki_get_artifact` coded tool |
| SK-05 GapDetectionSkill (Lambda) | `coded_tools/llmwiki/gap_detection_tool.py` |
| SK-06 GateValidationSkill (Lambda) | `coded_tools/llmwiki/gate_validation_tool.py` |
| Wiki Orchestrator (supervisor agent) | AAOSA FrontMan agent in `llmwiki_orchestrator.hocon` |
| AgentCore Memory Store | Neuro SAN session context (in-process per session) |
| IAM SigV4 agent identity | Sly Data + `AGENT_AUTHORIZER` (OpenFGA) |
| AgentCore MCP Tool Registry | Neuro SAN `/mcp` endpoint + `manifest.hocon` |
| Langfuse / CloudWatch | `LANGFUSE_ENABLED=true` + CloudWatch (ECS logs) |

### 2.2 Step-by-Step: How to Wire It Up

#### Step 1 — Create LLMWiki coded tools

Create `coded_tools/llmwiki/` with one Python class per skill:

```
coded_tools/
  llmwiki/
    __init__.py
    wiki_query_tool.py          ← SK-02: calls POST /wiki/ask
    wiki_contribute_tool.py     ← SK-03: calls POST /wiki/contribute
    context_bootstrap_tool.py   ← SK-01: calls GET /wiki/customer + GET /wiki/playbook
    artifact_resolution_tool.py ← SK-04: calls GET /wiki/artifact/{type}
    gap_detection_tool.py       ← SK-05: calls GET /wiki/gaps + writes DynamoDB
    gate_validation_tool.py     ← SK-06: checks DynamoDB evidence table
```

Each tool calls the existing LLMWiki Business Knowledge API — no changes to the Lambda or API Gateway layer.

#### Step 2 — Create UC agent HOCON files

```
registries/
  llmwiki/
    manifest.hocon              ← registers all UC agent networks
    uc1_sales_to_service.hocon  ← UC1 agent + AAOSA wiring
    uc2_provisioning.hocon      ← UC2 agent + SK-01/02/03/04/05/06/09
    uc3_iam_onboarding.hocon
    uc4_business_config.hocon
    uc5_data_migration.hocon
    uc6_sit_testing.hocon
    uc7_e2e_testing.hocon
    uc8_cutover_planning.hocon
    uc9_pto_handover.hocon
    uc10_hypercare.hocon
    llmwiki_orchestrator.hocon  ← top-level router for all 10 UCs
```

Each HOCON file defines the agent's instructions, its down-chain sub-agents, and the coded tools it can call.

#### Step 3 — Configure LLM to use Bedrock

```hocon
# config/llm_config.hocon
{
    "llm_config": {
        "model_name": "us.anthropic.claude-sonnet-4-6-v1:0",
        "provider": "bedrock",
        "region": "us-east-1"
    }
}
```

#### Step 4 — Build and deploy the container to ECS

```bash
# Build
docker build -f deploy/Dockerfile -t llmwiki-neuro-san:1.0 .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin 392568849512.dkr.ecr.us-east-1.amazonaws.com
docker tag llmwiki-neuro-san:1.0 392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-neuro-san:1.0
docker push 392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-neuro-san:1.0
```

ECS Task Definition environment variables:
```json
{
  "environment": [
    { "name": "AGENT_MANIFEST_FILE", "value": "/app/registries/llmwiki/manifest.hocon" },
    { "name": "AGENT_TOOL_PATH",     "value": "/app/coded_tools" },
    { "name": "AGENT_MCP_ENABLE",    "value": "true" },
    { "name": "LLMWIKI_API_URL",     "value": "https://<api-gateway-id>.execute-api.us-east-1.amazonaws.com/prod" },
    { "name": "LANGFUSE_ENABLED",    "value": "true" }
  ],
  "secrets": [
    { "name": "LLMWIKI_API_KEY",       "valueFrom": "arn:aws:secretsmanager:us-east-1:392568849512:secret:llmwiki-api-key" },
    { "name": "AWS_ACCESS_KEY_ID",     "valueFrom": "..." },
    { "name": "AWS_SECRET_ACCESS_KEY", "valueFrom": "..." }
  ]
}
```

#### Step 5 — Register Neuro SAN as MCP server in AgentCore

Once the ECS task is running:

```bash
# Register the Neuro SAN /mcp endpoint in AgentCore
aws bedrock-agent create-agent-action-group \
  --agent-id <agentcore-agent-id> \
  --action-group-name "LLMWikiNeuroSAN" \
  --action-group-executor '{
      "customControl": "RETURN_CONTROL"
  }' \
  --api-schema '{
      "payload": { "openapi": "3.0.0", ... }
  }'
```

Or simpler: register the Neuro SAN server as an **MCP server** in AgentCore's MCP tool registry, pointing to `http://<ecs-service-url>:8080/mcp`. AgentCore will discover all registered agent networks (UC1–UC10) as callable MCP tools automatically.

### 2.3 The UC1 Flow End-to-End with Neuro SAN

```
1. SOW uploaded → EventBridge fires → AgentCore triggered
        │
        ▼ AgentCore calls Neuro SAN MCP tool: "uc1_sales_to_service"
2. Neuro SAN server receives request
        │
        ▼ AAOSA FrontMan: UC1SalesToServiceAgent
3. FrontMan sends Determine to: ContextBootstrapTool, WikiQueryTool,
   ArtifactResolutionTool, GapDetectionTool, WikiContributeTool
        │
        ▼ Each tool returns { Relevant: Yes, Strength: 9, Claim: Partial }
4. FrontMan sends Fulfill to relevant tools in sequence:
   a. ContextBootstrapTool.invoke() → calls GET /wiki/customer/bcbs-mn-001
   b. WikiQueryTool.invoke()        → calls POST /wiki/ask (domain: customer-onboarding)
   c. ArtifactResolutionTool        → calls GET /wiki/artifact/persona-template
   d. GapDetectionTool              → if confidence=low, escalates via SNS
   e. WikiContributeTool.invoke()   → calls POST /wiki/contribute (customers/)
        │
        ▼ FrontMan compiles all tool responses
5. Returns structured answer to AgentCore
        │
        ▼ UC2 agent triggered next → same pattern, reads UC1 wiki output
```

---

## 3. Deploying Neuro SAN in AWS AgentCore — Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                     AWS Account 392568849512 (us-east-1)             │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  AWS AgentCore (supervisor layer)                             │   │
│  │  ┌──────────────────────────────────────────────────────────┐ │   │
│  │  │  Wiki Orchestrator Agent                                 │ │   │
│  │  │  Routes to UC1–UC10 based on EventBridge trigger         │ │   │
│  │  └──────────────────────┬───────────────────────────────────┘ │   │
│  │                         │ MCP tool call                        │   │
│  └─────────────────────────┼─────────────────────────────────────┘   │
│                            │                                          │
│  ┌─────────────────────────▼─────────────────────────────────────┐   │
│  │  ECS Fargate — llmwiki-neuro-san container                    │   │
│  │  Private subnet · no public IP                                │   │
│  │                                                               │   │
│  │  Neuro SAN Server :8080                                       │   │
│  │  ├── /mcp              ← AgentCore calls here                │   │
│  │  ├── /api/v1/uc1_s2s   ← direct REST (testing)              │   │
│  │  └── /api/v1/llmwiki_orchestrator                            │   │
│  │                                                               │   │
│  │  AAOSA agent networks:                                        │   │
│  │  uc1_sales_to_service.hocon   → coded_tools/llmwiki/         │   │
│  │  uc2_provisioning.hocon        → coded_tools/llmwiki/         │   │
│  │  ... (UC3–UC10)                                               │   │
│  │  llmwiki_orchestrator.hocon   → routes to UC1–UC10           │   │
│  └───────────────────────────────┬───────────────────────────────┘   │
│                                  │ coded_tools call                   │
│  ┌───────────────────────────────▼───────────────────────────────┐   │
│  │  LLMWiki Business Knowledge API (API Gateway)                 │   │
│  │  POST /wiki/ask  ·  GET /wiki/customer/{id}                   │   │
│  │  GET /wiki/playbook/{uc}  ·  POST /wiki/contribute            │   │
│  └───────────────────────────────┬───────────────────────────────┘   │
│                                  │                                    │
│  ┌───────────────────────────────▼───────────────────────────────┐   │
│  │  LLMWiki Knowledge Fabric                                     │   │
│  │  S3 wiki/  ·  DynamoDB  ·  Bedrock KB  ·  S3 Vectors          │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Neuro AI Trust — Governance Layer

The [Cognizant Neuro AI Trust platform](https://www.cognizant.com/us/en/services/cognizant-platforms/neuro-ai-trust) is the enterprise governance and observability layer that sits above the agent runtime. It is separate from Neuro SAN Studio but designed to work with it.

### 4.1 What Neuro AI Trust Provides

| Capability | What It Does | LLMWiki Application |
|---|---|---|
| **AI Model Monitoring** | Tracks model behavior drift, hallucination rates, output quality over time | Monitor SK-02 WikiQuerySkill confidence scores trending down — early warning that the KB needs reingestion |
| **Bias & Fairness Auditing** | Detects systematic patterns in model decisions | Ensure UC1 agent doesn't generate customer personas with systematically different risk flags by customer type |
| **Explainability** | Traces which source documents drove a given answer | Every SK-02 answer is traceable to specific wiki pages — satisfies AI Handbook evidence requirements |
| **Risk & Compliance Dashboard** | Centralized view of AI risk posture, gate compliance, policy violations | Maps directly to AI Handbook Decision Gates G0–G6; shows which gates are satisfied, which are pending human review |
| **Data Lineage** | Tracks data provenance from source to model output | Every wiki page contribution records `contributing_agent` + source provenance — Neuro AI Trust surfaces this lineage visually |
| **Policy Enforcement** | Defines and enforces acceptable use policies at the agent level | Enforces "agents cannot write to decisions/ without HITL approval" as a platform-level policy, not just a code check |

### 4.2 Integration Pattern with LLMWiki

```
Neuro AI Trust monitors:
  ├── Neuro SAN agent invocation telemetry (via Langfuse SDK or OpenTelemetry)
  ├── LLMWiki Bedrock model invocation logs (CloudTrail → Trust platform)
  ├── Wiki contribution audit trail (DynamoDB llmwiki-log → Trust dashboard)
  └── Decision gate evidence status (DynamoDB harness_runs → compliance view)

What it surfaces:
  ┌─────────────────────────────────────────────────────────────┐
  │  Neuro AI Trust Dashboard                                   │
  │                                                             │
  │  Active agents: 3 of 10 UC agents running                  │
  │  Gate G2 (UC2): 2 evidence items missing — BLOCKING        │
  │  SK-02 confidence avg (last 7d): 0.71 → trending down      │
  │  Contributions pending HITL review: 4                       │
  │  Poison detection alerts: 0                                 │
  │  Model: claude-sonnet-4-6 · No drift detected              │
  └─────────────────────────────────────────────────────────────┘
```

---

## 5. Pros and Cons

### 5.1 Pros — Why Use Neuro SAN for LLMWiki Agent Fleet

| # | Benefit | Detail |
|---|---|---|
| **1** | **Declarative agent design** | UC1–UC10 agents are HOCON files, not Python code. Non-engineers (delivery leads, domain experts) can read and modify agent behavior without touching Lambda code. AgentCore agents require console configuration or SDK code. |
| **2** | **AAOSA self-organizing delegation** | Agents decide their own relevance dynamically. Adding a new skill (SK-10) to a UC agent requires only adding a tool reference in the HOCON file — no code change, no redeploy of existing skills. |
| **3** | **MCP native** | Neuro SAN exposes `/mcp` out of the box. AgentCore, Claude Desktop, any MCP-compatible client can invoke any UC agent as a tool. Zero custom plumbing required. |
| **4** | **Sly Data for security** | Customer IDs, API keys, and sensitive context pass via Sly Data — never in the LLM context window. Directly mitigates the prompt injection / data exfiltration risks in `llmwiki-security.md §3`. |
| **5** | **Docker-native, cloud-agnostic** | One container runs on ECS Fargate, local dev, or any Kubernetes cluster. The current AgentCore agent fleet has no local dev equivalent — testing requires deploying to AWS. |
| **6** | **Built-in observability** | Langfuse integration ships with the container (`LANGFUSE_ENABLED=true`). Every agent call, tool invocation, and token count is traced without custom CloudWatch metric code. |
| **7** | **Multi-LLM fallback** | `music_nerd_llm_fallbacks.hocon` demonstrates failover between LLM providers. If Bedrock Claude throttles during a UC8 cutover, Neuro SAN can fall back to a secondary model — AgentCore has no equivalent built-in failover. |
| **8** | **Agent Network Designer** | The `agent_network_designer.hocon` meta-agent generates new agent network HOCON files from a natural language description. Can auto-generate new UC agent networks for future use cases (beyond UC10). |
| **9** | **Authorization via OpenFGA** | `AGENT_AUTHORIZER=OpenFgaAuthorizer` provides attribute-based access control on which agents each user/caller can invoke — a production-grade alternative to API Gateway usage plan keys. |
| **10** | **Cognizant-native** | Neuro SAN is Cognizant's own framework. LLMWiki is a Cognizant project. Alignment with the Neuro AI Trust governance platform (Section 4) is a natural fit. Internal support path is stronger. |

### 5.2 Cons — Why Not to (or Not Yet)

| # | Risk / Limitation | Detail |
|---|---|---|
| **1** | **Adds a runtime layer** | The stack becomes: AgentCore → Neuro SAN ECS → LLMWiki API Gateway → Lambda. Each hop adds latency (~50–200ms). For UC1 (non-time-critical) this is fine; for UC8 cutover (real-time decision-making), it may matter. |
| **2** | **AAOSA Determine → Fulfill adds LLM calls** | The AAOSA protocol makes two LLM calls per agent: one Determine round and one Fulfill round. The current skill invocation pattern makes one direct Lambda call. For a UC1 flow with 5 skills, Neuro SAN makes ~10 LLM calls vs ~5 in the current design. Higher token cost. |
| **3** | **Not AWS-native** | Neuro SAN is not a managed AWS service. It has no native integration with EventBridge, Step Functions, or SQS. Triggering a UC agent from an S3 event (SOW upload) requires custom glue (Lambda → HTTP call to Neuro SAN). |
| **4** | **Stateless by default** | Neuro SAN session context is in-process and ephemeral. The current AgentCore design uses DynamoDB `harness_runs` for durable execution state and cross-session audit trails. Neuro SAN would need S3 Reservations Storage (`AGENT_EXTERNAL_RESERVATIONS_STORAGE`) for multi-pod durability. |
| **5** | **HITL workflow is custom** | The wiki/pending/ HITL gate (SK-03 stages decisions/ and evidence/ for human review) is a LLMWiki custom mechanism. Neuro SAN has no built-in human approval workflow — this still requires the existing SNS → Streamlit approval pipeline alongside Neuro SAN. |
| **6** | **Learning curve for HOCON** | The team currently works in Python (Lambda) and HCL (Terraform). HOCON is a new config language. The AAOSA protocol (Determine/Fulfill/Follow-up modes) has a learning curve before agents are tuned well. |
| **7** | **AgentCore Memory Store not available** | AgentCore's native Memory Store (used for cross-session context) is not available in Neuro SAN. Session memory resets on container restart unless `AGENT_EXTERNAL_RESERVATIONS_STORAGE` is configured. |
| **8** | **Container always-on cost** | Neuro SAN runs as a long-running ECS Fargate service (unlike Lambda which scales to zero). For a low-frequency UC agent fleet (a few SOWs per week), an always-on container costs more than per-invocation Lambda calls. Minimum ~$30–50/month per container even at idle. |
| **9** | **Open source maturity** | Neuro SAN is active and growing (PyPI downloads growing, GitHub active), but it is not a GA AWS managed service. API changes between versions require testing before upgrading. The LLMWiki team would own the container update cadence. |
| **10** | **No AgentCore gate-validation parity** | SK-06 DecisionGateValidationSkill's tight integration with DynamoDB evidence tables is LLMWiki-specific. Neuro SAN coded tools can call DynamoDB, but there is no framework-level concept of "gate" or "blocking" — this logic stays custom. |

---

## 6. Recommended Approach — Hybrid Architecture

Rather than a full replacement, the recommended approach is **Neuro SAN for agent definition and orchestration, AgentCore for hosting and governance**:

```
Phase 2 (current target):  Pure AgentCore agents + Lambda skills
  → Ship UC1 POC with current design. No Neuro SAN yet.

Phase 3 (S2S Agent):       Introduce Neuro SAN as the UC1 agent definition layer
  → UC1 agent = HOCON file running in ECS Fargate
  → AgentCore invokes Neuro SAN via MCP
  → Existing LLMWiki Business API (API Gateway + Lambda) unchanged
  → If Neuro SAN AAOSA adds too much latency → fall back to direct Lambda

Phase 4 (Agent Fleet):     All UC agents as Neuro SAN HOCON files
  → One ECS service hosts all 10 UC agents
  → Agent Network Designer generates HOCON for new use cases
  → Neuro AI Trust monitors all agent telemetry via Langfuse

Phase 5 (Production):      Add OpenFGA authorization + Langfuse + S3 Reservations
  → Full enterprise governance via Neuro AI Trust
  → AgentCore remains as the event-driven trigger and supervisor layer
  → Neuro SAN handles agent logic and MCP tool exposure
```

### Decision criteria for "go Neuro SAN now" vs "stay pure AgentCore":

| Question | If Yes → Neuro SAN | If No → Stay AgentCore |
|---|---|---|
| Will non-engineers define or modify agent behavior? | ✅ HOCON is more accessible than Lambda Python | ✅ Pure Lambda + prompt engineering |
| Are there >5 UC agents to build in the next 6 weeks? | ✅ AAOSA reduces per-agent boilerplate | ✅ Current skill registry is sufficient |
| Is Langfuse / Neuro AI Trust in scope for governance? | ✅ Neuro SAN ships with Langfuse built-in | ✅ CloudWatch is sufficient |
| Is sub-200ms latency required for any agent? | ❌ Neuro SAN adds hops | ✅ Lambda is lower latency |
| Is cost a constraint (< $50/month budget)? | ❌ Always-on ECS is more expensive | ✅ Lambda scales to zero |

---

## 7. Quick-Start: Run LLMWiki UC1 Locally with Neuro SAN

```bash
# 1. Install
pip install neuro-san-studio

# 2. Scaffold in LLMWiki project root
cd /path/to/LLMWiki
ns init --providers anthropic  # or bedrock

# 3. Set credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export LLMWIKI_API_URL=https://<api-gw-id>.execute-api.us-east-1.amazonaws.com/prod
export LLMWIKI_API_KEY=...

# 4. Create coded_tools/llmwiki/wiki_query_tool.py (see Section 2.2 Step 1)

# 5. Create registries/llmwiki/uc1_sales_to_service.hocon (see Section 2.2 Step 2)

# 6. Run
ns run

# 7. Open http://localhost:4173 — select "uc1_sales_to_service" agent network
#    Send: "Onboard customer BCBS-MN-001 using the Sales-to-Service playbook"
```

---

*End of neuro-ai-agentic.md v1.0*

*Related documents: `AgenticDesign.md` (LLMWiki agentic architecture), `LLMWikiDesign.md` (AWS architecture), `llmwiki-security.md` (threat model), `LLMWikiDesignMVP.md` (phase plan)*

*Neuro SAN Studio source: `/mnt/c/Users/859600/OneDrive - Cognizant/projects/neuro-san-studio/`*
*Neuro AI Trust platform: https://www.cognizant.com/us/en/services/cognizant-platforms/neuro-ai-trust*
