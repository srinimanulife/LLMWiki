---
type: concept
title: The AI Layer (Rules, Commands, Skills) & System Evolution
tags:
- ai-layer
- rules
- commands
- skills
- system-evolution
related_videos:
- principled-agentic-engineer
- complete-guide-to-claude-code
- harness-engineering-archon
timestamp: '2026-06-25'
description: The versioned, reusable layer - rules, commands, skills - that turns
  a coding assistant into a system that compounds over time.
---

# The AI Layer (Rules, Commands, Skills) & System Evolution

What turns a one-off assistant into a *system*: a reusable **AI layer** you build
up and check into source control like code.

- **Global rules** - your coding, testing, and logging conventions, always
  loaded (CLAUDE.md / AGENTS.md).
- **Commands & skills** - reusable workflows. The rule of thumb: anytime you've
  prompted something more than ~three times, turn it into a command or skill, and
  minimize manual prompting.

The most powerful part is **system evolution** - two loops. The *inner loop* is
the PIV loop when everything works: just chug through tickets. The *outer loop*
fires after a bug - you run a retroactive session asking the agent to inspect its
*own* AI layer (rules, commands, skills, plan/PRD templates) and improve it so
that whole class of issue never recurs.

Because the AI layer lives in source control and ships via pull requests with
code review, one engineer's improvement can save the rest of the team dozens of
hours. Cole's deliberate stance: **start simple** and mold this foundation to
your own SDLC rather than adopting a bloated off-the-shelf framework.

# Videos on this
- [FULL Guide to Becoming a Principled Agentic Engineer (Build Anything with AI)](../videos/principled-agentic-engineer.md)
- [A Complete Guide to Claude Code - Here are ALL the Best Strategies](../videos/complete-guide-to-claude-code.md)
- [The Next Evolution of AI Coding Is Harnesses - Here's How to Build Them](../videos/harness-engineering-archon.md)
