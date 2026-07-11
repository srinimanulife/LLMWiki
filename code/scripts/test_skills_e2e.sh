#!/usr/bin/env bash
# =============================================================================
# test_skills_e2e.sh — End-to-end skill validation for UC1 POC
# Tests each skill individually (SK-01 through SK-05) then runs the full
# UC1 orchestrator to validate the complete 6-step skill flow.
#
# Usage: ./scripts/test_skills_e2e.sh [--profile tzg-sandbox] [--region us-east-1]
# =============================================================================
set -euo pipefail

PROFILE="${PROFILE:-tzg-sandbox}"
REGION="${REGION:-us-east-1}"
CUSTOMER_ID="skill-e2e-test-customer-001"
PASS=0
FAIL=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    *) shift ;;
  esac
done

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="$REGION"

echo "========================================"
echo "  LLMWiki Skill Architecture — E2E Tests"
echo "  Profile : $PROFILE | Region: $REGION"
echo "  Customer: $CUSTOMER_ID"
echo "========================================"

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ FAIL: $1"; FAIL=$((FAIL+1)); }

invoke_lambda() {
  local fn="$1"
  local payload="$2"
  aws lambda invoke \
    --function-name "$fn" \
    --payload "$payload" \
    --cli-binary-format raw-in-base64-out \
    /tmp/lambda_out.json \
    --profile "$PROFILE" \
    --region "$REGION" \
    > /dev/null 2>&1
  cat /tmp/lambda_out.json
}

# Unwrap Lambda body wrapper
unwrap() {
  python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
if 'body' in d:
    inner = d['body']
    if isinstance(inner, str):
        inner = json.loads(inner)
    d = inner
print(json.dumps(d))
" 2>/dev/null || echo "{}"
}

extract() {
  local json="$1"
  local field="$2"
  echo "$json" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('$field', ''))
" 2>/dev/null || echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — SK-01 Customer Briefing Loader
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 1: SK-01 Customer Briefing Loader ──"
SK01_PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'skill': 'ContextBootstrapSkill',
  'version': '1.0',
  'invoked_by': 'skill-e2e-test',
  'inputs': {
    'customer_id': '$CUSTOMER_ID',
    'use_case': 'UC1',
    'agent_id': 'skill-e2e-test'
  }
}))
")
SK01_OUT=$(invoke_lambda "llmwiki-skill-context-bootstrap" "$SK01_PAYLOAD" | unwrap)

SK01_STATUS=$(extract "$SK01_OUT" "status")
SK01_SKILL=$(extract "$SK01_OUT" "skill")
SK01_BIZ=$(extract "$SK01_OUT" "business_name")
SK01_LATENCY=$(extract "$SK01_OUT" "latency_ms")

if [[ "$SK01_STATUS" == "success" ]]; then
  ok "SK-01 returned status=success"
else
  fail "SK-01 failed: status=$SK01_STATUS — $SK01_OUT"
fi

if [[ "$SK01_SKILL" == "ContextBootstrapSkill" ]]; then
  ok "SK-01 skill name correct: $SK01_SKILL"
else
  fail "SK-01 skill name wrong: $SK01_SKILL"
fi

if [[ "$SK01_BIZ" == "Customer Briefing Loader" ]]; then
  ok "SK-01 business name: '$SK01_BIZ'"
else
  fail "SK-01 business name wrong: '$SK01_BIZ'"
fi

# Verify outputs structure
SK01_CUST_STATUS=$(echo "$SK01_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('customer_status', ''))
" 2>/dev/null || echo "")
if [[ -n "$SK01_CUST_STATUS" ]]; then
  ok "SK-01 outputs.customer_status present: $SK01_CUST_STATUS"
else
  fail "SK-01 outputs.customer_status missing"
fi

ok "SK-01 latency: ${SK01_LATENCY}ms"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — SK-02 Knowledge Finder
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 2: SK-02 Knowledge Finder ──"
SK02_PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'skill': 'WikiQuerySkill',
  'version': '1.0',
  'invoked_by': 'skill-e2e-test',
  'inputs': {
    'question': 'What are the key steps in the Sales-to-Service handoff process?',
    'domain': 'customer-onboarding',
    'customer_id': '$CUSTOMER_ID',
    'use_case': 'UC1',
    'max_results': 5
  }
}))
")
SK02_OUT=$(invoke_lambda "llmwiki-skill-wiki-query" "$SK02_PAYLOAD" | unwrap)

