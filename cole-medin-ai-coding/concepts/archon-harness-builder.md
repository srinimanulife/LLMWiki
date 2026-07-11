---
type: concept
title: Archon - the Open-Source Harness Builder
tags:
- archon
- harness
- harness-engineering
- workflows
- orchestration
related_videos:
- harness-engineering-archon
- principled-agentic-engineer
timestamp: '2026-06-25'
description: 'The new Archon: an open-source workflow/harness engine that sits ABOVE
  coding agents and orchestrates them with reusable YAML workflows - making AI coding
  deterministic and repeatable.'
---

# Archon - the Open-Source Harness Builder

Archon was rewritten. The new Archon is **the first open-source harness builder
for AI coding** - a workflow engine whose goal is to make AI coding *deterministic
and repeatable*. (The old RAG-knowledge-base + Kanban-task "command center" Archon
is archived on a `v1-task-management-rag` branch - that is **not** what this is.)

The framing is the evolution **prompt engineering → context engineering → harness
engineering**: a *harness* is the tooling/prompting/chaining layer above a coding
agent that makes it reliable. Cole cites the gap bluntly - a bare model lands a
small fraction of PRs, a good harness lands the large majority; Stripe ships
~1,300 AI-only PRs a week behind a harness; a large share of Anthropic's own
codebase is harness code.

Crucially, the new Archon **sits above the coding agents and orchestrates them**,
rather than (like the old one) being a tool wired *into* a single assistant.

- **Workflows** are YAML files made of **nodes**. Each node is either a *prompt*
  sent to a coding-agent session or a *deterministic command* (context creation,
  validation, git ops) you don't leave to the agent's discretion.
- **The hybrid secret:** mix deterministic steps with AI steps, plus
  human-in-the-loop approval gates - e.g. the plan → implement-in-loop → test →
  review → human-approve → open-PR pipeline.
- **Per-node control** of provider, model (cheap Haiku for classification, Sonnet
  for research), context injection, and fresh-vs-continued session.
- **Define once, run forever:** workflows are reusable across projects and run in
  parallel (e.g. six GitHub-issue fixes at once as background processes).

It ships a Claude Code skill and default workflows (fix-GitHub-issue, idea-to-PR,
PR review, interactive PRD, the Ralph loop) plus a meta workflow-builder workflow.
This is the layer that **automates the PIV loop and the AI layer** Cole teaches -
turning a hand-run process into one you can execute reliably on demand.

# Videos on this
- [The Next Evolution of AI Coding Is Harnesses - Here's How to Build Them](../videos/harness-engineering-archon.md)
- [FULL Guide to Becoming a Principled Agentic Engineer (Build Anything with AI)](../videos/principled-agentic-engineer.md)
