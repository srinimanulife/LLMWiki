---
title: How to Write a Skill Spec
type: guide
domain: skills
---

# How to Write a Skill Spec (Business User Guide)

This guide explains how to describe a new AI agent capability so it can be turned into
a working, deployed skill. You do not need to write code. You write a structured
Markdown file — the code generator does the rest.

---

## The Two Things You Can Create

| What | File type | What it becomes |
|---|---|---|
| **A new skill** | `sk-NN-my-skill-name.md` | A Lambda function wired into the skill registry |
| **A workflow** | `wf-UC99-my-workflow.md` | A multi-skill harness that runs skills in the right order |

---

## Part 1 — Writing a Skill Spec

### When to write a skill spec

Write a new skill spec when an agent needs to **do something the existing 5 skills cannot do**.
Existing skills are:

| ID | Name | Does what |
|---|---|---|
| SK-01 | Customer Briefing Loader | Load customer history + playbook at session start |
| SK-02 | Knowledge Finder | Answer a question from the wiki KB |
| SK-03 | Knowledge Recorder | Write new knowledge back to the wiki |
| SK-04 | Template Auto-Fill | Retrieve and populate a template with real data |
| SK-05 | Missing Info Radar | Detect and record what the wiki doesn't know |

If your need is "look something up" → use SK-02. If it's "save something" → use SK-03.
Only write a new skill if those don't cover it.

---

### Skill Spec File Format

Save your file as `sk-NN-descriptive-name.md` in `wiki_seed/skills/`.
Use the next available number after SK-05.

```
---
skill_id: SK-NN             ← Next available number, e.g. SK-06
business_name: "..."        ← Plain English name, 3-5 words
technical_name: "...Skill"  ← CamelCase, ends in "Skill"
tier: 1 | 2 | 3             ← See tier guide below
version: "1.0"
use_case_tags: [UC1, UC2]   ← Which use cases need this?
domain: "..."               ← e.g. customer-onboarding, provisioning, compliance
---

# [business_name]

## What It Does
One or two sentences in plain language.
No jargon. Imagine explaining to a business analyst.

## When to Call
Describe the moment in a workflow when an agent should invoke this skill.
Include: what triggers it, what must have happened before, what must NOT
have happened yet.

## What It Needs (Inputs)
List every piece of information the skill requires to do its job.
For each input write:
  - Name (snake_case)
  - What it is (plain English)
  - Required or optional
  - Where it comes from (e.g. "from SK-01 output", "user provides", "harness variable")

## What It Produces (Outputs)
List every piece of information the skill returns.
For each output write:
  - Name (snake_case)
  - What it contains
  - How downstream skills or the harness should use it

## Business Rules
List any rules the skill must enforce regardless of what the agent asks.
Examples:
  - "Always require human review if the claim amount exceeds $50,000"
  - "Never overwrite an existing approved record"
  - "Return 'not_applicable' if customer_type is 'government'"

## What It Calls (Backend)
Describe what AWS services or existing Lambdas this skill needs to reach.
The generator will wire these up automatically if you name them.

Allowed backends (already deployed):
  - wiki_query            → asks the knowledge base (wraps llmwiki-business-query)
  - wiki_contribute       → saves a page to the wiki (wraps llmwiki-contribute)
  - playbook_get_customer → loads customer history
  - playbook_get_playbook → loads a UC playbook
  - bedrock_claude        → calls Claude directly (use for classification/synthesis)
  - dynamodb_read         → reads from a DynamoDB table (specify table name)
  - dynamodb_write        → writes to a DynamoDB table (specify table name)
  - s3_read               → reads an S3 object (specify bucket/prefix)
  - s3_write              → writes an S3 object (specify bucket/prefix)
  - sns_publish           → sends an SNS notification (specify topic)
  - lambda_invoke         → calls another Lambda (specify function name)

## Error Handling
What should the skill do if something goes wrong?
  - What is a "soft failure" (return partial result, log warning, continue)?
  - What is a "hard failure" (raise an error, stop the workflow)?
  - Should failures trigger an SNS alert?

## Example: Happy Path
Walk through one concrete example end-to-end:
  - Input values (use realistic test data)
  - What the skill does step by step
  - Output values

## Example: Edge Case
Describe one case where the inputs are unusual or incomplete.
  - What happens?
  - What does the output look like?

## Telemetry Fields
Which extra fields (beyond standard skill_id/latency/status) should be logged
to `llmwiki-log` so you can track this skill's usage?
```

---

### Tier Guide

