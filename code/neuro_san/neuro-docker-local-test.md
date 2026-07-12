# Neuro SAN — Local Docker Test Guide

How to build, run, and test the LLMWiki neuro-san sidecar image locally
without touching any ECS deployment.

---

## Quick Reference — Rules That Will Burn You If You Forget

Learned the hard way building `uc_travel_booking`. Memorise these before you
write a single line of HOCON.

| # | Rule | What happens if you break it |
|---|---|---|
| 1 | Never use `"type": "integer"` in parameters | Silent `UndefinedType` pydantic crash — network skipped, no useful error message |
| 2 | Always include `"required": [...]` in every sub-agent parameters block | base aaosa_call injects `["inquiry","mode"]`; without override your required list stays as those two fields → same UndefinedType crash |
| 3 | Push to S3 **before** `docker cp`, never after | `sync_registries.sh` pulls from S3 every 3 s and will overwrite your docker cp with the old S3 version |
| 4 | Set `-e AGENT_TOOL_PATH=/app/coded_tools` on `docker run` | neuro-san scans its own package dir and fails to find any of your coded tools |
| 5 | nsflow WebSocket message format is `{"message": "...", "sly_data": {}}` | Sending `{"user_input": "..."}` (neuro-san direct API) gives a 120 s silence then timeout |
| 6 | Test scripts run inside the container use port 4173 (nsflow) or 8080 (neuro-san), not the host-mapped ports 14175/18082 | Connection refused inside container when you use host ports |
| 7 | Don't add `${aaosa_call}` to the FrontMan agent | FrontMan has no parameters — HOCON merge will produce a parameters block with only inquiry+mode and break validation |
| 8 | Coded tool changes (new `.py` files) are NOT picked up by S3 sync | Only HOCON files sync from S3; coded tools need `docker cp` or a full image rebuild |

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

## 10. Case Study — Building `uc_travel_booking` (What Went Wrong and Why)

This section walks through every error hit while building the travel booking use
case. Read it before building your own use case — each mistake costs 5–10 minutes
of debugging and log-reading.

### What we were building

A 4-agent AAOSA network:

```
User → TravelBookingAgent (FrontMan)
           ├── FlightSearchTool   (stub, returns 3 flight options)
           ├── HotelSearchTool    (stub, returns 3 hotel options)
           └── BookingConfirmTool (stub, returns a booking reference)
```

All coded tools are pure Python stubs — no Lambda, no external API — so the
entire network runs locally without AWS Bedrock being involved beyond the LLM
calls made by the neuro-san AAOSA engine itself.

---

### Problem 1 — `"type": "integer"` causes silent validation failure

**What we wrote:**
```hocon
"passengers": {"type": "integer", "description": "Number of passengers"}
```

**Error in logs:**
```
manifest registry uc_travel_booking.hocon has validation errors. Skipping.
  FlightSearchTool: pydantic model conversion failed - no validator found
  for <class 'pydantic.v1.fields.UndefinedType'>, see `arbitrary_types_allowed`
```

**Why it happens:**
neuro-san's internal converter (`BaseModelDictionaryConverter`) uses a hard-coded
`TYPE_LOOKUP` dictionary. It maps `"string"` → `str`, `"int"` → `int`, etc.
The string `"integer"` (standard JSON Schema) is **not in that lookup**. When the
converter calls `TYPE_LOOKUP.get("integer")` it gets `None`. Pydantic v1 then
receives a `None` type which resolves to `UndefinedType` — a sentinel that
pydantic uses for "not set yet" — and crashes.

The error message mentions `UndefinedType` but doesn't say which field or which
type string caused it, making it hard to diagnose without reading the source.

**Fix:**
```hocon
"passengers": {"type": "string", "description": "Number of passengers (as a number)"}
```

Cast in the coded tool:
```python
passengers = int(args.get("passengers", 1))
```

**Caution:** This is easy to miss because `"integer"` is completely valid JSON
Schema and works in OpenAI tool definitions. neuro-san's pydantic layer predates
standard JSON Schema and uses its own shorter type names.

---

### Problem 2 — Omitting `"required"` leaves inquiry+mode as required fields

**What we wrote (first attempt to fix Problem 1):**
We removed the `"required"` array entirely, thinking it would make all fields
optional and avoid the crash.

**Error in logs (same crash, different cause):**
```
FlightSearchTool: pydantic model conversion failed - no validator found
for <class 'pydantic.v1.fields.UndefinedType'>
```

**Why it happens:**
The HOCON substitution `${aaosa_call}{...}` merges your function block with the
base `aaosa_call` definition. After HOCON parsing the `FlightSearchTool.function`
object contains:

