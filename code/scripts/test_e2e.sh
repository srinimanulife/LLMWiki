#!/usr/bin/env bash
# =============================================================================
# test_e2e.sh — End-to-end test: upload a doc, wait for ingest, run a query
# Usage: ./scripts/test_e2e.sh [--profile <profile>]
# =============================================================================
set -euo pipefail

PROFILE="${PROFILE:-tzg-sandbox}"
REGION="${REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="$REGION"

echo "========================================"
echo "  LLMWiki End-to-End Test"
echo "========================================"

# Get outputs
cd "$TF_DIR"
WIKI_BUCKET=$(terraform output -raw wiki_bucket_name)
API_URL=$(terraform output -raw api_gateway_url)
API_KEY=$(aws ssm get-parameter \
  --name /llmwiki/api_key \
  --with-decryption \
  --profile "$PROFILE" \
  --query Parameter.Value \
  --output text)

INGEST_LAMBDA=$(terraform output -raw ingest_lambda_name)

echo ""
echo "Bucket  : $WIKI_BUCKET"
echo "API URL : $API_URL"
echo ""

# ── Test 1: Wiki status ───────────────────────────────────────────
echo "TEST 1: Wiki status..."
STATUS=$(curl -sf -X GET "$API_URL/wiki/status" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" || echo '{"error":"status_failed"}')
echo "  Response: $STATUS"
echo "  PASS: status endpoint reachable"
echo ""

# ── Test 2: Check sample docs exist ──────────────────────────────
echo "TEST 2: Checking sample source documents in S3..."
for key in \
  "raw/papers/cloud-strategy-2026.md" \
  "raw/notes/team-meeting-2026-05-01.md" \
  "raw/articles/generative-ai-enterprise-trends.md"; do
  if aws s3api head-object --bucket "$WIKI_BUCKET" --key "$key" --profile "$PROFILE" 2>/dev/null; then
    echo "  PASS: $key"
  else
    echo "  FAIL: $key not found"
  fi
done
echo ""

# ── Test 3: Trigger ingest on all sample docs ─────────────────────
echo "TEST 3: Triggering ingest Lambda directly on sample documents..."
for key in \
  "raw/papers/cloud-strategy-2026.md" \
  "raw/notes/team-meeting-2026-05-01.md" \
  "raw/articles/generative-ai-enterprise-trends.md" \
  "raw/notes/infrastructure-metrics-q1-2026.md" \
  "raw/articles/agentcore-architecture-overview.md"; do
  echo "  Ingesting: $key"
  PAYLOAD=$(python3 -c "
import json
print(json.dumps({'Records': [{'s3': {'bucket': {'name': '$WIKI_BUCKET'}, 'object': {'key': '$key'}}}]}))
")
  aws lambda invoke \
    --function-name "$INGEST_LAMBDA" \
    --invocation-type RequestResponse \
    --payload "$PAYLOAD" \
    --profile "$PROFILE" \
    --cli-binary-format raw-in-base64-out \
    /tmp/ingest_result.json > /dev/null
  RESULT=$(cat /tmp/ingest_result.json)
  echo "  Result: $RESULT"
done
echo ""

# ── Test 4: Wait and check wiki pages exist ───────────────────────
echo "TEST 4: Checking wiki pages were created (waiting up to 60s)..."
sleep 10
PAGES_FOUND=0
for i in $(seq 1 6); do
  COUNT=$(aws s3 ls "s3://$WIKI_BUCKET/wiki/sources/" --profile "$PROFILE" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$COUNT" -gt 0 ]; then
    echo "  PASS: $COUNT wiki page(s) found in wiki/sources/"
    PAGES_FOUND=1
    break
  fi
  echo "  Waiting... ($((i * 10))s)"
  sleep 10
done
[ "$PAGES_FOUND" -eq 0 ] && echo "  WARN: No wiki pages found after 60s — check Lambda logs"
echo ""

# ── Test 5: Query the wiki ────────────────────────────────────────
echo "TEST 5: Query — 'What are the key risks in the cloud strategy?'"
QUERY_RESULT=$(curl -sf -X POST "$API_URL/query" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "What are the key risks in the cloud strategy?"}')
echo "  Answer: $(echo "$QUERY_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('answer','')[:200])")"
echo "  Confidence: $(echo "$QUERY_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('confidence','unknown'))")"
echo "  PASS: Query returned a response"
echo ""

# ── Test 6: Cross-document query ─────────────────────────────────
echo "TEST 6: Cross-document query — 'What was Q1 2026 cloud spend and what are the AI trends?'"
QUERY_RESULT2=$(curl -sf -X POST "$API_URL/query" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "What was Q1 2026 cloud spend and what are the AI trends?"}')
SOURCES=$(echo "$QUERY_RESULT2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('sources',[])))")
echo "  Sources cited: $SOURCES"
echo "  PASS: Cross-document query complete"
echo ""

echo "========================================"
echo "  END-TO-END TEST COMPLETE"
echo "========================================"
