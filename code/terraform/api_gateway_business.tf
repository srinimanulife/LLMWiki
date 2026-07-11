# ── /wiki/ask  (universal agent query) ────────────────────────────
resource "aws_api_gateway_resource" "wiki_ask" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "ask"
}

resource "aws_api_gateway_method" "wiki_ask_post" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_ask.id
  http_method      = "POST"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_ask_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_ask.id
  http_method             = aws_api_gateway_method.wiki_ask_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.business_query.invoke_arn
}

# ── /wiki/query/{domain} ───────────────────────────────────────────
resource "aws_api_gateway_resource" "wiki_query" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "query"
}

resource "aws_api_gateway_resource" "wiki_query_domain" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_query.id
  path_part   = "{domain}"
}

resource "aws_api_gateway_method" "wiki_query_domain_post" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_query_domain.id
  http_method      = "POST"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_query_domain_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_query_domain.id
  http_method             = aws_api_gateway_method.wiki_query_domain_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.business_query.invoke_arn
}

# ── /wiki/contribute ──────────────────────────────────────────────
resource "aws_api_gateway_resource" "wiki_contribute" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "contribute"
}

resource "aws_api_gateway_method" "wiki_contribute_post" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_contribute.id
  http_method      = "POST"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_contribute_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_contribute.id
  http_method             = aws_api_gateway_method.wiki_contribute_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.contribute.invoke_arn
}

# ── /wiki/playbook/{use_case} ──────────────────────────────────────
resource "aws_api_gateway_resource" "wiki_playbook" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "playbook"
}

resource "aws_api_gateway_resource" "wiki_playbook_uc" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_playbook.id
  path_part   = "{use_case}"
}

resource "aws_api_gateway_method" "wiki_playbook_get" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_playbook_uc.id
  http_method      = "GET"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_playbook_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_playbook_uc.id
  http_method             = aws_api_gateway_method.wiki_playbook_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.playbook.invoke_arn
}

# ── /wiki/customer/{customer_id} ───────────────────────────────────
resource "aws_api_gateway_resource" "wiki_customer" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "customer"
}

resource "aws_api_gateway_resource" "wiki_customer_id" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_customer.id
  path_part   = "{customer_id}"
}

resource "aws_api_gateway_method" "wiki_customer_get" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_customer_id.id
  http_method      = "GET"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_customer_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_customer_id.id
  http_method             = aws_api_gateway_method.wiki_customer_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.playbook.invoke_arn
}

# ── /wiki/artifact/{artifact_type} ────────────────────────────────
resource "aws_api_gateway_resource" "wiki_artifact" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_resource.id
  path_part   = "artifact"
}

resource "aws_api_gateway_resource" "wiki_artifact_type" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id
  parent_id   = aws_api_gateway_resource.wiki_artifact.id
  path_part   = "{artifact_type}"
}

resource "aws_api_gateway_method" "wiki_artifact_get" {
  rest_api_id      = aws_api_gateway_rest_api.wiki.id
  resource_id      = aws_api_gateway_resource.wiki_artifact_type.id
  http_method      = "GET"
  authorization    = "AWS_IAM"
  api_key_required = false
}

resource "aws_api_gateway_integration" "wiki_artifact_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.wiki.id
  resource_id             = aws_api_gateway_resource.wiki_artifact_type.id
  http_method             = aws_api_gateway_method.wiki_artifact_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.playbook.invoke_arn
}

# ── Resource policy — allow AgentCore IAM role to call business routes ──
resource "aws_api_gateway_rest_api_policy" "wiki_agent_policy" {
  rest_api_id = aws_api_gateway_rest_api.wiki.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowAgentAccess"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.agentcore_s2s.arn }
        Action    = "execute-api:Invoke"
        Resource  = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/POST/wiki/ask"
      },
      {
        Sid       = "AllowAgentContribute"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.agentcore_s2s.arn }
        Action    = "execute-api:Invoke"
        Resource  = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/POST/wiki/contribute"
      },
      {
        Sid       = "AllowAgentPlaybook"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.agentcore_s2s.arn }
        Action    = "execute-api:Invoke"
        Resource  = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/GET/wiki/*"
      }
    ]
  })
}
