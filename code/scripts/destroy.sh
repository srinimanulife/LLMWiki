#!/usr/bin/env bash
# =============================================================================
# destroy.sh — PERMANENTLY destroy all LLMWiki AWS resources
# WARNING: This deletes all wiki data. This is NOT reversible.
# Usage: ./scripts/destroy.sh [--profile <profile>] [--force]
# =============================================================================
set -euo pipefail

PROFILE="${PROFILE:-tzg-sandbox}"
REGION="${REGION:-us-east-1}"
FORCE=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$(cd "$SCRIPT_DIR/../terraform" && pwd)"

while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    --force)   FORCE=true;   shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="$REGION"

echo "========================================"
echo "  LLMWiki DESTROY"
echo "  WARNING: ALL DATA WILL BE DELETED"
echo "========================================"
echo ""

if [ "$FORCE" != "true" ]; then
  read -r -p "Type DESTROY to confirm permanent deletion: " CONFIRM
  if [ "$CONFIRM" != "DESTROY" ]; then
    echo "Aborted."
    exit 0
  fi
fi

aws sts get-caller-identity --profile "$PROFILE" > /dev/null 2>&1 || {
  echo "ERROR: AWS session expired. Run: aws sso login --profile $PROFILE"
  exit 1
}

cd "$TF_DIR"

# Get bucket name before destroying
WIKI_BUCKET=$(terraform output -raw wiki_bucket_name 2>/dev/null || echo "")

# Empty S3 bucket first (Terraform can't delete non-empty versioned buckets)
if [ -n "$WIKI_BUCKET" ]; then
  echo "→ Emptying S3 bucket: $WIKI_BUCKET ..."

  # Delete all object versions
  aws s3api list-object-versions \
    --bucket "$WIKI_BUCKET" \
    --profile "$PROFILE" \
    --output json 2>/dev/null \
  | python3 -c "
import sys, json, subprocess, os
data = json.load(sys.stdin)
profile = os.environ.get('AWS_PROFILE','default')
region = os.environ.get('AWS_DEFAULT_REGION','us-east-1')
bucket = '$WIKI_BUCKET'
to_delete = []
for v in data.get('Versions', []) + data.get('DeleteMarkers', []):
    to_delete.append({'Key': v['Key'], 'VersionId': v['VersionId']})
    if len(to_delete) >= 1000:
        subprocess.run(['aws', 's3api', 'delete-objects',
            '--bucket', bucket, '--profile', profile,
            '--delete', json.dumps({'Objects': to_delete, 'Quiet': True})], check=True)
        to_delete = []
if to_delete:
    subprocess.run(['aws', 's3api', 'delete-objects',
        '--bucket', bucket, '--profile', profile,
        '--delete', json.dumps({'Objects': to_delete, 'Quiet': True})], check=True)
print('S3 bucket emptied.')
" 2>/dev/null || echo "  (bucket already empty or not found)"
fi

echo ""
echo "→ Running terraform destroy (auto-approve)..."
terraform destroy \
  -var="aws_region=$REGION" \
  -var="aws_profile=$PROFILE" \
  -auto-approve

echo ""
echo "========================================"
echo "  DESTROY COMPLETE"
echo "========================================"
echo ""
echo "  All LLMWiki AWS resources have been deleted."
echo "  Terraform state bucket (llmwiki-tfstate-*) was NOT deleted."
echo "  To delete it: aws s3 rb s3://llmwiki-tfstate-<account-id> --force --profile $PROFILE"
echo ""