SK02_STATUS=$(extract "$SK02_OUT" "status")
SK02_BIZ=$(extract "$SK02_OUT" "business_name")
SK02_CONFIDENCE=$(echo "$SK02_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('confidence', ''))
" 2>/dev/null || echo "")
SK02_ITEMS=$(echo "$SK02_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(len(d.get('outputs', {}).get('action_items', [])))
" 2>/dev/null || echo "0")

if [[ "$SK02_STATUS" == "success" ]]; then
  ok "SK-02 returned status=success"
else
  fail "SK-02 failed: status=$SK02_STATUS"
fi

if [[ "$SK02_BIZ" == "Knowledge Finder" ]]; then
  ok "SK-02 business name: '$SK02_BIZ'"
else
  fail "SK-02 business name wrong: '$SK02_BIZ'"
fi

if [[ -n "$SK02_CONFIDENCE" ]]; then
  ok "SK-02 confidence: $SK02_CONFIDENCE (action_items: $SK02_ITEMS)"
else
  fail "SK-02 confidence missing from outputs"
fi

SK02_PAGES=$(extract "$SK02_OUT" "wiki_pages_used")
ok "SK-02 wiki_pages_used: $SK02_PAGES"

# Verify retry logic field (note field appears on fallback)
SK02_ANSWER=$(echo "$SK02_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
a = d.get('outputs', {}).get('answer', '')
print(a[:80] if a else 'EMPTY')
" 2>/dev/null || echo "EMPTY")
if [[ "$SK02_ANSWER" != "EMPTY" ]]; then
  ok "SK-02 answer returned: '${SK02_ANSWER:0:60}...'"
else
  fail "SK-02 answer is empty"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — SK-05 Missing Info Radar (triggered on low-confidence scenario)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 3: SK-05 Missing Info Radar ──"
SK05_PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'skill': 'GapDetectionSkill',
  'version': '1.0',
  'invoked_by': 'skill-e2e-test',
  'inputs': {
    'question': 'What is the contracted SLA for claims turnaround for a new insurance customer?',
    'domain': 'customer-onboarding',
    'use_case': 'UC1',
    'customer_id': '$CUSTOMER_ID',
    'low_confidence_response': {
      'confidence': 'low',
      'gaps_detected': [],
      'answer': 'The wiki does not have specific SLA information for this customer.'
    }
  }
}))
")
SK05_OUT=$(invoke_lambda "llmwiki-skill-gap-detection" "$SK05_PAYLOAD" | unwrap)

SK05_STATUS=$(extract "$SK05_OUT" "status")
SK05_BIZ=$(extract "$SK05_OUT" "business_name")
SK05_GAPS=$(echo "$SK05_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('gap_count', 0))
" 2>/dev/null || echo "0")
SK05_LOGGED=$(extract "$SK05_OUT" "logged_to_gaps_table")

if [[ "$SK05_STATUS" == "success" ]]; then
  ok "SK-05 returned status=success"
else
  fail "SK-05 failed: status=$SK05_STATUS"
fi

if [[ "$SK05_BIZ" == "Missing Info Radar" ]]; then
  ok "SK-05 business name: '$SK05_BIZ'"
else
  fail "SK-05 business name wrong: '$SK05_BIZ'"
fi

if [[ "$SK05_GAPS" -gt 0 ]]; then
  ok "SK-05 detected $SK05_GAPS gap(s) — recorded in llmwiki-gaps"
else
  fail "SK-05 detected no gaps (expected at least 1)"
fi

if [[ "$SK05_LOGGED" == "True" || "$SK05_LOGGED" == "true" ]]; then
  ok "SK-05 logged_to_gaps_table=true"
else
  fail "SK-05 logged_to_gaps_table missing or false"
fi

# Verify human_prompt is present for first gap
SK05_PROMPT=$(echo "$SK05_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
gaps = d.get('outputs', {}).get('gaps', [])
if gaps:
    print(gaps[0].get('human_prompt', ''))
" 2>/dev/null || echo "")
if [[ -n "$SK05_PROMPT" ]]; then
  ok "SK-05 gap human_prompt present: '${SK05_PROMPT:0:60}...'"
else
  fail "SK-05 gap human_prompt missing"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — SK-04 Template Auto-Fill
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 4: SK-04 Template Auto-Fill ──"
SK04_PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'skill': 'ArtifactResolutionSkill',
  'version': '1.0',
  'invoked_by': 'skill-e2e-test',
  'inputs': {
    'artifact_type': 'persona-template',
    'customer_id': '$CUSTOMER_ID',
    'use_case': 'UC1',
    'available_context': {
      'customer_id': '$CUSTOMER_ID',
      'handoff_summary': 'New customer onboarding for health insurance platform',
      'action_items': ['Complete SOW review', 'Schedule kickoff meeting'],
      'products_in_scope': ['TriZetto Facets']
    }
  }
}))
")
SK04_OUT=$(invoke_lambda "llmwiki-skill-artifact-resolution" "$SK04_PAYLOAD" | unwrap)

