resource "aws_ssm_parameter" "wiki_bucket" {
  name  = "/llmwiki/wiki_bucket"
  type  = "String"
  value = aws_s3_bucket.wiki.id
}

resource "aws_ssm_parameter" "bedrock_model_id" {
  name  = "/llmwiki/bedrock_model_id"
  type  = "String"
  value = var.bedrock_model_id
}

resource "aws_ssm_parameter" "dynamodb_index_table" {
  name  = "/llmwiki/dynamodb_index_table"
  type  = "String"
  value = aws_dynamodb_table.wiki_index.name
}

resource "aws_ssm_parameter" "api_gateway_url" {
  name  = "/llmwiki/api_gateway_url"
  type  = "String"
  value = "https://${aws_api_gateway_rest_api.wiki.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.dev.stage_name}"
}

resource "aws_ssm_parameter" "api_key_value" {
  name  = "/llmwiki/api_key"
  type  = "SecureString"
  value = aws_api_gateway_api_key.wiki.value
}

# /llmwiki/bedrock_kb_id and /llmwiki/bedrock_kb_datasource_id are written
# by the local-exec in bedrock_kb.tf (provider does not support S3_VECTORS yet)
