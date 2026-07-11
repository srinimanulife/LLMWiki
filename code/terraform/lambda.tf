locals {
  ingest_zip    = "${path.module}/../.build/ingest.zip"
  query_zip     = "${path.module}/../.build/query.zip"
  converter_zip = "${path.module}/../.build/converter.zip"
}

# ── Ingest Lambda ─────────────────────────────────────────────────
data "archive_file" "ingest" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/ingest"
  output_path = local.ingest_zip
}

resource "aws_cloudwatch_log_group" "ingest_lambda" {
  name              = "/aws/lambda/llmwiki-ingest"
  retention_in_days = 14
}

resource "aws_lambda_function" "ingest" {
  function_name    = "llmwiki-ingest"
  role             = aws_iam_role.ingest_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      WIKI_BUCKET          = aws_s3_bucket.wiki.id
      DYNAMODB_INDEX_TABLE = aws_dynamodb_table.wiki_index.name
      DYNAMODB_LOG_TABLE   = aws_dynamodb_table.wiki_log.name
      DYNAMODB_REGISTRY    = aws_dynamodb_table.source_registry.name
      BEDROCK_MODEL_ID     = var.bedrock_model_id
      AWS_ACCOUNT_ID       = data.aws_caller_identity.current.account_id
      KB_ID_PARAM          = "/llmwiki/bedrock_kb_id"
      KB_DS_ID_PARAM       = "/llmwiki/bedrock_kb_datasource_id"
      GAPS_TABLE           = aws_dynamodb_table.gaps.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ingest_lambda,
    data.archive_file.ingest
  ]
}

resource "aws_lambda_permission" "allow_s3_ingest" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.wiki.arn
}

# ── Query Lambda ──────────────────────────────────────────────────
data "archive_file" "query" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/query"
  output_path = local.query_zip
}

resource "aws_cloudwatch_log_group" "query_lambda" {
  name              = "/aws/lambda/llmwiki-query"
  retention_in_days = 14
}

resource "aws_lambda_function" "query" {
  function_name    = "llmwiki-query"
  role             = aws_iam_role.query_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.query.output_path
  source_code_hash = data.archive_file.query.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      WIKI_BUCKET      = aws_s3_bucket.wiki.id
      PM_WIKI_BUCKET   = aws_s3_bucket.pm.id
      BEDROCK_MODEL_ID = var.bedrock_model_id
      KB_ID_PARAM      = "/llmwiki/bedrock_kb_id"
      DYNAMODB_INDEX   = aws_dynamodb_table.wiki_index.name
      REGISTRY_TABLE   = aws_dynamodb_table.source_registry.name
      GAPS_TABLE       = aws_dynamodb_table.gaps.name
      USAGE_TABLE      = aws_dynamodb_table.usage.name
      CACHE_TABLE      = aws_dynamodb_table.cache.name
      RATE_TABLE       = aws_dynamodb_table.rate_limits.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.query_lambda,
    data.archive_file.query
  ]
}

resource "aws_lambda_permission" "allow_apigw_query" {
  statement_id  = "AllowAPIGWInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/*"
}

# ── Converter Lambda (Phase 1: PDF / Office docs) ─────────────────
data "archive_file" "converter" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/converter"
  output_path = local.converter_zip
}

resource "aws_cloudwatch_log_group" "converter_lambda" {
  name              = "/aws/lambda/llmwiki-converter"
  retention_in_days = 14
}

resource "aws_lambda_function" "converter" {
  function_name    = "llmwiki-converter"
  role             = aws_iam_role.converter_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.converter.output_path
  source_code_hash = data.archive_file.converter.output_base64sha256
  timeout          = var.textract_timeout_seconds
  memory_size      = 1024

  environment {
    variables = {
      WIKI_BUCKET       = aws_s3_bucket.wiki.id
      REGISTRY_TABLE    = aws_dynamodb_table.source_registry.name
      BEDROCK_MODEL_ID  = var.bedrock_model_id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.converter_lambda,
    data.archive_file.converter
  ]
}

resource "aws_lambda_permission" "allow_s3_converter" {
  statement_id  = "AllowS3InvokeConverter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.converter.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.wiki.arn
}

# ── S3 notification: uploads/ → converter ─────────────────────────
resource "aws_s3_bucket_notification" "wiki_upload_trigger" {
  bucket = aws_s3_bucket.wiki.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".md"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.converter.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }

  depends_on = [
    aws_lambda_permission.allow_s3_ingest,
    aws_lambda_permission.allow_s3_converter
  ]
}
