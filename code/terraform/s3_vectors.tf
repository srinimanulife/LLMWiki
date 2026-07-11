# Amazon S3 Vectors — vector store for Bedrock Knowledge Base
#
# Architecture decision: S3 Vectors replaces OpenSearch Serverless.
#
# Why we dropped OpenSearch Serverless:
#   - Minimum cost: ~$11-12/day (2 OCU minimum, always on) regardless of usage
#   - Required a separate index-creation step (local-exec Python SigV4 signing)
#     that caused reliable deploy failures due to collection warm-up timing
#   - Operational overhead disproportionate to a wiki workload
#
# Why S3 Vectors:
#   - Pay-per-use: storage (~$0.023/GB) + query ops only — ~$0/day at demo scale
#   - Native Bedrock KB integration (no field_mapping, no separate auth policy)
#   - Simple CLI creation — no custom signing, no warm-up wait
#   - LLMWiki is NOT a high-throughput RAG system; it's a structured wiki with
#     tens to hundreds of pages. S3 Vectors is the right fit for this scale.
#
# Terraform AWS provider does not yet have native aws_s3vectors_* resources,
# so the bucket and index are created via local-exec on first apply.
# The ARNs are deterministic and constructed from known values.

locals {
  vector_bucket_name = "llmwiki-vectors-${random_id.bucket_suffix.hex}"
  vector_bucket_arn  = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${local.vector_bucket_name}"
  vector_index_name  = "llmwiki-index"
  vector_index_arn   = "${local.vector_bucket_arn}/index/${local.vector_index_name}"
}

resource "null_resource" "create_s3_vector_bucket" {
  triggers = {
    bucket_name = local.vector_bucket_name
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws s3vectors create-vector-bucket \
        --vector-bucket-name "${local.vector_bucket_name}" \
        --no-verify-ssl \
        --region "${var.aws_region}" \
        --profile "${var.aws_profile}" \
      && echo "Vector bucket created: ${local.vector_bucket_name}" \
      || echo "Vector bucket already exists — continuing."
    EOT
  }
}

resource "null_resource" "create_s3_vector_index" {
  triggers = {
    bucket_name = local.vector_bucket_name
    index_name  = local.vector_index_name
  }

  provisioner "local-exec" {
    # The s3vectors CLI command for index creation is "create-index" (not "create-vector-index")
    command = <<-EOT
      set -e
      PROFILE="${var.aws_profile}"
      REGION="${var.aws_region}"
      BUCKET="${local.vector_bucket_name}"
      INDEX="${local.vector_index_name}"

      # Check if index already exists
      EXISTING=$(aws s3vectors get-index \
        --vector-bucket-name "$BUCKET" \
        --index-name "$INDEX" \
        --no-verify-ssl \
        --profile "$PROFILE" --region "$REGION" \
        --query index.indexName --output text 2>/dev/null || echo "")

      if [ -n "$EXISTING" ]; then
        echo "Vector index already exists: $EXISTING"
        exit 0
      fi

      echo "Creating S3 Vectors index: $INDEX in bucket $BUCKET ..."
      aws s3vectors create-index \
        --vector-bucket-name "$BUCKET" \
        --index-name "$INDEX" \
        --data-type float32 \
        --dimension 1024 \
        --distance-metric cosine \
        --metadata-configuration '{"nonFilterableMetadataKeys":["AMAZON_BEDROCK_TEXT","AMAZON_BEDROCK_METADATA"]}' \
        --no-verify-ssl \
        --profile "$PROFILE" --region "$REGION"
      echo "Vector index created: $INDEX"
    EOT
  }

  depends_on = [null_resource.create_s3_vector_bucket]
}
