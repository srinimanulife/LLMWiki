---
type: concept
title: The PIV Loop (Plan → Implement → Validate)
tags:
- piv-loop
- agentic-coding
- workflow
- human-in-the-loop
related_videos:
- principled-agentic-engineer
- code-100x-faster-with-ai
- complete-guide-to-claude-code
- context-engineering-101
- harness-engineering-archon
timestamp: '2026-06-25'
description: 'Cole''s core operating loop: you own the planning and validation, the
  agent owns the implementation - you stay in the driver''s seat.'
---

# The PIV Loop (Plan → Implement → Validate)

The discipline at the center of Cole's system. The engineer's job has shifted
from writing code to the higher-leverage work of **planning and validating** -
and crucially this is *not* vibe coding, because a human stays in the driver's
seat through every plan and every validation gate.

The loop is **Plan → Implement → Validate**, run once per ticket:

- **Plan** in two layers - Layer 1 is project/PM-level (high-level features and
  bugs, no code); Layer 2 is task-level (dig into the codebase, find the files to
  touch). Both start as an unstructured brain dump, then move to structure; the
  key skill is having the agent ask clarifying questions one at a time to reduce
  its assumptions.
- **Implement** in a *fresh* session, separate from planning, so the agent comes
  in with unbiased eyes. Use sub-agents for research to manage context - they can
  burn 100k+ tokens exploring and return a few-thousand-token summary.
- **Validate** - the agent runs its own tests, linting, type-checking, even
  end-to-end browser testing, while the human reviews every artifact (PRD, plan,
  code). "Just because you can fit a million tokens doesn't mean you should."

Discipline that recurs across the videos: keep files small, one feature per
prompt, commit working states to git, and **never trust the AI with secrets**.

# Videos on this
- [FULL Guide to Becoming a Principled Agentic Engineer (Build Anything with AI)](../videos/principled-agentic-engineer.md)
- [Code 100x Faster with AI, Here's How (No Hype, FULL Process)](../videos/code-100x-faster-with-ai.md)
- [A Complete Guide to Claude Code - Here are ALL the Best Strategies](../videos/complete-guide-to-claude-code.md)
- [Context Engineering 101 - The Simple Strategy to 100x AI Coding](../videos/context-engineering-101.md)
- [The Next Evolution of AI Coding Is Harnesses - Here's How to Build Them](../videos/harness-engineering-archon.md)
