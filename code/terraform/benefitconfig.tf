# ══════════════════════════════════════════════════════════════════════════════
# Benefit Configuration Comparison — UC-BC Infrastructure
#
# SCP constraints respected:
#  - No VPC resources (no VPC endpoints, no private subnets) — cost
#  - No KMS CMK creation — use aws:kms (bucket key) only
#  - No cross-account roles
#  - IAM roles attached to existing skills_lambda role via inline policy extension
#  - PAY_PER_REQUEST billing on all DynamoDB tables — no provisioned capacity
# ══════════════════════════════════════════════════════════════════════════════

# ── DynamoDB: BC run tracking ─────────────────────────────────────────────────
resource "aws_dynamodb_table" "bc_runs" {
  name         = "llmwiki-bc-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"
  range_key    = "plan_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "plan_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "plan_status_index"
    hash_key        = "plan_id"
    range_key       = "status"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "status_created_index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    use_case = "UC-BC"
  }
}

# ── Copy common libraries into harness directory before zipping ───────────────
resource "null_resource" "copy_common_to_bc_harness" {
  triggers = {
    common         = filemd5("${path.module}/../lambda/common/llmwiki_common.py")
    harness_common = filemd5("${path.module}/../lambda/common/harness_common.py")
    handler        = filemd5("${path.module}/../lambda/harness/benefitconfig_harness/handler.py")
  }
  provisioner "local-exec" {
    command = <<-EOT
      cp '${path.module}/../lambda/common/llmwiki_common.py' \
         '${path.module}/../lambda/harness/benefitconfig_harness/' && \
      cp '${path.module}/../lambda/common/harness_common.py' \
         '${path.module}/../lambda/harness/benefitconfig_harness/' || true
    EOT
  }
}

# ── Lambda: Benefit Config Harness ───────────────────────────────────────────
data "archive_file" "bc_harness" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/harness/benefitconfig_harness"
  output_path = "${path.module}/../.build/bc_harness.zip"
  depends_on  = [null_resource.copy_common_to_bc_harness]
}

resource "aws_cloudwatch_log_group" "bc_harness" {
  name              = "/aws/lambda/llmwiki-harness-uc-bc"
  retention_in_days = 14
}

resource "aws_lambda_function" "bc_harness" {
  function_name    = "llmwiki-harness-uc-bc"
  role             = aws_iam_role.skills_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.bc_harness.output_path
  source_code_hash = data.archive_file.bc_harness.output_base64sha256
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
      WIKI_BUCKET      = aws_s3_bucket.wiki.id
      BC_RUNS_TABLE    = aws_dynamodb_table.bc_runs.name
      LOG_TABLE        = aws_dynamodb_table.wiki_log.name
      REGISTRY_TABLE   = aws_dynamodb_table.source_registry.name
      SK02_FUNCTION    = aws_lambda_function.sk02_wiki_query.function_name
      SK03_FUNCTION    = aws_lambda_function.sk03_wiki_contribute.function_name
      SK05_FUNCTION    = aws_lambda_function.sk05_gap_detection.function_name
    }
  }

  tags = {
    use_case = "UC-BC"
  }

  depends_on = [aws_cloudwatch_log_group.bc_harness]
}

# ── SSM parameter — harness ARN for discovery ─────────────────────────────────
resource "aws_ssm_parameter" "bc_harness_arn" {
  name  = "/llmwiki/harness/bc_harness_arn"
  type  = "String"
  value = aws_lambda_function.bc_harness.arn
}

# ── IAM: extend skills_lambda to access BC table + invoke BC harness ──────────
resource "aws_iam_role_policy" "skills_lambda_bc" {
  name = "llmwiki-skills-lambda-bc-policy"
  role = aws_iam_role.skills_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BCDynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.bc_runs.arn,
          "${aws_dynamodb_table.bc_runs.arn}/index/*",
        ]
      },
      {
        Sid    = "InvokeBCHarness"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_function.bc_harness.arn]
      },
      {
        Sid    = "BCS3BenefitWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.wiki.arn}/wiki/benefitconfig/*",
          "${aws_s3_bucket.wiki.arn}/uploads/benefit-config/*",
        ]
      },
      {
        Sid    = "BCS3PresignRead"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/wiki/benefitconfig/*"
      }
    ]
  })
}

# ── IAM: allow Streamlit task to invoke BC harness ────────────────────────────
resource "aws_iam_role_policy" "streamlit_bc_invoke" {
  name = "llmwiki-streamlit-bc-invoke"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeBCHarness"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_function.bc_harness.arn]
      },
      {
        Sid    = "BCRunsRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.bc_runs.arn,
          "${aws_dynamodb_table.bc_runs.arn}/index/*",
        ]
      },
      {
        Sid    = "BCUploadPDFs"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/uploads/benefit-config/*"
      }
    ]
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "bc_harness_lambda_arn" {
  description = "ARN of the Benefit Config harness Lambda"
  value       = aws_lambda_function.bc_harness.arn
}

output "bc_runs_table_name" {
  description = "DynamoDB table tracking BC runs"
  value       = aws_dynamodb_table.bc_runs.name
}
