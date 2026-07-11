#!/usr/bin/env python3
"""
generate_harness.py — Reads a workflow spec (.md) and generates a deployable
harness Lambda that orchestrates multiple skills in the correct order.

Usage:
  python3 scripts/generate_harness.py --spec wiki_seed/skills/wf-UC1-sales-to-service.md
  python3 scripts/generate_harness.py --spec wiki_seed/skills/wf-UC1-sales-to-service.md --dry-run
  python3 scripts/generate_harness.py --spec wiki_seed/skills/wf-UC1-sales-to-service.md --deploy

What it produces:
  lambda/harness/{uc_id}_harness/handler.py     ← deployable harness Lambda
  lambda/harness/{uc_id}_harness/test_harness.py ← integration test stubs
  terraform/harness_generated.tf                 ← Terraform resource block (appended)

The harness generator uses the UC1 handler as a few-shot example so Claude
understands the exact pattern (phase functions, pause/resume, DynamoDB persistence,
HTML report builder, presigned URLs).
"""

import argparse
import ast
import json
import os
import re
import sys
import textwrap
import boto3

ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(ROOT_DIR, "lambda", "harness")
WIKI_SEED   = os.path.join(ROOT_DIR, "wiki_seed", "skills")
TF_FILE     = os.path.join(ROOT_DIR, "terraform", "harness_generated.tf")

AWS_REGION  = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Reference harness — used as the primary few-shot example
UC1_HARNESS_PATH = os.path.join(ROOT_DIR, "lambda", "harness", "uc1_harness", "handler.py")


# ════════════════════════════════════════════════════════════════════════════════
# Workflow spec parser
# ════════════════════════════════════════════════════════════════════════════════

def parse_workflow_spec(spec_path: str) -> dict:
    """Parse a workflow spec .md file into a structured dict."""
    with open(spec_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Extract YAML front matter
    fm = {}
    fm_match = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                v = v.strip().strip('"').strip("'")
                fm[k.strip()] = v
        raw = raw[fm_match.end():]

    wf = {
        "workflow_id":      fm.get("workflow_id", "WF-XX"),
        "use_case":         fm.get("use_case", "UC99"),
        "business_name":    fm.get("business_name", "Unnamed Workflow"),
        "domain":           fm.get("domain", "general"),
        "version":          fm.get("version", "1.0"),
        "requires_human":   fm.get("requires_human_input", "false").lower() == "true",
        "human_phase":      int(fm.get("human_input_phase", 0)),
        "harness_lambda":   fm.get("harness_lambda", "llmwiki-harness-uc99"),
        "harness_table":    fm.get("harness_table", "llmwiki-harness-runs"),
        "workspace_table":  fm.get("workspace_table", "llmwiki-workspace-files"),
        "report_bucket_prefix": fm.get("report_bucket_prefix", "wiki/reports"),
        "wiki_page_prefix": fm.get("wiki_page_prefix", "customers"),
    }

    # Extract freeform sections
    def _section(name: str) -> str:
        m = re.search(
            rf"##\s+{re.escape(name)}\s*\n(.*?)(?=\n##\s|\Z)",
            raw, re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    wf["business_goal"]     = _section("Business Goal")
    wf["harness_inputs"]    = _section("Harness Inputs")
    wf["workflow_steps"]    = _section("Workflow Steps")
    wf["human_input_detail"] = _section("Human Input Step — Full Detail")
    wf["report_sections"]   = _section("Report Sections")
    wf["composition_notes"] = _section("Composition Notes")
    wf["output_deliverable"] = _section("Output / Deliverable")

    # Derive UC slug and harness dir name
    uc_id   = wf["use_case"].lower()   # "uc1"
    wf["uc_id"] = uc_id
    wf["slug"]  = f"{uc_id}_harness"
    wf["harness_dir"] = os.path.join(HARNESS_DIR, wf["slug"])

    return wf


# ════════════════════════════════════════════════════════════════════════════════
# Load few-shot reference (UC1 harness)
# ════════════════════════════════════════════════════════════════════════════════

def _load_reference_harness() -> str:
    if os.path.exists(UC1_HARNESS_PATH):
        with open(UC1_HARNESS_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "# Reference harness not available"


# ════════════════════════════════════════════════════════════════════════════════
# Syntax validation + auto-repair
# ════════════════════════════════════════════════════════════════════════════════

def _validate_and_fix_code(code: str, context_label: str, bedrock_client,
                            max_retries: int = 2) -> str:
    """
    Parse the generated code with ast.parse().  If it fails, ask Claude to
    complete/fix it.  Returns valid Python or raises SyntaxError after retries.
    """
    for attempt in range(max_retries + 1):
        try:
            ast.parse(code)
            if attempt > 0:
                print(f"  Syntax OK after {attempt} fix attempt(s).")
            return code
        except SyntaxError as exc:
            if attempt == max_retries:
                raise SyntaxError(
                    f"{context_label}: code still has syntax error after "
                    f"{max_retries} fix attempt(s): {exc}"
                ) from exc

            print(f"  WARN: syntax error in generated code ({exc}). "
                  f"Asking Claude to fix (attempt {attempt + 1}/{max_retries})...")

            fix_prompt = (
                f"The Python code below has a syntax error: {exc}\n\n"
                "Please return the COMPLETE, corrected Python file. "
                "Do not truncate. Do not add markdown fences. "
                "Output only valid Python source code.\n\n"
                f"```\n{code}\n```"
            )
            resp = bedrock_client.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": fix_prompt}],
                }),
                contentType="application/json",
                accept="application/json",
            )
            fixed = json.loads(resp["body"].read())["content"][0]["text"].strip()
            fixed = re.sub(r"^```python\s*", "", fixed)
            fixed = re.sub(r"\s*```$", "", fixed)
            code = fixed


