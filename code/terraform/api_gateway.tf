resource "aws_api_gateway_rest_api" "wiki" {
  name        = "llmwiki-api"
  description = "LLMWiki REST API — query and ingest endpoints"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# ── /query endpoint ───────────────────────────────────────────────
resource "aws_api_gateway_resource" "query" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_rest_api.wiki.root_resource_id
  path_part   = "query"
}

resource "aws_api_gateway_method" "query_post" {
  rest_api_id   = aws_api_gateway_rest_api.wiki.id
  resource_id   = aws_api_gateway_resource.query.id
  http_method   = "POST"
  authorization = "NONE"

  api_key_required = true
}

resource "aws_api_gateway_integration" "query_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.query.id
  http_method             = aws_api_gateway_method.query_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query.invoke_arn
}

# ── /wiki/status endpoint ─────────────────────────────────────────
resource "aws_api_gateway_resource" "wiki_resource" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_rest_api.wiki.root_resource_id
  path_part   = "wiki"
}

resource "aws_api_gateway_resource" "wiki_status" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "status"
}

resource "aws_api_gateway_method" "wiki_status_get" {
  rest_api_id   = aws_api_gateway_rest_api.wiki.id
  resource_id   = aws_api_gateway_resource.wiki_status.id
  http_method   = "GET"
  authorization = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "wiki_status_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_status.id
  http_method             = aws_api_gateway_method.wiki_status_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query.invoke_arn

  request_templates = {
    "application/json" = jsonencode({ action = "status" })
  }
}

# ── /wiki/gaps endpoint ───────────────────────────────────────────
resource "aws_api_gateway_resource" "wiki_gaps" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "gaps"
}

resource "aws_api_gateway_method" "wiki_gaps_get" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_gaps.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "wiki_gaps_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_gaps.id
  http_method             = aws_api_gateway_method.wiki_gaps_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query.invoke_arn
}

# ── Deployment ────────────────────────────────────────────────────
resource "aws_api_gateway_deployment" "wiki" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.query.id,
      aws_api_gateway_method.query_post.id,
      aws_api_gateway_integration.query_lambda.id,
      aws_api_gateway_resource.wiki_gaps.id,
      aws_api_gateway_method.wiki_gaps_get.id,
      aws_api_gateway_integration.wiki_gaps_lambda.id,
      # Business API routes
      aws_api_gateway_resource.wiki_ask.id,
      aws_api_gateway_method.wiki_ask_post.id,
      aws_api_gateway_integration.wiki_ask_lambda.id,
      aws_api_gateway_resource.wiki_contribute.id,
      aws_api_gateway_method.wiki_contribute_post.id,
      aws_api_gateway_integration.wiki_contribute_lambda.id,
      aws_api_gateway_resource.wiki_playbook_uc.id,
      aws_api_gateway_method.wiki_playbook_get.id,
      aws_api_gateway_integration.wiki_playbook_lambda.id,
      aws_api_gateway_resource.wiki_customer_id.id,
      aws_api_gateway_method.wiki_customer_get.id,
      aws_api_gateway_integration.wiki_customer_lambda.id,
      aws_api_gateway_resource.wiki_artifact_type.id,
      aws_api_gateway_method.wiki_artifact_get.id,
      aws_api_gateway_integration.wiki_artifact_lambda.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.query_lambda,
    aws_api_gateway_integration.wiki_status_lambda,
    aws_api_gateway_integration.wiki_gaps_lambda,
    aws_api_gateway_integration.wiki_ask_lambda,
    aws_api_gateway_integration.wiki_contribute_lambda,
    aws_api_gateway_integration.wiki_playbook_lambda,
    aws_api_gateway_integration.wiki_customer_lambda,
    aws_api_gateway_integration.wiki_artifact_lambda,
  ]
}

resource "aws_api_gateway_stage" "dev" {
  deployment_id = aws_api_gateway_deployment.wiki.id
  rest_api_id   = aws_api_gateway_rest_api.wiki.id
  stage_name    = "dev"
  # Access logging omitted for MVP — requires CloudWatch Logs role ARN
  # configured at the account level in API Gateway settings.
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/llmwiki"
  retention_in_days = 14
}

# ── API Key + Usage Plan ──────────────────────────────────────────
resource "aws_api_gateway_api_key" "wiki" {
  name    = "llmwiki-api-key"
  enabled = true
}

resource "aws_api_gateway_usage_plan" "wiki" {
  name = "llmwiki-usage-plan"

  api_stages {
    api_id = aws_api_gateway_rest_api.wiki.id
    stage  = aws_api_gateway_stage.dev.stage_name
  }

  throttle_settings {
    burst_limit = 50
    rate_limit  = 20
  }

  quota_settings {
    limit  = 5000
    period = "MONTH"
  }
}

resource "aws_api_gateway_usage_plan_key" "wiki" {
  key_id        = aws_api_gateway_api_key.wiki.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.wiki.id
}
