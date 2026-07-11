#!/usr/bin/env python3
"""
generate_skill_lambda.py — Reads a skill spec (.md) and generates a deployable Lambda.

Usage:
  python3 scripts/generate_skill_lambda.py --spec wiki_seed/skills/sk-06-my-skill.md
  python3 scripts/generate_skill_lambda.py --spec wiki_seed/skills/sk-06-my-skill.md --dry-run
  python3 scripts/generate_skill_lambda.py --spec wiki_seed/skills/sk-06-my-skill.md --deploy

What it produces:
  lambda/skills/<slug>/handler.py          ← deployable Lambda handler
  lambda/skills/<slug>/requirements.txt    ← dependencies
  lambda/skills/<slug>/test_<slug>.py      ← unit test stubs from the happy path example
  terraform/lambda_skills_generated.tf     ← Terraform resource block (appended)

After running, deploy with:
  bash scripts/deploy.sh
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
SKILLS_DIR  = os.path.join(ROOT_DIR, "lambda", "skills")
WIKI_SEED   = os.path.join(ROOT_DIR, "wiki_seed", "skills")
TF_FILE     = os.path.join(ROOT_DIR, "terraform", "lambda_skills_generated.tf")

AWS_REGION  = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# ── Reference examples (few-shot): existing skill Lambdas read at runtime ──────
EXAMPLE_SKILLS = ["context_bootstrap", "wiki_query", "gap_detection"]

# ── Backend → boto3 client + Lambda name mapping ───────────────────────────────
BACKEND_MAP = {
    "wiki_query":            {"type": "lambda", "fn": "llmwiki-business-query",       "client": "lambda_client"},
    "wiki_contribute":       {"type": "lambda", "fn": "llmwiki-contribute",            "client": "lambda_client"},
    "playbook_get_customer": {"type": "lambda", "fn": "llmwiki-playbook",              "client": "lambda_client"},
    "playbook_get_playbook": {"type": "lambda", "fn": "llmwiki-playbook",              "client": "lambda_client"},
    "bedrock_claude":        {"type": "bedrock",                                        "client": "bedrock"},
    "dynamodb_read":         {"type": "dynamodb",                                       "client": "dynamodb"},
    "dynamodb_write":        {"type": "dynamodb",                                       "client": "dynamodb"},
    "s3_read":               {"type": "s3",                                             "client": "s3_client"},
    "s3_write":              {"type": "s3",                                             "client": "s3_client"},
    "sns_publish":           {"type": "sns",                                            "client": "sns"},
    "lambda_invoke":         {"type": "lambda",                                         "client": "lambda_client"},
}

IAM_FOR_BACKEND = {
    "wiki_query":            ["lambda:InvokeFunction"],
    "wiki_contribute":       ["lambda:InvokeFunction"],
    "playbook_get_customer": ["lambda:InvokeFunction"],
    "playbook_get_playbook": ["lambda:InvokeFunction"],
    "bedrock_claude":        ["bedrock:InvokeModel"],
    "dynamodb_read":         ["dynamodb:GetItem", "dynamodb:Query"],
    "dynamodb_write":        ["dynamodb:PutItem", "dynamodb:UpdateItem"],
    "s3_read":               ["s3:GetObject"],
    "s3_write":              ["s3:PutObject"],
    "sns_publish":           ["sns:Publish"],
    "lambda_invoke":         ["lambda:InvokeFunction"],
}


# ════════════════════════════════════════════════════════════════════════════════
# Spec parser
# ════════════════════════════════════════════════════════════════════════════════

def parse_spec(spec_path: str) -> dict:
    """Parse a skill spec .md file into a structured dict."""
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
                # Handle list values like [UC1, UC2]
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip() for x in v[1:-1].split(",")]
                fm[k.strip()] = v
        raw = raw[fm_match.end():]

    spec = {
        "skill_id":      fm.get("skill_id", "SK-XX"),
        "business_name": fm.get("business_name", "Unnamed Skill"),
        "technical_name": fm.get("technical_name", "UnnamedSkill"),
        "tier":          int(fm.get("tier", 2)),
        "version":       fm.get("version", "1.0"),
        "domain":        fm.get("domain", "general"),
        "use_case_tags": fm.get("use_case_tags", []),
        "status":        fm.get("status", "spec"),
    }

    # Extract freeform sections
    def _section(name: str) -> str:
        m = re.search(
            rf"##\s+{re.escape(name)}\s*\n(.*?)(?=\n##\s|\Z)",
            raw, re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    spec["what_it_does"]      = _section("What It Does")
    spec["when_to_call"]      = _section("When to Call")
    spec["inputs_section"]    = _section("What It Needs (Inputs)")
    spec["outputs_section"]   = _section("What It Produces (Outputs)")
    spec["business_rules"]    = _section("Business Rules")
    spec["backends_section"]  = _section("What It Calls (Backend)")
    spec["error_handling"]    = _section("Error Handling")
    spec["happy_path"]        = _section("Example: Happy Path")
    spec["edge_case"]         = _section("Example: Edge Case")
    spec["telemetry_section"] = _section("Telemetry Fields")

    # Detect which backends are referenced
    spec["backends"] = [
        b for b in BACKEND_MAP
        if b in spec["backends_section"]
    ]

    # Derive slug from skill_id + business_name
    slug = spec["technical_name"]
    slug = re.sub(r"(?<!^)(?=[A-Z])", "_", slug).lower()   # CamelCase → snake_case
    slug = slug.rstrip("_skill")                             # remove trailing _skill
    spec["slug"] = slug

    # Lambda function name
    spec["lambda_name"] = f"llmwiki-skill-{spec['skill_id'].lower().replace('-','')}-{slug.replace('_','-')}"

    return spec


# ════════════════════════════════════════════════════════════════════════════════
# Few-shot example builder
# ════════════════════════════════════════════════════════════════════════════════

def _load_reference_examples() -> str:
    examples = []
    for skill_slug in EXAMPLE_SKILLS:
        path = os.path.join(SKILLS_DIR, skill_slug, "handler.py")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
            examples.append(f"=== EXISTING SKILL: {skill_slug}/handler.py ===\n{code}")
    return "\n\n".join(examples)


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
# Code generation via Claude
# ════════════════════════════════════════════════════════════════════════════════

def generate_handler(spec: dict, dry_run: bool = False) -> str:
    """Call Claude to generate a Lambda handler from the spec + few-shot examples."""
    reference_code = _load_reference_examples()
    backends_needed = spec["backends"]
    clients_needed  = sorted({BACKEND_MAP[b]["client"] for b in backends_needed if b in BACKEND_MAP})
    iam_actions     = sorted({a for b in backends_needed for a in IAM_FOR_BACKEND.get(b, [])})

    system_prompt = textwrap.dedent(f"""
    You are an expert AWS Lambda developer generating a new skill handler for LLMWiki.

    STRICT REQUIREMENTS:
    1. Follow the exact standard skill contract used in the reference examples
    2. Use the same response format: _skill_response() → statusCode/headers/body
    3. Include _log_telemetry() that writes to LOG_TABLE DynamoDB
    4. Every input must be read from body.get("inputs", body) with safe defaults
    5. Wrap all external calls in try/except — soft failures log and continue, hard failures raise _SkillError
    6. Generate real boto3 code — not pseudocode, not placeholders
    7. Use only these AWS clients (already in scope): {', '.join(clients_needed) or 'none required beyond boto3.resource(dynamodb)'}
    8. The Lambda function name is: {spec['lambda_name']}
    9. SKILL_ID = "{spec['skill_id']}", SKILL_NAME = "{spec['technical_name']}", BUSINESS_NAME = "{spec['business_name']}"
    10. Do NOT add any comment explaining what you generated. Write production code only.
    """).strip()

    user_prompt = textwrap.dedent(f"""
    Generate the complete Lambda handler.py for this skill spec.

    ## SKILL SPEC

    **Skill ID:** {spec['skill_id']}
    **Business Name:** {spec['business_name']}
    **Technical Name:** {spec['technical_name']}
    **Domain:** {spec['domain']}
    **Use Cases:** {', '.join(spec['use_case_tags']) if isinstance(spec['use_case_tags'], list) else spec['use_case_tags']}

    ### What It Does
    {spec['what_it_does']}

    ### When to Call
    {spec['when_to_call']}

    ### Inputs
    {spec['inputs_section']}

    ### Outputs
    {spec['outputs_section']}

    ### Business Rules (MUST be enforced in code)
    {spec['business_rules']}

    ### Backends to Use
    {spec['backends_section']}

    ### Error Handling
    {spec['error_handling']}

    ### Happy Path Example
    {spec['happy_path']}

    ### Edge Case Example
    {spec['edge_case']}

    ### Extra Telemetry Fields
    {spec['telemetry_section']}

    ## REFERENCE CODE (follow this exact pattern)

    {reference_code[:8000]}

    ## GENERATE THE COMPLETE handler.py NOW
    Return ONLY the Python source code. No markdown fences, no explanation.
    """).strip()

    from botocore.config import Config as BotocoreConfig
    bedrock_client = boto3.client(
        "bedrock-runtime", region_name=AWS_REGION,
        config=BotocoreConfig(read_timeout=300, connect_timeout=10,
                              retries={"max_attempts": 2}),
    )
    print(f"  Calling Claude ({MODEL_ID}) to generate handler ({spec['skill_id']})...")

    resp = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
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
    text = _validate_and_fix_code(text, spec["skill_id"], bedrock_client)
    return text


# ════════════════════════════════════════════════════════════════════════════════
# Test stub generation
# ════════════════════════════════════════════════════════════════════════════════

def generate_test_stubs(spec: dict) -> str:
    """Generate minimal unit test stubs from the happy path / edge case examples."""

    # Extract JSON blocks from happy path and edge case
    def _extract_json(text: str) -> list:
        return [m.group() for m in re.finditer(r'\{[^{}]*\}', text, re.DOTALL)]

    hp_jsons = _extract_json(spec["happy_path"])
    input_json = hp_jsons[0] if hp_jsons else '{"customer_id": "test-001"}'

    return textwrap.dedent(f"""
    \"\"\"
    Unit test stubs for {spec['technical_name']} — auto-generated from skill spec.
    Fill in mock_response values before running.
    \"\"\"
    import json
    import pytest
    from unittest.mock import MagicMock, patch

    import handler  # the generated handler.py


    HAPPY_PATH_INPUT = {input_json}


    def _make_event(inputs: dict) -> dict:
        return {{"inputs": inputs, "version": "1.0", "invoked_by": "test-runner"}}


    def test_happy_path(monkeypatch):
        event = _make_event(HAPPY_PATH_INPUT)
        # TODO: mock boto3 clients used by this skill
        result = handler.lambda_handler(event, None)
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "outputs" in body
        assert body["outputs"].get("status") in ("ready", "success", "not_applicable")


    def test_missing_required_input():
        event = _make_event({{}})  # empty inputs
        result = handler.lambda_handler(event, None)
        assert result["statusCode"] == 400


    def test_government_customer_returns_not_applicable():
        inputs = dict(HAPPY_PATH_INPUT)
        inputs["customer_type"] = "government"
        event = _make_event(inputs)
        # TODO: mock boto3 clients
        result = handler.lambda_handler(event, None)
        body = json.loads(result["body"])
        assert body["outputs"].get("status") == "not_applicable"
    """).strip()


# ════════════════════════════════════════════════════════════════════════════════
# Terraform block generation
# ════════════════════════════════════════════════════════════════════════════════

def generate_terraform(spec: dict) -> str:
    timeout = 30 if spec["tier"] == 1 else (60 if spec["tier"] == 2 else 120)
    memory  = 256 if spec["tier"] == 1 else (512 if spec["tier"] == 2 else 512)
    slug_tf = spec["slug"]
    fn_name = spec["lambda_name"]
    iam_actions = sorted({a for b in spec["backends"] for a in IAM_FOR_BACKEND.get(b, [])})
    iam_actions += ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]

    backends_needed = spec["backends"]
    needs_bedrock  = "bedrock_claude" in backends_needed
    needs_dynamodb = any(b in backends_needed for b in ("dynamodb_read", "dynamodb_write"))
    needs_sns      = "sns_publish" in backends_needed

    env_vars = 'LOG_TABLE = aws_dynamodb_table.wiki_log.name'
    if needs_bedrock:
        env_vars += '\n      BEDROCK_MODEL_ID = var.bedrock_model_id'
    if needs_dynamodb:
        env_vars += '\n      # TODO: add table env vars for this skill'
    if needs_sns:
        env_vars += '\n      # TODO: add SNS_TOPIC_ARN for this skill'

    return textwrap.dedent(f"""
    # ── {spec['skill_id']} {spec['business_name']} — auto-generated ──────────────────────────
    # Generated by scripts/generate_skill_lambda.py from {spec['skill_id'].lower()}-{slug_tf.replace('_','-')}.md

    data "archive_file" "skill_{slug_tf}" {{
      type        = "zip"
      source_dir  = "${{path.module}}/../lambda/skills/{slug_tf}"
      output_path = "${{path.module}}/../.build/skill_{slug_tf}.zip"
    }}

    resource "aws_lambda_function" "skill_{slug_tf}" {{
      function_name    = "{fn_name}"
      role             = aws_iam_role.skills_lambda.arn
      handler          = "handler.lambda_handler"
      runtime          = "python3.12"
      filename         = data.archive_file.skill_{slug_tf}.output_path
      source_code_hash = data.archive_file.skill_{slug_tf}.output_base64sha256
      timeout          = {timeout}
      memory_size      = {memory}

      environment {{
        variables = {{
          {env_vars}
        }}
      }}

      tags = {{
        skill_id      = "{spec['skill_id']}"
        tier          = "{spec['tier']}"
        use_case_tags = "{', '.join(spec['use_case_tags']) if isinstance(spec['use_case_tags'], list) else spec['use_case_tags']}"
        generated_by  = "generate_skill_lambda.py"
      }}
    }}

    resource "aws_cloudwatch_log_group" "skill_{slug_tf}" {{
      name              = "/aws/lambda/{fn_name}"
      retention_in_days = 30
    }}

    # ── SSM param so agents can look up the ARN without hardcoding ────────────
    resource "aws_ssm_parameter" "skill_{slug_tf}_arn" {{
      name  = "/llmwiki/skills/{spec['skill_id'].lower().replace('-','')}_arn"
      type  = "String"
      value = aws_lambda_function.skill_{slug_tf}.arn
    }}
    """).strip()


# ════════════════════════════════════════════════════════════════════════════════
# Requirements file
# ════════════════════════════════════════════════════════════════════════════════

def generate_requirements(spec: dict) -> str:
    libs = ["boto3>=1.34.0"]
    return "\n".join(libs) + "\n"


# ════════════════════════════════════════════════════════════════════════════════
# Write outputs
# ════════════════════════════════════════════════════════════════════════════════

def write_outputs(spec: dict, handler_code: str, test_code: str, tf_block: str,
                  requirements: str, dry_run: bool):
    skill_dir = os.path.join(SKILLS_DIR, spec["slug"])

    if dry_run:
        print("\n" + "="*72)
        print(f"DRY RUN — would write to: {skill_dir}/")
        print("="*72)
        print("\n--- handler.py (first 60 lines) ---")
        print("\n".join(handler_code.splitlines()[:60]))
        print("\n--- terraform block (first 20 lines) ---")
        print("\n".join(tf_block.splitlines()[:20]))
        print("\n--- test stubs (first 20 lines) ---")
        print("\n".join(test_code.splitlines()[:20]))
        return

    os.makedirs(skill_dir, exist_ok=True)

    handler_path = os.path.join(skill_dir, "handler.py")
    with open(handler_path, "w", encoding="utf-8") as f:
        f.write(handler_code)
    print(f"  Wrote: {handler_path}")

    req_path = os.path.join(skill_dir, "requirements.txt")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write(requirements)
    print(f"  Wrote: {req_path}")

    test_path = os.path.join(skill_dir, f"test_{spec['slug']}.py")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    print(f"  Wrote: {test_path}")

    # Append Terraform block (skip if already present)
    existing_tf = ""
    if os.path.exists(TF_FILE):
        with open(TF_FILE, "r", encoding="utf-8") as f:
            existing_tf = f.read()

    if spec["lambda_name"] not in existing_tf:
        with open(TF_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n" + tf_block + "\n")
        print(f"  Appended Terraform to: {TF_FILE}")
    else:
        print(f"  Terraform block for {spec['lambda_name']} already present — skipped")


# ════════════════════════════════════════════════════════════════════════════════
# Seed the Skill Registry DynamoDB
# ════════════════════════════════════════════════════════════════════════════════

def seed_registry(spec: dict, dry_run: bool):
    """Write a registry entry to llmwiki-skills-registry DynamoDB (if table exists)."""
    import time
    from datetime import datetime, timezone
    if dry_run:
        print("  [dry-run] Would write to llmwiki-skills-registry DynamoDB")
        return
    try:
        ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = ddb.Table("llmwiki-skills-registry")
        table.put_item(Item={
            "skill_id":      spec["skill_id"],
            "skill_name":    spec["technical_name"],
            "business_name": spec["business_name"],
            "lambda_name":   spec["lambda_name"],
            "tier":          spec["tier"],
            "version":       spec["version"],
            "domain":        spec["domain"],
            "use_case_tags": spec["use_case_tags"] if isinstance(spec["use_case_tags"], list) else [spec["use_case_tags"]],
            "status":        "generated",
            "spec_source":   os.path.basename(args.spec),
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "expires_at":    int(time.time()) + 365 * 86400,
        })
        print("  Registered in llmwiki-skills-registry DynamoDB")
    except Exception as e:
        print(f"  WARN: Could not write to skills-registry (table may not exist yet): {e}")
        print("  The registry entry will be created on next 'terraform apply'")


# ════════════════════════════════════════════════════════════════════════════════
# Deploy helper
# ════════════════════════════════════════════════════════════════════════════════

def deploy_lambda(spec: dict):
    """Zip and deploy the generated Lambda directly (bypassing full Terraform apply)."""
    import subprocess, zipfile, tempfile
    skill_dir  = os.path.join(SKILLS_DIR, spec["slug"])
    build_dir  = os.path.join(ROOT_DIR, ".build")
    os.makedirs(build_dir, exist_ok=True)
    zip_path   = os.path.join(build_dir, f"skill_{spec['slug']}.zip")

    print(f"  Zipping {skill_dir} → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(skill_dir):
            if fname.endswith(".py"):
                zf.write(os.path.join(skill_dir, fname), fname)

    fn = spec["lambda_name"]
    profile = os.environ.get("AWS_PROFILE", "tzg-sandbox")
    print(f"  Deploying {fn} via aws lambda update-function-code ...")
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
        info = json.loads(result.stdout)
        print(f"  Deployed: {info}")
    else:
        print(f"  WARN: aws lambda update-function-code failed: {result.stderr.strip()}")
        print("  If the function does not exist yet, run 'terraform apply' first.")


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a skill Lambda from a skill spec .md file")
    parser.add_argument("--spec",    required=True, help="Path to the skill spec .md file")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing files")
    parser.add_argument("--deploy",  action="store_true", help="Deploy Lambda immediately after generating")
    parser.add_argument("--region",  default=None, help="AWS region (overrides AWS_DEFAULT_REGION)")
    parser.add_argument("--profile", default=None, help="AWS SSO profile name")
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

    print(f"\nLLMWiki Skill Generator")
    print(f"{'='*60}")
    print(f"Spec  : {spec_path}")
    print(f"Region: {AWS_REGION}")
    print(f"Model : {MODEL_ID}")
    print(f"{'='*60}\n")

    print("Step 1/5 — Parsing skill spec...")
    spec = parse_spec(spec_path)
    print(f"  Skill ID      : {spec['skill_id']}")
    print(f"  Business Name : {spec['business_name']}")
    print(f"  Technical Name: {spec['technical_name']}")
    print(f"  Lambda Name   : {spec['lambda_name']}")
    print(f"  Backends      : {spec['backends'] or ['none']}")
    print(f"  Output dir    : lambda/skills/{spec['slug']}/")

    print("\nStep 2/5 — Generating Lambda handler (calling Claude)...")
    handler_code = generate_handler(spec, dry_run=args.dry_run)
    print(f"  Generated {len(handler_code.splitlines())} lines")

    print("\nStep 3/5 — Generating test stubs...")
    test_code = generate_test_stubs(spec)

    print("\nStep 4/5 — Generating Terraform block...")
    tf_block     = generate_terraform(spec)
    requirements = generate_requirements(spec)

    print("\nStep 5/5 — Writing output files...")
    write_outputs(spec, handler_code, test_code, tf_block, requirements, dry_run=args.dry_run)

    if not args.dry_run:
        seed_registry(spec, dry_run=False)

    if args.deploy and not args.dry_run:
        print("\nDeploying Lambda...")
        deploy_lambda(spec)

    print(f"\n{'='*60}")
    if args.dry_run:
        print("DRY RUN complete — no files written")
    else:
        print(f"DONE — skill {spec['skill_id']} {spec['business_name']} generated")
        print(f"\nNext steps:")
        print(f"  1. Review lambda/skills/{spec['slug']}/handler.py")
        print(f"  2. Run tests: cd lambda/skills/{spec['slug']} && python -m pytest")
        if not args.deploy:
            print(f"  3. Deploy: bash scripts/deploy.sh  (or re-run with --deploy)")
        print(f"  4. Register spec in wiki: aws s3 cp {args.spec} s3://$WIKI_BUCKET/wiki/skills/ --profile $AWS_PROFILE")
    print(f"{'='*60}\n")