```json
{
  "description": "...",
  "parameters": {
    "type": "object",
    "properties": {
      "inquiry": {"type": "string"},
      "mode":    {"type": "string"},
      "origin":  {"type": "string"},
      ...
    },
    "required": ["inquiry", "mode"]   ← base aaosa_call's required, still present
  }
}
```

The `"required"` array is **additive in HOCON object merge only when both sides
have different keys**. An array is replaced wholesale by the overriding value.
Because we provided no `"required"` key at all in our override, the base
`["inquiry", "mode"]` survived unchanged. Pydantic then creates `inquiry` and
`mode` as required fields (no `default=None`) but our properties contained
`origin`, `destination`, etc. — not `inquiry` / `mode` — so pydantic gets
`None` type for those required fields → `UndefinedType`.

**Fix:** Always include a `"required"` array in every sub-agent's parameters
override. It replaces the base `["inquiry", "mode"]`:

```hocon
"parameters": {
    "type": "object",
    "properties": {
        "origin":      {"type": "string", "description": "Origin city"},
        "destination": {"type": "string", "description": "Destination city"},
        "departure_date": {"type": "string", "description": "Departure date YYYY-MM-DD"},
        "passengers":  {"type": "string", "description": "Number of passengers"}
    },
    "required": ["origin", "destination", "departure_date", "passengers"]
}
```

---

### Problem 3 — S3 sync silently overwrote the fixed container file

**What happened:**
After fixing Problems 1 and 2 in the local file and running `docker cp` to push
the fixed HOCON into the container, the container logs still showed the old error.
Checking the file inside the container revealed `"type": "integer"` was back.

**Why it happens:**
`sync_registries.sh` runs `aws s3 sync` every 3 seconds and pulls from S3 into
`/app/registries/`. The S3 object still had the old version. So 3 seconds after
our `docker cp`, the sync loop overwrote the container file with the stale S3 version.

**Fix:**
Always do both operations in order:
```bash
# 1. Push to S3 first
aws s3 cp code/registries/llmwiki/uc_travel_booking.hocon \
    s3://llmwiki-278e7e22/neuro-san/registries/llmwiki/uc_travel_booking.hocon \
    --profile tzg-sandbox

# 2. Then docker cp for immediate effect (optional — S3 sync will also do it within 3s)
docker cp code/registries/llmwiki/uc_travel_booking.hocon \
    llmwiki-ns-test:/app/registries/llmwiki/uc_travel_booking.hocon
```

Never the other order.

---

### Problem 4 — Wrong WebSocket endpoint and message format

**What we tried first:**
```python
uri = "ws://localhost:18082/v1/streaming_agent"
await ws.send(json.dumps({"agent_network_name": "uc_travel_booking", "request": {"user_input": question}}))
```

**Error:** `HTTP 404` — the path doesn't exist.

**Then tried (still wrong):**
```python
uri = f"ws://localhost:14175/api/v1/ws/chat/{agent}/{sid}"
await ws.send(json.dumps({"user_input": question}))
```

This connected successfully but received 0 messages even after 120 seconds.
nsflow accepted the WebSocket but the `handle_user_input` method reads the
`"message"` key — not `"user_input"` — so the query was silently discarded.

**Why it's confusing:**
- Port `18082` → neuro-san's raw HTTP/WS API (not the same as nsflow)
- Port `14175` → nsflow's FastAPI backend
- nsflow is the correct entry point for interactive chat
- nsflow's raw neuro-san call is on the **internal** port 8080, not the host port 18082
- nsflow expects `{"message": "...", "sly_data": {}}` not `{"user_input": "..."}`

**Fix:** Always use the nsflow endpoint with the correct message format:
```python
uri = f"ws://localhost:14175/api/v1/ws/chat/{agent_name}/{session_id}"
await ws.send(json.dumps({"message": question, "sly_data": {}}))
```

When running a test script **inside** the container (via `docker exec`), use the
internal port instead:
```python
uri = f"ws://localhost:4173/api/v1/ws/chat/{agent_name}/{session_id}"
```

---

### Summary — Travel Booking Debugging Timeline

| Step | What we did | Time wasted |
|---|---|---|
| Wrote initial HOCON with `"integer"` types | Seemed reasonable, standard JSON Schema | — |
| Saw `UndefinedType` error | Didn't recognise it as a type-name issue | 10 min |
| Changed to `"string"`, removed `"required"` | Fixed one bug, introduced another | 5 min |
| Same `UndefinedType` error, different cause | Had to read neuro-san source to understand | 15 min |
| Added back `"required"` with domain fields | Fixed crash | — |
| HOCON still showing old `"integer"` in container | S3 sync overwrote docker cp | 10 min |
| Fixed deploy order (S3 first, then cp) | Network loaded | — |
| Wrong WS path / message format | Two rounds of 120 s timeouts | 5 min |
| Used correct nsflow path + `{"message":...}` | End-to-end test passed | — |

