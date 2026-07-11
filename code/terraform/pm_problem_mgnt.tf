# ══════════════════════════════════════════════════════════════════════════════
# Problem Management — UC-PM Infrastructure
# ══════════════════════════════════════════════════════════════════════════════

# ── DynamoDB: PM Run tracking ─────────────────────────────────────────────────
# run_id = "{batch_id}#{problem_id}", batch_id is sort key for index
resource "aws_dynamodb_table" "pm_runs" {
  name         = "llmwiki-pm-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"
  range_key    = "batch_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "batch_id"
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
    name            = "batch_status_index"
    hash_key        = "batch_id"
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
    use_case = "UC-PM"
  }
}

# ── DynamoDB: SK-06 classifications ──────────────────────────────────────────
resource "aws_dynamodb_table" "pm_classifications" {
  name         = "llmwiki-pm-classifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "problem_id"
  range_key    = "classified_at"

  attribute {
    name = "problem_id"
    type = "S"
  }

  attribute {
    name = "classified_at"
    type = "S"
  }

  attribute {
    name = "product"
    type = "S"
  }

  global_secondary_index {
    name            = "product_classified_index"
    hash_key        = "product"
    range_key       = "classified_at"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    use_case = "UC-PM"
    skill_id = "SK-06"
  }
}

# ── SNS: High-severity PM alerts ─────────────────────────────────────────────
resource "aws_sns_topic" "pm_high_severity_alerts" {
  name = "llmwiki-pm-high-severity-alerts"

  tags = {
    use_case = "UC-PM"
    skill_id = "SK-06"
  }
}

resource "aws_ssm_parameter" "pm_sns_topic_arn" {
  name  = "/llmwiki/pm/sns_alerts_arn"
  type  = "String"
  value = aws_sns_topic.pm_high_severity_alerts.arn
}

# ── Copy common library into PM app directories before zipping ────────────────
# This bundles llmwiki_common.py and harness_common.py alongside each handler
# so Lambda can import them without a Layer. Triggered whenever common lib changes.
resource "null_resource" "copy_common_to_sk06" {
  triggers = {
    common = filemd5("${path.module}/../lambda/common/llmwiki_common.py")
  }
  provisioner "local-exec" {
    command = "cp '${path.module}/../lambda/common/llmwiki_common.py' '${path.module}/../lambda/apps/problem_mgnt/skills/problem_classifier/'"
  }
}

resource "null_resource" "copy_common_to_pm_harness" {
  triggers = {
    common         = filemd5("${path.module}/../lambda/common/llmwiki_common.py")
    harness_common = filemd5("${path.module}/../lambda/common/harness_common.py")
  }
  provisioner "local-exec" {
    command = "cp '${path.module}/../lambda/common/llmwiki_common.py' '${path.module}/../lambda/apps/problem_mgnt/harness/pm_harness/' && cp '${path.module}/../lambda/common/harness_common.py' '${path.module}/../lambda/apps/problem_mgnt/harness/pm_harness/'"
  }
}

# ── Lambda: SK-06 Problem Classifier ─────────────────────────────────────────
data "archive_file" "skill_problem_classifier" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/apps/problem_mgnt/skills/problem_classifier"
  output_path = "${path.module}/../.build/skill_problem_classifier.zip"
  depends_on  = [null_resource.copy_common_to_sk06]
}

resource "aws_cloudwatch_log_group" "skill_problem_classifier" {
  name              = "/aws/lambda/llmwiki-skill-problem-classifier"
  retention_in_days = 30
}

resource "aws_lambda_function" "skill_problem_classifier" {
  function_name    = "llmwiki-skill-problem-classifier"
  role             = aws_iam_role.skills_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.skill_problem_classifier.output_path
  source_code_hash = data.archive_file.skill_problem_classifier.output_base64sha256
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      LOG_TABLE         = aws_dynamodb_table.wiki_log.name
      PM_CLASS_TABLE    = aws_dynamodb_table.pm_classifications.name
      PM_SNS_TOPIC_ARN  = aws_sns_topic.pm_high_severity_alerts.arn
    }
  }

  tags = {
    skill_id      = "SK-06"
    tier          = "3"
    use_case_tags = "UC-PM"
  }

  depends_on = [aws_cloudwatch_log_group.skill_problem_classifier]
}

