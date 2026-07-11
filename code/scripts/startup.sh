#!/usr/bin/env bash
# =============================================================================
# startup.sh — Start LLMWiki services (resume after cost-saving shutdown)
# Starts: ECS Fargate Streamlit service (set desired_count = 1)
# Usage: ./scripts/startup.sh [--profile <profile>]
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
echo "  LLMWiki Startup"
echo "========================================"

# Verify session
aws sts get-caller-identity --profile "$PROFILE" > /dev/null 2>&1 || {
  echo "ERROR: AWS session expired. Run: aws sso login --profile $PROFILE"
  exit 1
}

# Resolve cluster/service from Terraform state (or SSM)
cd "$TF_DIR"
ECS_CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null || echo "llmwiki-cluster")
ECS_SERVICE=$(terraform output -raw ecs_service_name 2>/dev/null || echo "llmwiki-streamlit")
STREAMLIT_URL=$(terraform output -raw streamlit_url 2>/dev/null || echo "")

echo ""
echo "→ Starting ECS service: $ECS_SERVICE (desired count → 1)..."
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --desired-count 1 \
  --region "$REGION" \
  --profile "$PROFILE" \
  > /dev/null

echo "  Waiting for service to become stable..."
aws ecs wait services-stable \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$REGION" \
  --profile "$PROFILE"

echo ""
echo "========================================"
echo "  STARTUP COMPLETE"
echo "========================================"
echo ""
echo "  Streamlit UI   : $STREAMLIT_URL"
echo "  (may take 30-60s for health checks to pass)"
echo ""

# Show status
CURRENT_COUNT=$(aws ecs describe-services \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --query 'services[0].runningCount' \
  --output text)

echo "  Running tasks: $CURRENT_COUNT"
echo ""
echo "  Services always ON (no action needed):"
echo "  - Lambda (ingest, query, converter) — serverless, zero cost when idle"
echo "  - S3 (wiki bucket) — storage only"
echo "  - DynamoDB (index, log, registry) — on-demand, zero cost when idle"
echo "  - API Gateway — zero cost when idle"
echo "  - Bedrock Knowledge Base — zero cost when idle"
echo ""
