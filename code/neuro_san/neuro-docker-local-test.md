# Neuro SAN — Local Docker Test Guide

How to build, run, and test the LLMWiki neuro-san sidecar image locally
without touching any ECS deployment.

---

## Overview

The local stack runs two processes inside one container:

| Process | Port (internal) | Port (host, test run) | What it does |
|---|---|---|---|
| `neuro-san-server` | 8080 | 18082 | HTTP + WebSocket API; executes AAOSA agent networks |
| `nsflow` FastAPI + React SPA | 4173 | 14175 | Chat UI; proxies to neuro-san-server |

Both start automatically via `start.sh`. The standard `docker compose` setup
binds them on `8080`/`4173`. The test run described here uses `18082`/`14175`
to avoid port conflicts with any already-running compose stack.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Desktop (or Docker Engine) | Must be running |
| AWS SSO profile `tzg-sandbox` (account 392568849512) | Needed for Bedrock calls |
| `~/.aws/` credentials directory | Mounted into container read-only |
| Active SSO session | Run `aws sso login --profile tzg-sandbox` before starting |

---

## 1. AWS SSO Login

```bash
aws sso login --profile tzg-sandbox
```

Verify it works:

```bash
aws sts get-caller-identity --profile tzg-sandbox
# Expected: account "392568849512"
```

---

## 2. Build the Image

From the repository root (`code/` directory):

```bash
cd /path/to/LLMWiki/code

docker build \
  -f neuro_san/Dockerfile \
  -t llmwiki-neuro-san:local \
  .
```

The Dockerfile:
- Installs pre-bundled wheels from `neuro_san/*.whl` (avoids proxy issues with pyhocon)
- Installs remaining deps from PyPI via `uv`
- Copies `coded_tools/`, `registries/`, `config/`, `start.sh`, `sync_registries.sh`
- Exposes ports 8080 and 4173

> **Note on image depth:** If the build fails with `max depth exceeded`, the base image
> has too many layers. Fix by flattening:
> ```bash
> docker export llmwiki-neuro-san:local | docker import - llmwiki-neuro-san:flat
> ```
> Then change the Dockerfile `FROM` line to `FROM llmwiki-neuro-san:flat`.

---

## 3. Run the Container

Use different host ports (`18082`, `14175`) to avoid collisions with the compose stack:

```bash
docker run -d \
  --name llmwiki-ns-test \
  -p 18082:8080 \
  -p 14175:4173 \
  -v ~/.aws:/root/.aws:ro \
  -e WIKI_BUCKET=llmwiki-278e7e22 \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e AWS_PROFILE=tzg-sandbox \
  -e AGENT_MANIFEST_FILE=registries/llmwiki/manifest.hocon \
  -e AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=5 \
  -e AGENT_TOOL_PATH=/app/coded_tools \
  llmwiki-neuro-san:local
```

Key environment variables:

| Variable | Value | Purpose |
|---|---|---|
| `WIKI_BUCKET` | `llmwiki-278e7e22` | S3 bucket for hot-reload HOCON sync |
| `AWS_PROFILE` | `tzg-sandbox` | AWS credentials profile for Bedrock + S3 |
| `AGENT_MANIFEST_FILE` | `registries/llmwiki/manifest.hocon` | Tells neuro-san which networks to load |
| `AGENT_MANIFEST_UPDATE_PERIOD_SECONDS` | `5` | Hot-reload poll interval (seconds) |
| `AGENT_TOOL_PATH` | `/app/coded_tools` | **Critical** — without this neuro-san can't find LLMWiki coded tools |

> **`AGENT_TOOL_PATH` is mandatory.** Without it neuro-san searches its own package
> directory and fails with:
> `No reasonable agent tool path found in PYTHONPATH for /usr/local/lib/python3.12/site-packages/neuro_san/coded_tools`

---

## 4. Verify the Container Started

```bash
# Container health
docker ps --filter name=llmwiki-ns-test

# Server health endpoint
curl http://localhost:18082/
# Expected: {"service": "neuro-san.Agent", "status": "ok", ...}

# List loaded agent networks
curl http://localhost:14175/api/v1/list
# Expected JSON listing all 4 networks
```

Example response from `/api/v1/list`:
```json
{
  "agents": [
    {"agent_name": "uc_test_hello", ...},
    {"agent_name": "uc_pm_problem_management", ...},
    {"agent_name": "uc1_sales_to_service", ...},
    {"agent_name": "uc_travel_booking", ...}
  ]
}
```

Watch startup logs to confirm all networks validate without errors:

