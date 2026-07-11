# Neuro SAN on ECS — Full Demo Plan
## "Edit NLP skills live, deploy instantly, watch agents negotiate autonomously"

**Date:** 2026-07-10  
**Account:** 392568849512 (Sandbox-01, profile `tzg-sandbox`)

---

## What We're Building

A business-demo environment where:
1. A presenter edits a HOCON NLP instruction block in a browser (no code, no IDE)
2. Presses save → the Neuro SAN server hot-reloads within 5 seconds (zero restart)
3. Business user types "Run UC1 for bcbs-mn-001" in the nsflow chat
4. They watch agents autonomously negotiate all AAOSA rounds — Determine, Fulfill, Follow-up, Compile
5. When a human decision is needed (decisions/evidence page type, or blocking gap), nsflow pauses and the user types back
6. The completed handoff brief appears in the LLMWiki Streamlit UI immediately after

---

## Architecture — Two New ECS Services

```
Internet
  │
  ▼
ALB (existing: llmwiki-alb)
  │
  ├── /           → Streamlit (existing, port 8501)   ← LLMWiki business UI
  ├── /agents/*   → nsflow     (new, port 4173)        ← Neuro SAN chat UI
  └── /api/*      → neuro-san  (new, port 8080)        ← Agent server HTTP API
        │
        └── calls same Lambda skills (SK-01 to SK-05)
              same S3 wiki bucket, same DynamoDB, same Bedrock KB
```

### Container 1 — neuro-san-server
- **Image:** Built from `deploy/Dockerfile` (already exists in neuro-san-studio repo)
- **Port:** 8080 (HTTP API + WebSocket for agent chat)
- **Entry:** `deploy/entrypoint.sh` → runs `neuro_san_server_wrapper.py`
- **Key env vars:**
  ```
  AGENT_MANIFEST_FILE       = s3://llmwiki-<id>/neuro-san/registries/manifest.hocon
  AGENT_TOOL_PATH           = /app/coded_tools            ← our SK-01..SK-05 tools
  AGENT_MANIFEST_UPDATE_PERIOD_SECONDS = 5               ← HOT RELOAD
  AWS_DEFAULT_REGION        = us-east-1
  AWS_ACCESS_KEY_ID / SECRET / TOKEN  (via ECS task role, not hardcoded)
  DEFAULT_SLY_DATA          = {"llmwiki_api_key": "...", "engagement_id": "live"}
  LANGFUSE_ENABLED          = true   (optional — full AAOSA trace observability)
  ```
- **CPU/Memory:** 1 vCPU / 2 GB (Fargate) — Claude calls are async, not CPU-bound

### Container 2 — nsflow
- **Image:** `pip install nsflow==0.6.15` → `uvicorn nsflow.backend.main:app --host 0.0.0.0 --port 4173`
- **Port:** 4173 (FastAPI backend + serves React SPA static files)
- **Key env vars:**
  ```
  NEURO_SAN_SERVER_HOST       = localhost (same task) OR internal ALB DNS
  NEURO_SAN_SERVER_HTTP_PORT  = 8080
  NEURO_SAN_SERVER_CONNECTION = http
  VITE_API_PROTOCOL           = http
  VITE_WS_PROTOCOL            = ws
  ```
- **Deployment option A:** Same ECS task as neuro-san-server (sidecar, share localhost)
- **Deployment option B:** Separate ECS service (simpler ALB routing, better scaling)
- **Recommendation: Option A (sidecar)** — nsflow and server must share WebSocket on same host for the live graph animation to work correctly

---

## The Three Key Capabilities

### 1. Hot-reload NLP editing

**How it works:**  
`AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=5` makes the server re-read HOCON files every 5 seconds.  
The presenter edits the NLP instruction text in the LLMWiki Streamlit "HOCON Editor" tab → 
saves to S3 → a sync sidecar (or Lambda trigger) writes the file to the ECS task's `/app/registries/` → 
server picks it up within 5 seconds.