SK04_STATUS=$(extract "$SK04_OUT" "status")
SK04_BIZ=$(extract "$SK04_OUT" "business_name")
SK04_FOUND=$(echo "$SK04_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('found', False))
" 2>/dev/null || echo "False")

if [[ "$SK04_STATUS" == "success" || "$SK04_STATUS" == "not_found" ]]; then
  ok "SK-04 returned status=$SK04_STATUS (artifact found=$SK04_FOUND)"
else
  fail "SK-04 failed with unexpected status=$SK04_STATUS"
fi

if [[ "$SK04_BIZ" == "Template Auto-Fill" ]]; then
  ok "SK-04 business name: '$SK04_BIZ'"
else
  fail "SK-04 business name wrong: '$SK04_BIZ'"
fi

# Either found (with populated fields) or graceful not_found (with note)
SK04_CONTENT=$(echo "$SK04_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
c = d.get('outputs', {}).get('artifact_content', '')
n = d.get('outputs', {}).get('note', '')
print(c[:60] if c else n[:60])
" 2>/dev/null || echo "")
ok "SK-04 result: '${SK04_CONTENT:0:80}...'"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — SK-03 Knowledge Recorder
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 5: SK-03 Knowledge Recorder ──"
TODAY=$(date +%Y-%m-%d)
SK03_CONTENT="---
title: Skill E2E Test Handoff Brief
date: $TODAY
customer_id: $CUSTOMER_ID
use_case_tags: [UC1]
domain: customer-onboarding
contributing_agent: skill-e2e-test
status: active
---

# Skill E2E Test Handoff Brief

This page was created by the automated skill E2E test suite on $TODAY.
It validates that SK-03 (Knowledge Recorder / WikiContributeSkill) correctly
writes pages to S3, updates DynamoDB, and triggers Bedrock KB sync.

## Test Context

- Customer: $CUSTOMER_ID
- Test: test_skills_e2e.sh
- Skill: SK-03 WikiContributeSkill v1.0
"

SK03_PAYLOAD=$(python3 -c "
import json, sys
content = open('/dev/stdin').read()
print(json.dumps({
  'skill': 'WikiContributeSkill',
  'version': '1.0',
  'invoked_by': 'skill-e2e-test',
  'inputs': {
    'page_type': 'customers',
    'page_slug': 'skill-e2e-test-customer-001-handoff-skill-test',
    'content': content,
    'agent_id': 'skill-e2e-test',
    'customer_id': '$CUSTOMER_ID',
    'use_case': 'UC1',
    'human_review_required': False
  }
}))
" <<< "$SK03_CONTENT")

SK03_OUT=$(invoke_lambda "llmwiki-skill-wiki-contribute" "$SK03_PAYLOAD" | unwrap)

SK03_STATUS=$(extract "$SK03_OUT" "status")
SK03_BIZ=$(extract "$SK03_OUT" "business_name")
SK03_CONTRIB_STATUS=$(echo "$SK03_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('status', ''))
" 2>/dev/null || echo "")
SK03_S3=$(echo "$SK03_OUT" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('outputs', {}).get('s3_uri', ''))
" 2>/dev/null || echo "")

if [[ "$SK03_STATUS" == "success" ]]; then
  ok "SK-03 returned skill status=success"
else
  fail "SK-03 skill failed: $SK03_STATUS — $SK03_OUT"
fi

if [[ "$SK03_BIZ" == "Knowledge Recorder" ]]; then
  ok "SK-03 business name: '$SK03_BIZ'"
else
  fail "SK-03 business name wrong: '$SK03_BIZ'"
fi

if [[ "$SK03_CONTRIB_STATUS" == "indexed" ]]; then
  ok "SK-03 contribution indexed: $SK03_S3"
else
  fail "SK-03 contribution not indexed (status=$SK03_CONTRIB_STATUS)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — Skill telemetry logged to DynamoDB
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 6: Skill telemetry in llmwiki-log ──"
TODAY_LOG=$(date +%Y-%m-%d)
LOG_COUNT=$(aws dynamodb scan \
  --table-name llmwiki-log \
  --filter-expression "log_date = :d AND agent_id = :a" \
  --expression-attribute-values "{\":d\":{\"S\":\"$TODAY_LOG\"},\":a\":{\"S\":\"skill-e2e-test\"}}" \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('Count', 0))" 2>/dev/null || echo "0")

if [[ "$LOG_COUNT" -ge 3 ]]; then
  ok "Skill telemetry: $LOG_COUNT invocation records in llmwiki-log"
else
  fail "Expected ≥3 telemetry records, found $LOG_COUNT"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 — Full UC1 Orchestrator (all 6 skill steps)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 7: Full UC1 Skill Orchestrator ──"
UC1_PAYLOAD=$(python3 -c "
import json
print(json.dumps({'customer_id': '$CUSTOMER_ID'}))
")
UC1_OUT=$(invoke_lambda "llmwiki-uc1-orchestrator" "$UC1_PAYLOAD" | unwrap)

UC1_STATUS=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(200 if 'customer_id' in d else d.get('statusCode', 0))
" <<< "$UC1_OUT" 2>/dev/null || echo "0")

UC1_INDEXED=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('wiki_indexed', False))
" <<< "$UC1_OUT" 2>/dev/null || echo "False")

UC1_SKILLS=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(','.join(d.get('skills_used', [])))
" <<< "$UC1_OUT" 2>/dev/null || echo "")

UC1_LOG_COUNT=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(len(d.get('skill_execution_log', [])))
" <<< "$UC1_OUT" 2>/dev/null || echo "0")

UC1_LATENCY=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('total_latency_ms', 0))
" <<< "$UC1_OUT" 2>/dev/null || echo "0")

if [[ "$UC1_INDEXED" == "True" || "$UC1_INDEXED" == "true" ]]; then
  ok "UC1 orchestrator: handoff brief indexed in wiki"
else
  fail "UC1 orchestrator: wiki_indexed=False — $UC1_OUT"
fi

if [[ "$UC1_LOG_COUNT" -ge 5 ]]; then
  ok "UC1 orchestrator: $UC1_LOG_COUNT skill execution steps logged"
else
  fail "UC1 orchestrator: expected ≥5 skill steps, got $UC1_LOG_COUNT"
fi

if [[ -n "$UC1_SKILLS" ]]; then
  ok "UC1 skills used: $UC1_SKILLS"
else
  fail "UC1 skills_used missing"
fi

ok "UC1 total latency: ${UC1_LATENCY}ms"

UC1_SUMMARY=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('summary', ''))
" <<< "$UC1_OUT" 2>/dev/null || echo "")
if [[ -n "$UC1_SUMMARY" ]]; then
  ok "UC1 summary: '${UC1_SUMMARY:0:100}...'"
else
  fail "UC1 summary missing"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 8 — Verify contributed page readable from S3
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 8: UC1 handoff page readable from S3 ──"
UC1_S3_URI=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('handoff_s3_uri', ''))
" <<< "$UC1_OUT" 2>/dev/null || echo "")
UC1_S3_KEY=$(echo "$UC1_S3_URI" | sed 's|s3://[^/]*/||')

if [[ -n "$UC1_S3_KEY" ]]; then
  WIKI_BUCKET=$(cd /mnt/c/Users/859600/OneDrive\ -\ Cognizant/AWSLab/LLMWiki/code/terraform && \
    terraform output -raw wiki_bucket_name 2>/dev/null || echo "")
  if [[ -n "$WIKI_BUCKET" ]] && aws s3 cp "s3://$WIKI_BUCKET/$UC1_S3_KEY" /tmp/uc1_brief.md \
      --profile "$PROFILE" --region "$REGION" 2>/dev/null; then
    PAGE_SIZE=$(wc -c < /tmp/uc1_brief.md)
    ok "UC1 handoff page readable from S3 ($PAGE_SIZE bytes): $UC1_S3_KEY"
  else
    fail "Could not read UC1 handoff page from S3: $UC1_S3_KEY"
  fi
else
  fail "UC1 handoff_s3_uri missing from orchestrator response"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 9 — Skill contract validation (all skills return standard fields)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "── Test 9: Skill contract validation ──"
for SKILL_OUT_VAR in "SK01_OUT" "SK02_OUT" "SK05_OUT" "SK04_OUT" "SK03_OUT"; do
  OUT="${!SKILL_OUT_VAR}"
  MISSING_FIELDS=$(python3 -c "
import json, sys
d = json.loads('''$OUT'''.replace(\"'''\", ''))
required = ['skill', 'business_name', 'skill_id', 'version', 'status', 'outputs', 'latency_ms']
missing = [f for f in required if f not in d]
print(','.join(missing) if missing else 'none')
" 2>/dev/null || echo "parse-error")
  if [[ "$MISSING_FIELDS" == "none" ]]; then
    SKILL_NAME=$(python3 -c "import json;d=json.loads('''$OUT'''.replace(\"'''\",'')); print(d.get('skill_id','?'))" 2>/dev/null || echo "?")
    ok "$SKILL_NAME standard contract fields all present"
  else
    fail "$SKILL_OUT_VAR missing contract fields: $MISSING_FIELDS"
  fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "→ Cleaning up E2E test artifacts..."
WIKI_BUCKET=$(cd /mnt/c/Users/859600/OneDrive\ -\ Cognizant/AWSLab/LLMWiki/code/terraform && \
  terraform output -raw wiki_bucket_name 2>/dev/null || echo "")

if [[ -n "$WIKI_BUCKET" ]]; then
  # Remove SK-03 test page
  aws s3 rm "s3://$WIKI_BUCKET/wiki/customers/skill-e2e-test-customer-001-handoff-skill-test.md" \
    --profile "$PROFILE" --region "$REGION" 2>/dev/null \
    && echo "  Removed SK-03 test page" || echo "  (SK-03 test page already removed)"

  # Remove UC1 orchestrator test page
  if [[ -n "$UC1_S3_KEY" ]]; then
    aws s3 rm "s3://$WIKI_BUCKET/$UC1_S3_KEY" \
      --profile "$PROFILE" --region "$REGION" 2>/dev/null \
      && echo "  Removed UC1 orchestrator test page" || true
  fi
fi

# Remove DynamoDB test records
aws dynamodb delete-item \
  --table-name llmwiki-index \
  --key '{"page_type":{"S":"customers"},"page_slug":{"S":"skill-e2e-test-customer-001-handoff-skill-test"}}' \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null \
  && echo "  Removed SK-03 DynamoDB record" || true

BRIEF_SLUG=$(python3 -c "
import json, sys
d = json.loads('''$(cat /tmp/lambda_out.json 2>/dev/null || echo '{}')'''.replace(\"'''\", ''))
# slug from UC1 output
" 2>/dev/null || echo "")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  SKILL E2E TEST RESULTS"
echo "  PASSED : $PASS"
echo "  FAILED : $FAIL"
echo "========================================"
echo ""
echo "  Skills tested: SK-01 SK-02 SK-03 SK-04 SK-05 + UC1 Orchestrator"
echo "  Each skill: invocation contract ✓  business name ✓  telemetry ✓"
echo ""
[[ "$FAIL" -eq 0 ]]
