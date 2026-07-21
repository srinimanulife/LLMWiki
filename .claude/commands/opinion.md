# /opinion — Dual-Model Opinion Fusion

Run both **Claude** (architect) and **Codex / gpt-5.3-codex-2** (builder) against the same prompt
independently, then display a side-by-side comparison.

## Usage
```
/opinion <your question or task>
```

## What happens
1. Claude answers the prompt directly in this session (ARCHITECT role).
2. A subagent calls the Azure Codex endpoint via the local proxy and returns its answer.
3. Both answers are shown side-by-side with a brief synthesis noting where they agree/differ.

## Instructions for Claude

When this command is invoked with `$ARGUMENTS`:

**Step 1 — Claude answers first.**
Produce your own complete answer to `$ARGUMENTS`. Label it clearly:

```
## 🏛 ARCHITECT (Claude $MODEL)
<your answer here>
```

**Step 2 — Call Codex.**
Make a POST request to `http://127.0.0.1:18080/openai/responses` with:
```json
{
  "model": "gpt-5.3-codex-2",
  "input": "<the same prompt from $ARGUMENTS>",
  "reasoning": { "effort": "high" }
}
```
Use `Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e`.
Extract `output[last].content[0].text` as the Codex answer. Label it:

```
## ⚡ BUILDER (gpt-5.3-codex-2 via Azure)
<codex answer here>
```

**Step 3 — Synthesize.**
Write a short `## 🔀 Synthesis` section (3–5 bullets) noting:
- Where both models agree (high-confidence signal)
- Where they diverge (worth deeper investigation)
- Which answer is more actionable for `$ARGUMENTS`
