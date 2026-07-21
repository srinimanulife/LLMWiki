# LLMWiki Harness Improvement — Agent Session Lifecycle

**Source reference:** https://github.com/walkinglabs/learn-harness-engineering  
**Context:** LLMWiki already has a Hard Harness for UC1 and UC-PM (8 system-enforced phases, gatekeeper validation). This document identifies what is missing from the **WRAP UP** side and recommends concrete additions.

---

## What We Already Have

| Subsystem | LLMWiki Status |
|---|---|
| Instructions harness | ✅ HOCON agent definitions, CLAUDE.md |
| State (feature tracking) | ⚠️ Partial — no `feature_list.json` or `claude-progress.md` |
| Verification (phases) | ✅ 8-phase hard harness with gatekeeper |
| Scope (bounded changes) | ✅ per-use-case Lambda + skill isolation |
| **Session Lifecycle** | ❌ **START and DURING are present; WRAP UP is missing entirely** |

The harness enforces what happens during a workflow. It does **not** enforce what gets captured, committed, or handed off when the session ends.

---

## What Is Missing: WRAP UP

The `learn-harness-engineering` course defines five non-negotiables at session end:

1. Build compiles without errors
2. All tests pass
3. Progress recorded in machine-readable artifacts
4. No temp files, debug code, or TODOs left behind
5. Next session can start without manual intervention

LLMWiki satisfies none of these at session end. The agent completes the 8 phases, emits a final response, and stops. There is no:

- Session summary artifact written to S3 or DynamoDB
- `session-handoff.md` equivalent for the next agent invocation
- Machine-readable record of what the agent did, found, or decided
- Cleanup pass on temp/intermediate artefacts
- Confidence rating for the session outcome

---

## Recommended Additions

### 1. Session Wrap-Up Lambda Phase (Phase 9)

Add a mandatory **Phase 9 — Session Wrap-Up** to both harnesses (UC1 and UC-PM). This phase runs unconditionally at the end of every workflow and writes a compact session record.

**What Phase 9 writes to DynamoDB `llmwiki-log`:**

```python
{
  "log_date":       "session#<harness_id>#<date>",
  "timestamp_id":   "<iso-timestamp>#<session_id>",

  # What was verified
  "phases_completed": ["phase-1", "phase-2", ..., "phase-8"],
  "phases_failed":    [],            # any phase that raised an exception
  "outcome":          "success",     # success | partial | failed

  # What was produced
  "artifacts_written": [
    "s3://llmwiki-278e7e22/wiki/decisions/rca-PRB0042-draft.md",
    "s3://llmwiki-278e7e22/wiki/pending/..."
  ],

  # What should happen next
  "handoff": {
    "next_best_step":   "SME review of RCA draft within 24h",
    "open_items":       ["confirm symptom timestamp", "verify DB connectivity"],
    "risk_flags":       ["no deployment change found — infra drift likely"],
    "confidence":       "medium"
  },

  # Audit
  "agent_id":     "UC-PM-ProblemManagementAgent",
  "session_id":   "<uuid>",
  "user_id":      "None",
  "harness_version": "v1.2"
}
```

**Implementation:** Add `_write_session_wrapup()` to `llmwiki-harness-uc-pm` and `llmwiki-uc1-harness` Lambdas, called from a `try/finally` block so it runs even if earlier phases raise.

---

### 2. Handoff Context Passed Into Next Session (Session Memory)

The hard harness gatekeeper currently validates prerequisites from scratch each time. It should first check for a prior session record in DynamoDB and use it to pre-load context:

```python
# In gatekeeper Lambda
def load_prior_session(engagement_id: str) -> dict:
    """Return the most recent wrap-up record for this engagement."""
    table = dynamodb.Table("llmwiki-log")
    resp = table.query(
        KeyConditionExpression="log_date = :lk",
        ExpressionAttributeValues={":lk": f"session#{harness_id}#{today}"},
        ScanIndexForward=False,
        Limit=1,
    )
    return resp.get("Items", [{}])[0]
```

The gatekeeper injects `prior_session.handoff.open_items` into the Phase 1 system prompt so the agent picks up exactly where the last session ended — rather than re-discovering the same context from scratch.

**Benefit (from harness course):** Without state persistence, context rebuild takes ~15 minutes per session. With it, under 3 minutes.

---

