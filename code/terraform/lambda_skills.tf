# ── SK-01 Customer Briefing Loader (ContextBootstrapSkill) ────────

data "archive_file" "sk01_context_bootstrap" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/context_bootstrap"
  output_path = "${path.module}/../.build/sk01_context_bootstrap.zip"
}

resource "aws_cloudwatch_log_group" "sk01" {
  name              = "/aws/lambda/llmwiki-skill-context-bootstrap"
  retention_in_days = 14
}

resource "aws_lambda_function" "sk01_context_bootstrap" {
  function_name    = "llmwiki-skill-context-bootstrap"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.sk01_context_bootstrap.output_path
  source_code_hash = data.archive_file.sk01_context_bootstrap.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      PLAYBOOK_FUNCTION = aws_lambda_function.playbook.function_name
      LOG_TABLE         = aws_dynamodb_table.wiki_log.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.sk01]
}

# ── SK-02 Knowledge Finder (WikiQuerySkill) ────────────────────────

data "archive_file" "sk02_wiki_query" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/wiki_query"
  output_path = "${path.module}/../.build/sk02_wiki_query.zip"
}

resource "aws_cloudwatch_log_group" "sk02" {
  name              = "/aws/lambda/llmwiki-skill-wiki-query"
  retention_in_days = 14
}

resource "aws_lambda_function" "sk02_wiki_query" {
  function_name    = "llmwiki-skill-wiki-query"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.sk02_wiki_query.output_path
  source_code_hash = data.archive_file.sk02_wiki_query.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUSINESS_QUERY_FUNCTION = aws_lambda_function.business_query.function_name
      LOG_TABLE               = aws_dynamodb_table.wiki_log.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.sk02]
}

# ── SK-03 Knowledge Recorder (WikiContributeSkill) ────────────────

data "archive_file" "sk03_wiki_contribute" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/wiki_contribute"
  output_path = "${path.module}/../.build/sk03_wiki_contribute.zip"
}

resource "aws_cloudwatch_log_group" "sk03" {
  name              = "/aws/lambda/llmwiki-skill-wiki-contribute"
  retention_in_days = 14
}

resource "aws_lambda_function" "sk03_wiki_contribute" {
  function_name    = "llmwiki-skill-wiki-contribute"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.sk03_wiki_contribute.output_path
  source_code_hash = data.archive_file.sk03_wiki_contribute.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      CONTRIBUTE_FUNCTION = aws_lambda_function.contribute.function_name
      LOG_TABLE           = aws_dynamodb_table.wiki_log.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.sk03]
}

# ── SK-04 Template Auto-Fill (ArtifactResolutionSkill) ────────────

data "archive_file" "sk04_artifact_resolution" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/artifact_resolution"
  output_path = "${path.module}/../.build/sk04_artifact_resolution.zip"
}

resource "aws_cloudwatch_log_group" "sk04" {
  name              = "/aws/lambda/llmwiki-skill-artifact-resolution"
  retention_in_days = 14
}

resource "aws_lambda_function" "sk04_artifact_resolution" {
  function_name    = "llmwiki-skill-artifact-resolution"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.sk04_artifact_resolution.output_path
  source_code_hash = data.archive_file.sk04_artifact_resolution.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      PLAYBOOK_FUNCTION = aws_lambda_function.playbook.function_name
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      LOG_TABLE         = aws_dynamodb_table.wiki_log.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.sk04]
}

# ── SK-05 Missing Info Radar (GapDetectionSkill) ──────────────────

data "archive_file" "sk05_gap_detection" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/gap_detection"
  output_path = "${path.module}/../.build/sk05_gap_detection.zip"
}

resource "aws_cloudwatch_log_group" "sk05" {
  name              = "/aws/lambda/llmwiki-skill-gap-detection"
  retention_in_days = 14
}

resource "aws_lambda_function" "sk05_gap_detection" {
  function_name    = "llmwiki-skill-gap-detection"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.sk05_gap_detection.output_path
  source_code_hash = data.archive_file.sk05_gap_detection.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      GAPS_TABLE        = aws_dynamodb_table.gaps.name
      LOG_TABLE         = aws_dynamodb_table.wiki_log.name
      GAPS_SNS_TOPIC_ARN = ""
    }
  }

  depends_on = [aws_cloudwatch_log_group.sk05]
}

# ── UC1 Orchestrator (demo of full 5-skill flow) ──────────────────

data "archive_file" "uc1_orchestrator" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/skills/uc1_orchestrator"
  output_path = "${path.module}/../.build/uc1_orchestrator.zip"
}

resource "aws_cloudwatch_log_group" "uc1_orchestrator" {
  name              = "/aws/lambda/llmwiki-uc1-orchestrator"
  retention_in_days = 14
}

resource "aws_lambda_function" "uc1_orchestrator" {
  function_name    = "llmwiki-uc1-orchestrator"
  role             = aws_iam_role.skills_lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.uc1_orchestrator.output_path
  source_code_hash = data.archive_file.uc1_orchestrator.output_base64sha256
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      SK01_FUNCTION = aws_lambda_function.sk01_context_bootstrap.function_name
      SK02_FUNCTION = aws_lambda_function.sk02_wiki_query.function_name
      SK03_FUNCTION = aws_lambda_function.sk03_wiki_contribute.function_name
      SK04_FUNCTION = aws_lambda_function.sk04_artifact_resolution.function_name
      SK05_FUNCTION = aws_lambda_function.sk05_gap_detection.function_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.uc1_orchestrator]
}

# ── SSM parameters — skill ARNs for AgentCore discovery ──────────

resource "aws_ssm_parameter" "sk01_arn" {
  name  = "/llmwiki/skills/sk01_context_bootstrap_arn"
  type  = "String"
  value = aws_lambda_function.sk01_context_bootstrap.arn
}

resource "aws_ssm_parameter" "sk02_arn" {
  name  = "/llmwiki/skills/sk02_wiki_query_arn"
  type  = "String"
  value = aws_lambda_function.sk02_wiki_query.arn
}

resource "aws_ssm_parameter" "sk03_arn" {
  name  = "/llmwiki/skills/sk03_wiki_contribute_arn"
  type  = "String"
  value = aws_lambda_function.sk03_wiki_contribute.arn
}

resource "aws_ssm_parameter" "sk04_arn" {
  name  = "/llmwiki/skills/sk04_artifact_resolution_arn"
  type  = "String"
  value = aws_lambda_function.sk04_artifact_resolution.arn
}

resource "aws_ssm_parameter" "sk05_arn" {
  name  = "/llmwiki/skills/sk05_gap_detection_arn"
  type  = "String"
  value = aws_lambda_function.sk05_gap_detection.arn
}

resource "aws_ssm_parameter" "uc1_orchestrator_arn" {
  name  = "/llmwiki/skills/uc1_orchestrator_arn"
  type  = "String"
  value = aws_lambda_function.uc1_orchestrator.arn
}