```bash
docker logs llmwiki-ns-test --follow
```

Look for lines like:
```
ADDED network for agent uc_test_hello : ...
ADDED network for agent uc_travel_booking : ...
```

If you see `validation errors. Skipping.` for any network, see the
[Troubleshooting](#troubleshooting) section.

---

## 5. Loaded Agent Networks

The manifest at `code/registries/llmwiki/manifest.hocon` controls which
networks load:

```hocon
{
    "uc1_sales_to_service.hocon":     true,
    "uc_pm_problem_management.hocon": true,
    "uc_test_hello.hocon":            true,
    "uc_travel_booking.hocon":        true
}
```

| Network | Purpose | Requires Lambda? |
|---|---|---|
| `uc_test_hello` | Minimal connectivity test — no AWS calls | No (EchoTool stub) |
| `uc_travel_booking` | Travel booking demo — flight + hotel search + confirm | No (all stubs) |
| `uc1_sales_to_service` | Sales-to-Service handoff brief | Yes (Bedrock + S3) |
| `uc_pm_problem_management` | Problem Management RCA | Yes (Bedrock + S3) |

---

## 6. Test Without Lambdas — Connectivity Test

`uc_test_hello` uses `EchoTool` (pure Python stub, no Lambda). Use it to
confirm the AAOSA engine, WebSocket path, and coded tool loading all work.

### Via nsflow WebSocket API

The nsflow chat endpoint format:

```
ws://localhost:14175/api/v1/ws/chat/{agent_name}/{session_id}
```

Message format (JSON string sent over WebSocket):
```json
{"message": "your question here", "sly_data": {}}
```

Python test script (`/tmp/test_hello.py`):

```python
import asyncio, json, uuid
import websockets

async def main():
    agent  = "uc_test_hello"
    sid    = uuid.uuid4().hex[:10]
    uri    = f"ws://localhost:14175/api/v1/ws/chat/{agent}/{sid}"
    query  = "Hello, my name is Srini. Please run a quick connectivity test."

    async with websockets.connect(uri, ping_interval=60, ping_timeout=120) as ws:
        await ws.send(json.dumps({"message": query, "sly_data": {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            msg = json.loads(raw)
            nested = msg.get("message", {})
            if isinstance(nested, dict) and nested.get("text"):
                print(nested["text"])
                break

asyncio.run(main())
```

Run it inside the container (where `websockets` is installed):

```bash
docker cp /tmp/test_hello.py llmwiki-ns-test:/tmp/test_hello.py
docker exec llmwiki-ns-test python3 /tmp/test_hello.py
```

Expected output:
```
✅ Connectivity confirmed! EchoTool responded:
- Echo: "Hello, my name is Srini. Please run a quick connectivity test."
- User: Srini
- Timestamp: 2026-07-12T01:05:00Z
- Note: EchoTool stub — no Lambda call made. Local stack verified.
Local Neuro SAN stack is working correctly.
```

---

## 7. Test Without Lambdas — Travel Booking Demo

`uc_travel_booking` has four agents (FrontMan → FlightSearchTool + HotelSearchTool
→ BookingConfirmTool) all backed by Python stub coded tools. No external APIs.

```python
import asyncio, json, uuid
import websockets

async def main():
    agent = "uc_travel_booking"
    sid   = uuid.uuid4().hex[:10]
    uri   = f"ws://localhost:14175/api/v1/ws/chat/{agent}/{sid}"
    query = ("Book a flight from New York to London for 2 passengers "
             "on 2026-07-25, returning 2026-08-01. Mid-range hotel preferred.")

    async with websockets.connect(uri, ping_interval=60, ping_timeout=120) as ws:
        await ws.send(json.dumps({"message": query, "sly_data": {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=120)
            msg = json.loads(raw)
            nested = msg.get("message", {})
            if isinstance(nested, dict) and nested.get("text"):
                print(nested["text"])
                break

asyncio.run(main())
```

Expected output includes a markdown table of 3 flight options + 3 hotel options
with pricing, then prompts for selection.

---

## 8. Open the nsflow UI

Navigate to `http://localhost:14175/` in a browser.

The nsflow React UI shows all loaded agent networks. Select one and chat with it
interactively. This is the same UI served by nsflow in production.

> **Note:** The nsflow UI communicates with neuro-san over WebSocket via the
> FastAPI backend. The backend connects to `localhost:8080` (the neuro-san server
> inside the same container). No direct browser → neuro-san connection is made.

---

## 9. Hot-Reload HOCON Changes

The container syncs HOCON files from S3 every 3 seconds (`sync_registries.sh`).
neuro-san picks up changes every 5 seconds (`AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=5`).
Total lag from S3 upload to live network reload: **~8 seconds**.

### Reload cycle for HOCON instruction text changes

```bash
# 1. Edit the HOCON file locally
# 2. Push to S3
aws s3 cp code/registries/llmwiki/my_agent.hocon \
    s3://llmwiki-278e7e22/neuro-san/registries/llmwiki/my_agent.hocon \
    --profile tzg-sandbox

# 3. Wait ~8 seconds — the container auto-reloads
# 4. Watch logs to confirm
docker logs llmwiki-ns-test --tail=5
# Look for: REPLACED network for agent my_agent : ...
```

### Skip S3 for immediate testing

Copy directly into the running container (instant — no S3 round-trip):

```bash
docker cp code/registries/llmwiki/my_agent.hocon \
    llmwiki-ns-test:/app/registries/llmwiki/my_agent.hocon
```

> **Warning:** `sync_registries.sh` overwrites the container's `/app/registries/`
> from S3 every 3 seconds. If your S3 copy is older than the local copy, S3 wins
> and reverts your change. Always push to S3 AND docker cp, or disable S3 sync
> by omitting `WIKI_BUCKET` from the docker run command.

### What triggers a full image rebuild

S3 hot-reload only replaces the **text inside** `"""..."""` instruction blocks.
These changes require a full image rebuild + container restart:

| Change type | Deploy method |
|---|---|
| Add/rename a `"parameters"` field in a tool | Rebuild image |
| Add a new `"class"` (coded tool) | Rebuild image |
| Change a `"function"` block structure | Rebuild image |
| Modify instruction text inside `"""..."""` | S3 sync (hot-reload) |
| Add a new HOCON file to `manifest.hocon` | S3 sync (hot-reload) |

---

## 10. Add a New Use Case Locally

1. **Write the HOCON** in `code/registries/llmwiki/uc_my_usecase.hocon`

2. **Write the coded tool** in `code/neuro_san/coded_tools/llmwiki/my_tool.py`
   extending `CodedTool`:
   ```python
   from neuro_san.interfaces.coded_tool import CodedTool

   class MyTool(CodedTool):
       async def async_invoke(self, args, sly_data):
           return {"status": "ok", "result": args.get("input", "")}
   ```

3. **Add to manifest** in `code/registries/llmwiki/manifest.hocon`:
   ```hocon
   { ..., "uc_my_usecase.hocon": true }
   ```

4. **Copy tool into running container** (tool changes require container-side copy
   since `sync_registries.sh` only syncs `registries/`, not `coded_tools/`):
   ```bash
   docker cp code/neuro_san/coded_tools/llmwiki/my_tool.py \
       llmwiki-ns-test:/app/coded_tools/llmwiki/my_tool.py
   ```

5. **Push HOCON + manifest to S3**:
   ```bash
   aws s3 sync code/registries/llmwiki/ \
       s3://llmwiki-278e7e22/neuro-san/registries/llmwiki/ \
       --profile tzg-sandbox
   ```

6. **Confirm reload** in logs:
   ```bash
   docker logs llmwiki-ns-test --tail=5
   # ADDED network for agent uc_my_usecase : ...
   ```

7. **Test via nsflow** at `http://localhost:14175/` or with a Python WebSocket script.

---

## 11. HOCON Authoring Rules

These rules prevent validation errors that cause networks to silently fail to load.

### Parameter types

neuro-san's pydantic v1 converter (`BaseModelDictionaryConverter`) only recognises
these JSON Schema type strings:

| Use in HOCON | Python type |
|---|---|
| `"string"` | `str` |
| `"int"` | `int` |
| `"float"` | `float` |
| `"boolean"` | `bool` |
| `"array"` | `List` |
| `"object"` | `Any` |

> **`"integer"` is NOT supported.** Use `"string"` for numeric params and cast in
> the coded tool: `count = int(args.get("count", 1))`.

### The `${aaosa_call}` merge pattern

When you write:
```hocon
"function": ${aaosa_call}{
    "description": "...",
    "parameters": { ... }
}
```

HOCON merges your block with `aaosa_call`. This means `aaosa_call`'s base
`properties` (`inquiry`, `mode`) are **prepended** to your `properties`. Your
`"required"` array **replaces** the base `["inquiry", "mode"]` — so you must
always provide a `"required"` list in your override, even if it only lists your
own fields:

```hocon
"parameters": {
    "type": "object",
    "properties": {
        "origin":      {"type": "string", "description": "Origin city"},
        "destination": {"type": "string", "description": "Destination city"}
    },
    "required": ["origin", "destination"]   # <-- mandatory; replaces base ["inquiry","mode"]
}
```

Omitting `"required"` leaves the merged `required: ["inquiry","mode"]` in place.
Pydantic then tries to create those as required fields but they don't appear in the
`properties` block after the filter chain runs — causing `UndefinedType` errors.

### FrontMan agents

FrontMan agents (the entry-point agent) use `"function"` with a plain
`"description"` and no `"parameters"` block:

```hocon
"function": {
    "description": "I am your agent. Tell me what you need."
}
```

Do not add `${aaosa_call}` to a FrontMan. That pattern is only for sub-agents
that are called by the FrontMan.

---

## 12. Docker Compose (Full Stack)

For the full Streamlit + neuro-san stack together:

```bash
cd code/
docker compose up --build
```

Then:
- Streamlit UI: `http://localhost:8501`
- nsflow UI: `http://localhost:4173`
- neuro-san API: `http://localhost:8080`

The compose file (`code/docker-compose.yml`) sets `AGENT_TOOL_PATH` via
the Dockerfile `ENV` defaults and `depends_on: neuro-san: condition: service_healthy`
so Streamlit only starts after neuro-san passes its health check.

> **Port conflicts:** The compose stack uses `4173` and `8080`. If those ports
> are already taken (e.g. by drawio, other containers), run the manual `docker run`
> with alternate ports (`14175`, `18082`) as described in step 3.

---

## 13. Stop and Clean Up

```bash
# Stop the test container
docker stop llmwiki-ns-test

# Remove it
docker rm llmwiki-ns-test

# Remove the image (optional — keep if you'll rebuild soon)
docker rmi llmwiki-neuro-san:local
```

---

## Troubleshooting

### `No reasonable agent tool path found`

`AGENT_TOOL_PATH` is not set. Add `-e AGENT_TOOL_PATH=/app/coded_tools` to the
`docker run` command. Without it neuro-san scans its own package directory instead
of `/app/coded_tools/`.

### `validation errors. Skipping. Errors: pydantic model conversion failed — no validator found for UndefinedType`

One of your HOCON parameter fields uses `"type": "integer"`. Change it to
`"type": "string"` and cast in the coded tool with `int(args.get(...))`.

### `validation errors: inquiry field required / mode field required`

The `"required"` array in your `"parameters"` block is missing. When you use
`${aaosa_call}{...}`, the base aaosa_call `required: ["inquiry","mode"]` merges
in unless your override explicitly replaces it. Add:
```hocon
"required": ["your_field_1", "your_field_2"]
```

### S3 sync overwrites my container changes

`sync_registries.sh` runs every 3 seconds and pulls from S3. If S3 has an older
version, it reverts your `docker cp`. Always push to S3 first:
```bash
aws s3 cp myfile.hocon s3://llmwiki-278e7e22/neuro-san/registries/llmwiki/myfile.hocon \
    --profile tzg-sandbox
```
Then `docker cp` if you need the change immediately without waiting for the S3
sync cycle.

### Network loaded but agent returns wrong field errors at runtime

The coded tool received field names it doesn't expect. This happens when the
FrontMan LLM uses the previous tool's output field name as the next tool's input
(e.g. passing `filled_template` instead of `content`). Fix with two steps:

1. **HOCON instruction**: add explicit field name instruction:
   `"The field name MUST be 'content'. Do not use 'filled_template', 'markdown', or 'inquiry'."`

2. **Coded tool fallback**: accept aliases:
   ```python
   content = (args.get("content")
              or args.get("filled_template")
              or args.get("markdown")
              or args.get("inquiry", ""))
   ```

### WebSocket timeout (no response after 300s / 600s)

UC1 and UC-PM run 20–30 Bedrock LLM calls via AAOSA. At ~3–5s per call that is
60–150s of LLM time alone; total wall-clock is 3–7 minutes. The Streamlit client
timeout is set to 600s. If you hit timeout in a custom test script, increase
`asyncio.wait_for(..., timeout=600)`.

### Container exits immediately

Check logs: `docker logs llmwiki-ns-test`. Common causes:
- Missing `AGENT_TOOL_PATH` (Python import error on startup)
- AWS SSO session expired — re-run `aws sso login --profile tzg-sandbox`
- Port already in use — change host ports in `docker run -p`
