---
type: video
title: Code 100x Faster with AI, Here's How (No Hype, FULL Process)
resource: https://www.youtube.com/watch?v=SS5DYx6mPw8
channel: Cole Medin (@ColeMedin)
published: 2025-03 (approximate)
source: transcript-verified
tags:
- ai-coding-workflow
- mcp
- supabase
- planning-docs
- ai-coding-security
- cursor-windsurf
related_concepts:
- the-piv-loop
- mcp-integration-layer
- context-engineering
timestamp: '2026-06-25'
description: An end-to-end walkthrough of Cole's structured AI-coding workflow, driven
  by a Google Doc of 'golden rules' and a numbered process (planning → global rules
  → MCP setup → specific prompt → iteration → testing → deployment). He one-shots
  a working Supabase MCP server (~300 lines) in Windsurf, tests it in Claude Desktop,
  then adds git, 14 passing tests, a README, and a Dockerfile.
---

# Code 100x Faster with AI, Here's How (No Hype, FULL Process)

> An end-to-end walkthrough of Cole's structured AI-coding workflow, driven by a Google Doc of 'golden rules' and a numbered process (planning → global rules → MCP setup → specific prompt → iteration → testing → deployment). He one-shots a working Supabase MCP server (~300 lines) in Windsurf, tests it in Claude Desktop, then adds git, 14 passing tests, a README, and a Dockerfile.

**Watch:** https://www.youtube.com/watch?v=SS5DYx6mPw8

> ✅ *Summary, key ideas, and tools verified against the full video transcript.*

# Key Ideas
- Use higher-level markdown docs - a `planning.md` (vision/architecture/stack) and a `task.md` - created in a chatbot before any coding
- Don't overwhelm the LLM (longer context → more hallucination): keep files under 500 lines, start fresh conversations, do one feature per prompt
- Ask the AI to write tests after each feature; be specific (name libraries, desired output); write docs as you go
- Implement env vars yourself - never trust the LLM with API keys/DB security (shows the viral hacked-SaaS cautionary tale)
- Global rules = the assistant's system prompt; project-specific rules are preferred over global ones
- His three core MCP servers: filesystem, Brave Search (web search), and Git (commit working states so you can revert when the AI breaks things)
- The specific initial prompt matters most - feed docs/examples via IDE doc-pulling, Brave search, or manual links (a sample MCP-server repo)

# Tools & Projects
Windsurf, Cursor, Cline, Roo Code, Claude Desktop, Supabase, MCP, filesystem MCP, Brave Search MCP, Git MCP, Qdrant MCP, Docker, Python / pytest

# Related Concepts
- [The PIV Loop (Plan → Implement → Validate)](../concepts/the-piv-loop.md) - Cole's core operating loop: you own the planning and validation, the agent owns the implementation - you stay in the driver's seat.
- [MCP as the Integration Layer for AI Coding](../concepts/mcp-integration-layer.md) - Model Context Protocol is the standard wiring Cole uses to plug knowledge, tools, and tasks into any AI coding assistant.
- [Context Engineering & the PRP Framework](../concepts/context-engineering.md) - Cole's signature thesis: AI coding assistants fail from missing context, not weak models - so engineer the context up front.
