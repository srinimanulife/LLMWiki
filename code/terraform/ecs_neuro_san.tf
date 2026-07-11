# ── Neuro SAN ECS resources ───────────────────────────────────────
# Sidecar task: neuro-san-server (8080) + nsflow UI (4173) in one Fargate task.
# ALB rules: /agents/* → nsflow, /api/agents/* → neuro-san HTTP API

# ── ECR Repository ────────────────────────────────────────────────
resource "aws_ecr_repository" "neuro_san" {
  name                 = "llmwiki-neuro-san"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "llmwiki-neuro-san" }
}

resource "aws_ecr_lifecycle_policy" "neuro_san" {
  repository = aws_ecr_repository.neuro_san.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

# ── Security Group ────────────────────────────────────────────────
resource "aws_security_group" "neuro_san" {
  name        = "llmwiki-neuro-san-sg"
  description = "Allow ALB traffic to neuro-san and nsflow ports"
  vpc_id      = aws_vpc.wiki.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    from_port       = 4173
    to_port         = 4173
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "llmwiki-neuro-san-sg" }
}

# ── CloudWatch Log Group ──────────────────────────────────────────
resource "aws_cloudwatch_log_group" "neuro_san" {
  name              = "/ecs/llmwiki-neuro-san"
  retention_in_days = 7
}

# ── ECS Task Definition ───────────────────────────────────────────
# 1 vCPU / 2 GB — Claude calls are async, not CPU-bound
resource "aws_ecs_task_definition" "neuro_san" {
  family                   = "llmwiki-neuro-san"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  task_role_arn            = aws_iam_role.streamlit_task.arn
  execution_role_arn       = aws_iam_role.streamlit_execution.arn

  container_definitions = jsonencode([{
    name      = "neuro-san"
    image     = "${aws_ecr_repository.neuro_san.repository_url}:latest"
    essential = true

    portMappings = [
      { containerPort = 8080, protocol = "tcp" },
      { containerPort = 4173, protocol = "tcp" }
    ]

    environment = [
      # Neuro SAN server config
      { name = "AGENT_MANIFEST_FILE",                    value = "registries/llmwiki/manifest.hocon" },
      { name = "AGENT_TOOL_PATH",                        value = "/app/coded_tools" },
      { name = "AGENT_MANIFEST_UPDATE_PERIOD_SECONDS",   value = "5" },
      # S3 hot-reload
      { name = "WIKI_BUCKET",                            value = aws_s3_bucket.wiki.id },
      # nsflow → server (sidecar, same task = localhost)
      { name = "NEURO_SAN_SERVER_HOST",                  value = "localhost" },
      { name = "NEURO_SAN_SERVER_HTTP_PORT",             value = "8080" },
      { name = "NEURO_SAN_SERVER_CONNECTION",            value = "http" },
      # Pre-loaded sly data (api_key resolved at runtime via SSM or hardcoded demo value)
      { name = "DEFAULT_SLY_DATA",                       value = "{\"engagement_id\":\"demo\"}" },
      # Lambda skill function names (same as Streamlit env)
      { name = "AWS_DEFAULT_REGION",                     value = var.aws_region },
      { name = "SK01_FUNCTION",                          value = aws_lambda_function.sk01_context_bootstrap.function_name },
      { name = "SK02_FUNCTION",                          value = aws_lambda_function.sk02_wiki_query.function_name },
      { name = "SK03_FUNCTION",                          value = aws_lambda_function.sk03_wiki_contribute.function_name },
      { name = "SK04_FUNCTION",                          value = aws_lambda_function.sk04_artifact_resolution.function_name },
      { name = "SK05_FUNCTION",                          value = aws_lambda_function.sk05_gap_detection.function_name }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.neuro_san.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "neuro-san"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:4173/ > /dev/null || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 90
    }
  }])
}

# ── ALB Target Groups ─────────────────────────────────────────────
resource "aws_lb_target_group" "nsflow" {
  name        = "llmwiki-nsflow-tg"
  port        = 4173
  protocol    = "HTTP"
  vpc_id      = aws_vpc.wiki.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200-399"
  }
}

resource "aws_lb_target_group" "neuro_san_api" {
  name        = "llmwiki-neuro-san-api-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.wiki.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200-404"
  }
}

# ── ALB Listener Rules ────────────────────────────────────────────
# /agents/* → nsflow React UI (port 4173)  — priority 10
resource "aws_lb_listener_rule" "nsflow" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.nsflow.arn
  }

  condition {
    path_pattern {
      values = ["/agents", "/agents/*"]
    }
  }
}

# /api/agents/* → neuro-san HTTP API (port 8080)  — priority 11
resource "aws_lb_listener_rule" "neuro_san_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 11

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.neuro_san_api.arn
  }

  condition {
    path_pattern {
      values = ["/api/agents", "/api/agents/*"]
    }
  }
}

# ── ECS Service ───────────────────────────────────────────────────
# desired_count=0 at creation — start manually for demo sessions to save cost
resource "aws_ecs_service" "neuro_san" {
  name            = "llmwiki-neuro-san"
  cluster         = aws_ecs_cluster.wiki.id
  task_definition = aws_ecs_task_definition.neuro_san.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.neuro_san.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.nsflow.arn
    container_name   = "neuro-san"
    container_port   = 4173
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.neuro_san_api.arn
    container_name   = "neuro-san"
    container_port   = 8080
  }

  depends_on = [
    aws_lb_listener_rule.nsflow,
    aws_lb_listener_rule.neuro_san_api
  ]

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}

# ── Outputs ───────────────────────────────────────────────────────
output "neuro_san_ecr_url" {
  value       = aws_ecr_repository.neuro_san.repository_url
  description = "ECR URL for the neuro-san Docker image"
}

output "nsflow_url" {
  value       = "http://${aws_lb.wiki.dns_name}/agents/"
  description = "nsflow React UI via ALB"
}