**Implementation options (simplest first):**
- **Option A — S3 + EFS mount:** Store HOCON files in EFS. Streamlit writes to EFS. Server reads from EFS. No sync needed. Most reliable for demo.
- **Option B — S3 + Init container:** On each task start, sync from S3. Combined with `AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=0` (static) — requires restart to see changes.
- **Option C — S3 sync loop:** Sidecar container runs `aws s3 sync s3://llmwiki/neuro-san/registries/ /app/registries/ --watch` every 3 seconds.

**Recommendation: Option C (S3 sync sidecar)** — simplest, no EFS cost, works with existing S3.

### 2. Autonomous AAOSA negotiation

**How it works:**  
nsflow chat → HTTP POST to neuro-san server `/chat` or `/function_call` → 
FrontMan LLM reads HOCON instructions → calls Determine round on each sub-agent →
sub-agents invoke coded tools (our SK-01..SK-05 Lambda wrappers) → 
results flow back through Follow-up and Compile rounds →
nsflow displays each AAOSA round as it streams in via WebSocket.

**What the business user sees:**
- Left panel: live agent network graph with animated edges as each Determine/Fulfill fires
- Right panel: streaming chat — each agent's message appears as it completes
- Bottom bar: per-agent latency, token count, confidence score per round

**No code changes to our Lambda skills.** They are already the coded tools. The HOCON FrontMan orchestrates them.

### 3. Human-in-the-Loop (HITL)

**How HITL works in Neuro SAN:**  
HITL is not a separate protocol — it is the **AAOSA conversation itself**.  
When `WikiContributeTool` detects `page_type=decisions` or `page_type=evidence`, 
it returns a structured response: `{"human_review_required": true, "human_prompt": "..."}`.  
The FrontMan LLM sees this, wraps the question in a Follow-up message, and 
**waits for the user's next chat message** before proceeding to Compile.

The user sees nsflow chat pause with the agent's question. They type their answer.
The FrontMan continues. This is identical behavior to the Hard Harness Phase 3 pause,
but driven entirely by the LLM reading the NLP instructions — not hardcoded Python phases.

**Additional HITL patterns:**
- Blocking gap from SK-05 → FrontMan asks user to provide missing information
- Low-confidence answer from SK-02 → FrontMan asks user to confirm or correct
- Artifact with missing fields from SK-04 → FrontMan asks user to fill in blanks

---

## What Needs to Be Built

### Phase 1 — Neuro SAN Server on ECS (2-3 days)

**1a. ECR repository for neuro-san-server**
```hcl
resource "aws_ecr_repository" "neuro_san" {
  name = "llmwiki-neuro-san"
}
```

**1b. Docker image: `code/neuro_san/Dockerfile`**
```dockerfile
# Based on deploy/Dockerfile from neuro-san-studio
FROM python:3.12-slim

WORKDIR /app

# Install neuro-san + nsflow (both Python packages, no Node/npm needed)
COPY requirements.txt .
RUN pip install neuro-san==0.6.54 neuro-san-studio==0.6.54 nsflow==0.6.15 boto3>=1.34

# Copy LLMWiki coded tools (SK-01 to SK-05)
COPY neuro_san/coded_tools/ coded_tools/
COPY lambda/common/ lambda_common/
ENV PYTHONPATH=/app/lambda_common:/app

# Copy HOCON registries and LLM config
COPY registries/ registries/
COPY config/llm_config.hocon config/llm_config.hocon

# Copy S3 sync sidecar script
COPY neuro_san/sync_registries.sh sync_registries.sh

# Expose neuro-san HTTP port and nsflow port
EXPOSE 8080 4173

COPY neuro_san/start.sh start.sh
ENTRYPOINT ["/bin/bash", "start.sh"]
```

**1c. `start.sh` — starts 3 processes in one container**
```bash
#!/bin/bash
# Sync registries from S3 every 3s (hot-reload source)
/bin/bash sync_registries.sh &

# Start neuro-san server (port 8080)
python -m neuro_san_studio.runner.neuro_san_server_wrapper --http_port 8080 &
sleep 5  # wait for server to be ready

# Start nsflow UI (port 4173)
python -m uvicorn nsflow.backend.main:app --host 0.0.0.0 --port 4173

wait
```

