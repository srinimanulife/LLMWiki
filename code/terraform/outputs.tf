output "wiki_bucket_name" {
  description = "S3 bucket containing raw sources and wiki pages (Sales-to-Service)"
  value       = aws_s3_bucket.wiki.id
}

output "pm_wiki_bucket_name" {
  description = "S3 bucket for Problem Management agent (isolated from main wiki)"
  value       = aws_s3_bucket.pm.id
}

output "api_gateway_url" {
  description = "API Gateway base URL"
  value       = "https://${aws_api_gateway_rest_api.wiki.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.dev.stage_name}"
}

output "api_key_ssm_param" {
  description = "SSM parameter containing the API key (SecureString)"
  value       = aws_ssm_parameter.api_key_value.name
}

output "streamlit_url" {
  description = "Streamlit UI URL via ALB"
  value       = "http://${aws_lb.wiki.dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL for Streamlit image"
  value       = aws_ecr_repository.streamlit.repository_url
}

output "bedrock_kb_id" {
  description = "Bedrock Knowledge Base ID (from SSM /llmwiki/bedrock_kb_id)"
  value       = "see: aws ssm get-parameter --name /llmwiki/bedrock_kb_id --profile tzg-sandbox --query Parameter.Value --output text"
}

output "s3_vectors_bucket_name" {
  description = "S3 Vectors bucket name (vector store for Bedrock KB)"
  value       = local.vector_bucket_name
}

output "dynamodb_index_table" {
  description = "DynamoDB wiki index table name"
  value       = aws_dynamodb_table.wiki_index.name
}

output "ingest_lambda_name" {
  description = "Ingest Lambda function name"
  value       = aws_lambda_function.ingest.function_name
}

output "query_lambda_name" {
  description = "Query Lambda function name"
  value       = aws_lambda_function.query.function_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name for Streamlit"
  value       = aws_ecs_cluster.wiki.name
}

output "ecs_service_name" {
  description = "ECS service name for Streamlit"
  value       = aws_ecs_service.streamlit.name
}

output "business_query_lambda_name" {
  description = "Business Query Lambda name"
  value       = aws_lambda_function.business_query.function_name
}

output "contribute_lambda_name" {
  description = "Contribute Lambda name"
  value       = aws_lambda_function.contribute.function_name
}

output "playbook_lambda_name" {
  description = "Playbook Lambda name"
  value       = aws_lambda_function.playbook.function_name
}

output "agentcore_s2s_role_arn" {
  description = "IAM role ARN for AgentCore Sales-to-Service agent"
  value       = aws_iam_role.agentcore_s2s.arn
}

output "wiki_ask_url" {
  description = "Business Knowledge API — POST /wiki/ask (SigV4 auth required)"
  value       = "https://${aws_api_gateway_rest_api.wiki.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.dev.stage_name}/wiki/ask"
}

output "contributions_table" {
  description = "DynamoDB contributions audit table"
  value       = aws_dynamodb_table.contributions.name
}

# ── Skill Lambda outputs ──────────────────────────────────────────

output "sk01_context_bootstrap_arn" {
  description = "SK-01 Customer Briefing Loader Lambda ARN"
  value       = aws_lambda_function.sk01_context_bootstrap.arn
}

output "sk02_wiki_query_arn" {
  description = "SK-02 Knowledge Finder Lambda ARN"
  value       = aws_lambda_function.sk02_wiki_query.arn
}

output "sk03_wiki_contribute_arn" {
  description = "SK-03 Knowledge Recorder Lambda ARN"
  value       = aws_lambda_function.sk03_wiki_contribute.arn
}

output "sk04_artifact_resolution_arn" {
  description = "SK-04 Template Auto-Fill Lambda ARN"
  value       = aws_lambda_function.sk04_artifact_resolution.arn
}

output "sk05_gap_detection_arn" {
  description = "SK-05 Missing Info Radar Lambda ARN"
  value       = aws_lambda_function.sk05_gap_detection.arn
}

output "uc1_orchestrator_arn" {
  description = "UC1 Orchestrator Lambda ARN (full 5-skill demo)"
  value       = aws_lambda_function.uc1_orchestrator.arn
}
