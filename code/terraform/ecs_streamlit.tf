# ── VPC (minimal — public subnets for demo) ───────────────────────
resource "aws_vpc" "wiki" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "llmwiki-vpc" }
}

resource "aws_internet_gateway" "wiki" {
  vpc_id = aws_vpc.wiki.id
  tags   = { Name = "llmwiki-igw" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.wiki.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "llmwiki-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.wiki.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true
  tags                    = { Name = "llmwiki-public-b" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.wiki.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.wiki.id
  }
  tags = { Name = "llmwiki-public-rt" }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# ── Security Groups ───────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name        = "llmwiki-alb-sg"
  description = "Allow HTTP/HTTPS to ALB"
  vpc_id      = aws_vpc.wiki.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "llmwiki-alb-sg" }
}

resource "aws_security_group" "streamlit" {
  name        = "llmwiki-streamlit-sg"
  description = "Allow traffic from ALB to Streamlit"
  vpc_id      = aws_vpc.wiki.id

  ingress {
    from_port       = var.streamlit_port
    to_port         = var.streamlit_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # neuro-san HTTP API + WebSocket
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # nsflow React UI
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

  tags = { Name = "llmwiki-streamlit-sg" }
}

# ── ECR Repository ────────────────────────────────────────────────
resource "aws_ecr_repository" "streamlit" {
  name                 = "llmwiki-streamlit"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "streamlit" {
  repository = aws_ecr_repository.streamlit.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# ── ECS Cluster ───────────────────────────────────────────────────
resource "aws_ecs_cluster" "wiki" {
  name = "llmwiki-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "streamlit" {
  name              = "/ecs/llmwiki-streamlit"
  retention_in_days = 7
}

# ── ECS Task Definition ───────────────────────────────────────────
# Includes neuro-san as a non-essential sidecar (can be disabled by setting image tag to "disabled")
resource "aws_ecs_task_definition" "streamlit" {
  family                   = "llmwiki-streamlit"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  # Bumped to 2 vCPU / 4 GB to accommodate both Streamlit + neuro-san sidecar
  cpu                      = "2048"
  memory                   = "4096"
  task_role_arn            = aws_iam_role.streamlit_task.arn
  execution_role_arn       = aws_iam_role.streamlit_execution.arn

  container_definitions = jsonencode([
    {
      name      = "streamlit"
      image     = "${aws_ecr_repository.streamlit.repository_url}:latest"
      essential = true

      portMappings = [{
        containerPort = var.streamlit_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "WIKI_BUCKET",              value = aws_s3_bucket.wiki.id },
        { name = "QUERY_LAMBDA",             value = aws_lambda_function.query.function_name },
        { name = "CONVERTER_LAMBDA",         value = aws_lambda_function.converter.function_name },
        { name = "BUSINESS_QUERY_LAMBDA",    value = aws_lambda_function.business_query.function_name },
        { name = "CONTRIBUTE_LAMBDA",        value = aws_lambda_function.contribute.function_name },
        { name = "PLAYBOOK_LAMBDA",          value = aws_lambda_function.playbook.function_name },
        { name = "DYNAMODB_INDEX",           value = aws_dynamodb_table.wiki_index.name },
        { name = "DYNAMODB_LOG",             value = aws_dynamodb_table.wiki_log.name },
        { name = "GAPS_TABLE",               value = aws_dynamodb_table.gaps.name },
        { name = "REGISTRY_TABLE",           value = aws_dynamodb_table.source_registry.name },
        { name = "CONTRIB_TABLE",            value = aws_dynamodb_table.contributions.name },
        { name = "AWS_DEFAULT_REGION",       value = var.aws_region },
        { name = "API_GATEWAY_URL",          value = "https://${aws_api_gateway_rest_api.wiki.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.dev.stage_name}" },
        { name = "GATEKEEPER_FUNCTION",      value = aws_lambda_function.gatekeeper.function_name },
        { name = "UC1_HARNESS_FUNCTION",     value = aws_lambda_function.uc1_harness.function_name },
        { name = "PM_HARNESS_FUNCTION",      value = aws_lambda_function.pm_harness.function_name },
        { name = "SK06_FUNCTION",            value = aws_lambda_function.skill_problem_classifier.function_name },
        { name = "PM_WIKI_BUCKET",           value = aws_s3_bucket.pm.id },
        { name = "USAGE_TABLE",              value = aws_dynamodb_table.usage.name },
        { name = "CACHE_TABLE",               value = aws_dynamodb_table.cache.name },
        { name = "RATE_TABLE",               value = aws_dynamodb_table.rate_limits.name }
        # nsflow sidecar is reached on localhost:4173 (same ECS task) — no env var needed
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.streamlit.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "streamlit"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.streamlit_port}/_stcore/health || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
      }
    },
    {
      # Neuro SAN sidecar: neuro-san-server (8080) + nsflow UI (4173)
      # Non-essential: Streamlit continues running if this container fails
      name      = "neuro-san"
      image     = "${aws_ecr_repository.streamlit.repository_url}:neuro-san-latest"
      essential = false

      portMappings = [
        { containerPort = 8080, protocol = "tcp" },
        { containerPort = 4173, protocol = "tcp" }
      ]

      environment = [
        { name = "AGENT_MANIFEST_FILE",                   value = "registries/llmwiki/manifest.hocon" },
        { name = "AGENT_TOOL_PATH",                       value = "/app/coded_tools" },
        { name = "AGENT_MANIFEST_UPDATE_PERIOD_SECONDS",  value = "5" },
        { name = "WIKI_BUCKET",                           value = aws_s3_bucket.wiki.id },
        { name = "NEURO_SAN_SERVER_HOST",                 value = "localhost" },
        { name = "NEURO_SAN_SERVER_HTTP_PORT",            value = "8080" },
        { name = "NEURO_SAN_SERVER_CONNECTION",           value = "http" },
        { name = "DEFAULT_SLY_DATA",                      value = "{\"engagement_id\":\"demo\"}" },
        { name = "AWS_DEFAULT_REGION",                    value = var.aws_region },
        { name = "SK01_FUNCTION",                         value = aws_lambda_function.sk01_context_bootstrap.function_name },
        { name = "SK02_FUNCTION",                         value = aws_lambda_function.sk02_wiki_query.function_name },
        { name = "SK03_FUNCTION",                         value = aws_lambda_function.sk03_wiki_contribute.function_name },
        { name = "SK04_FUNCTION",                         value = aws_lambda_function.sk04_artifact_resolution.function_name },
        { name = "SK05_FUNCTION",                         value = aws_lambda_function.sk05_gap_detection.function_name }
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
    }
  ])
}

# ── ALB ───────────────────────────────────────────────────────────
resource "aws_lb" "wiki" {
  name               = "llmwiki-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  enable_deletion_protection = false
}

resource "aws_lb_target_group" "streamlit" {
  name        = "llmwiki-streamlit-tg"
  port        = var.streamlit_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.wiki.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/_stcore/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.wiki.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.streamlit.arn
  }
}

# ── ECS Service ───────────────────────────────────────────────────
resource "aws_ecs_service" "streamlit" {
  name            = "llmwiki-streamlit"
  cluster         = aws_ecs_cluster.wiki.id
  task_definition = aws_ecs_task_definition.streamlit.arn
  desired_count   = var.streamlit_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.streamlit.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.streamlit.arn
    container_name   = "streamlit"
    container_port   = var.streamlit_port
  }

  # neuro-san sidecar load balancers — already provisioned via AWS CLI
  # These reference target groups created outside Terraform (to avoid recreating the service)
  load_balancer {
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:392568849512:targetgroup/llmwiki-nsflow-tg/381cad09f7da7684"
    container_name   = "neuro-san"
    container_port   = 4173
  }

  load_balancer {
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:392568849512:targetgroup/llmwiki-neuro-san-api-tg/f540831737ded9a2"
    container_name   = "neuro-san"
    container_port   = 8080
  }

  depends_on = [aws_lb_listener.http]

  lifecycle {
    ignore_changes = [desired_count, load_balancer]
  }
}