### 3. Artifact Cleanup Pass

After phase 8, before writing the session record, run a lightweight cleanup check:

```python
CLEANUP_CHECKS = [
    ("pending_wiki_pages",  lambda s: list_s3_pending(s)),   # warn if >10 unreviewed
    ("orphan_gap_stubs",    lambda: get_gaps(status="stub_created", limit=50)),
    ("stale_traces_today",  lambda: count_traces_today()),   # confirm traces written
]
```

Log any cleanup findings into the session record under `"cleanup_warnings"`. This surfaces drift before it accumulates across sessions (the "Clean Up Later trap" the course explicitly warns about).

---

### 4. `session-handoff.md` Written to S3

After every completed engagement workflow, write a human-readable handoff file:

**Path:** `s3://llmwiki-<bucket>/sessions/<engagement_id>/<date>-handoff.md`

**Template:**
```markdown
# Session Handoff — <harness_id> — <date>

## Verified Now
- Phases 1–8 completed successfully
- Artifacts: <list>
- Confidence: <level>

## Changed This Session
- Created: <list of S3 keys written>
- Modified: <list>

## Open / Unverified
- <open_items from wrap-up record>
- <risk_flags>

## Next Best Step
<next_best_step text>

**Passing criteria for next session:** <what must be true for this to be resolved>
**Do not change:** <any stability invariants — e.g., approved KB ID, engagement metadata>
```

This file is surfaced in the **Harness Demo UI** at the bottom of each completed workflow run, and is also readable by the next agent invocation via gatekeeper pre-load.

---

### 5. Maker / Checker Split for High-Risk Sessions

The harness course's most important rule for automated loops: **the agent that writes cannot reliably judge its own output.**

For UC-PM (problem management), this is particularly important for RCA drafts. Add an independent **checker phase** after Phase 8:

- **Maker** (existing): UC-PM agent produces the RCA skeleton
- **Checker** (new, Phase 9a): A separate Lambda invocation with a different system prompt — reads the draft, scores it against: completeness (symptom, cause, change, action, timeline), factual consistency with the source knowledge base, risk tier assignment accuracy

The checker writes a `checker_verdict` field into the session wrap-up record:

```json
{
  "checker_verdict": {
    "completeness_score": 4,
    "max_score": 5,
    "flags": ["symptom timestamp missing", "no upstream validation step"],
    "approved": false
  }
}
```

If `approved: false`, the artifact routes to `wiki/pending/` (already implemented) — but now with specific remediation notes visible in the Harness Demo UI rather than a generic "pending review" message.

---

### 6. Context Anxiety Protocol

From Lecture 05 of the harness course: if a session is approaching context limits, it must **not rush to finish** — instead it must write a checkpoint and stop cleanly.

Add a context budget check to the harness Lambda:

```python
MAX_PHASES_BEFORE_CHECKPOINT = 6   # If Phase 7+ would exceed token budget, checkpoint instead

def _should_checkpoint(phases_done: int, token_estimate: int) -> bool:
    return phases_done >= MAX_PHASES_BEFORE_CHECKPOINT and token_estimate > 50_000
```

If triggered: write a `"checkpoint"` session record instead of `"success"`, surface it in the UI as "⚠️ Session checkpointed — continue from Phase N", and let the next session resume from that phase using the prior_session loader in step 2.

---

## Implementation Priority

| Priority | Change | Effort | Impact |
|---|---|---|---|
| P1 | Phase 9 wrap-up write to DynamoDB | 1 day | High — every session produces a record |
| P1 | Prior session load in gatekeeper | 1 day | High — eliminates 12-min context rebuild |
| P2 | `session-handoff.md` to S3 + UI surface | 1 day | Medium — human visibility |
| P2 | Artifact cleanup warnings | 0.5 days | Medium — prevents drift accumulation |
| P3 | Maker/checker split (UC-PM RCA) | 2 days | High quality — prevents bad RCA drafts |
| P3 | Context anxiety checkpoint | 1 day | Resilience for long sessions |

---

## What NOT to Change

The existing 8-phase structure is sound. The harness course explicitly warns against over-harness complexity — add only what the session lifecycle is missing (wrap-up and continuity), not new verification layers on top of what already works.

The gatekeeper pattern (prerequisite validation before Phase 1) is correct and matches the course's "fix broken baseline first" principle. Keep it.
