data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ── Ingest Lambda role ────────────────────────────────────────────
resource "aws_iam_role" "ingest_lambda" {
  name               = "llmwiki-ingest-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "ingest_lambda_policy" {
  name = "llmwiki-ingest-lambda-policy"
  role = aws_iam_role.ingest_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3RawRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:HeadObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/raw/*"
      },
      {
        Sid    = "S3WikiWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.wiki.arn}/wiki/*",
          "${aws_s3_bucket.wiki.arn}/config/*"
        ]
      },
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
          aws_dynamodb_table.wiki_log.arn,
          aws_dynamodb_table.source_registry.arn,
          "${aws_dynamodb_table.source_registry.arn}/index/*",
          aws_dynamodb_table.gaps.arn,
          "${aws_dynamodb_table.gaps.arn}/index/*"
        ]
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:StartIngestionJob"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid    = "SSMParameters"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/llmwiki/*"
      }
    ]
  })
}

# ── Query Lambda role ─────────────────────────────────────────────
resource "aws_iam_role" "query_lambda" {
  name               = "llmwiki-query-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "query_lambda_policy" {
  name = "llmwiki-query-lambda-policy"
  role = aws_iam_role.query_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3WikiRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.wiki.arn,
          "${aws_s3_bucket.wiki.arn}/wiki/*",
          "${aws_s3_bucket.wiki.arn}/output/*",
          aws_s3_bucket.pm.arn,
          "${aws_s3_bucket.pm.arn}/raw/*",
          "${aws_s3_bucket.pm.arn}/wiki/*"
        ]
      },
      {
        Sid    = "S3WikiWrite"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/wiki/questions/*"
      },
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
          aws_dynamodb_table.wiki_log.arn,
          aws_dynamodb_table.source_registry.arn,
          "${aws_dynamodb_table.source_registry.arn}/index/*",
          aws_dynamodb_table.gaps.arn,
          "${aws_dynamodb_table.gaps.arn}/index/*"
        ]
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:RetrieveAndGenerate", "bedrock:Retrieve"]
        Resource = "*"
      },
      {
        Sid    = "SSMParameters"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/llmwiki/*"
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

# ── Converter Lambda role ─────────────────────────────────────────
resource "aws_iam_role" "converter_lambda" {
  name               = "llmwiki-converter-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy" "converter_lambda_policy" {
  name = "llmwiki-converter-lambda-policy"
  role = aws_iam_role.converter_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3RawAccess"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:HeadObject", "s3:CopyObject"]
        Resource = [
          "${aws_s3_bucket.wiki.arn}/raw/*",
          "${aws_s3_bucket.wiki.arn}/uploads/*"
        ]
      },
      {
        Sid    = "TextractAccess"
        Effect = "Allow"
        Action = [
          "textract:DetectDocumentText",
          "textract:AnalyzeDocument",
          "textract:StartDocumentTextDetection",
          "textract:GetDocumentTextDetection"
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDBSourceRegistry"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.source_registry.arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "*"
      }
    ]
  })
}

# ── ECS task role (Streamlit) ─────────────────────────────────────
data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "streamlit_task" {
  name               = "llmwiki-streamlit-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy" "streamlit_task_policy" {
  name = "llmwiki-streamlit-task-policy"
  role = aws_iam_role.streamlit_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3WikiRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket", "s3:PutObject"]
        Resource = [
          aws_s3_bucket.wiki.arn,
          "${aws_s3_bucket.wiki.arn}/wiki/*",
          "${aws_s3_bucket.wiki.arn}/uploads/*",
          "${aws_s3_bucket.wiki.arn}/output/*"
        ]
      },
      {
        Sid    = "S3RawRead"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.wiki.arn}/raw/assets/*"
      },
      {
        Sid    = "DynamoDBRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.wiki_index.arn,
          "${aws_dynamodb_table.wiki_index.arn}/index/*",
          aws_dynamodb_table.wiki_log.arn,
          aws_dynamodb_table.source_registry.arn,
          "${aws_dynamodb_table.source_registry.arn}/index/*",
          aws_dynamodb_table.gaps.arn,
          "${aws_dynamodb_table.gaps.arn}/index/*"
        ]
      },
      {
        Sid    = "LambdaInvoke"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.query.arn,
          aws_lambda_function.converter.arn
        ]
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

resource "aws_iam_role" "streamlit_execution" {
  name               = "llmwiki-streamlit-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "streamlit_execution_policy" {
  role       = aws_iam_role.streamlit_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "streamlit_execution_logs" {
  name = "llmwiki-streamlit-execution-logs"
  role = aws_iam_role.streamlit_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup"]
        Resource = "*"
      }
    ]
  })
}

# ── Bedrock Knowledge Base role ───────────────────────────────────
data "aws_iam_policy_document" "bedrock_kb_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  name               = "llmwiki-bedrock-kb-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_kb_assume.json
}

resource "aws_iam_role_policy" "bedrock_kb_policy" {
  name = "llmwiki-bedrock-kb-policy"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.wiki.arn,
          "${aws_s3_bucket.wiki.arn}/wiki/*"
        ]
      },
      # PM KB bucket access is granted via aws_iam_role_policy.bedrock_kb_pm_s3
      # in pm_bedrock_kb.tf (separate policy to keep PM lifecycle independent).
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
      },
      {
        Sid    = "S3VectorsAccess"
        Effect = "Allow"
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:QueryVectors",
          "s3vectors:GetIndex",
          "s3vectors:ListVectors"
        ]
        Resource = local.vector_index_arn
      }
    ]
  })
}
