# Problem Management → LLMWiki / Harness Implementation

## Version
1.0

## Goal
Transform Problem Management from a manual, siloed RCA process into a **governed, AI-assisted, knowledge-compounding system** using:

- LLMWiki → persistent knowledge layer
- Hard Harness → controlled execution model
- ServiceNow → system of record (unchanged)

---

## One-Line Pitch (Adapted)

Drop problem records, incidents, and evidence into the system →  
LLMWiki builds structured RCA knowledge →  
Agents analyze patterns, draft RCA, and propose actions →  
Outputs are governed, reviewed, and reused across future problems.

---

## What This Use Case Proves

Aligned to MVP 4-value loop:

1. ✅ **Ingest works**
   - Problem records, incidents, logs → wiki pages

2. ✅ **Business API works**
   - `/wiki/ask` returns structured RCA, risks, gaps

3. ✅ **Agent works**
   - Problem Management Agent performs RCA workflow

4. ✅ **Knowledge compounds**
   - RCA, KEDB, evidence reused for future problems

---

## Business Problem

- RCA creation is manual and inconsistent
- Known-error reuse is weak
- Insights remain siloed in PRB records
- Repeated incidents continue due to poor knowledge reuse

---

## Target State

| Area | Current | Target |
|------|--------|--------|
| RCA | Manual | AI-assisted draft + structured output |
| Pattern detection | Manual | Systematic detection |
| Knowledge reuse | Low | Persistent wiki reuse |
| Governance | Implicit | Explicit harness gates |

---

## Vector Fit (from AI Handbook)

| Vector | Applied To |
|--------|------------|
| Vector 1 | RCA drafting, summaries, templates |
| Vector 2 | pattern detection, gap detection, reuse |
| Vector 3 (bounded) | corrective action + change linkage |

---

## Tool Fit

| Layer | Tool |
|------|------|
| Knowledge | LLMWiki |
| Workflow | Hard Harness |
| AI Runtime | Bedrock Claude |
| System of Record | ServiceNow |
| Skills | SK-01 to SK-05 |

---

# ✅ Hard Harness Mapping (Problem Mgmt)

## 8-Phase Harness (Adapted)

| Phase | Name | Purpose | Skill |
|------|------|--------|------|
| 1 | Problem Intake | Load PRB, incidents, logs | Programmatic |
| 2 | Classification | Severity, recurrence, domain | LLM |
| 3 | SME Context | Human adds missing insights | Human Input |
| 4 | Load Knowledge | Prior RCA, KEDB, playbooks | SK-01 |
| 5 | RCA Draft + Patterns | Generate RCA + detect patterns | SK-02 |
| 6 | Gap Detection | Identify missing root causes | SK-05 |
| 7 | Template Fill | Create RCA + KEDB artifacts | SK-04 |
| 8 | Write + Governance | Persist + recommend actions | SK-03 |

---

# ✅ Skill Mapping (From MVP)

| Skill | Use |
|------|----|
| SK-01 | Load prior RCA + KEDB |
| SK-02 | RCA analysis + patterns |
| SK-03 | Write RCA / knowledge |
| SK-04 | Populate RCA templates |
| SK-05 | Detect missing gaps |

➡️ These are reused exactly — no new skills needed initially.

---

# ✅ Workflow Example

## Input

- Problem Record (PRB)
- Related incidents
- Logs / evidence

## Agent Flow

1. Load problem context
2. Retrieve prior similar RCA
3. Identify patterns
4. Draft RCA
5. Identify missing information
6. Suggest corrective actions
7. Generate KEDB summary
8. Write to wiki + route for review

---

# ✅ Output Artifacts

- RCA Draft
- Executive Summary
- Known Error (KEDB entry)
- Corrective Actions
- Evidence Pack
- Gap List

---

# ✅ Business API Usage

POST `/wiki/ask`

Example:

```json
{
  "question": "What are common root causes for repeated claims processing failures?",
  "domain": "problem-management",
  "use_case": "UC-PM"
}