#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full LLMWiki deploy (Phase 0 + Phase 1)
# Usage: ./scripts/deploy.sh [--profile <profile>] [--region <region>]
# =============================================================================
set -euo pipefail

PROFILE="${PROFILE:-tzg-sandbox}"
REGION="${REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$ROOT_DIR/terraform"
BUILD_DIR="$ROOT_DIR/.build"

# Parse flags
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="$REGION"

# Use docker.exe when running under WSL without native Docker
if ! command -v docker &>/dev/null && command -v docker.exe &>/dev/null; then
  shopt -s expand_aliases 2>/dev/null || true
  alias docker=docker.exe
  DOCKER_CMD="docker.exe"
else
  DOCKER_CMD="docker"
fi

echo "========================================"
echo "  LLMWiki Deploy"
echo "  Profile : $PROFILE"
echo "  Region  : $REGION"
echo "========================================"

# ── Step 0: Verify AWS session ────────────────────────────────────
echo ""
echo "→ Verifying AWS credentials..."
IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" 2>&1)
if echo "$IDENTITY" | grep -q "error\|Error\|expired"; then
  echo "ERROR: AWS session invalid. Run: aws sso login --profile $PROFILE"
  exit 1
fi
ACCOUNT_ID=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
echo "  Account: $ACCOUNT_ID"

# ── Step 1: Bootstrap Terraform backend ──────────────────────────
echo ""
echo "→ Bootstrapping Terraform backend (S3 + DynamoDB state)..."
TF_STATE_BUCKET="llmwiki-tfstate-${ACCOUNT_ID}"