| Tier | Meaning | Examples |
|---|---|---|
| **1 — Universal** | Every agent in the fleet needs this | Load context, query wiki, write wiki |
| **2 — Common** | Most agents need this for specific phases | Fill template, detect gaps, check gate |
| **3 — Domain-specific** | Only agents in one domain need this | Claim validation, test scenario builder |

---

## Part 2 — Writing a Workflow Spec

A workflow spec describes **how skills are composed for a specific use case**. It replaces the hardcoded phase sequence in the UC1 harness with a declarative file any business user can write.

Save your file as `wf-UCnn-workflow-name.md` in `wiki_seed/skills/`.

```
---
workflow_id: WF-UCnn
use_case: UCnn
business_name: "..."         ← Plain English name of the business process
domain: "..."
version: "1.0"
requires_human_input: true | false
human_input_phase: N         ← Which phase pauses for human input (if any)
---

# [workflow name]

## Business Goal
One paragraph. What business outcome does this workflow produce?
Who uses it? What does it replace (manual step, email chain, spreadsheet)?

## Workflow Steps

For each step, write:

### Step N: [Step Name]

| Field | Value |
|---|---|
| Skill | SK-XX or "built-in" |
| Type | programmatic / llm_single / llm_human_input / llm_agent |
| Input from | "harness" or "Step N-1 output.field_name" |
| Output to | "Step N+1" or "report" or "wiki" |
| Gating rule | What must be true from prior steps for this step to run |
| On failure | skip / retry / abort_workflow / alert |

**What this step does:**
Plain English description.

**Decision logic:**
If the step has branching behaviour, describe it here.
Example: "If confidence=high, skip Step 6. If confidence=low, run Step 6."

---

## Human Input Step (if applicable)

**When it fires:** After Step N
**What the agent knows by this point:** (summary of what phases 1..N produced)
**Questions to ask the human:** List them exactly as they should appear in the UI
**How the answers flow forward:** Which steps consume the human input and how

---

## Output / Deliverable

Describe what the workflow produces at the end:
- What file(s) are written to S3?
- What wiki page(s) are created?
- What does the user see?
- What downstream workflow can consume this output?

---

## Composition Notes

List which skills from the registry are used, in order:
SK-01 → SK-02 → SK-05 → SK-04 → SK-03

List which skills are optional (only run under certain conditions):
- SK-05 only runs if SK-02 confidence < high

List any NEW skills this workflow needs that don't exist yet:
- SK-XX: [describe it] — write a separate skill spec file for it
```

---

## Part 3 — What Happens After You Submit a Spec

1. **Drop your file** into `wiki_seed/skills/` and run:
   ```
   python3 scripts/generate_skill_lambda.py --spec wiki_seed/skills/sk-NN-your-skill.md
   ```

2. The generator:
   - Reads your spec
   - Uses the existing SK-01 to SK-05 Lambda code as examples
   - Calls Claude to synthesize a new `handler.py` matching the standard skill contract
   - Writes it to `lambda/skills/your_skill/handler.py`
   - Generates Terraform in `terraform/lambda_skills_generated.tf`
   - Updates the Skill Registry DynamoDB entry via `scripts/seed_skill_registry.py`

3. Run `scripts/deploy.sh` to deploy.

4. The new skill is immediately available to all UC agents via the standard Lambda invoke contract.

---

## Quick Reference: Field Names That Matter

The generator reads these YAML front-matter fields to wire up infrastructure automatically:

| Field | Effect |
|---|---|
| `skill_id: SK-NN` | Sets Lambda name `llmwiki-skill-sk-nn-*`, SSM param path |
| `tier: 1` | Tier 1 skills get higher memory/timeout allocation |
| `use_case_tags` | Registers skill in Skill Registry for those UCs |
| `domain` | Sets default domain filter on any wiki_query calls |
| backends listed under "What It Calls" | Generator creates the boto3 client and IAM permissions |
| `requires_human_input: true` | Generator adds pause/resume logic to the workflow harness |

---

## Tips for Good Skill Specs

**Be concrete in inputs/outputs.** "customer_id: string, required, from SK-01 output.customer_status" is 10× more useful to the generator than "customer info".

**One skill, one responsibility.** If your skill does three different things, split it. The generator works best with focused specs.

**Write the happy path example with real test data.** The generator uses this to write unit test stubs.

**Name business rules explicitly.** Rules like "never overwrite approved records" become `if` guards in the generated code. If you don't write them, the generator won't add them.

**Reuse existing backends.** If your skill needs to look something up, say `wiki_query` — don't say "call Bedrock". The generator wraps the right Lambda automatically.