Total time that could have been saved with this document: **~45 minutes**.

---

## 11. Step-by-Step Guide — Adding a New Use Case

This is the authoritative checklist. Follow it in order. Do not skip steps.

### Step 0 — Plan before you code

Sketch the agent graph on paper first:

```
User → FrontManAgent
          ├── ToolA   (what inputs does it need? what does it return?)
          ├── ToolB
          └── ToolC
```

For each sub-agent tool decide:
- What fields does the FrontMan pass in? (these become `"parameters"`)
- What does the coded tool return? (this becomes context for the next step)
- Does it need a real Lambda, or can it be a stub first?

Start with stubs. Validate the AAOSA graph works before wiring real lambdas.

---

### Step 1 — Write the coded tool(s)

File location: `code/neuro_san/coded_tools/llmwiki/my_tool.py`

```python
from typing import Any, Dict, Union
from neuro_san.interfaces.coded_tool import CodedTool

class MyTool(CodedTool):
    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Union[Dict[str, Any], str]:
        # Always use .get() with a default — never args["field"]
        field_a = args.get("field_a", "")
        count   = int(args.get("count", 1))   # cast string → int here

        return {
            "status": "ok",
            "result": f"Processed {field_a} x{count}",
        }
```

**Cautions:**
- Use `args.get("field", default)` — never `args["field"]`. The AAOSA engine may
  omit optional fields entirely.
- Cast numeric args in Python (`int(args.get(...))`) not in HOCON (`"type": "integer"`).
- Return a plain `dict` or `str`. Do not raise exceptions for missing optional
  fields — return an error key in the dict instead.

---

### Step 2 — Write the HOCON

File location: `code/registries/llmwiki/uc_my_usecase.hocon`

**FrontMan template:**
```hocon
include "registries/aaosa.hocon",
include "config/llm_config.hocon",

"tools": [
    {
        "name": "MyFrontManAgent",

        "function": {
            "description": "I am the MyUseCase agent. Tell me X and I will Y."
        },

        "instructions": """
You are the MyFrontManAgent.

STEP 1 — Gather required information from the user.
STEP 2 — Call MyTool with these named fields:
  field_a = ...
  count   = ...
STEP 3 — Present the result.
""" ${aaosa_instructions},

        "tools": ["MyTool"]
    },
```

**Sub-agent template:**
```hocon
    {
        "name": "MyTool",

        "function": ${aaosa_call}{
            "description": "Does X given field_a and count. Pass field_a and count as named fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_a": {"type": "string", "description": "The primary input"},
                    "count":   {"type": "string", "description": "How many times (as a number)"}
                },
                "required": ["field_a", "count"]
            }
        },

        "instructions": """
You are MyTool.
Given field_a and count, do X and return a structured result.
""",

        "class": "coded_tools.llmwiki.my_tool.MyTool"
    }

]
```

**Cautions at this step:**
- ❌ Do NOT use `"type": "integer"` — use `"type": "string"` for all numeric params.
- ❌ Do NOT omit the `"required": [...]` array from any sub-agent's parameters.
- ❌ Do NOT add `${aaosa_call}` to the FrontMan function block.
- ✅ The `"class"` path must match exactly: `coded_tools.llmwiki.<filename>.<ClassName>`.
- ✅ All sub-agents must appear in the same `"tools"` array.

---

### Step 3 — Add to manifest

File: `code/registries/llmwiki/manifest.hocon`

```hocon
{
    "uc1_sales_to_service.hocon":     true,
    "uc_pm_problem_management.hocon": true,
    "uc_test_hello.hocon":            true,
    "uc_travel_booking.hocon":        true,
    "uc_my_usecase.hocon":            true    ← add this line
}
```

---

### Step 4 — Pre-flight validation (before touching the container)

Run the pydantic validator locally without starting a container. This catches
type errors and missing required fields in under 1 second:

```bash
docker exec llmwiki-ns-test python3 - << 'EOF'
import sys
sys.path.insert(0, '/app')
from leaf_common.config.config_handler import ConfigHandler
from neuro_san.internals.graph.filters.network_config_filter_chain import NetworkConfigFilterChain
from neuro_san.internals.run_context.langchain.core.base_model_dictionary_converter import BaseModelDictionaryConverter

raw      = ConfigHandler().import_config('/app/registries/llmwiki/uc_my_usecase.hocon')
filtered = NetworkConfigFilterChain().filter_config(raw)

for tool in filtered.get('tools', []):
    name   = tool.get('name', '')
    params = tool.get('function', {}).get('parameters')
    if not params or not isinstance(params, dict):
        print(f"  {name}: no parameters (FrontMan or external)")
        continue
    try:
        BaseModelDictionaryConverter('parameters').from_dict(params)
        print(f"  ✅ {name}: OK")
    except Exception as e:
        print(f"  ❌ {name}: {e}")
EOF
```

