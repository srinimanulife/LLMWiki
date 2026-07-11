# ── Shared role for all 5 POC skill Lambdas + UC1 orchestrator ────

resource "aws_iam_role" "skills_lambda" {
  name               = "llmwiki-skills-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "skills_lambda_policy" {
  name = "llmwiki-skills-lambda-policy"
  role = aws_iam_role.skills_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeDownstreamLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.playbook.arn,
          aws_lambda_function.business_query.arn,
          aws_lambda_function.contribute.arn,
          # Self-referential skill invocations (UC1 orchestrator → skill Lambdas)
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:llmwiki-skill-*",
        ]
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query",
                  "dynamodb:Scan", "dynamodb:UpdateItem"]
        Resource = [
          aws_dynamodb_table.wiki_log.arn,
          aws_dynamodb_table.gaps.arn,
          "${aws_dynamodb_table.gaps.arn}/index/*",
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
          aws_dynamodb_table.harness_runs.arn,
          "${aws_dynamodb_table.harness_runs.arn}/index/*",
          aws_dynamodb_table.workspace_files.arn,
          "${aws_dynamodb_table.workspace_files.arn}/index/*",
        ]
      },
      {
        Sid    = "S3HarnessReports"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectAttributes"]
        Resource = "${aws_s3_bucket.wiki.arn}/wiki/reports/*"
      },
      {
        Sid    = "S3PMBucketFull"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectAttributes", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.pm.arn,
          "${aws_s3_bucket.pm.arn}/*"
        ]
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Sid    = "SNSPublish"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Allow Streamlit ECS task to invoke skill Lambdas, harness Lambdas, and read harness state
resource "aws_iam_role_policy" "streamlit_skills_invoke" {
  name = "llmwiki-streamlit-skills-invoke"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeSkillAndHarnessLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:llmwiki-skill-*",
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:llmwiki-uc1-orchestrator",
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:llmwiki-gatekeeper",
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:llmwiki-uc1-harness",
        ]
      },
      {
        Sid    = "HarnessStateRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.harness_runs.arn,
          "${aws_dynamodb_table.harness_runs.arn}/index/*",
          aws_dynamodb_table.workspace_files.arn,
          "${aws_dynamodb_table.workspace_files.arn}/index/*",
        ]
      },
      {
        Sid    = "HarnessReportDownload"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/wiki/reports/*"
      },
      {
        Sid    = "PMBucketRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.pm.arn,
          "${aws_s3_bucket.pm.arn}/*"
        ]
      },
      {
        Sid    = "BedrockInvokeForPostHarnessChat"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "*"
      }
    ]
  })
}
