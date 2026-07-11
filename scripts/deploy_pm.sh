#!/usr/bin/env bash
# Deploy PM (UC-PM) infrastructure: terraform apply + Lambda code updates + S3 seed + ECS redeploy
set -euo pipefail

PROFILE="tzg-sandbox"
REGION="us-east-1"
ACCOUNT="392568849512"
TF_DIR="/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code/terraform"
LAMBDA_DIR="/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code/lambda"
PM_DIR="/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/problem-mgnt"
BUILD_DIR="/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code/.build"

echo "=== Verifying account ==="
ACTUAL=$(aws sts get-caller-identity --profile $PROFILE --query Account --output text)
if [ "$ACTUAL" != "$ACCOUNT" ]; then
  echo "ERROR: Expected $ACCOUNT but got $ACTUAL — aborting"
  exit 1
fi
echo "Account: $ACTUAL ✓"

mkdir -p "$BUILD_DIR"

echo ""
echo "=== Terraform apply (PM resources) ==="
cd "$TF_DIR"
terraform init -upgrade -reconfigure
terraform plan -out=pm.tfplan
terraform apply pm.tfplan

echo ""
echo "=== Fetch deployed Lambda names from Terraform output ==="
PM_BUCKET=$(terraform output -raw pm_wiki_bucket 2>/dev/null || aws ssm get-parameter --name /llmwiki/pm/wiki_bucket --profile $PROFILE --query Parameter.Value --output text 2>/dev/null || echo "")
SK06_FN="llmwiki-skill-problem-classifier"
PM_HARNESS_FN="llmwiki-harness-uc-pm"

echo ""
echo "=== Update SK-06 Lambda code ==="
cd "$LAMBDA_DIR/skills/problem_classifier"
zip -r "$BUILD_DIR/skill_problem_classifier.zip" handler.py
aws lambda update-function-code \
  --function-name $SK06_FN \
  --zip-file fileb://"$BUILD_DIR/skill_problem_classifier.zip" \
  --profile $PROFILE \
  --region $REGION

echo ""
echo "=== Update PM Harness Lambda code ==="
cd "$LAMBDA_DIR/harness/pm_harness"
zip -r "$BUILD_DIR/pm_harness.zip" handler.py
aws lambda update-function-code \
  --function-name $PM_HARNESS_FN \
  --zip-file fileb://"$BUILD_DIR/pm_harness.zip" \
  --profile $PROFILE \
  --region $REGION

echo ""
echo "=== Seed PM S3 bucket (PM-specific files only) ==="
PM_BUCKET=$(aws ssm get-parameter \
  --name /llmwiki/pm/wiki_bucket \
  --profile $PROFILE \
  --region $REGION \
  --query Parameter.Value --output text 2>/dev/null || \
  aws lambda get-function-configuration \
    --function-name $PM_HARNESS_FN \
    --profile $PROFILE --region $REGION \
    --query 'Environment.Variables.PM_WIKI_BUCKET' --output text)

if [ -n "$PM_BUCKET" ]; then
  echo "PM bucket: $PM_BUCKET"
  aws s3 cp "$PM_DIR/pm-uc-brief.md"               "s3://$PM_BUCKET/specs/pm-uc-brief.md"               --profile $PROFILE
  aws s3 cp "$PM_DIR/pm-workflow-spec.md"           "s3://$PM_BUCKET/specs/pm-workflow-spec.md"           --profile $PROFILE
  aws s3 cp "$PM_DIR/pm-skill-spec-sk06-problem-classifier.md" "s3://$PM_BUCKET/specs/pm-skill-spec-sk06.md" --profile $PROFILE
  aws s3 cp "$PM_DIR/problem-mgnt-llmwiki-harness.md"          "s3://$PM_BUCKET/docs/pm-harness-overview.md"  --profile $PROFILE
  aws s3 cp "$PM_DIR/problem-mgnt-llmwiki-harness-sample-outputs.md" "s3://$PM_BUCKET/docs/pm-sample-outputs.md" --profile $PROFILE
  aws s3 cp "$PM_DIR/raw/problem-mgnt-ingest-templates-qnxt-tcs-eam-edm-compact.xlsx" \
            "s3://$PM_BUCKET/raw/pm-ingest-templates.xlsx" --profile $PROFILE
  echo "Seed files uploaded to $PM_BUCKET ✓"
else
  echo "WARN: Could not determine PM_BUCKET — skipping seed upload"
fi

echo ""
echo "=== Force ECS redeployment (picks up PM_HARNESS_FUNCTION env var) ==="
CLUSTER="llmwiki-cluster"
SERVICE=$(aws ecs list-services --cluster $CLUSTER --profile $PROFILE --region $REGION \
  --query 'serviceArns[0]' --output text | sed 's|.*/||')
aws ecs update-service \
  --cluster $CLUSTER \
  --service $SERVICE \
  --force-new-deployment \
  --profile $PROFILE \
  --region $REGION \
  --query 'service.serviceName' --output text

echo ""
echo "=== Deploy complete ==="
echo "SK-06 function:    $SK06_FN"
echo "PM harness:        $PM_HARNESS_FN"
echo "ECS service:       $SERVICE (redeploying)"
