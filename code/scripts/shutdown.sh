#!/usr/bin/env bash
# =============================================================================
# shutdown.sh — Stop LLMWiki services to save cost
# Stops: ECS Fargate Streamlit (desired_count → 0)
# Does NOT stop: Lambda, S3, DynamoDB, API GW, Bedrock KB (zero cost when idle)
# Does NOT destroy any data.
# Usage: ./scripts/shutdown.sh [--profile <profile>]
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
echo "  LLMWiki Shutdown (cost-saving mode)"
echo "  No data will be deleted."
echo "========================================"

aws sts get-caller-identity --profile "$PROFILE" > /dev/null 2>&1 || {
  echo "ERROR: AWS session expired. Run: aws sso login --profile $PROFILE"
  exit 1
}

cd "$TF_DIR"
ECS_CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null || echo "llmwiki-cluster")
ECS_SERVICE=$(terraform output -raw ecs_service_name 2>/dev/null || echo "llmwiki-streamlit")

echo ""
echo "→ Stopping ECS service: $ECS_SERVICE (desired count → 0)..."
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --desired-count 0 \
  --region "$REGION" \
  --profile "$PROFILE" \
  > /dev/null

echo "  Waiting for tasks to drain..."
aws ecs wait services-stable \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$REGION" \
  --profile "$PROFILE"

echo ""
echo "========================================"
echo "  SHUTDOWN COMPLETE"
echo "========================================"
echo ""
echo "  Stopped (cost = \$0/hr while stopped):"
echo "  ✓ ECS Fargate Streamlit (0 tasks running)"
echo ""
echo "  Still running (zero cost when idle):"
echo "  ✓ Lambda functions     — charged only on invocation"
echo "  ✓ S3 wiki bucket       — storage cost only (~\$0.023/GB/month)"
echo "  ✓ DynamoDB tables      — on-demand, \$0 when not queried"
echo "  ✓ API Gateway          — \$0 when not called"
echo "  ✓ Bedrock KB           — \$0 when not queried"
echo "  ✓ OpenSearch Serverless— minimal standby cost"
echo ""
echo "  Estimated monthly cost while STOPPED: < \$5"
echo "  Run ./scripts/startup.sh to resume."
echo ""
