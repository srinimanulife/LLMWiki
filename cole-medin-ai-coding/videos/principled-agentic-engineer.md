---
type: video
title: FULL Guide to Becoming a Principled Agentic Engineer (Build Anything with AI)
resource: https://www.youtube.com/watch?v=luBkbzjo-TA
channel: Cole Medin (@ColeMedin)
published: 2026 (approximate)
source: transcript-verified
tags:
- principles
- piv-loop
- ai-layer
- system-evolution
- agentic-engineering
- context-engineering
related_concepts:
- the-piv-loop
- the-ai-layer
- archon-harness-builder
timestamp: '2026-06-25'
description: A polished cut of Cole's hour-long AI-transformation workshop teaching
  a deliberately simple, foundational system for reliable, repeatable results from
  AI coding assistants. He frames the engineer's job as shifting from writing code
  to planning and validating, and walks a three-phase system - ideation, the PIV loop,
  and system evolution - with a live build into a poll-builder app using Claude Code
  and Jira.
---

# FULL Guide to Becoming a Principled Agentic Engineer (Build Anything with AI)

> A polished cut of Cole's hour-long AI-transformation workshop teaching a deliberately simple, foundational system for reliable, repeatable results from AI coding assistants. He frames the engineer's job as shifting from writing code to planning and validating, and walks a three-phase system - ideation, the PIV loop, and system evolution - with a live build into a poll-builder app using Claude Code and Jira.

**Watch:** https://www.youtube.com/watch?v=luBkbzjo-TA

> ✅ *Summary, key ideas, and tools verified against the full video transcript.*

# Key Ideas
- The engineer's role is no longer to write code but to plan and validate - and this is NOT vibe coding, because the human stays in the driver's seat
- The system has three phases: ideation (what to build), the PIV loop (execute each ticket), and system evolution (make the agents more powerful over time) - system evolution is the most powerful part
- Keep it simple on purpose: popular frameworks (Spec Kit, BMAD, etc.) are over-engineered and hard to mold to your SDLC - build a foundation you customize
- Build an AI layer of reusable assets - global rules, commands, and skills; rule of thumb: anything you prompt more than three times becomes a command/skill
- Planning has two layers - Layer 1 project/PM-level (no code), Layer 2 task-level (find the files) - both starting as a brain dump, with the agent asking clarifying questions one at a time
- Use sub-agents for research to manage context: they burn 100k+ tokens exploring and return a small summary - 'just because you can fit a million tokens doesn't mean you should'
- Separate planning and implementation into distinct sessions for fresh eyes; the agent validates its own work (tests, linting, type-checks, even browser testing) so the human isn't the bottleneck
- System evolution = inner loop (PIV when it works) + outer loop (after a bug, have the agent inspect and improve its own AI layer); the AI layer is checked into source control and shared via PRs

# Tools & Projects
Claude Code, Jira, Atlassian / Jira MCP, Confluence, sub-agents, Opus (1M context), agent-browser (E2E testing), git, GitHub CLI, create-prd / create-stories / prime / plan / implement commands

# Related Concepts
- [The PIV Loop (Plan → Implement → Validate)](../concepts/the-piv-loop.md) - Cole's core operating loop: you own the planning and validation, the agent owns the implementation - you stay in the driver's seat.
- [The AI Layer (Rules, Commands, Skills) & System Evolution](../concepts/the-ai-layer.md) - The versioned, reusable layer - rules, commands, skills - that turns a coding assistant into a system that compounds over time.
- [Archon - the Open-Source Harness Builder](../concepts/archon-harness-builder.md) - The new Archon: an open-source workflow/harness engine that sits ABOVE coding agents and orchestrates them with reusable YAML workflows - making AI coding deterministic and repeatable.
