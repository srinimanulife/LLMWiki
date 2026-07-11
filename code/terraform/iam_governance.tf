# ── Governance IAM — add DynamoDB + CloudWatch permissions to existing roles ──
#
# Query Lambda needs: usage + cache + rate-limits read/write
resource "aws_iam_role_policy" "query_governance" {
  name = "llmwiki-query-governance"
  role = aws_iam_role.query_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GovernanceTables"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.usage.arn,
          "${aws_dynamodb_table.usage.arn}/index/*",
          aws_dynamodb_table.cache.arn,
          "${aws_dynamodb_table.cache.arn}/index/*",
          aws_dynamodb_table.rate_limits.arn,
        ]
      },
      {
        Sid    = "BedrockEmbed"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Sid    = "CloudWatchGovernance"
        Effect = "Allow"
        Action = ["cloudwatch:PutMetricData"]
        Resource = "*"
      },
    ]
  })
}

# Business Query Lambda needs the same governance tables + rate limits
resource "aws_iam_role_policy" "business_query_governance" {
  name = "llmwiki-business-query-governance"
  role = aws_iam_role.business_query_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GovernanceTables"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.usage.arn,
          "${aws_dynamodb_table.usage.arn}/index/*",
          aws_dynamodb_table.cache.arn,
          "${aws_dynamodb_table.cache.arn}/index/*",
          aws_dynamodb_table.rate_limits.arn,
        ]
      },
      {
        Sid    = "BedrockEmbed"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Sid    = "CloudWatchGovernance"
        Effect = "Allow"
        Action = ["cloudwatch:PutMetricData"]
        Resource = "*"
      },
    ]
  })
}

# Streamlit task role needs to read usage + cache for Governance page
resource "aws_iam_role_policy" "streamlit_governance_read" {
  name = "llmwiki-streamlit-governance-read"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GovernanceRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.usage.arn,
          "${aws_dynamodb_table.usage.arn}/index/*",
          aws_dynamodb_table.cache.arn,
          "${aws_dynamodb_table.cache.arn}/index/*",
          aws_dynamodb_table.rate_limits.arn,
        ]
      },
    ]
  })
}
