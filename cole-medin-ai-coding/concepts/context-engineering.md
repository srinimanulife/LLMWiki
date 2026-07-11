---
type: concept
title: Context Engineering & the PRP Framework
tags:
- context-engineering
- prp
- prompt-engineering
- ai-coding-workflow
related_videos:
- context-engineering-101
- complete-guide-to-claude-code
- code-100x-faster-with-ai
timestamp: '2026-06-25'
description: 'Cole''s signature thesis: AI coding assistants fail from missing context,
  not weak models - so engineer the context up front.'
---

# Context Engineering & the PRP Framework

The idea Cole's whole approach is built on: an AI coding assistant almost never
fails because the model is too weak - it fails because it was given too little of
the right context. **Context engineering** is a superset of prompt engineering:
instead of tweaking words on a single prompt, you hand the assistant everything
it needs up front - architecture, project rules, concrete examples, and
validation criteria.

The central artifact is the **PRP (Product Requirements Prompt)** - "a PRD +
curated codebase intelligence + agent runbook," the minimum viable packet an AI
needs to ship production code on the first pass. Context engineering is the middle
beat of the broader arc Cole teaches: **prompt engineering → context engineering →
harness engineering** (the last automated by [[archon-harness-builder]]).

This is the same instinct behind OKF and Karpathy's LLM wiki: **curate knowledge
once, in a form the model can consume directly, instead of re-deriving it every
time.**

# Videos on this
- [Context Engineering 101 - The Simple Strategy to 100x AI Coding](../videos/context-engineering-101.md)
- [A Complete Guide to Claude Code - Here are ALL the Best Strategies](../videos/complete-guide-to-claude-code.md)
- [Code 100x Faster with AI, Here's How (No Hype, FULL Process)](../videos/code-100x-faster-with-ai.md)
