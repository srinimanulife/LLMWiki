---
type: video
title: A Complete Guide to Claude Code - Here are ALL the Best Strategies
resource: https://www.youtube.com/watch?v=amEUIuBKwvg
channel: Cole Medin (@ColeMedin)
published: 2025-08 (approximate)
source: transcript-verified
tags:
- claude-code
- context-engineering
- mcp
- subagents
- agentic-engineering
- ai-coding-workflow
related_concepts:
- context-engineering
- the-ai-layer
- the-piv-loop
- mcp-integration-layer
timestamp: '2026-06-25'
description: A start-to-finish masterclass on Claude Code, built up as a README of
  strategies in Cole's context-engineering repo. He walks through global rules, permissions,
  custom slash commands, MCP servers (Serena, Archon), the PRP framework, sub-agents,
  hooks, the GitHub CLI, YOLO mode in dev containers, and parallel agents via git
  worktrees - stressing how each generalizes to any AI coding assistant.
---

# A Complete Guide to Claude Code - Here are ALL the Best Strategies

> A start-to-finish masterclass on Claude Code, built up as a README of strategies in Cole's context-engineering repo. He walks through global rules, permissions, custom slash commands, MCP servers (Serena, Archon), the PRP framework, sub-agents, hooks, the GitHub CLI, YOLO mode in dev containers, and parallel agents via git worktrees - stressing how each generalizes to any AI coding assistant.

**Watch:** https://www.youtube.com/watch?v=amEUIuBKwvg

> ✅ *Summary, key ideas, and tools verified against the full video transcript.*

# Key Ideas
- `CLAUDE.md` is the system prompt you craft for Claude Code; keep it sparse and reference external pattern/best-practice files rather than inlining
- Permissions live in `settings.local.json` allow-lists - never allow `rm` or a blanket `bash *`; be explicit about commands
- Serena MCP is a 'game-changer' for semantic code retrieval/editing on larger existing codebases; allow MCP tools via the `mcp__<server>` syntax
- Sub-agents each have their own context window and system prompt; the PRIMARY agent crafts the prompt, invokes them, and can run many in parallel
- Hooks add deterministic control at lifecycle points via scripts referenced in settings (demo: a bash hook logging every edit with a timestamp)
- GitHub CLI + a `/fix-github-issue` command lets Claude take an issue → fix → test → branch → push → open a PR end-to-end
- YOLO mode (`--dangerously-skip-permissions`) made safe inside Anthropic's dev container; parallel agents via git worktrees build the same feature N ways so you pick the best

# Tools & Projects
Claude Code, CLAUDE.md, settings.local.json, MCP, Serena MCP, Archon (v2 beta), PRP framework, sub-agents, hooks, GitHub CLI, dev containers, git worktrees, Pydantic AI (demo agent), Cursor / Windsurf / Cline

# Related Concepts
- [Context Engineering & the PRP Framework](../concepts/context-engineering.md) - Cole's signature thesis: AI coding assistants fail from missing context, not weak models - so engineer the context up front.
- [The AI Layer (Rules, Commands, Skills) & System Evolution](../concepts/the-ai-layer.md) - The versioned, reusable layer - rules, commands, skills - that turns a coding assistant into a system that compounds over time.
- [The PIV Loop (Plan → Implement → Validate)](../concepts/the-piv-loop.md) - Cole's core operating loop: you own the planning and validation, the agent owns the implementation - you stay in the driver's seat.
- [MCP as the Integration Layer for AI Coding](../concepts/mcp-integration-layer.md) - Model Context Protocol is the standard wiring Cole uses to plug knowledge, tools, and tasks into any AI coding assistant.
