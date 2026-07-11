# Bedrock Knowledge Base backed by Amazon S3 Vectors
#
# The Terraform AWS provider (v5.x) does not yet expose the S3_VECTORS storage
# type on aws_bedrockagent_knowledge_base. We create the KB and data source
# via local-exec CLI calls and store the resulting IDs in SSM so the Lambda
# functions can resolve them at runtime without hard-coding.
#
# When Terraform provider support lands, this can be replaced with:
#   resource "aws_bedrockagent_knowledge_base" "wiki" {
#     storage_configuration { type = "S3_VECTORS" ... }
#   }

resource "null_resource" "bedrock_kb" {
  triggers = {
    role_arn          = aws_iam_role.bedrock_kb.arn
    vector_bucket_arn = local.vector_bucket_arn
    vector_index_arn  = local.vector_index_arn
    embedding_model   = var.bedrock_embedding_model_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      PROFILE="${var.aws_profile}"
      REGION="${var.aws_region}"

      # Check if KB already exists
      EXISTING=$(aws ssm get-parameter \
        --name /llmwiki/bedrock_kb_id \
        --profile "$PROFILE" --region "$REGION" \
        --query Parameter.Value --output text 2>/dev/null || echo "")

      if [ -n "$EXISTING" ]; then
        echo "Bedrock KB already exists: $EXISTING"
        exit 0
      fi

      echo "Creating Bedrock Knowledge Base with S3 Vectors storage..."
      KB_RESPONSE=$(aws bedrock-agent create-knowledge-base \
        --name "llmwiki-knowledge-base" \
        --role-arn "${aws_iam_role.bedrock_kb.arn}" \
        --knowledge-base-configuration '{"type":"VECTOR","vectorKnowledgeBaseConfiguration":{"embeddingModelArn":"arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}","embeddingModelConfiguration":{"bedrockEmbeddingModelConfiguration":{"dimensions":1024}}}}' \
        --storage-configuration '{"type":"S3_VECTORS","s3VectorsConfiguration":{"vectorBucketArn":"${local.vector_bucket_arn}","indexArn":"${local.vector_index_arn}"}}' \
        --profile "$PROFILE" --region "$REGION" \
        --output json)

      KB_ID=$(echo "$KB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['knowledgeBase']['knowledgeBaseId'])")
      echo "Created KB: $KB_ID"

      aws ssm put-parameter \
        --name /llmwiki/bedrock_kb_id \
        --value "$KB_ID" \
        --type String \
        --overwrite \
        --profile "$PROFILE" --region "$REGION"

      echo "Waiting for KB to become ACTIVE..."
      for i in $(seq 1 20); do
        STATUS=$(aws bedrock-agent get-knowledge-base \
          --knowledge-base-id "$KB_ID" \
          --profile "$PROFILE" --region "$REGION" \
          --query knowledgeBase.status --output text 2>/dev/null || echo "CREATING")
        echo "  Status: $STATUS ($i/20)"
        [ "$STATUS" = "ACTIVE" ] && break
        sleep 10
      done

      echo "Creating data source (S3 wiki/ prefix)..."
      DS_RESPONSE=$(aws bedrock-agent create-data-source \
        --knowledge-base-id "$KB_ID" \
        --name "llmwiki-wiki-pages" \
        --data-source-configuration '{"type":"S3","s3Configuration":{"bucketArn":"${aws_s3_bucket.wiki.arn}","inclusionPrefixes":["wiki/"]}}' \
        --vector-ingestion-configuration '{"chunkingConfiguration":{"chunkingStrategy":"FIXED_SIZE","fixedSizeChunkingConfiguration":{"maxTokens":512,"overlapPercentage":20}}}' \
        --profile "$PROFILE" --region "$REGION" \
        --output json)

      DS_ID=$(echo "$DS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['dataSource']['dataSourceId'])")
      echo "Created data source: $DS_ID"

      aws ssm put-parameter \
        --name /llmwiki/bedrock_kb_datasource_id \
        --value "$DS_ID" \
        --type String \
        --overwrite \
        --profile "$PROFILE" --region "$REGION"

      echo "Bedrock KB setup complete. KB=$KB_ID DS=$DS_ID"
    EOT
  }

  depends_on = [
    null_resource.create_s3_vector_index,
    aws_iam_role_policy.bedrock_kb_policy,
    aws_s3_bucket.wiki
  ]
}

# KB ID and DS ID are written to SSM by the local-exec above.
# They are read at runtime by the Lambda functions via SSM GetParameter.
# The output in outputs.tf reads the value via aws CLI after apply.