> Copy the HOCON into the container first: `docker cp code/registries/llmwiki/uc_my_usecase.hocon llmwiki-ns-test:/app/registries/llmwiki/uc_my_usecase.hocon`

All tools should print ✅ before proceeding. Fix any ❌ before the next step.

---

### Step 5 — Deploy to running container

**Always in this order:**

```bash
# 1. Push HOCON + manifest to S3
aws s3 sync code/registries/llmwiki/ \
    s3://llmwiki-278e7e22/neuro-san/registries/llmwiki/ \
    --profile tzg-sandbox --region us-east-1

# 2. Copy coded tool into container (S3 sync does NOT cover coded_tools/)
docker cp code/neuro_san/coded_tools/llmwiki/my_tool.py \
    llmwiki-ns-test:/app/coded_tools/llmwiki/my_tool.py

# 3. Copy HOCON directly for immediate effect (S3 sync will also do this in ~3s)
docker cp code/registries/llmwiki/uc_my_usecase.hocon \
    llmwiki-ns-test:/app/registries/llmwiki/uc_my_usecase.hocon
docker cp code/registries/llmwiki/manifest.hocon \
    llmwiki-ns-test:/app/registries/llmwiki/manifest.hocon
```

**Why this order matters:** If you do `docker cp` before pushing S3, the
`sync_registries.sh` loop will overwrite your container file with the old S3
version within 3 seconds. S3 first, always.

---

### Step 6 — Confirm the network loaded

```bash
docker logs llmwiki-ns-test --tail=15
```

**Success looks like:**
```
Validating uc_my_usecase agent network...
ADDED network for agent uc_my_usecase : 127759173735760
```

**Failure looks like:**
```
Validating uc_my_usecase agent network...
manifest registry uc_my_usecase.hocon has validation errors. Skipping. Errors: [
    "MyTool: pydantic model conversion failed - ..."
]
```

If you see failure, go back to Step 4 (pre-flight validation) to identify the
specific parameter causing the error.

Also confirm via the list endpoint:
```bash
curl http://localhost:14175/api/v1/list | python3 -m json.tool
```

---

### Step 7 — Test end-to-end

Save as `/tmp/test_my_usecase.py` and run inside the container:

```python
import asyncio, json, uuid, websockets

async def main():
    agent = "uc_my_usecase"
    sid   = uuid.uuid4().hex[:10]
    uri   = f"ws://localhost:4173/api/v1/ws/chat/{agent}/{sid}"
    query = "Your test query here with all required information."

    print(f"Testing {agent}")
    async with websockets.connect(uri, ping_interval=60, ping_timeout=120) as ws:
        await ws.send(json.dumps({"message": query, "sly_data": {}}))
        while True:
            raw  = await asyncio.wait_for(ws.recv(), timeout=120)
            msg  = json.loads(raw)
            text = (msg.get("message") or {}).get("text", "")
            if text:
                print(text)
                break

asyncio.run(main())
```

```bash
docker cp /tmp/test_my_usecase.py llmwiki-ns-test:/tmp/test_my_usecase.py
docker exec llmwiki-ns-test python3 /tmp/test_my_usecase.py
```

---

### Step 8 — Commit and push to GitHub

```bash
cd /path/to/LLMWiki
git add \
    code/registries/llmwiki/uc_my_usecase.hocon \
    code/registries/llmwiki/manifest.hocon \
    code/neuro_san/coded_tools/llmwiki/my_tool.py
git commit -m "Add uc_my_usecase agent network with MyTool stub"
git push origin main
```

---

### Common mistakes checklist

Before asking "why isn't my network loading?", go through this list:

- [ ] No `"type": "integer"` anywhere in parameters — changed to `"string"`?
- [ ] Every sub-agent parameters block has a `"required": [...]` array?
- [ ] FrontMan does **not** have `${aaosa_call}` in its function block?
- [ ] The `"class"` path matches the actual Python module path and class name exactly?
- [ ] S3 was pushed **before** `docker cp` (not after)?
- [ ] Coded tool was copied into the container with `docker cp` (S3 sync won't do it)?
- [ ] Logs show `ADDED network for agent ...` (not `validation errors. Skipping`)?
- [ ] Test script runs **inside** the container on port 4173 (not on host port 14175)?
- [ ] WebSocket message is `{"message": "...", "sly_data": {}}` (not `user_input`)?

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
