# ── Business Query Lambda role ─────────────────────────────────────
resource "aws_iam_role" "business_query_lambda" {
  name               = "llmwiki-business-query-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "business_query_lambda_policy" {
  name = "llmwiki-business-query-lambda-policy"
  role = aws_iam_role.business_query_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3WikiRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.wiki.arn, "${aws_s3_bucket.wiki.arn}/wiki/*"]
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan",
                  "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
          aws_dynamodb_table.gaps.arn,
          "${aws_dynamodb_table.gaps.arn}/index/*",
          aws_dynamodb_table.contributions.arn,
        ]
      },
      {
        Sid    = "Bedrock"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:Retrieve"]
        Resource = "*"
      },
      {
        Sid    = "SSM"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/llmwiki/*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# ── Contribute Lambda role ─────────────────────────────────────────
resource "aws_iam_role" "contribute_lambda" {
  name               = "llmwiki-contribute-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "contribute_lambda_policy" {
  name = "llmwiki-contribute-lambda-policy"
  role = aws_iam_role.contribute_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3WikiWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:HeadObject"]
        Resource = [
          "${aws_s3_bucket.wiki.arn}/wiki/*",
          "${aws_s3_bucket.wiki.arn}/wiki/pending/*",
        ]
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          aws_dynamodb_table.contributions.arn,
        ]
      },
      {
        Sid    = "BedrockAgent"
        Effect = "Allow"
        Action = ["bedrock:StartIngestionJob"]
        Resource = "*"
      },
      {
        Sid    = "SSM"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/llmwiki/*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# ── Playbook Lambda role ───────────────────────────────────────────
resource "aws_iam_role" "playbook_lambda" {
  name               = "llmwiki-playbook-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "playbook_lambda_policy" {
  name = "llmwiki-playbook-lambda-policy"
  role = aws_iam_role.playbook_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3WikiRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.wiki.arn, "${aws_s3_bucket.wiki.arn}/wiki/*"]
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
        ]
      },
      {
        Sid    = "Bedrock"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# ── AgentCore Sales-to-Service agent role ──────────────────────────
# This role is assumed by the AgentCore agent to call LLMWiki APIs via SigV4.
resource "aws_iam_role" "agentcore_s2s" {
  name = "llmwiki-agentcore-s2s-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAgentCoreAssume"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "agentcore_s2s_policy" {
  name = "llmwiki-agentcore-s2s-policy"
  role = aws_iam_role.agentcore_s2s.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeLLMWikiAPI"
        Effect = "Allow"
        Action = "execute-api:Invoke"
        Resource = "${aws_api_gateway_rest_api.wiki.execution_arn}/*"
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeAgent"]
        Resource = "*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Update Streamlit task role to also invoke new Lambdas
resource "aws_iam_role_policy" "streamlit_business_api_invoke" {
  name = "llmwiki-streamlit-business-api-invoke"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeBusinessLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.business_query.arn,
          aws_lambda_function.contribute.arn,
          aws_lambda_function.playbook.arn,
        ]
      },
      {
        Sid    = "WikiWriteForContrib"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.wiki.arn}/wiki/pending/*",
          "${aws_s3_bucket.wiki.arn}/wiki/customers/*",
        ]
      }
    ]
  })
}
