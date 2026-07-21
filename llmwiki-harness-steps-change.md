# LLMWiki Harness — How to Change Steps

This document maps every file you need to touch when adding, removing, or reordering steps
in either the Lambda harness or the Neuro-SAN harness, for both UC1 (Sales-to-Service) and
UC-PM (Problem Management).

---

## Two independent implementations

The Lambda harness and the Neuro-SAN harness share no step logic. Changes to one do not
affect the other.

| | Lambda harness | Neuro-SAN harness |
|---|---|---|
| **Orchestration** | Hard-coded Python — phases run in a fixed sequence | LLM-orchestrated — the agent decides when to call each tool |
| **Pause point** | Always at Phase 3 (human input gate) | Conversational — the agent asks questions naturally |
| **Step enforcement** | Phase numbers are locked; UI tracks them explicitly | Numbered STEP instructions in the HOCON prompt |
| **Adding a step** | New Python function + sequence call + UI list entry | New paragraph in `instructions` block |

---

## Lambda harness — files to touch

### UC1 Sales-to-Service

| What you are changing | File |
|---|---|
| Phase logic — what the step does | `code/lambda/harness/uc1_harness/handler.py` — add/edit `_phaseN_*` function |
| Orchestration flow — add/remove phase, change order, move pause point | Same file — the resume path block in `lambda_handler` (~line 263) |
| Phase tracker UI — phase name, icon, skill badge, summary line | `code/streamlit/pages/lambda_harness.py` — `AGENTS["s2s"]["phases"]` list and `_phase_summary()` |
| Downloaded HTML report content | `code/lambda/harness/uc1_harness/handler.py` — `_build_report_html()` |
| Completion message shown in chat | `code/streamlit/pages/lambda_harness.py` — `_completion_message()`, `else:` branch |

### UC-PM Problem Management

| What you are changing | File |
|---|---|
| Phase logic — what the step does | `code/lambda/harness/pm_harness/handler.py` — add/edit `_phaseN_*` function |
| Orchestration flow — add/remove phase, change order | Same file — `_start_workflow()` (phases 1–3 + pause) and `_resume_workflow()` (phases 4–8) |
| Phase tracker UI | `code/streamlit/pages/lambda_harness.py` — `AGENTS["pm"]["phases"]` list and `_phase_summary()` |
| Downloaded HTML report content | `code/lambda/harness/pm_harness/handler.py` — `_build_report_html()` |
| Completion message shown in chat | `code/streamlit/pages/lambda_harness.py` — `_completion_message()`, `if agent_id == "pm":` branch |

### Checklist for adding one Lambda phase (both harnesses)

1. Write `_phaseN_name(...)` function in the handler.
2. Call it in sequence and call `_save_phase(table, ..., N, phaseN, accumulated)` immediately after.
3. Add `{"num": N, "name": "...", "type": "...", "skill": "SK-XX", "icon": "..."}` to `AGENTS[...]["phases"]`.
4. Handle `phase_num == N` in `_phase_summary()` to show a one-line status in the UI tracker.
5. If the new phase writes an artifact, add it to `_write_session_wrapup()` artifacts list.
6. Rebuild and push the Lambda zip; rebuild the Streamlit Docker image for the UI change.

---

## Neuro-SAN harness — files to touch

### UC1 Sales-to-Service

| What you are changing | File |
|---|---|
| Step sequence and instructions — add/remove/reorder steps, change what each step does | `code/registries/llmwiki/uc1_sales_to_service.hocon` — numbered `STEP 1–6` list inside `UC1SalesToServiceAgent.instructions` |
| Add a new sub-agent/skill to the orchestrator | Same HOCON — add agent block + add its name to `UC1SalesToServiceAgent.tools` list |
| Sub-agent prompt or description | Same HOCON — each named agent block has its own `function.description` and `instructions` |
| Sub-agent Python implementation | `code/neuro_san/coded_tools/llmwiki/` — one `.py` file per skill |

### UC-PM Problem Management

