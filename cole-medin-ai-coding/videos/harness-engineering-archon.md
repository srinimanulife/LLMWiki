---
type: video
title: The Next Evolution of AI Coding Is Harnesses - Here's How to Build Them
resource: https://www.youtube.com/watch?v=qMnClynCAmM
channel: Cole Medin (@ColeMedin)
published: 2026 (approximate)
source: transcript-verified
tags:
- archon
- harness
- harness-engineering
- workflows
- orchestration
- ai-coding
related_concepts:
- archon-harness-builder
- the-piv-loop
- the-ai-layer
timestamp: '2026-06-25'
description: The official unveiling of the rewritten Archon - repositioned from last
  year's 'AI command center' into 'the first open-source harness builder for AI coding.'
  Cole teaches why harnesses matter, then walks through setup, the bundled default
  workflows, the YAML/node/command architecture, parallel workflow execution, the
  web UI, and building custom workflows.
---

# The Next Evolution of AI Coding Is Harnesses - Here's How to Build Them

> The official unveiling of the rewritten Archon - repositioned from last year's 'AI command center' into 'the first open-source harness builder for AI coding.' Cole teaches why harnesses matter, then walks through setup, the bundled default workflows, the YAML/node/command architecture, parallel workflow execution, the web UI, and building custom workflows.

**Watch:** https://www.youtube.com/watch?v=qMnClynCAmM

> ✅ *Summary, key ideas, and tools verified against the full video transcript.*

# Key Ideas
- The arc that explains why Archon exists now: prompt engineering → context engineering (curate context for one agent) → harness engineering (string many coding-agent sessions together)
- A harness is the tooling/prompting/chaining layer above coding agents that makes AI coding deterministic and repeatable - cites ~6.7% PR acceptance for a bare model vs. ~70% with a good harness; Stripe's ~1,300 AI-only PRs/week
- Old vs. new Archon: the old one was a RAG + task-management tool built INTO an assistant (now archived/irrelevant); the new Archon sits ABOVE the agents and orchestrates them - 'define once, run forever'
- Workflows are YAML files made of nodes; each node is either a prompt to a coding-agent session or a deterministic command (context creation, validation) you don't leave to the agent's discretion
- The 'hybrid secret': mix deterministic nodes with AI nodes plus human-in-the-loop gates - the plan → implement-in-loop → test → review → approve → open-PR DAG
- Per-node control of provider, model (Haiku for cheap classification, Sonnet default), context injection (a skill/MCP only at one step), and fresh-vs-continued session for token/context management
- Ships a Claude Code skill and many default workflows (fix-GitHub-issue, idea-to-PR, PR review, interactive PRD, the Ralph loop) plus a meta workflow-builder workflow
- Demos: <5-min agent-guided setup; an issue fixed end-to-end to a PR; six issue-fix workflows running in parallel as background processes

# Tools & Projects
Archon (harness builder), Claude Code, Codex, Pi Agent SDK, Claude Agent SDK, Opus / Sonnet / Haiku, Bun, SQLite / Postgres, GitHub / Telegram / Slack (interfaces), the Ralph loop, GSD / BMAD / beads (importable workflows)

# Links
- GitHub: https://github.com/coleam00/Archon

# Related Concepts
- [Archon - the Open-Source Harness Builder](../concepts/archon-harness-builder.md) - The new Archon: an open-source workflow/harness engine that sits ABOVE coding agents and orchestrates them with reusable YAML workflows - making AI coding deterministic and repeatable.
- [The PIV Loop (Plan → Implement → Validate)](../concepts/the-piv-loop.md) - Cole's core operating loop: you own the planning and validation, the agent owns the implementation - you stay in the driver's seat.
- [The AI Layer (Rules, Commands, Skills) & System Evolution](../concepts/the-ai-layer.md) - The versioned, reusable layer - rules, commands, skills - that turns a coding assistant into a system that compounds over time.
