# LLMWiki Test Suite

All tests for the LLMWiki platform live here. Run any layer independently or
run the full suite via `pytest`.

## Structure

```
tests/
├── golden/          # Fixed reference datasets — the ground truth
│   ├── rag_golden_v1.json          # 20 RAG Q&A pairs for RAGAS scoring
│   ├── api_golden_v1.json          # 20 Business API structured response pairs
│   └── uc1_agent_golden_v1.json    # 10 UC1 agent trace reference cases
│
├── unit/            # Isolated Lambda/module tests — no AWS, fast (<1 min)
│   ├── query/           test_query_handler.py
│   ├── business_query/  test_business_query_handler.py
│   ├── uc1_harness/     test_uc1_harness.py        (migrated from lambda/)
│   ├── skills/          test_skills.py
│   └── governance/      test_governance.py
│
├── integration/     # Live AWS calls — needs tzg-sandbox profile + deployed stack
│   └── test_live_lambdas.py
│
├── eval/            # Eval-first: define contracts before implementation
│   ├── test_uc1_eval_first.py      ← UC1 golden cases, run BEFORE agent goes live
│   ├── ragas_runner.py             ← RAGAS scorer against rag_golden_v1.json
│   └── judge_calibration.py        ← Cohen's Kappa calibration for LLM-as-judge
│
├── ci/              # CI/CD gates wired to GitHub Actions / CodeBuild
│   ├── test_schema_gate.py         ← Gate 1: deterministic schema checks
│   └── test_ragas_gate.py          ← Gate 2: RAGAS regression on 50-sample subset
│
└── e2e/             # Playwright browser tests against live ALB
    ├── test_governance_e2e.py      ← Governance page (migrated from /tmp)
    ├── test_uc1_e2e.py             ← UC1 Sales-to-Service full UI flow
    └── conftest.py                 ← shared fixtures (browser, BASE_URL)
```

## Running Tests

### Prerequisites
```bash
pip install pytest playwright boto3 ragas datasets pandas
playwright install chromium
export AWS_PROFILE=tzg-sandbox
```

### Unit tests (no AWS needed)
```bash
pytest tests/unit/ -v
```

### Eval-first — run BEFORE deploying UC1 agent to production
```bash
pytest tests/eval/test_uc1_eval_first.py -v
# Must show all contract checks passing before AgentCore wires UC1
```

### Integration tests (needs live AWS)
```bash
pytest tests/integration/ -v -m integration
```

### E2E tests (needs running ALB)
```bash
pytest tests/e2e/ -v
# Or target specific suite:
pytest tests/e2e/test_uc1_e2e.py -v
```

### CI gates (used in CodeBuild / GitHub Actions)
```bash
pytest tests/ci/test_schema_gate.py -v          # Gate 1 — every commit
pytest tests/ci/test_ragas_gate.py -v           # Gate 2 — every PR
```

### Full eval with RAGAS
```bash
python tests/eval/ragas_runner.py               # scores all 20 golden pairs
```

## Golden Dataset Versions

| File | Version | Examples | Created | Notes |
|------|---------|----------|---------|-------|
| rag_golden_v1.json | v1 | 20 | 2026-07-08 | Seed set — replace with production-mined set at 100+ |
| api_golden_v1.json | v1 | 20 | 2026-07-08 | Business API contract examples |
| uc1_agent_golden_v1.json | v1 | 10 | 2026-07-08 | UC1 trace reference cases |

Rotate every 6 months: add 20% new production examples, retire 20% oldest.
See `llmwiki-eval-strategy.md` Part 1 for the full rotation process.

## Eval-First Rule

**No agent goes to production without passing `tests/eval/test_uc1_eval_first.py`.**

The eval test defines the contract. The implementation must make it pass.
Every production failure must become a regression test within 24 hours.
