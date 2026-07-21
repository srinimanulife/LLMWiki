# LLMWiki Fusion Harness — Implementation Guide

> **Model fusion for LLMWiki**: Claude (Architect) + gpt-5.3-codex-2 on Azure (Builder),
> wired directly into Claude Code via slash commands — no separate agent runtime needed.

---

## What Was Built

The [fusion-harness](https://github.com/disler/fusion-harness) pattern ported natively into
Claude Code. Instead of the original `pi` CLI agent framework, every fusion workflow runs as
Claude Code slash commands that call the Azure Codex endpoint through a local reverse proxy.

| Component | Location | Purpose |
|---|---|---|
| Azure proxy | `~/codex-proxy/proxy.js` | Injects `api-key` + `?api-version` — fixes Azure ↔ Codex CLI incompatibility |
| systemd service | `~/.config/systemd/user/codex-proxy.service` | Keeps proxy alive across sessions |
| `/opinion` command | `~/.claude/commands/opinion.md` | Side-by-side Claude vs Codex comparison |
| `/fusion` command | `~/.claude/commands/fusion.md` | Parallel workers + merge agent |
| `/auto-validate` command | `~/.claude/commands/auto-validate.md` | Build-and-gate validation loop |
| `/fh-reset` command | `~/.claude/commands/fh-reset.md` | Reset harness state |
| `/unit-test` command | `~/.claude/commands/unit-test.md` | Codex unit test generator + fix loop |

> **Commands are global** — installed at `~/.claude/commands/` so they work in every project,
> not just LLMWiki. Project-level copies at `.claude/commands/` can override them if needed.

**Roles:**
- **ARCHITECT** = Claude (current session, `us.anthropic.claude-sonnet-4-6`)
- **BUILDER** = `gpt-5.3-codex-2` on Azure OpenAI via `http://127.0.0.1:18080`
- **FUSION** = Claude acting as a fresh merge agent (same session, different framing)

---

## Prerequisites

All already satisfied in this environment:
- Node.js 20+ (`node --version`)
- `@openai/codex` 0.144.6 at `~/.npm-global/bin/codex`
- Azure OpenAI deployment: `gpt-5.3-codex-2` at `aoaihpcsipoc.openai.azure.com`
- Claude Code CLI installed and authenticated

---

## Step-by-Step Setup (already done — reference only)

### Step 1 — Install Codex CLI

```bash
npm install -g @openai/codex --prefix ~/.npm-global
```

### Step 2 — Create Azure reverse proxy

File: `~/codex-proxy/proxy.js`
- Rewrites every request: injects `?api-version=2025-04-01-preview` and `api-key:` header
- Returns HTTP 404 on WebSocket upgrades (forces Codex CLI to use HTTPS transport)
- Exposes `GET /health` for readiness checks

```bash
cd ~/codex-proxy && npm install http-proxy
```

### Step 3 — Configure Codex CLI

File: `~/.codex/config.toml`
```toml
model = "gpt-5.3-codex-2"
model_reasoning_effort = "high"
openai_base_url = "http://127.0.0.1:18080/openai"
```

### Step 4 — Install systemd user service (auto-start)

File: `~/.config/systemd/user/codex-proxy.service`
```ini
[Unit]
Description=Azure OpenAI Proxy for Codex CLI
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/codex-proxy
ExecStart=/usr/bin/node %h/codex-proxy/proxy.js
Restart=on-failure
Environment=OPENAI_API_KEY=<your-key>

[Install]
WantedBy=default.target
```

Enable:
```bash
systemctl --user daemon-reload
systemctl --user enable codex-proxy
systemctl --user start codex-proxy
```

Verify:
```bash
curl http://127.0.0.1:18080/health
# → {"status":"ok","target":"aoaihpcsipoc.openai.azure.com","api_version":"2025-04-01-preview"}
```

### Step 5 — Install slash commands (global)

Commands are installed at `~/.claude/commands/` — available in **every project**:
```
~/.claude/commands/opinion.md        → /opinion
~/.claude/commands/fusion.md         → /fusion
~/.claude/commands/auto-validate.md  → /auto-validate
~/.claude/commands/fh-reset.md       → /fh-reset
```

Project-level copies at `.claude/commands/` shadow the global ones if you need
to specialise a command for a specific codebase.

To copy global commands to a new project for local override:
```bash
cp ~/.claude/commands/*.md <project>/.claude/commands/
```

### Step 6 — Load bash aliases

```bash
source ~/.bashrc
```

Aliases available after reload:
```
codex-proxy-start    start the proxy via systemd
codex-proxy-stop     stop it
codex-proxy-status   status + health check
codex-proxy-log      live journal log
```

---

## Daily Usage — How to Run Fusion Workflows

### Check proxy is alive (do this first)

```bash
codex-proxy-status
# or
curl http://127.0.0.1:18080/health
```

If it's down:
```bash
codex-proxy-start
```

---

### Workflow 1 — `/opinion` (Side-by-side comparison)

**When to use:** You want two independent perspectives on a question or design decision
before committing to one answer.

In Claude Code, type:
```
/opinion Should LLMWiki use streaming SSE or polling for the knowledge gap feed?
```

**What you get:**
```
## 🏛 ARCHITECT (Claude)
<Claude's answer>

## ⚡ BUILDER (gpt-5.3-codex-2)
<Codex's answer>

## 🔀 Synthesis
- Both agree on: ...
- They diverge on: ...
- More actionable answer: ...
```

**LLMWiki example prompts:**
```
/opinion What's the best chunking strategy for medical PDF ingestion into Bedrock KB?
/opinion Should the Lambda harness use Step Functions or a direct invocation chain?
/opinion How should we handle low-confidence answers in the wiki query response?
```

---

### Workflow 2 — `/fusion` (Parallel workers + merge)

**When to use:** Complex tasks where you want both models to work the problem independently
and then have a third pass merge the best of both.

```
/fusion "Design the schema for LLMWiki's knowledge gap tracking DynamoDB table" "Merge into a single schema that is cost-optimised and supports gap lifecycle queries"
```

**What you get:**
```
## 🏛 Worker A — Claude (Architect)
<Claude's schema design>

## ⚡ Worker B — gpt-5.3-codex-2 (Builder)
<Codex's schema design>

---
## 🔀 FUSED OUTPUT
<merged schema with attribution>

### Attribution Map
| Insight | Source |
|---------|--------|
| GSI on gap_status | [Builder] |
| TTL field for auto-expiry | [Architect] |
| Composite sort key pattern | [Both] |
```

**LLMWiki example prompts:**
```
/fusion "Write the Streamlit component for displaying knowledge gap badges" "Prefer Claude's UX reasoning but Codex's implementation specifics"
/fusion "Outline the S3 Vectors sync strategy for new document ingestion" "Merge into ops runbook format"
/fusion "Design the neuro_san agent network for hospital management system" "Synthesise into a single HOCON registry"
```

---

### Workflow 3 — `/auto-validate` (Build-and-gate loop)

**When to use:** You need to **ship working code** — not just a plan. The gate ensures
the Builder's output actually satisfies the requirement before you accept it.

```
/auto-validate Write a Python function that extracts named entities from a wiki page markdown string and returns them as a JSON list with type labels
```

**What happens:**
```
## 🔍 VALIDATOR — Acceptance Gate
```python
# gate.py — exits 0 only if the function works correctly
import json, sys
sys.path.insert(0, '.')
from solution import extract_entities

result = extract_entities("Dr. Smith treated patient John Doe at Mayo Clinic.")
assert isinstance(result, list), "Must return a list"
assert any(e.get('type') == 'PERSON' for e in result), "Must detect PERSON entities"
assert any(e.get('type') == 'ORG' for e in result), "Must detect ORG entities"
print("PASS")
```

## ⚡ BUILDER — Implementation (Round 1)
<Codex writes solution.py>

## 🚦 Gate Result — Round 1
Status: PASS ✅
```

**LLMWiki example tasks:**
```
/auto-validate Write a function to convert DynamoDB scan results to markdown table format
/auto-validate Build a retry wrapper for Bedrock InvokeModel with exponential backoff
/auto-validate Create a Python script to batch-upload PDFs from a local folder to S3 with progress tracking
```

---

### Workflow 4 — `/unit-test` (Codex unit test generator + fix loop)

**When to use:** You have a file produced by Codex (or any generator) and want
comprehensive unit tests written, run, and auto-fixed until they pass — without
writing a single test by hand.

```
/unit-test code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py pytest "cover all public methods, mock HTTP requests"
```

**Argument format:**
```
/unit-test <file_path> [framework] ["extra instructions"]
```

| Arg | Default | Notes |
|---|---|---|
| `file_path` | required | Relative or absolute path to the source file |
| `framework` | auto-detected | `pytest` for `.py`, `jest` for `.js/.ts`, `junit` for `.java`, `go test` for `.go` |
| `"extra instructions"` | none | Quoted string — any extra Codex constraints |

**What happens:**
```
## 📂 Target File — code/lambda/query/handler.py
Language: Python  |  Framework: pytest
Symbols to test: handle, _build_response, _parse_event

## ⚡ Codex — Generated Tests (Round 1)
Written to: code/lambda/query/test_handler.py
<full test file>

## 🚦 Test Run — Round 1
... pytest output ...
Status: FAIL ❌ (2 passed / 3 failed)

## ⚡ Codex — Fixed Tests (Round 2)
<corrected test file>

## 🚦 Test Run — Round 2
Status: PASS ✅ (5 passed / 0 failed)

## ✅ Unit Tests Complete
Test file: code/lambda/query/test_handler.py
Tests passed: 5  |  Rounds needed: 2
```

**Fix loop behaviour:**
- Rounds 1–2: Codex receives the failure output and fixes the test file automatically
- Round 3: Claude acts as TRIAGE — diagnoses missing deps, bad imports, wrong mocks
- Round 4+: Halts with `🛑 Max Rounds Reached`, leaves test file in place for manual review

**LLMWiki example invocations:**
```
/unit-test code/lambda/query/handler.py pytest "mock all boto3 and bedrock calls"
/unit-test code/lambda/harness/pm_harness/handler.py pytest "mock DynamoDB, mock Lambda invoke"
/unit-test code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py pytest "cover all public methods, mock HTTP"
/unit-test code/streamlit/app.py pytest "mock all AWS SDK calls, do not start Streamlit server"
```

---

### Workflow 5 — `/fh-reset` (Clear state)

Run this if Claude seems confused about its role, or after a very long session:
```
/fh-reset
```

---

## Fusion Harness Architecture (how it works inside Claude Code)

```
┌─────────────────────────────────────────────────────────┐
│  Claude Code Session                                     │
│                                                          │
│  You type: /fusion "design X" "merge Y"                  │
│                  │                                       │
│          Claude reads fusion.md                          │
│                  │                                       │
│    ┌─────────────┴──────────────┐                        │
│    │                            │                        │
│  ARCHITECT               BUILDER                         │
│  Claude answers          Claude POSTs to:                │
│  in-session              http://127.0.0.1:18080          │
│                                 │                        │
│                    ┌────────────▼────────────────────┐   │
│                    │  ~/codex-proxy/proxy.js          │   │
│                    │  • injects ?api-version          │   │
│                    │  • rewrites auth → api-key       │   │
│                    │  • rejects WS → HTTPS fallback   │   │
│                    └────────────┬────────────────────┘   │
│                                 │                        │
│                    aoaihpcsipoc.openai.azure.com         │
│                    model: gpt-5.3-codex-2                │
│                                 │                        │
│    ┌────────────────────────────▼──────────┐             │
│    │         FUSION MERGE AGENT            │             │
│    │  Claude synthesises ANSWER_A +        │             │
│    │  ANSWER_B → single fused output       │             │
│    └───────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

The key difference from the original fusion-harness (which uses `pi` CLI subprocesses):
**all three agents run inside the same Claude Code session** — no subprocess spawning,
no IPC, no separate CLI. Claude plays Architect, calls Codex over HTTP for Builder,
then plays Fusion merge agent in the same turn.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `curl http://127.0.0.1:18080/health` hangs | `codex-proxy-start` or `systemctl --user restart codex-proxy` |
| `/opinion` Codex call returns error | Check `codex-proxy-log` for 401/404 from Azure |
| `/auto-validate` gate never passes | Ask Claude to diagnose the gate itself — or run `/fh-reset` |
| Codex CLI `review --uncommitted` fails | This is separate from slash commands; proxy must be running first |
| WSL proxy dies after wake from sleep | `codex-proxy-start` (systemd user services may not auto-resume in WSL) |

---

## File Index

```
# Proxy & service
~/codex-proxy/proxy.js                              Reverse proxy source
~/codex-proxy/start-proxy.sh                        Manual start script
~/codex-proxy/package.json                          http-proxy dependency
~/.config/systemd/user/codex-proxy.service          systemd unit (auto-start on login)

# Codex CLI config
~/.codex/config.toml                                model + Azure base URL

# Global slash commands (all projects)
~/.claude/commands/opinion.md                       /opinion
~/.claude/commands/fusion.md                        /fusion
~/.claude/commands/auto-validate.md                 /auto-validate
~/.claude/commands/fh-reset.md                      /fh-reset
~/.claude/commands/unit-test.md                     /unit-test

# LLMWiki project-level copies (shadow global if present)
.claude/commands/opinion.md
.claude/commands/fusion.md
.claude/commands/auto-validate.md
.claude/commands/fh-reset.md
.claude/commands/unit-test.md

# Shell
~/.bashrc                                           codex-proxy-* aliases + env vars
```

---

## Scope: Global vs Project

| Scope | Path | Loaded when |
|---|---|---|
| **Global** | `~/.claude/commands/` | Any Claude Code session on this machine |
| **Project** | `<repo>/.claude/commands/` | Only when `claude` is run in that directory |

The fusion harness is generic — the global copies work everywhere. Use project-level
overrides only when you need domain-specific prompts (e.g. different Builder model,
extra context injected into the Validator gate).
