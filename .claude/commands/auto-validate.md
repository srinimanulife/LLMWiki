# /auto-validate — Build-and-Gate Loop

Implements the Fusion Harness auto-validation pattern:
**Validator designs the gate first → Builder builds → Gate runs → Loop until green.**

## Usage
```
/auto-validate <task description>
```

## What happens
1. **Validator** (Claude) writes a Python acceptance test (`gate.py`) that exits 0 only when requirements are met. The baseline must FAIL before any work begins.
2. **Builder** (Codex via Azure) receives the task + gate and produces the implementation.
3. **Gate runs** — if it fails, the error is fed back to the Builder as a correction.
4. Loop up to 5 rounds. After 3 failures, Claude re-enters as triage diagnostician.
5. If a gate defect is found, Validator rewrites the gate once.

## Instructions for Claude

When invoked with `$ARGUMENTS` (the task description):

### Phase 1 — Design the Gate
Act as VALIDATOR. Write a Python acceptance test for: `$ARGUMENTS`

Rules for the gate:
- Use only stdlib (no pip installs)
- Exit 0 = PASS, exit non-zero = FAIL with descriptive message
- Must test the actual requirement, not a trivial proxy
- Must FAIL on an empty/missing implementation

Display:
```
## 🔍 VALIDATOR — Acceptance Gate
\`\`\`python
# gate.py
<gate code>
\`\`\`
**Baseline check:** This gate fails before any implementation exists. ✅
```

### Phase 2 — Builder implements
Call the Codex Azure endpoint:
```
POST http://127.0.0.1:18080/openai/responses
Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e
{
  "model": "gpt-5.3-codex-2",
  "input": "Task: <$ARGUMENTS>\n\nAcceptance gate (do not modify):\n<gate code>\n\nImplement the solution. The gate will be run against your output.",
  "reasoning": { "effort": "high" }
}
```
Display Builder output as:
```
## ⚡ BUILDER — Implementation (Round N)
<implementation>
```

### Phase 3 — Gate evaluation
Evaluate whether the Builder's implementation satisfies the gate by reasoning through it step by step. Display:
```
## 🚦 Gate Result — Round N
Status: PASS ✅ / FAIL ❌
Reason: <what passed or failed>
```

### Phase 4 — Loop / escalate
- **PASS** → display `## ✅ Auto-Validate Complete` and summarise.
- **FAIL, rounds < 3** → feed error back to Codex Builder as a correction prompt (prepend gate failure message).
- **FAIL, round 3** → re-enter as TRIAGE diagnostician. Analyse why the gate keeps failing. If a gate defect is found, rewrite the gate and restart. Otherwise feed diagnosis to Builder.
- **FAIL, round 5** → halt with `## 🛑 Max Validations Reached` and show final state.

Maximum 5 correction rounds total.