resource "aws_ssm_parameter" "skill_problem_classifier_arn" {
  name  = "/llmwiki/skills/sk06_arn"
  type  = "String"
  value = aws_lambda_function.skill_problem_classifier.arn
}

# ── Lambda: PM Harness ────────────────────────────────────────────────────────
data "archive_file" "pm_harness" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/apps/problem_mgnt/harness/pm_harness"
  output_path = "${path.module}/../.build/pm_harness.zip"
  depends_on  = [null_resource.copy_common_to_pm_harness]
}

resource "aws_cloudwatch_log_group" "pm_harness" {
  name              = "/aws/lambda/llmwiki-harness-uc-pm"
  retention_in_days = 14
}

resource "aws_lambda_function" "pm_harness" {
  function_name    = "llmwiki-harness-uc-pm"
  role             = aws_iam_role.skills_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.pm_harness.output_path
  source_code_hash = data.archive_file.pm_harness.output_base64sha256
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
      PM_WIKI_BUCKET   = aws_s3_bucket.pm.id
      PM_RUNS_TABLE    = aws_dynamodb_table.pm_runs.name
      LOG_TABLE        = aws_dynamodb_table.wiki_log.name
      SK01_FUNCTION    = aws_lambda_function.sk01_context_bootstrap.function_name
      SK02_FUNCTION    = aws_lambda_function.sk02_wiki_query.function_name
      SK03_FUNCTION    = aws_lambda_function.sk03_wiki_contribute.function_name
      SK04_FUNCTION    = aws_lambda_function.sk04_artifact_resolution.function_name
      SK05_FUNCTION    = aws_lambda_function.sk05_gap_detection.function_name
      SK06_FUNCTION    = aws_lambda_function.skill_problem_classifier.function_name
      # PM KB ID is resolved from SSM at runtime if this env var is empty/pending
      # Set at apply time via data source once null_resource.bedrock_pm_kb completes.
      PM_KB_ID         = ""
    }
  }

  tags = {
    use_case = "UC-PM"
  }

  depends_on = [aws_cloudwatch_log_group.pm_harness]
}

resource "aws_ssm_parameter" "pm_harness_arn" {
  name  = "/llmwiki/harness/pm_harness_arn"
  type  = "String"
  value = aws_lambda_function.pm_harness.arn
}

# ── IAM: extend skills_lambda to access PM tables + KB + SSM ─────────────────
resource "aws_iam_role_policy" "skills_lambda_pm" {
  name = "llmwiki-skills-lambda-pm-policy"
  role = aws_iam_role.skills_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PMDynamoDB"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query",
                  "dynamodb:Scan", "dynamodb:UpdateItem"]
        Resource = [
          aws_dynamodb_table.pm_runs.arn,
          "${aws_dynamodb_table.pm_runs.arn}/index/*",
          aws_dynamodb_table.pm_classifications.arn,
          "${aws_dynamodb_table.pm_classifications.arn}/index/*",
        ]
      },
      {
        Sid    = "InvokePMHarness"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.pm_harness.arn,
          aws_lambda_function.skill_problem_classifier.arn,
        ]
      },
      {
        Sid    = "PMBedrockKBRetrieve"
        Effect = "Allow"
        Action = ["bedrock:Retrieve", "bedrock-agent-runtime:Retrieve"]
        Resource = "arn:aws:bedrock:us-east-1:*:knowledge-base/*"
      },
      {
        Sid    = "PMSSMReadKBId"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:us-east-1:*:parameter/llmwiki/pm_*"
      }
    ]
  })
}

# ── IAM: allow Streamlit to invoke PM harness ─────────────────────────────────
resource "aws_iam_role_policy" "streamlit_pm_invoke" {
  name = "llmwiki-streamlit-pm-invoke"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokePMHarness"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.pm_harness.arn,
        ]
      },
      {
        Sid    = "PMRunsRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.pm_runs.arn,
          "${aws_dynamodb_table.pm_runs.arn}/index/*",
        ]
      }
    ]
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "pm_harness_lambda_arn" {
  description = "ARN of the PM harness Lambda"
  value       = aws_lambda_function.pm_harness.arn
}

output "pm_sns_alert_topic_arn" {
  description = "ARN of the PM high-severity SNS topic"
  value       = aws_sns_topic.pm_high_severity_alerts.arn
}
