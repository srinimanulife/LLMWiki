# ── Business Query Lambda ──────────────────────────────────────────
data "archive_file" "business_query" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/business_query"
  output_path = "${path.module}/../.build/business_query.zip"
}

resource "aws_cloudwatch_log_group" "business_query_lambda" {
  name              = "/aws/lambda/llmwiki-business-query"
  retention_in_days = 14
}

resource "aws_lambda_function" "business_query" {
  function_name    = "llmwiki-business-query"
  role             = aws_iam_role.business_query_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.business_query.output_path
  source_code_hash = data.archive_file.business_query.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      WIKI_BUCKET      = aws_s3_bucket.wiki.id
      BEDROCK_MODEL_ID = var.bedrock_model_id
      KB_ID_PARAM      = "/llmwiki/bedrock_kb_id"
      DYNAMODB_INDEX   = aws_dynamodb_table.wiki_index.name
      GAPS_TABLE       = aws_dynamodb_table.gaps.name
      CONTRIB_TABLE    = aws_dynamodb_table.contributions.name
      USAGE_TABLE      = aws_dynamodb_table.usage.name
      CACHE_TABLE      = aws_dynamodb_table.cache.name
      RATE_TABLE       = aws_dynamodb_table.rate_limits.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.business_query_lambda,
    data.archive_file.business_query
  ]
}

resource "aws_lambda_permission" "allow_apigw_business_query" {
  statement_id  = "AllowAPIGWInvokeBusinessQuery"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.business_query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/*"
}

# ── Contribute Lambda ──────────────────────────────────────────────
data "archive_file" "contribute" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/contribute"
  output_path = "${path.module}/../.build/contribute.zip"
}

resource "aws_cloudwatch_log_group" "contribute_lambda" {
  name              = "/aws/lambda/llmwiki-contribute"
  retention_in_days = 14
}

resource "aws_lambda_function" "contribute" {
  function_name    = "llmwiki-contribute"
  role             = aws_iam_role.contribute_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.contribute.output_path
  source_code_hash = data.archive_file.contribute.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      WIKI_BUCKET      = aws_s3_bucket.wiki.id
      DYNAMODB_INDEX   = aws_dynamodb_table.wiki_index.name
      CONTRIB_TABLE    = aws_dynamodb_table.contributions.name
      KB_ID_PARAM      = "/llmwiki/bedrock_kb_id"
      KB_DS_ID_PARAM   = "/llmwiki/bedrock_kb_datasource_id"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.contribute_lambda,
    data.archive_file.contribute
  ]
}

resource "aws_lambda_permission" "allow_apigw_contribute" {
  statement_id  = "AllowAPIGWInvokeContribute"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.contribute.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/*"
}

# ── Playbook Lambda ────────────────────────────────────────────────
data "archive_file" "playbook" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/playbook"
  output_path = "${path.module}/../.build/playbook.zip"
}

resource "aws_cloudwatch_log_group" "playbook_lambda" {
  name              = "/aws/lambda/llmwiki-playbook"
  retention_in_days = 14
}

resource "aws_lambda_function" "playbook" {
  function_name    = "llmwiki-playbook"
  role             = aws_iam_role.playbook_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.playbook.output_path
  source_code_hash = data.archive_file.playbook.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      WIKI_BUCKET      = aws_s3_bucket.wiki.id
      BEDROCK_MODEL_ID = var.bedrock_model_id
      KB_ID_PARAM      = "/llmwiki/bedrock_kb_id"
      DYNAMODB_INDEX   = aws_dynamodb_table.wiki_index.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.playbook_lambda,
    data.archive_file.playbook
  ]
}

resource "aws_lambda_permission" "allow_apigw_playbook" {
  statement_id  = "AllowAPIGWInvokePlaybook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.playbook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.wiki.execution_arn}/*/*"
}
