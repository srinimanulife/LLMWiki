# ── Gatekeeper Lambda ─────────────────────────────────────────────
# Validates incoming harness requests, writes the initial run record to
# harness_runs, then invokes uc1_harness asynchronously.

data "archive_file" "gatekeeper" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/harness/gatekeeper"
  output_path = "${path.module}/../.build/gatekeeper.zip"
}

resource "aws_cloudwatch_log_group" "gatekeeper" {
  name              = "/aws/lambda/llmwiki-gatekeeper"
  retention_in_days = 14
}

resource "aws_lambda_function" "gatekeeper" {
  function_name    = "llmwiki-gatekeeper"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.gatekeeper.output_path
  source_code_hash = data.archive_file.gatekeeper.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      HARNESS_RUNS_TABLE = aws_dynamodb_table.harness_runs.name
      WIKI_BUCKET        = aws_s3_bucket.wiki.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.gatekeeper]
}

# ── UC1 Harness Lambda ────────────────────────────────────────────
# Runs the full 8-phase UC1 test scenario end-to-end.
# 900 s timeout covers worst-case Bedrock latency across all phases.
# 1024 MB memory covers in-memory workspace accumulation.

data "archive_file" "uc1_harness" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/harness/uc1_harness"
  output_path = "${path.module}/../.build/uc1_harness.zip"
}

resource "aws_cloudwatch_log_group" "uc1_harness" {
  name              = "/aws/lambda/llmwiki-uc1-harness"
  retention_in_days = 14
}

resource "aws_lambda_function" "uc1_harness" {
  function_name    = "llmwiki-uc1-harness"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.uc1_harness.output_path
  source_code_hash = data.archive_file.uc1_harness.output_base64sha256
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      WIKI_BUCKET        = aws_s3_bucket.wiki.id
      HARNESS_RUNS_TABLE = aws_dynamodb_table.harness_runs.name
      WORKSPACE_TABLE    = aws_dynamodb_table.workspace_files.name
      LOG_TABLE          = aws_dynamodb_table.wiki_log.name
      GAPS_TABLE         = aws_dynamodb_table.gaps.name
      SK01_FUNCTION      = aws_lambda_function.sk01_context_bootstrap.function_name
      SK02_FUNCTION      = aws_lambda_function.sk02_wiki_query.function_name
      SK03_FUNCTION      = aws_lambda_function.sk03_wiki_contribute.function_name
      SK04_FUNCTION      = aws_lambda_function.sk04_artifact_resolution.function_name
      SK05_FUNCTION      = aws_lambda_function.sk05_gap_detection.function_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.uc1_harness]
}

# ── SSM parameters — harness ARNs for discovery ───────────────────

resource "aws_ssm_parameter" "gatekeeper_arn" {
  name  = "/llmwiki/harness/gatekeeper_arn"
  type  = "String"
  value = aws_lambda_function.gatekeeper.arn
}

resource "aws_ssm_parameter" "uc1_harness_arn" {
  name  = "/llmwiki/harness/uc1_harness_arn"
  type  = "String"
  value = aws_lambda_function.uc1_harness.arn
}

# ── Outputs ───────────────────────────────────────────────────────

output "gatekeeper_lambda_arn" {
  description = "ARN of the harness gatekeeper Lambda"
  value       = aws_lambda_function.gatekeeper.arn
}

output "uc1_harness_lambda_arn" {
  description = "ARN of the UC1 harness Lambda"
  value       = aws_lambda_function.uc1_harness.arn
}
