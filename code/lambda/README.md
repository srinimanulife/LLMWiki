# LLMWiki Lambda Code Structure

## Directory Layout

```
lambda/
├── common/                          # Shared library — used by all Lambdas
│   ├── llmwiki_common.py            # Core utilities: Bedrock, DDB telemetry, S3, HTTP
│   └── harness_common.py            # Harness-specific DDB state management
│
├── apps/                            # Application-specific Lambdas
│   ├── s2s/                         # UC1 Sales-to-Service
│   │   └── harness/
│   │       ├── gatekeeper/          # Validates prerequisites, starts run
│   │       └── uc1_harness/         # 8-phase S2S workflow
│   │
│   └── problem_mgnt/                # UC-PM Problem Management
│       ├── harness/
│       │   └── pm_harness/          # 8-phase PM RCA workflow
│       └── skills/
│           └── problem_classifier/  # SK-06: classifies problems, SNS for P1/High
│
├── skills_shared/                   # Skills reused across multiple apps
│   ├── context_bootstrap/           # SK-01: loads customer context + playbook
│   ├── wiki_query/                  # SK-02: queries wiki knowledge base
│   ├── wiki_contribute/             # SK-03: writes draft wiki pages
│   ├── artifact_resolution/         # SK-04: fills templates
│   ├── gap_detection/               # SK-05: detects knowledge gaps
│   └── claim_readine/               # SK-06-placeholder (generated, not active)
│
└── platform/                        # Core platform Lambdas (infra, not app-specific)
    ├── business_query/              # Bedrock KB query with RAG
    ├── query/                       # Simple wiki lookup
    ├── contribute/                  # Wiki write endpoint
    ├── converter/                   # Document format conversion
    ├── ingest/                      # Batch ingestion from S3
    └── playbook/                    # Playbook retrieval
```

> **Legacy paths** (`lambda/harness/`, `lambda/skills/`) still exist and are what
> Terraform currently points to. New development should go into `apps/` or
> `skills_shared/`. See [Terraform Migration](#terraform-migration) below.

## What Goes Where

| Code type | Location | Rule |
|---|---|---|
| New use case harness | `apps/<uc_name>/harness/` | One harness per use case |
| Use-case-specific skill | `apps/<uc_name>/skills/` | Only used by that app |
| Skill reused by 2+ apps | `skills_shared/` | Must follow skill contract |
| Core infra (query, ingest) | `platform/` | No business logic |
| Repeated utility code | `common/llmwiki_common.py` | Extract when 3+ handlers share it |

## Common Library Usage

Every handler that uses `llmwiki_common.py` must include it in its Lambda zip.
The Terraform `archive_file` data source uses `source_dir` which zips the whole
directory — so place `common/` as a sibling or use a build step to copy it in.

**Option A — copy-on-build (current approach for new apps):**
```hcl
# In terraform, add a null_resource to copy common lib before zipping
resource "null_resource" "copy_common_to_pm_harness" {
  triggers = { common = filemd5("${path.module}/../lambda/common/llmwiki_common.py") }
  provisioner "local-exec" {
    command = "cp ${path.module}/../lambda/common/llmwiki_common.py ${path.module}/../lambda/apps/problem_mgnt/harness/pm_harness/"
  }
}
```

**Option B — Lambda Layer (recommended for 5+ Lambdas):**
Create a single Lambda Layer from `common/` and attach it to all functions.
The layer is mounted at `/opt/python/` which is on `sys.path` automatically.

## Adding a New Use Case

1. Create `apps/<uc_name>/` directory
2. Write the spec in `/<uc_name>/` (parallel to `problem-mgnt/`)
3. Add `harness/` with `handler.py` — import from `common/`
4. Add app-specific skills in `apps/<uc_name>/skills/` if needed
5. Check `skills_shared/` first — reuse before building new
6. Add Terraform resources in a new `terraform/<uc_name>_infra.tf` file
7. Add the agent to `streamlit/pages/harness_demo.py` AGENTS registry
8. Seed app bucket with spec files only (no cross-app content)

## Terraform Migration

Current Terraform points to old paths (`lambda/harness/`, `lambda/skills/`).
New resources (`pm_problem_mgnt.tf`) point to the new `apps/` structure.
Old resources will be migrated progressively — don't move files until the
corresponding `.tf` file is updated to avoid breaking the deployed Lambdas.
