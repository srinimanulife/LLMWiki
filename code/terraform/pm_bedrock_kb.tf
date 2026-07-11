# ══════════════════════════════════════════════════════════════════════════════
# PM Bedrock Knowledge Base (semantic KB for Problem Management domain)
#
# Uses the same S3 Vectors index (llmwiki-index) and Bedrock KB role as the
# main wiki KB. A separate KB (C4MNP6NOP2-equivalent) scopes retrieval to only
# PM documents so cross-domain contamination is impossible.
#
# Source files are uploaded from problem-mgnt/raw/ to kb/ prefix with short
# names to stay under the S3 Vectors metadata 2048-byte limit.
# ══════════════════════════════════════════════════════════════════════════════

# ── IAM: extend KB role to access PM S3 bucket ───────────────────────────────
resource "aws_iam_role_policy" "bedrock_kb_pm_s3" {
  name = "llmwiki-bedrock-kb-pm-s3-policy"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PMKBBucketAccess"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.pm.arn,
          "${aws_s3_bucket.pm.arn}/*"
        ]
      }
    ]
  })
}

# ── S3: upload PM KB source files with short keys ────────────────────────────
# Short keys are required — long S3 object keys inflate the per-vector metadata
# JSON beyond the S3 Vectors 2048-byte limit and cause ingestion failures.

resource "aws_s3_object" "pm_kb_facets" {
  bucket       = aws_s3_bucket.pm.id
  key          = "kb/facets.md"
  source       = "${path.module}/../../problem-mgnt/raw/facets-known-issues.md"
  source_hash  = filemd5("${path.module}/../../problem-mgnt/raw/facets-known-issues.md")
  content_type = "text/markdown"
}

resource "aws_s3_object" "pm_kb_qnxt" {
  bucket       = aws_s3_bucket.pm.id
  key          = "kb/qnxt.md"
  source       = "${path.module}/../../problem-mgnt/raw/qnxt-known-issues.md"
  source_hash  = filemd5("${path.module}/../../problem-mgnt/raw/qnxt-known-issues.md")
  content_type = "text/markdown"
}

resource "aws_s3_object" "pm_kb_edm_eam_tcs" {
  bucket       = aws_s3_bucket.pm.id
  key          = "kb/edm-eam-tcs.md"
  source       = "${path.module}/../../problem-mgnt/raw/edm-eam-tcs-known-issues.md"
  source_hash  = filemd5("${path.module}/../../problem-mgnt/raw/edm-eam-tcs-known-issues.md")
  content_type = "text/markdown"
}

resource "aws_s3_object" "pm_kb_networx_frm" {
  bucket       = aws_s3_bucket.pm.id
  key          = "kb/networx-frm.md"
  source       = "${path.module}/../../problem-mgnt/raw/networx-frm-known-issues.md"
  source_hash  = filemd5("${path.module}/../../problem-mgnt/raw/networx-frm-known-issues.md")
  content_type = "text/markdown"
}

resource "aws_s3_object" "pm_kb_issues_csv" {
  bucket       = aws_s3_bucket.pm.id
  key          = "kb/trizetto-issues.csv"
  source       = "${path.module}/../../problem-mgnt/raw/trizetto-issues.csv"
  source_hash  = filemd5("${path.module}/../../problem-mgnt/raw/trizetto-issues.csv")
  content_type = "text/csv"
}

# ── Bedrock KB: create PM Knowledge Base via CLI ─────────────────────────────
# Terraform AWS provider v5.x does not support S3_VECTORS storage type yet.
# Using local-exec (same pattern as bedrock_kb.tf) until provider support lands.

