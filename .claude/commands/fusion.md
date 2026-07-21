# /fusion — Three-Agent Fusion

Run two worker agents in parallel, then a third merge agent synthesises their outputs
into a single best answer with explicit attribution.

## Usage
```
/fusion "<worker prompt>" "<optional merge instruction>"
```
If merge instruction is omitted, the default is: *"Merge the two responses into one superior answer,
preserving the best reasoning from each. Attribute each insight to its source model."*

## What happens
1. **Worker A** (Claude architect role) answers the worker prompt.
2. **Worker B** (Codex via Azure proxy) answers the same worker prompt.
3. **Merge agent** (Claude, fresh context) receives both answers and the merge instruction,
   then produces a single fused response.

## Instructions for Claude

When invoked with `$ARGUMENTS` (format: `"<worker_prompt>" "<merge_instruction>"`):

Parse arguments: first quoted string = WORKER_PROMPT, second quoted string = MERGE_INSTRUCTION
(default merge instruction if omitted: see above).

**Step 1 — Architect answer.**
Answer WORKER_PROMPT fully. Save internally as ANSWER_A. Display:
```
## 🏛 Worker A — Claude (Architect)
<answer>
```

**Step 2 — Codex answer.**
POST to `http://127.0.0.1:18080/openai/responses`:
```json
{
  "model": "gpt-5.3-codex-2",
  "input": "<WORKER_PROMPT>",
  "reasoning": { "effort": "high" }
}
```
Header: `Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e`
Extract response text as ANSWER_B. Display:
```
## ⚡ Worker B — gpt-5.3-codex-2 (Builder)
<answer>
```

**Step 3 — Fusion merge.**
Now act as the FUSION merge agent (clear your task framing; you are now synthesising, not answering).
Merge ANSWER_A and ANSWER_B using the MERGE_INSTRUCTION. Display:

```
---
## 🔀 FUSED OUTPUT
*Merged by Claude acting as Fusion Agent*

<merged answer with [Architect] / [Builder] attribution on specific insights>

### Attribution Map
| Insight | Source |
|---------|--------|
| ... | [Architect] / [Builder] / [Both] |
```