# ════════════════════════════════════════════════════════════════════════════════
# Harness code generation via Claude
# ════════════════════════════════════════════════════════════════════════════════

def generate_harness_handler(wf: dict, dry_run: bool = False) -> str:
    """Call Claude to generate a complete harness handler from the workflow spec."""
    reference_code = _load_reference_harness()

    system_prompt = textwrap.dedent(f"""
    You are an expert AWS Lambda developer generating a new workflow harness for LLMWiki.

    STRICT REQUIREMENTS:
    1. Follow the exact pattern of the UC1 reference harness provided below.
    2. Implement every phase described in the workflow spec as a separate _phaseN_* function.
    3. Preserve the DynamoDB persistence pattern (_init_harness_run, _update_harness_run).
    4. Preserve the pause/resume pattern for human input phases (status="paused" → return early).
    5. Preserve the _PhaseError exception for hard failures.
    6. Generate a _build_report_html() function producing a styled HTML report matching
       the Report Sections table in the spec.
    7. Generate a _build_report_text() fallback function.
    8. Use these exact env var names: HARNESS_RUNS_TABLE, WORKSPACE_TABLE, WIKI_BUCKET.
       For MODEL_ID: MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    9. Skill Lambda names must be env-overridable (SK01_FUNCTION, SK02_FUNCTION, etc.).
    10. The harness Lambda name is: {wf['harness_lambda']}
    11. Generate REAL boto3 code — no pseudocode, no TODO placeholders.
    12. Write production-quality code with proper error handling throughout.
    13. Do NOT add any explanatory comment about what you generated. Write production code only.
    """).strip()

    user_prompt = textwrap.dedent(f"""
    Generate the complete Lambda handler.py for this workflow harness.

    ## WORKFLOW SPEC

    **Workflow ID:** {wf['workflow_id']}
    **Use Case:** {wf['use_case']}
    **Business Name:** {wf['business_name']}
    **Domain:** {wf['domain']}
    **Requires Human Input:** {wf['requires_human']}
    **Human Input Phase:** {wf['human_phase']}
    **Harness Lambda Name:** {wf['harness_lambda']}

    ### Business Goal
    {wf['business_goal']}

    ### Harness Inputs
    {wf['harness_inputs']}

    ### Workflow Steps (implement each as a _phaseN_* function)
    {wf['workflow_steps']}

    ### Human Input Step Details
    {wf['human_input_detail']}

    ### Report Sections (implement in _build_report_html)
    {wf['report_sections']}

    ### Composition Notes
    {wf['composition_notes']}

    ### Output / Deliverable
    {wf['output_deliverable']}

    ## REFERENCE HARNESS — FOLLOW THIS EXACT PATTERN

    {reference_code[:6000]}

    ## GENERATE THE COMPLETE handler.py NOW

    Requirements checklist before you output:
    - [ ] lambda_handler entry point with body unwrapping
    - [ ] action="get_status" poll path
    - [ ] _find_paused_run() to resume paused runs
    - [ ] All phases implemented as _phaseN_*() functions
    - [ ] Phase {wf['human_phase']} uses pause/resume pattern
    - [ ] _build_report_html() with KPI bar and all report sections
    - [ ] _build_report_text() plain-text fallback
    - [ ] _build_handoff_markdown() for wiki indexing
    - [ ] _build_completion_summary()
    - [ ] All helper functions (_invoke_skill, _write_workspace, _bedrock_call, etc.)
    - [ ] _PhaseError custom exception
    - [ ] _ok() and _error_response() response helpers

    Return ONLY the Python source code. No markdown fences, no explanation.
    """).strip()

    from botocore.config import Config as BotocoreConfig
    bedrock_client = boto3.client(
        "bedrock-runtime", region_name=AWS_REGION,
        config=BotocoreConfig(read_timeout=300, connect_timeout=10, retries={"max_attempts": 2}),
    )
    print(f"  Calling Claude ({MODEL_ID}) to generate harness handler ({wf['workflow_id']})...")

    resp = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }),
        contentType="application/json",
        accept="application/json",
    )
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()

    # Strip any accidental markdown fences
    text = re.sub(r"^```python\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Validate syntax; auto-fix if Claude truncated the output
    text = _validate_and_fix_code(text, wf["workflow_id"], bedrock_client)
    return text


# ════════════════════════════════════════════════════════════════════════════════
# Test stub generation
# ════════════════════════════════════════════════════════════════════════════════

def generate_harness_tests(wf: dict) -> str:
    """Generate integration test stubs for the harness."""
    requires_human = wf["requires_human"]
    human_phase    = wf["human_phase"]
    biz_name       = wf["business_name"]

    # Build conditional blocks without backslashes in f-string expressions
    if requires_human:
        pause_test = (
            "\ndef test_first_invocation_pauses_at_human_phase(mock_aws):\n"
            '    """First call should run phases 1-' + str(human_phase - 1) + ' then pause waiting for human input."""\n'
            "    result = handler.lambda_handler(VALID_EVENT, None)\n"
            '    body   = json.loads(result["body"])\n'
            '    assert body["status"] == "paused"\n'
            "    assert body[\"current_phase\"] == " + str(human_phase) + "\n"
            '    assert "question" in body\n'
        )
        resume_fn = "def test_resume_with_human_context_completes(mock_aws):"
        resume_doc = '    """Providing human_context should resume and complete all phases."""'
        paused_run_block = (
            "    paused_run = {\n"
            '        "engagement_id": "test-customer-001",\n'
            '        "run_id": "run-test-customer-001-999",\n'
            '        "status": "paused",\n'
            "        \"current_phase\": " + str(human_phase) + ",\n"
            '        "started_at": "2026-01-01T00:00:00Z",\n'
            '        "phase_results": \'{"phase1": {"customer_status": "new", "pages_found": 0}, '
            '"phase2": {"risk_tier": "HIGH", "go_live_urgency": "MEDIUM", '
            '"implementation_complexity": "HIGH", "rationale": "test", '
            '"customer_type": "payer", "products": ["TestProduct"]}}\',\n'
            "    }\n"
            '    mock_aws["table"].query.return_value = {"Items": [paused_run]}\n'
            "    event = RESUME_EVENT\n"
        )
        html_event_line = "    event = RESUME_EVENT\n"
    else:
        pause_test = "\n# No human input phase — workflow runs straight through\n"
        resume_fn  = "def test_full_run_completes(mock_aws):"
        resume_doc = '    """A valid event should complete all phases."""'
        paused_run_block = "    event = VALID_EVENT\n"
        html_event_line  = "    event = VALID_EVENT\n"

    lines = [
        '"""',
        f"Integration test stubs for {biz_name} harness — auto-generated.",
        "Mocks all AWS clients. Fill in assertion values after reviewing generated code.",
        "Run with: python -m pytest test_harness.py -v",
        '"""',
        "import json",
        "import pytest",
        "from unittest.mock import MagicMock, patch, call",
        "import handler",
        "",
        "",
        "# ── Minimal valid inputs ──────────────────────────────────────────────────",
        "VALID_EVENT = {",
        '    "customer_id":   "test-customer-001",',
        '    "customer_name": "Test Corp",',
        '    "product":       "TestProduct v1",',
        '    "sow_reference": "SOW-TEST-001",',
        "}",
        "",
        "RESUME_EVENT = {",
        "    **VALID_EVENT,",
        '    "human_context": "Executive sponsor is Jane Smith. Go-live Q3. No prior attempts.",',
        "}",
        "",
        "",
        "def _make_lambda_response(body: dict) -> dict:",
        "    return {",
        '        "Payload": MagicMock(read=lambda: json.dumps({"body": json.dumps(body)}).encode())',
        "    }",
        "",
        "",
        "@pytest.fixture",
        "def mock_aws(monkeypatch):",
        '    """Patch all AWS clients used by the harness."""',
        "    dynamo_mock  = MagicMock()",
        "    lambda_mock  = MagicMock()",
        "    bedrock_mock = MagicMock()",
        "    s3_mock      = MagicMock()",
        "",
        "    table_mock = MagicMock()",
        "    table_mock.put_item.return_value    = {}",
        "    table_mock.update_item.return_value = {}",
        '    table_mock.query.return_value       = {"Items": []}',
        '    table_mock.get_item.return_value    = {"Item": {}}',
        "    dynamo_mock.Table.return_value      = table_mock",
        "",
        "    lambda_mock.invoke.return_value = _make_lambda_response({",
        '        "status": "success", "customer_status": "new", "pages_found": 0,',
        '        "key_facts": [], "overview": "Test customer",',
        '        "outputs": {',
        '            "customer_status": "new", "pages_loaded": 1,',
        '            "playbook": {"steps": []}, "confidence": "low",',
        '            "answer": "Test risk answer",',
        '            "action_items": ["Review data migration plan"],',
        '            "gaps": [], "found": False, "completion_pct": 0,',
        '            "populated_fields": [], "missing_fields": [],',
        '            "status": "indexed", "s3_uri": "s3://test-bucket/test.md",',
        "        }",
        "    })",
        "",
        "    bedrock_mock.invoke_model.return_value = {",
        '        "body": MagicMock(read=lambda: json.dumps({',
        '            "content": [{"text": \'{"customer_type":"payer","products":["TestProduct v1"],',
        '                "risk_tier":"HIGH","go_live_urgency":"MEDIUM",',
        '                "implementation_complexity":"HIGH","rationale":"New customer"}\'}]',
        "        }).encode())",
        "    }",
        "",
        "    s3_mock.put_object.return_value           = {}",
        '    s3_mock.generate_presigned_url.return_value = "https://s3.example.com/report.html"',
        "",
        '    monkeypatch.setattr(handler, "dynamodb",      dynamo_mock)',
        '    monkeypatch.setattr(handler, "lambda_client", lambda_mock)',
        '    monkeypatch.setattr(handler, "bedrock",       bedrock_mock)',
        '    monkeypatch.setattr(handler, "s3_client",     s3_mock)',
        '    monkeypatch.setattr(handler, "WIKI_BUCKET",   "test-llmwiki-bucket")',
        "",
        '    return {"dynamo": dynamo_mock, "table": table_mock,',
        '            "lambda_": lambda_mock, "bedrock": bedrock_mock, "s3": s3_mock}',
        "",
        "",
        "def test_missing_customer_id_returns_error():",
        '    """Harness must reject events with no customer_id."""',
        "    result = handler.lambda_handler({}, None)",
        '    body   = json.loads(result["body"])',
        '    assert result["statusCode"] == 200',
        '    assert body["status"] == "error"',
        '    assert "customer_id" in body.get("error", "").lower()',
    ]

    lines.append(pause_test)

    lines += [
        "",
        resume_fn,
        resume_doc,
        "    # Make _find_paused_run return a paused run so resume path is taken",
        paused_run_block,
        "    result = handler.lambda_handler(event, None)",
        '    body   = json.loads(result["body"])',
        '    assert body["status"] == "completed"',
        '    assert body.get("phases_completed") is not None',
        "",
        "",
        "def test_get_status_action(mock_aws):",
        '    """get_status action should return current run state."""',
        "    run_item = {",
        '        "engagement_id":  "test-customer-001",',
        '        "run_id":         "run-test-customer-001-999",',
        '        "status":         "completed",',
        '        "current_phase":  8,',
        '        "phase_results":  "{}",',
        '        "total_latency_ms": 5000,',
        "    }",
        '    mock_aws["table"].query.return_value = {"Items": [run_item]}',
        '    event  = {"action": "get_status", "engagement_id": "test-customer-001"}',
        "    result = handler.lambda_handler(event, None)",
        '    body   = json.loads(result["body"])',
        '    assert body["status"] == "completed"',
        "",
        "",
        "def test_report_html_contains_required_sections(mock_aws):",
        '    """The HTML report must contain all required section headings."""',
        '    mock_aws["table"].query.return_value = {"Items": []}',
        html_event_line,
        "    result = handler.lambda_handler(event, None)",
        "",
        "    p1 = {'overview': 'Test overview', 'key_facts': ['Fact 1'], 'pages_found': 1}",
        "    p2 = {'risk_tier': 'HIGH', 'go_live_urgency': 'MEDIUM', 'implementation_complexity': 'HIGH',",
        "          'rationale': 'Test', 'customer_type': 'payer', 'products': ['TestProduct']}",
        "    p3 = {'summary': 'Human context'}",
        "    p4 = {'playbook_steps': 3, 'pages_loaded': 5}",
        "    p5 = {'confidence': 'medium', 'answer': 'Risk answer', 'action_items': ['Action 1']}",
        "    p6 = {'gaps': [{'title': 'Gap 1', 'gap_type': 'missing-artifact',",
        "                    'blocking': True, 'human_prompt': 'What is X?'}],",
        "          'gap_count': 1, 'blocking_count': 1}",
        "    p7 = {'found': False, 'completion_pct': 0, 'populated_fields': [], 'missing_fields': []}",
        "    if hasattr(handler, '_build_report_html'):",
        "        html = handler._build_report_html(",
        "            'test-001', 'Test Corp', 'TestProduct', 'SOW-001', '2026-01-01',",
        "            p1, p2, p3, p4, p5, p6, p7,",
        "        )",
        "        assert '<!DOCTYPE html>' in html",
        "        assert 'Customer Overview' in html",
        "        assert 'Knowledge Gaps' in html",
        "        assert 'kpi' in html.lower()",
    ]

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════════
# Terraform generation
# ════════════════════════════════════════════════════════════════════════════════

def generate_harness_terraform(wf: dict) -> str:
    slug    = wf["slug"]
    fn_name = wf["harness_lambda"]
    uc_id   = wf["use_case"].upper()

    return textwrap.dedent(f"""
    # ── {wf['workflow_id']} {wf['business_name']} Harness — auto-generated ──────────────────
    # Generated by scripts/generate_harness.py from wf-{uc_id.lower()}-*.md

    data "archive_file" "harness_{slug}" {{
      type        = "zip"
      source_dir  = "${{path.module}}/../lambda/harness/{slug}"
      output_path = "${{path.module}}/../.build/harness_{slug}.zip"
    }}

    resource "aws_lambda_function" "harness_{slug}" {{
      function_name    = "{fn_name}"
      role             = aws_iam_role.harness_lambda.arn
      handler          = "handler.lambda_handler"
      runtime          = "python3.12"
      filename         = data.archive_file.harness_{slug}.output_path
      source_code_hash = data.archive_file.harness_{slug}.output_base64sha256
      timeout          = 300
      memory_size      = 1024

      environment {{
        variables = {{
          HARNESS_RUNS_TABLE  = aws_dynamodb_table.harness_runs.name
          WORKSPACE_TABLE     = aws_dynamodb_table.workspace_files.name
          BEDROCK_MODEL_ID    = var.bedrock_model_id
          WIKI_BUCKET         = var.wiki_bucket
          SK01_FUNCTION       = aws_lambda_function.skill_context_bootstrap.function_name
          SK02_FUNCTION       = aws_lambda_function.skill_wiki_query.function_name
          SK03_FUNCTION       = aws_lambda_function.skill_wiki_contribute.function_name
          SK04_FUNCTION       = aws_lambda_function.skill_artifact_resolution.function_name
          SK05_FUNCTION       = aws_lambda_function.skill_gap_detection.function_name
          PLAYBOOK_FUNCTION   = aws_lambda_function.playbook.function_name
        }}
      }}

      tags = {{
        workflow_id  = "{wf['workflow_id']}"
        use_case     = "{uc_id}"
        generated_by = "generate_harness.py"
      }}
    }}

    resource "aws_cloudwatch_log_group" "harness_{slug}" {{
      name              = "/aws/lambda/{fn_name}"
      retention_in_days = 30
    }}

    resource "aws_ssm_parameter" "harness_{slug}_arn" {{
      name  = "/llmwiki/harness/{uc_id.lower()}_arn"
      type  = "String"
      value = aws_lambda_function.harness_{slug}.arn
    }}
    """).strip()


# ════════════════════════════════════════════════════════════════════════════════
# Write outputs
# ════════════════════════════════════════════════════════════════════════════════

def write_outputs(wf: dict, handler_code: str, test_code: str,
                  tf_block: str, dry_run: bool):
    harness_dir = wf["harness_dir"]

    if dry_run:
        print("\n" + "="*72)
        print(f"DRY RUN — would write to: {harness_dir}/")
        print("="*72)
        print("\n--- handler.py (first 80 lines) ---")
        print("\n".join(handler_code.splitlines()[:80]))
        print("\n--- test_harness.py (first 30 lines) ---")
        print("\n".join(test_code.splitlines()[:30]))
        print("\n--- terraform (first 20 lines) ---")
        print("\n".join(tf_block.splitlines()[:20]))
        return

    os.makedirs(harness_dir, exist_ok=True)

    handler_path = os.path.join(harness_dir, "handler.py")
    with open(handler_path, "w", encoding="utf-8") as f:
        f.write(handler_code)
    print(f"  Wrote: {handler_path}")

    test_path = os.path.join(harness_dir, "test_harness.py")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    print(f"  Wrote: {test_path}")

    # Append TF block
    existing_tf = ""
    if os.path.exists(TF_FILE):
        with open(TF_FILE, "r", encoding="utf-8") as f:
            existing_tf = f.read()

    if wf["harness_lambda"] not in existing_tf:
        with open(TF_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n" + tf_block + "\n")
        print(f"  Appended Terraform to: {TF_FILE}")
    else:
        print(f"  Terraform for {wf['harness_lambda']} already present — skipped")


# ════════════════════════════════════════════════════════════════════════════════
# Deploy helper
# ════════════════════════════════════════════════════════════════════════════════

def deploy_harness(wf: dict):
    import subprocess, zipfile
    harness_dir = wf["harness_dir"]
    build_dir   = os.path.join(ROOT_DIR, ".build")
    os.makedirs(build_dir, exist_ok=True)
    zip_path    = os.path.join(build_dir, f"harness_{wf['slug']}.zip")

    print(f"  Zipping {harness_dir} → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(harness_dir):
            if fname.endswith(".py"):
                zf.write(os.path.join(harness_dir, fname), fname)

    fn      = wf["harness_lambda"]
    profile = os.environ.get("AWS_PROFILE", "tzg-sandbox")
    print(f"  Deploying {fn}...")
    result = subprocess.run([
        "aws", "lambda", "update-function-code",
        "--function-name", fn,
        "--zip-file", f"fileb://{zip_path}",
        "--profile", profile,
        "--region", AWS_REGION,
        "--query", "{FunctionName:FunctionName,LastModified:LastModified}",
        "--output", "json",
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  Deployed: {json.loads(result.stdout)}")
    else:
        print(f"  WARN: deploy failed: {result.stderr.strip()}")
        print("  If the function doesn't exist yet, run 'terraform apply' first.")


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a workflow harness Lambda from a workflow spec .md file"
    )
    parser.add_argument("--spec",    required=True, help="Path to wf-UCnn-*.md spec file")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing files")
    parser.add_argument("--deploy",  action="store_true", help="Deploy Lambda immediately")
    parser.add_argument("--region",  default=None)
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    if args.region:
        AWS_REGION = args.region
        os.environ["AWS_DEFAULT_REGION"] = args.region
    if args.profile:
        os.environ["AWS_PROFILE"] = args.profile

    spec_path = os.path.abspath(args.spec)
    if not os.path.exists(spec_path):
        print(f"ERROR: spec file not found: {spec_path}")
        sys.exit(1)

    print(f"\nLLMWiki Harness Generator")
    print(f"{'='*60}")
    print(f"Spec  : {spec_path}")
    print(f"Region: {AWS_REGION}")
    print(f"Model : {MODEL_ID}")
    print(f"{'='*60}\n")

    print("Step 1/5 — Parsing workflow spec...")
    wf = parse_workflow_spec(spec_path)
    print(f"  Workflow ID   : {wf['workflow_id']}")
    print(f"  Business Name : {wf['business_name']}")
    print(f"  Use Case      : {wf['use_case']}")
    print(f"  Human Phase   : {wf['human_phase'] if wf['requires_human'] else 'none'}")
    print(f"  Harness Lambda: {wf['harness_lambda']}")
    print(f"  Output dir    : lambda/harness/{wf['slug']}/")

    print("\nStep 2/5 — Generating harness handler (calling Claude)...")
    handler_code = generate_harness_handler(wf, dry_run=args.dry_run)
    print(f"  Generated {len(handler_code.splitlines())} lines")

    print("\nStep 3/5 — Generating test stubs...")
    test_code = generate_harness_tests(wf)
    print(f"  Generated {len(test_code.splitlines())} lines")

    print("\nStep 4/5 — Generating Terraform block...")
    tf_block = generate_harness_terraform(wf)

    print("\nStep 5/5 — Writing output files...")
    write_outputs(wf, handler_code, test_code, tf_block, dry_run=args.dry_run)

    if args.deploy and not args.dry_run:
        print("\nDeploying harness Lambda...")
        deploy_harness(wf)

    print(f"\n{'='*60}")
    if args.dry_run:
        print("DRY RUN complete — no files written")
    else:
        print(f"DONE — harness {wf['workflow_id']} {wf['business_name']} generated")
        print(f"\nNext steps:")
        print(f"  1. Review lambda/harness/{wf['slug']}/handler.py")
        print(f"  2. Run tests: cd lambda/harness/{wf['slug']} && python -m pytest test_harness.py -v")
        if not args.deploy:
            print(f"  3. Deploy: python3 scripts/generate_harness.py --spec {args.spec} --deploy")
        print(f"  4. Or run full pipeline: python3 scripts/generate_pipeline.py --brief wiki_seed/skills/uc-{wf['use_case'].lower()[2:]}-*.md")
    print(f"{'='*60}\n")