**1d. `sync_registries.sh` — S3 hot-reload**
```bash
#!/bin/bash
while true; do
  aws s3 sync s3://${WIKI_BUCKET}/neuro-san/registries/ /app/registries/ --quiet
  sleep 3
done
```

**1e. Terraform — ECS task + ALB listener rules**
- New task definition: `llmwiki-neuro-san` (1 vCPU, 2 GB)
- New target groups: port 8080 (health: `GET /health`) and port 4173 (health: `GET /`)
- ALB listener rules:
  - `path /agents/*` → nsflow target group (port 4173)
  - `path /api/agents/*` → neuro-san target group (port 8080)
- IAM task role: same as Streamlit (already has Lambda invoke + S3 + DynamoDB access)

**1f. `config/llm_config.hocon` — point to Bedrock**
```hocon
{
  "llm_config": {
    "class": "bedrock",
    "model_name": "us.anthropic.claude-sonnet-4-6-v1:0"
  }
}
```

### Phase 2 — LLMWiki Streamlit HOCON Editor tab (1 day)

Add a new page `pages/neuro_san.py` with three tabs:

**Tab 1 — HOCON Editor**
- Dropdown: select which agent (UC1 FrontMan, ContextBootstrap, WikiQuery, etc.)
- Text area: editable NLP instruction block (pre-loaded from S3)
- "Save & Deploy" button → writes back to `s3://llmwiki/neuro-san/registries/`
- Status: "Server will reload in ~5 seconds"

**Tab 2 — nsflow Embed**
- iframe pointing to `http://ALB-DNS/agents/` (the nsflow React UI)
- Pre-fill chat input with suggested prompts: "Run UC1 for bcbs-mn-001"

**Tab 3 — Compare: Harness vs Neuro**
- Side-by-side: Hard Harness 8 phases (fixed Python) vs Neuro SAN AAOSA (LLM-driven)
- Show how the same 5 Lambdas are called both ways

### Phase 3 — `registries/llmwiki/uc1_sales_to_service.hocon` refinement (1 day)

The HOCON already exists. Needs:
- HITL instruction in the FrontMan: "When WikiContribute returns human_review_required=true, ask the user the human_prompt before proceeding"
- Blocking gap instruction: "When GapDetection returns blocking=true, stop and ask the user to provide the missing information"
- Sly data wiring: `DEFAULT_SLY_DATA` includes `customer_id` for the demo scenario

---

## Environment Variables Summary

| Var | Value | Purpose |
|-----|-------|---------|
| `AGENT_MANIFEST_FILE` | `s3://llmwiki-xxx/neuro-san/registries/manifest.hocon` | Which agents to serve |
| `AGENT_TOOL_PATH` | `/app/coded_tools` | Where SK-01..SK-05 Python tools live |
| `AGENT_MANIFEST_UPDATE_PERIOD_SECONDS` | `5` | Hot-reload interval |
| `DEFAULT_SLY_DATA` | `{"llmwiki_api_key":"","engagement_id":"demo"}` | Pre-loaded sly data |
| `AWS_DEFAULT_REGION` | `us-east-1` | For boto3 calls to Lambda |
| `LANGFUSE_ENABLED` | `true` (optional) | Full AAOSA observability |
| `NEURO_SAN_SERVER_HOST` | `localhost` | nsflow → server (sidecar) |
| `NEURO_SAN_SERVER_HTTP_PORT` | `8080` | nsflow → server port |

---

## Demo Script (Business Audience, ~10 minutes)

**Setup:** Open two browser tabs — LLMWiki Streamlit and nsflow (via ALB)

**Part 1 — Live NLP edit (3 min)**
1. Open AI Skill Studio → HOCON Editor → select "WikiQuery"
2. Change one sentence: "Return confidence: HIGH if ≥2 sources" → "HIGH if ≥3 sources"
3. Click "Save & Deploy"
4. Wait 5 seconds. Point: "No code commit. No Lambda redeploy. No CI/CD pipeline."
5. "A business analyst just changed the confidence threshold — by themselves."