| What you are changing | File |
|---|---|
| Step sequence and instructions | `code/registries/llmwiki/uc_pm_problem_management.hocon` — numbered `STEP 1–7` list inside `UCPMProblemManagementAgent.instructions` |
| Add a new sub-agent/skill | Same HOCON — add agent block + add to `UCPMProblemManagementAgent.tools` list |
| Sub-agent prompt or description | Same HOCON — agent block `function.description` and `instructions` |
| Sub-agent Python implementation | `code/neuro_san/coded_tools/llmwiki/` — new `.py` file (e.g. `my_new_tool.py`) |

### Registering a new HOCON network

| What you are changing | File |
|---|---|
| Add a new use-case network | `code/registries/llmwiki/manifest.hocon` — add entry pointing to the new HOCON file |

### Checklist for adding one Neuro-SAN step (both harnesses)

1. Add a `STEP N —` paragraph to the orchestrator `instructions` block in the HOCON.
2. If the step needs a new tool: add an agent block in the same HOCON with `function.description` and `instructions`.
3. Add the new agent name to the orchestrator `"tools": [...]` list.
4. If the tool needs custom Python logic: create `code/neuro_san/coded_tools/llmwiki/my_tool.py` implementing `BaseTool`.
5. Rebuild and push the Streamlit Docker image (registries and coded_tools are baked into the container).

---

## If you are changing both harnesses for the same logical step

Do all of the above independently — there is no shared code path between them.
The Lambda harness is invoked from the **Lambda Harness** Streamlit page.
The Neuro-SAN harness runs via the **Neuro SAN** Streamlit page through nsflow.

---

## Current step inventory

### Lambda — UC1 (9 phases including wrap-up)

| Phase | Name | Type | Skill |
|---|---|---|---|
| 1 | SOW Intake & Extraction | Programmatic | — |
| 2 | Customer Classification | Claude (LLM) | — |
| 3 | Gather Handoff Context | Human input gate | — |
| 4 | Load Delivery Playbook | Agent | SK-01 |
| 5 | Risk & Gap Analysis | Agent | SK-02 |
| 6 | Gap Detection & Recording | Parallel agents | SK-05 |
| 7 | Template Population | Agent | SK-04 |
| 8 | Write Handoff + Report | Claude (LLM) | SK-03 |
| 9 | Session Wrap-up | Programmatic | — |

### Lambda — UC-PM (9 phases including wrap-up)

| Phase | Name | Type | Skill |
|---|---|---|---|
| 1 | Problem Record Load | Programmatic | — |
| 2 | Problem Classification | Claude (LLM) | SK-06 |
| 3 | SME Context Collection | Human input gate | — |
| 4 | Load Prior Knowledge | Agent | SK-01 |
| 5 | RCA Draft & Cross-System Patterns | Agent | SK-02 |
| 6 | Knowledge Gap Detection | Agent | SK-05 |
| 7 | Fill RCA & KEDB Templates | Claude (LLM) | SK-04 |
| 8 | Write Draft & Route Review | Programmatic | SK-03 |
| 9 | Session Wrap-up | Programmatic | — |

### Neuro-SAN — UC1 (6 steps)

| Step | Action | Tool |
|---|---|---|
| 1 | Load customer history and UC1 playbook | ContextBootstrap (SK-01) |
| 2 | Delivery risk query | WikiQuery (SK-02) |
| 3 | Gap detection if confidence < high | GapDetection (SK-05) |
| 4 | Populate persona template | ArtifactResolution (SK-04) |
| 5 | Compose handoff brief markdown | — (LLM synthesis) |
| 6 | Index to wiki | WikiContribute (SK-03) |

### Neuro-SAN — UC-PM (7 steps)

| Step | Action | Tool |
|---|---|---|
| 1 | Classify problem record | ProblemClassifier (SK-06) |
| 2 | Ask SME questions, wait for answers | — (conversational) |
| 3 | Load prior RCAs and KEDB | ContextBootstrap (SK-01) |
| 4 | Query KEDB patterns | WikiQuery (SK-02) |
| 5 | Draft Root Cause Analysis | — (LLM synthesis) |
| 6 | Populate RCA and KEDB templates | ArtifactResolution (SK-04) |
| 7 | Save RCA draft to review queue | WikiContribute (SK-03) |