resource "null_resource" "bedrock_pm_kb" {
  triggers = {
    role_arn         = aws_iam_role.bedrock_kb.arn
    vector_index_arn = local.vector_index_arn
    pm_bucket        = aws_s3_bucket.pm.id
    facets_md        = filemd5("${path.module}/../../problem-mgnt/raw/facets-known-issues.md")
    qnxt_md          = filemd5("${path.module}/../../problem-mgnt/raw/qnxt-known-issues.md")
    edm_eam_tcs_md   = filemd5("${path.module}/../../problem-mgnt/raw/edm-eam-tcs-known-issues.md")
    networx_frm_md   = filemd5("${path.module}/../../problem-mgnt/raw/networx-frm-known-issues.md")
    issues_csv       = filemd5("${path.module}/../../problem-mgnt/raw/trizetto-issues.csv")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      PROFILE="${var.aws_profile}"
      REGION="${var.aws_region}"
      PM_BUCKET="${aws_s3_bucket.pm.id}"

      # ── Check if PM KB already exists ──────────────────────────────────────
      EXISTING_KB=$(aws ssm get-parameter \
        --name /llmwiki/pm_bedrock_kb_id \
        --profile "$PROFILE" --region "$REGION" \
        --query Parameter.Value --output text 2>/dev/null || echo "")

      if [ -n "$EXISTING_KB" ]; then
        echo "PM Bedrock KB already exists: $EXISTING_KB"
        # Still re-sync data source to pick up file changes
        EXISTING_DS=$(aws ssm get-parameter \
          --name /llmwiki/pm_bedrock_kb_datasource_id \
          --profile "$PROFILE" --region "$REGION" \
          --query Parameter.Value --output text 2>/dev/null || echo "")
        if [ -n "$EXISTING_DS" ]; then
          echo "Triggering ingestion sync for updated files..."
          aws bedrock-agent start-ingestion-job \
            --knowledge-base-id "$EXISTING_KB" \
            --data-source-id "$EXISTING_DS" \
            --profile "$PROFILE" --region "$REGION" || echo "Sync triggered (or already running)"
        fi
        exit 0
      fi

      # ── Create the PM Knowledge Base ───────────────────────────────────────
      echo "Creating PM Bedrock Knowledge Base with S3 Vectors storage..."
      KB_RESPONSE=$(aws bedrock-agent create-knowledge-base \
        --name "llmwiki-pm-kb" \
        --description "TriZetto cross-product known issues — Facets, QNXT, EAM, EDM, TCS, NetworX, FRM" \
        --role-arn "${aws_iam_role.bedrock_kb.arn}" \
        --knowledge-base-configuration '{"type":"VECTOR","vectorKnowledgeBaseConfiguration":{"embeddingModelArn":"arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}","embeddingModelConfiguration":{"bedrockEmbeddingModelConfiguration":{"dimensions":1024}}}}' \
        --storage-configuration '{"type":"S3_VECTORS","s3VectorsConfiguration":{"vectorBucketArn":"${local.vector_bucket_arn}","indexArn":"${local.vector_index_arn}"}}' \
        --profile "$PROFILE" --region "$REGION" \
        --output json)

      PM_KB_ID=$(echo "$KB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['knowledgeBase']['knowledgeBaseId'])")
      echo "Created PM KB: $PM_KB_ID"

      aws ssm put-parameter \
        --name /llmwiki/pm_bedrock_kb_id \
        --value "$PM_KB_ID" \
        --type String \
        --overwrite \
        --profile "$PROFILE" --region "$REGION"

      # ── Wait for KB to become ACTIVE ───────────────────────────────────────
      echo "Waiting for PM KB to become ACTIVE..."
      for i in $(seq 1 24); do
        STATUS=$(aws bedrock-agent get-knowledge-base \
          --knowledge-base-id "$PM_KB_ID" \
          --profile "$PROFILE" --region "$REGION" \
          --query knowledgeBase.status --output text 2>/dev/null || echo "CREATING")
        echo "  Status: $STATUS ($i/24)"
        [ "$STATUS" = "ACTIVE" ] && break
        sleep 10
      done

      # ── Create data source pointing at kb/ prefix ──────────────────────────
      echo "Creating PM data source (S3 kb/ prefix, fixed-size chunking)..."
      DS_RESPONSE=$(aws bedrock-agent create-data-source \
        --knowledge-base-id "$PM_KB_ID" \
        --name "llmwiki-pm-issues" \
        --data-source-configuration '{"type":"S3","s3Configuration":{"bucketArn":"${aws_s3_bucket.pm.arn}","inclusionPrefixes":["kb/"]}}' \
        --vector-ingestion-configuration '{"chunkingConfiguration":{"chunkingStrategy":"FIXED_SIZE","fixedSizeChunkingConfiguration":{"maxTokens":512,"overlapPercentage":20}}}' \
        --profile "$PROFILE" --region "$REGION" \
        --output json)

      PM_DS_ID=$(echo "$DS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['dataSource']['dataSourceId'])")
      echo "Created PM data source: $PM_DS_ID"

      aws ssm put-parameter \
        --name /llmwiki/pm_bedrock_kb_datasource_id \
        --value "$PM_DS_ID" \
        --type String \
        --overwrite \
        --profile "$PROFILE" --region "$REGION"

      # ── Trigger initial ingestion ──────────────────────────────────────────
      echo "Starting initial ingestion job..."
      JOB_RESPONSE=$(aws bedrock-agent start-ingestion-job \
        --knowledge-base-id "$PM_KB_ID" \
        --data-source-id "$PM_DS_ID" \
        --profile "$PROFILE" --region "$REGION" \
        --output json)

      JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['ingestionJob']['ingestionJobId'])")
      echo "Ingestion job started: $JOB_ID"

      # Wait for ingestion to complete (up to 10 min)
      for i in $(seq 1 30); do
        JOB_STATUS=$(aws bedrock-agent get-ingestion-job \
          --knowledge-base-id "$PM_KB_ID" \
          --data-source-id "$PM_DS_ID" \
          --ingestion-job-id "$JOB_ID" \
          --profile "$PROFILE" --region "$REGION" \
          --query ingestionJob.status --output text 2>/dev/null || echo "IN_PROGRESS")
        echo "  Ingestion: $JOB_STATUS ($i/30)"
        [ "$JOB_STATUS" = "COMPLETE" ] && break
        [ "$JOB_STATUS" = "FAILED" ] && echo "WARNING: Ingestion job failed — check CloudTrail" && break
        sleep 20
      done

      echo "PM Bedrock KB setup complete. KB=$PM_KB_ID DS=$PM_DS_ID"
    EOT
  }

  depends_on = [
    null_resource.bedrock_kb,
    aws_iam_role_policy.bedrock_kb_pm_s3,
    aws_s3_object.pm_kb_facets,
    aws_s3_object.pm_kb_qnxt,
    aws_s3_object.pm_kb_edm_eam_tcs,
    aws_s3_object.pm_kb_networx_frm,
    aws_s3_object.pm_kb_issues_csv,
  ]
}

# ── SSM: static reference parameters ─────────────────────────────────────────
# These are written by the local-exec above. Adding placeholder SSM params here
# ensures the parameter paths exist after a fresh apply even before KB is queried.
# The local-exec overwrites them with real IDs.

resource "aws_ssm_parameter" "pm_bedrock_kb_id_placeholder" {
  name  = "/llmwiki/pm_bedrock_kb_id"
  type  = "String"
  value = "pending"

  lifecycle {
    # local-exec writes the real value; ignore changes so Terraform doesn't revert it
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "pm_bedrock_kb_datasource_id_placeholder" {
  name  = "/llmwiki/pm_bedrock_kb_datasource_id"
  type  = "String"
  value = "pending"

  lifecycle {
    ignore_changes = [value]
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "pm_bedrock_kb_id" {
  description = "PM Bedrock KB ID (written to SSM /llmwiki/pm_bedrock_kb_id)"
  value       = "/llmwiki/pm_bedrock_kb_id"
}

output "pm_bedrock_kb_datasource_id" {
  description = "PM KB data source ID (written to SSM /llmwiki/pm_bedrock_kb_datasource_id)"
  value       = "/llmwiki/pm_bedrock_kb_datasource_id"
}
