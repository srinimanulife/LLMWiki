---
type: video
title: Context Engineering 101 - The Simple Strategy to 100x AI Coding
resource: https://www.youtube.com/watch?v=Mk87sFlUG28
channel: Cole Medin (@ColeMedin)
published: 2025-07 (approximate)
source: transcript-verified
tags:
- context-engineering
- prp
- claude-code
- prompt-engineering
- vibe-coding
related_concepts:
- context-engineering
- the-piv-loop
timestamp: '2026-06-25'
description: Cole goes deep on context engineering with the PRP (Product Requirement
  Prompt) framework - including a guest interview with its creator Rasmus - then live-builds
  a 'PRP Taskmaster' MCP server end-to-end with an MCP-specific PRP template, ending
  with 18 working tools after a two-shot build.
---

# Context Engineering 101 - The Simple Strategy to 100x AI Coding

> Cole goes deep on context engineering with the PRP (Product Requirement Prompt) framework - including a guest interview with its creator Rasmus - then live-builds a 'PRP Taskmaster' MCP server end-to-end with an MCP-specific PRP template, ending with 18 working tools after a two-shot build.

**Watch:** https://www.youtube.com/watch?v=Mk87sFlUG28

> ✅ *Summary, key ideas, and tools verified against the full video transcript.*

# Key Ideas
- Context engineering is a superset of prompt engineering: provide all the info, examples, best practices, and constraints up front instead of tweaking words on a single prompt
- Rasmus defines a PRP as 'a PRD + curated codebase intelligence + agent runbook' - the minimum viable packet to ship production code on the first pass
- Workflow: fill out `initial.md` → run the create/generate command (research + planning) → VALIDATE the PRP yourself → run execute
- Validation is stressed throughout: read the PRP before executing, test every tool, have the AI write tests - don't trust it blindly
- Split of responsibilities: CLAUDE.md holds constant rules; slash commands are generic drop-ins; the base PRP holds the work-specific context
- Model gains matter: with Claude 3.7 ~100-line PRPs were reliable; with Claude 4 Rasmus reliably runs 500-line and has run 1000-1500-line prompts
- The central demo builds an MCP server (Cloudflare Workers + TypeScript + Postgres + GitHub OAuth), replicating Claude Taskmaster; method is tool-agnostic

# Tools & Projects
Claude Code, PRP framework, initial.md, context-engineering-intro repo (MCP template), Cloudflare Workers + Wrangler, TypeScript, Postgres, GitHub OAuth, Claude Taskmaster, Claude Desktop, Gemini CLI / Cursor / Windsurf

# Links
- Companion repo: https://github.com/coleam00/context-engineering-intro

# Related Concepts
- [Context Engineering & the PRP Framework](../concepts/context-engineering.md) - Cole's signature thesis: AI coding assistants fail from missing context, not weak models - so engineer the context up front.
- [The PIV Loop (Plan → Implement → Validate)](../concepts/the-piv-loop.md) - Cole's core operating loop: you own the planning and validation, the agent owns the implementation - you stay in the driver's seat.