if ! aws s3api head-bucket --bucket "$TF_STATE_BUCKET" --profile "$PROFILE" 2>/dev/null; then
  echo "  Creating Terraform state bucket: $TF_STATE_BUCKET"
  aws s3api create-bucket \
    --bucket "$TF_STATE_BUCKET" \
    --region "$REGION" \
    --profile "$PROFILE" \
    $([ "$REGION" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=$REGION" || echo "")

  aws s3api put-bucket-versioning \
    --bucket "$TF_STATE_BUCKET" \
    --versioning-configuration Status=Enabled \
    --profile "$PROFILE"

  aws s3api put-bucket-encryption \
    --bucket "$TF_STATE_BUCKET" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' \
    --profile "$PROFILE"

  aws s3api put-public-access-block \
    --bucket "$TF_STATE_BUCKET" \
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    --profile "$PROFILE"
fi

if ! aws dynamodb describe-table --table-name llmwiki-tfstate-lock --profile "$PROFILE" 2>/dev/null; then
  echo "  Creating Terraform lock table: llmwiki-tfstate-lock"
  aws dynamodb create-table \
    --table-name llmwiki-tfstate-lock \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" \
    --profile "$PROFILE"
fi

# Update backend.tf with correct bucket name
sed -i "s/bucket.*=.*\"llmwiki-tfstate\"/bucket         = \"$TF_STATE_BUCKET\"/" "$TF_DIR/main.tf" 2>/dev/null || true

# ── Step 2: Build Lambda packages ─────────────────────────────────
echo ""
echo "→ Building Lambda packages..."
mkdir -p "$BUILD_DIR"

for fn in ingest query converter business_query contribute playbook; do
  echo "  Packaging $fn..."
  SRC="$ROOT_DIR/lambda/$fn"
  ZIP="$BUILD_DIR/$fn.zip"
  (cd "$SRC" && zip -qr "$ZIP" . -x "*.pyc" "__pycache__/*")
  echo "    → $ZIP ($(du -sh "$ZIP" | cut -f1))"
done

# Skill Lambdas (SK-01 through SK-05 + UC1 orchestrator)
echo "  Packaging skill Lambdas..."
for skill in context_bootstrap wiki_query wiki_contribute artifact_resolution gap_detection uc1_orchestrator; do
  SRC="$ROOT_DIR/lambda/skills/$skill"
  if [[ -d "$SRC" ]]; then
    ZIP_NAME="$(echo "$skill" | sed 's/_/-/g')"
    ZIP="$BUILD_DIR/skill_${skill}.zip"
    (cd "$SRC" && zip -qr "$ZIP" . -x "*.pyc" "__pycache__/*")
    echo "    → $ZIP ($(du -sh "$ZIP" | cut -f1))"
  fi
done

# ── Step 3: Upload AGENTS.md schema to S3 (will be created by Terraform first) ─
echo ""
echo "→ AGENTS.md will be uploaded after Terraform apply."

# ── Step 4: Terraform init + apply ────────────────────────────────
echo ""
echo "→ Running terraform init..."
cd "$TF_DIR"
terraform init \
  -backend-config="bucket=$TF_STATE_BUCKET" \
  -backend-config="key=llmwiki/dev/terraform.tfstate" \
  -backend-config="region=$REGION" \
  -backend-config="dynamodb_table=llmwiki-tfstate-lock" \
  -backend-config="encrypt=true" \
  -backend-config="profile=$PROFILE" \
  -reconfigure

echo ""
echo "→ Running terraform apply (auto-approve)..."
terraform apply \
  -var="aws_region=$REGION" \
  -var="aws_profile=$PROFILE" \
  -var="account_id=$ACCOUNT_ID" \
  -auto-approve

# ── Step 5: Capture outputs ───────────────────────────────────────
echo ""
echo "→ Reading Terraform outputs..."
WIKI_BUCKET=$(terraform output -raw wiki_bucket_name)
API_URL=$(terraform output -raw api_gateway_url)
ECR_URL=$(terraform output -raw ecr_repository_url)
ECS_CLUSTER=$(terraform output -raw ecs_cluster_name)
ECS_SERVICE=$(terraform output -raw ecs_service_name)
STREAMLIT_URL=$(terraform output -raw streamlit_url)
VECTORS_BUCKET=$(terraform output -raw s3_vectors_bucket_name)

# ── Step 6: Upload AGENTS.md schema ──────────────────────────────
echo ""
echo "→ Uploading AGENTS.md schema to S3..."
aws s3 cp "$ROOT_DIR/config/AGENTS.md" \
  "s3://$WIKI_BUCKET/config/AGENTS.md" \
  --profile "$PROFILE"

# ── Step 7: Build and push Streamlit Docker image ─────────────────
echo ""
echo "→ Building and pushing Streamlit Docker image..."
cd "$ROOT_DIR"

# Sync Neuro SAN registries and config into the Docker build context
echo "  Syncing registries/ and config/ into build context..."
mkdir -p registries/llmwiki
cp ../registries/aaosa.hocon registries/ 2>/dev/null || true
cp ../registries/llmwiki/uc1_sales_to_service.hocon registries/llmwiki/ 2>/dev/null || true
cp ../registries/llmwiki/manifest.hocon registries/llmwiki/ 2>/dev/null || true
cp ../config/llm_config.hocon config/ 2>/dev/null || true
echo "  Registries synced."

aws ecr get-login-password \
  --region "$REGION" \
  --profile "$PROFILE" \
  | $DOCKER_CMD login --username AWS --password-stdin "$ECR_URL"

$DOCKER_CMD build -f streamlit/Dockerfile -t llmwiki-streamlit .
$DOCKER_CMD tag llmwiki-streamlit:latest "$ECR_URL:latest"
$DOCKER_CMD push "$ECR_URL:latest"
echo "  Image pushed: $ECR_URL:latest"

# Force ECS service to pull new image
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --force-new-deployment \
  --region "$REGION" \
  --profile "$PROFILE" \
  > /dev/null

echo ""
echo "========================================"
echo "  DEPLOY COMPLETE"
echo "========================================"
echo ""
echo "  Wiki S3 Bucket  : $WIKI_BUCKET"
echo "  Vectors Bucket  : $VECTORS_BUCKET"
echo "  API Gateway     : $API_URL"
echo "  Streamlit UI    : $STREAMLIT_URL"
echo "  (ECS may take 2-3 minutes to become healthy)"
echo ""
echo "  Get API key:"
echo "  aws ssm get-parameter --name /llmwiki/api_key --with-decryption --profile $PROFILE --query Parameter.Value --output text"
echo ""
echo "  Test basic query:"
echo "  curl -s -X POST $API_URL/query \\"
echo "    -H 'x-api-key: <KEY>' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"q\": \"What are the key risks in our cloud strategy?\"}'"
echo ""
echo "  Test Business API (UC1 agent query):"
echo "  curl -s -X POST $API_URL/wiki/ask \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    --aws-sigv4 \"aws:amz:$REGION:execute-api\" \\"
echo "    --user \"\$(aws configure get aws_access_key_id --profile $PROFILE):\$(aws configure get aws_secret_access_key --profile $PROFILE)\" \\"
echo "    -d '{\"question\":\"What is the Sales-to-Service handoff checklist?\",\"domain\":\"customer-onboarding\",\"use_case\":\"UC1\"}'"
echo ""
echo "  Test playbook:"
echo "  curl -s $API_URL/wiki/playbook/UC1 (with SigV4 auth)"
echo ""
echo "  Ingest seed documents:"
echo "  aws s3 cp ../AIFactory/ s3://$WIKI_BUCKET/raw/ --recursive --profile $PROFILE"
echo ""
echo "  Upload skill wiki pages:"
echo "  aws s3 cp wiki_seed/skills/ s3://$WIKI_BUCKET/wiki/skills/ --recursive --profile $PROFILE"
echo ""
echo "  Run skill E2E tests:"
echo "  bash scripts/test_skills_e2e.sh --profile $PROFILE"
echo ""
echo "  Run full UC1 orchestrator:"
echo "  aws lambda invoke --function-name llmwiki-uc1-orchestrator \\"
echo "    --payload '{\"customer_id\":\"scan-health-plan-2026\"}' \\"
echo "    --cli-binary-format raw-in-base64-out /tmp/uc1_out.json \\"
echo "    --profile $PROFILE && cat /tmp/uc1_out.json | python3 -m json.tool"
echo ""