**Part 2 — Autonomous AAOSA (5 min)**
1. Switch to nsflow tab
2. Type: "Run UC1 for bcbs-mn-001 — produce a sales-to-service handoff brief"
3. Watch the agent network graph animate: each AAOSA round fires in sequence
4. Point to each round as it completes:
   - "R1: ContextBootstrap — loaded 6 pages about this customer"
   - "R2: WikiQuery — confidence HIGH (3 sources, matching our new rule)"
   - "R3: GapDetection — 2 gaps found, 1 blocking"
5. The chat pauses — agent asks: "The SLA document is missing. Can you provide it?"
6. Type: "Use 30-day standard SLA as default"
7. Agent continues to Compile → saves draft to wiki

**Part 3 — Before vs After (2 min)**
1. Switch back to Streamlit → AI Skill Studio → Before vs After tab
2. Point to the metrics: "425 lines of Python business logic → 5 NLP instruction blocks"
3. "The same 5 Lambda skills. Same AWS. But now a BA owns the workflow."

---

## What This Is NOT

- **Not a replacement for the Hard Harness** — the Hard Harness demos the *production system* running today. Neuro SAN demos the *next-generation architecture* for how the same outcome is achieved with LLM-driven orchestration.
- **Not requiring Neuro SAN to be production-stable** — this is a POC demo environment. The Hard Harness stays live for all real customer work. The Neuro SAN ECS task can be stopped between demo sessions to save cost (~$0.04/hour when running).

---

## Cost Estimate (ECS Fargate, on-demand)

| Component | Size | Cost/hour | Notes |
|-----------|------|-----------|-------|
| neuro-san + nsflow task | 1 vCPU / 2 GB | ~$0.06/hr | Stop between demos |
| ALB (additional rules) | — | ~$0.001/hr | Shared with existing ALB |
| S3 sync | — | negligible | ~100 S3 GET requests/hour |
| Bedrock (during demo) | ~20k tokens | ~$0.06/demo | Claude Sonnet 4.6 |
| **Total for 1 demo session** | | **~$0.12** | |

---

## Effort Estimate

| Task | Effort |
|------|--------|
| Dockerfile + start.sh + sync script | 0.5 day |
| Terraform: ECR + ECS task + ALB rules | 0.5 day |
| HOCON editor Streamlit page | 1 day |
| UC1 HOCON HITL refinement | 0.5 day |
| End-to-end test + demo rehearsal | 0.5 day |
| **Total** | **3 days** |

---

## ns CLI — What It Does

The `ns` CLI (entry point: `neuro_san_studio.commands.cli:main`) is the local development tool:

```bash
ns run                          # start server + nsflow locally
ns run --server-only            # server only (no nsflow UI)
ns run --client-only            # nsflow UI only (connect to existing server)
ns run --server-http-port 8080  # custom port
ns init                         # scaffold new project
ns check-llm-keys               # validate API keys (3 tiers: placeholder/format/live)
ns check-config                 # validate HOCON files
```

In ECS we don't use `ns run` directly — we call `neuro_san_server_wrapper.py` (server) and `uvicorn nsflow.backend.main:app` (UI) separately, matching what `ns run` does internally. This gives us better process isolation and health checks per container.

---

## Neuro AI Trust (Cognizant, July 2026)

Relevant context from the Cognizant Neuro AI Trust announcement:  
Cognizant is positioning Neuro SAN as enterprise-grade AI orchestration with real-time assurance — exactly what this demo shows. The HITL enforcement (hardcoded `_HITL_PAGE_TYPES` in Python, unreachable by LLM instructions), sly_data security channel, and Langfuse observability map directly to the "trust" pillars: safety, transparency, and human control.

The LLMWiki demo is a concrete implementation of Neuro AI Trust for the TriZetto healthcare domain.

---

## Next Steps

1. Confirm approach: sidecar (both processes in one task) vs separate services
2. Decide HITL UX: nsflow chat pause (native) vs Streamlit HITL panel (custom)
3. Build Phase 1 (server on ECS) — can demo basic AAOSA in ~3 days
4. Build Phase 2 (HOCON editor) — the "wow moment" for business audience
