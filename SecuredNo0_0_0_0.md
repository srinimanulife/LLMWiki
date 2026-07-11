# LLMWiki — Eliminating 0.0.0.0/0 NACL Rules (Prisma Compliance)

## Background

Prisma Cloud flags AWS Network ACL rules that allow ingress from `0.0.0.0/0` as a high-severity
finding. Today the LLMWiki NACL (`acl-080e051365cf6c3f7`) has four rules with `0.0.0.0/0` added
as a hotfix to restore service. Prisma will auto-remediate (delete) those rules and break the
service again.

The root cause is architectural: the ECS Fargate tasks and the internet-facing ALB share the same
public subnets and the same NACL. Any rule needed for the ALB (inbound port 80 from internet)
applies equally to the ECS tasks, and vice versa. The fix is **subnet separation** — ALB stays in
public subnets, ECS tasks move to private subnets with their own tighter NACL.

Two options provide this separation; both are fully Terraform-managed so the entire stack can be
created and destroyed to control cost.

---

## Current Architecture (Problem State)

```
Internet
   │  port 80 (0.0.0.0/0 — Prisma flags)
   ▼
[ALB]   ──── public subnet us-east-1a  10.0.1.0/24 ────┐
             public subnet us-east-1b  10.0.2.0/24      │  SAME NACL
[ECS Task]  ──── public subnet us-east-1a              ─┘  acl-080e051365cf6c3f7
             assign_public_ip = true
             ECR pull → direct internet via IGW (0.0.0.0/0 — Prisma flags)
```

**NACL rules that Prisma flags (all four will be auto-deleted):**

| Direction | Rule | CIDR | Port | Why Prisma flags |
|-----------|------|------|------|-----------------|
| Inbound  | 90  | `0.0.0.0/0` | 80         | Internet access to subnet |
| Inbound  | 110 | `0.0.0.0/0` | 1024-65535 | Internet access to subnet |
| Outbound | 100 | `0.0.0.0/0` | 443        | Unrestricted egress |
| Outbound | 110 | `0.0.0.0/0` | 1024-65535 | Unrestricted egress |

---

## Option A — NAT Gateway + Private Subnets (Recommended)

### Architecture

```
Internet
   │  port 80 (0.0.0.0/0 — inherent to internet ALB, suppressible)
   ▼
[ALB] ─── public subnets ─── Public NACL (ALB-only rules)
              │  port 8501, scoped to 10.0.0.0/16
              ▼
[ECS Task] ─── private subnets ─── Private NACL (NO 0.0.0.0/0 inbound)
              │  port 443 outbound (ECR, Lambda, Logs, STS)
              ▼
[NAT Gateway] ─── public subnet ─── IGW ─── Internet (ECR, AWS APIs)
```

### NACL Analysis — Option A

**Public NACL** (subnets: `10.0.1.0/24`, `10.0.2.0/24` — ALB only):

| Dir | Rule | CIDR | Port | Flag | Suppression |
|-----|------|------|------|------|-------------|
| In  | 90  | `0.0.0.0/0` | 80         | Prisma flags | Suppress: "internet-facing ALB" |
| In  | 100 | `0.0.0.0/0` | 443        | Prisma flags | Suppress: "internet-facing ALB HTTPS" |
| In  | 110 | `0.0.0.0/0` | 1024-65535 | Prisma flags | Suppress: "ALB ephemeral return traffic" |
| Out | 100 | `10.0.0.0/16` | 8501     | Clean ✓ | — |
| Out | 110 | `0.0.0.0/0` | 1024-65535 | Prisma flags | Suppress: "ALB return to internet clients" |

**Private NACL** (subnets: `10.0.3.0/24`, `10.0.4.0/24` — ECS tasks):

| Dir | Rule | CIDR | Port | Flag |
|-----|------|------|------|------|
| In  | 100 | `10.0.0.0/16` | 8501       | Clean ✓ (from ALB only) |
| In  | 110 | `10.0.0.0/16` | 1024-65535 | Clean ✓ (return from NAT GW private IP) |
| Out | 100 | `0.0.0.0/0`   | 443        | Low risk — egress HTTPS via NAT GW |
| Out | 110 | `10.0.0.0/16` | 1024-65535 | Clean ✓ (return to ALB) |

> **Key insight on return traffic:** When a private subnet task calls ECR via NAT Gateway, the
> response packet arrives from the NAT Gateway's **private IP** (`10.0.1.x`) — not from the
> internet. So inbound NACL rule 110 can be locked to `10.0.0.0/16`. Zero `0.0.0.0/0` inbound
> on the ECS subnet — Prisma's main concern.

**Result:** Private subnet (ECS) has **zero `0.0.0.0/0` inbound** rules.
ALB public subnet flags are suppressed once with business justification. Done.

### Cost — Option A

| Resource | Calculation | Monthly (always-on) | Monthly (8h/day, 20 days) |
|----------|------------|---------------------|--------------------------|
| NAT Gateway | $0.045/hr × 730 | **$32.85** | **$7.20** |
| Elastic IP (attached) | Free | $0 | $0 |
| NAT data processing | $0.045/GB × ~10GB | ~$0.45 | ~$0.10 |
| **Option A add-on total** | | **~$33/month** | **~$7/month** |

Existing stack (ALB ~$18, ECS ~$18, Lambda/DDB/S3 ~$5):
- **Running total with Option A: ~$74/month**
- **`terraform destroy` total: ~$0/month** (only tfstate S3 bucket pennies)

---

## Option B — VPC Interface Endpoints + Private Subnets (Strictest Compliance)

### Architecture

```
Internet
   │  port 80 (0.0.0.0/0 — inherent to internet ALB, suppressible)
   ▼
[ALB] ─── public subnets ─── Public NACL (ALB-only rules)
              │  port 8501, scoped to 10.0.0.0/16
              ▼
[ECS Task] ─── private subnets ─── Private NACL (ZERO 0.0.0.0/0 rules)
              │  port 443 to 10.0.0.0/16 only
              ▼
[VPC Interface Endpoints] — ecr.api, ecr.dkr, logs, sts, lambda
[VPC Gateway Endpoints]   — s3 (free), dynamodb (free)
   All AWS API calls stay entirely within the VPC — no internet path
```

### NACL Analysis — Option B

**Public NACL** — identical to Option A (ALB, suppressible with same justification).

**Private NACL** (subnets: `10.0.3.0/24`, `10.0.4.0/24` — ECS tasks):

| Dir | Rule | CIDR | Port | Flag |
|-----|------|------|------|------|
| In  | 100 | `10.0.0.0/16` | 8501       | Clean ✓ |
| In  | 110 | `10.0.0.0/16` | 1024-65535 | Clean ✓ |
| Out | 100 | `10.0.0.0/16` | 443        | Clean ✓ (VPC endpoint ENI IPs) |
| Out | 110 | `10.0.0.0/16` | 1024-65535 | Clean ✓ |

> **ZERO `0.0.0.0/0` rules on private subnet — inbound AND outbound.**
> All AWS service calls (ECR, Lambda, CloudWatch Logs, STS) resolve via private DNS to endpoint
> ENI IPs within `10.0.0.0/16`. S3/DynamoDB use Gateway Endpoints (free, route via prefix list).

**ECS Task Security Group** — also cleanable in Option B:

```hcl
# Option B: tighten egress to VPC CIDR only — no 0.0.0.0/0 on SG either
egress {
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = ["10.0.0.0/16"]   # VPC endpoint ENIs only
}
```

### Cost — Option B

| Resource | Calculation | Monthly (always-on) | Monthly (8h/day, 20 days) |
|----------|------------|---------------------|--------------------------|
| ecr.api endpoint (2 AZs) | 2 × $0.01/hr × 730 | $14.60 | $3.20 |
| ecr.dkr endpoint (2 AZs) | 2 × $0.01/hr × 730 | $14.60 | $3.20 |
| logs endpoint (2 AZs) | 2 × $0.01/hr × 730 | $14.60 | $3.20 |
| sts endpoint (2 AZs) | 2 × $0.01/hr × 730 | $14.60 | $3.20 |
| lambda endpoint (2 AZs) | 2 × $0.01/hr × 730 | $14.60 | $3.20 |
| s3 gateway endpoint | Free | $0 | $0 |
| dynamodb gateway endpoint | Free | $0 | $0 |
| **Option B add-on total** | | **~$73/month** | **~$16/month** |

- **Running total with Option B: ~$114/month**
- **`terraform destroy` total: ~$0/month**

> **Single-AZ dev shortcut:** Deploy endpoints in 1 AZ only (accept AZ-failure risk for dev).
> Cost drops to ~$36.50/month always-on, ~$8/month part-time.

---

## Comparison Table

| Criteria | Current (broken) | Option A — NAT GW | Option B — VPC Endpoints |
|----------|-----------------|-------------------|--------------------------|
| Private NACL inbound `0.0.0.0/0` | Yes (Prisma deletes) | **None ✓** | **None ✓** |
| Private NACL egress `0.0.0.0/0` | Yes | Port 443 only | **None ✓** |
| ECS task SG `0.0.0.0/0` egress | Yes | Port 443 only | **None ✓** |
| Public NACL `0.0.0.0/0` | Yes | Suppressible | Suppressible |
| Always-on add-on cost | $0 | **~$33/month** | ~$73/month |
| Part-time (8h/20d) add-on | $0 | **~$7/month** | ~$16/month |
| `terraform destroy` cost | $0 | **$0** | **$0** |
| Complexity | Low | **Low** | Medium |
| Prisma pass rate (private subnet) | Fail | **~95%** | **100%** |

**Recommendation: Option A for this sandbox.** The only remaining Prisma flags on the private
subnet are egress-only (outbound port 443), which most Prisma policies don't flag or allow
suppression with a one-line justification. Option B costs 2.2× more for marginal compliance gain
in a dev environment.

---

## Terraform Implementation

The changes below are structured as **additions to the existing** `code/terraform/ecs_streamlit.tf`
and a **new** `code/terraform/vpc_endpoints.tf` (Option B only).

---

### Option A Terraform — `ecs_streamlit.tf` additions/changes

Paste these blocks into `ecs_streamlit.tf`, then modify the two existing resources marked below.

```hcl
# ── Private Subnets ───────────────────────────────────────────────
resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.wiki.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = { Name = "llmwiki-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.wiki.id
  cidr_block        = "10.0.4.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags              = { Name = "llmwiki-private-b" }
}

# ── NAT Gateway ───────────────────────────────────────────────────
resource "aws_eip" "nat" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.wiki]
  tags       = { Name = "llmwiki-nat-eip" }
}

resource "aws_nat_gateway" "wiki" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_a.id   # NAT GW must live in a public subnet
  tags          = { Name = "llmwiki-nat-gw" }
  depends_on    = [aws_internet_gateway.wiki]
}

# ── Private Route Table ───────────────────────────────────────────
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.wiki.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.wiki.id
  }
  tags = { Name = "llmwiki-private-rt" }
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}

# ── Public NACL (ALB subnets) ─────────────────────────────────────
# Prisma suppression justification: "internet-facing Application Load Balancer"
resource "aws_network_acl" "public" {
  vpc_id     = aws_vpc.wiki.id
  subnet_ids = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  ingress {
    rule_no    = 90
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 80
    to_port    = 80
  }
  ingress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 443
    to_port    = 443
  }
  ingress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }

  egress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 8501
    to_port    = 8501
  }
  egress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }

  tags = { Name = "llmwiki-public-nacl" }
}

# ── Private NACL (ECS task subnets) — zero 0.0.0.0/0 inbound ────
resource "aws_network_acl" "private" {
  vpc_id     = aws_vpc.wiki.id
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  # Inbound: only from ALB (8501) and return from NAT GW private IP
  ingress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 8501
    to_port    = 8501
  }
  ingress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"   # NAT GW returns via its private IP
    from_port  = 1024
    to_port    = 65535
  }

  # Outbound: HTTPS to ECR/AWS via NAT GW, return to ALB
  egress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "0.0.0.0/0"    # packets destined for ECR public IP via NAT
    from_port  = 443
    to_port    = 443
  }
  egress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 1024
    to_port    = 65535
  }

  tags = { Name = "llmwiki-private-nacl" }
}
```

**MODIFY** the existing `aws_security_group "streamlit"` — tighten egress:

```hcl
# Replace the existing catch-all egress in aws_security_group "streamlit"
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

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]   # HTTPS to ECR/Lambda/Logs via NAT GW
    description = "HTTPS to AWS services via NAT Gateway"
  }

  tags = { Name = "llmwiki-streamlit-sg" }
}
```

**MODIFY** the existing `aws_ecs_service "streamlit"` — move to private subnets:

```hcl
resource "aws_ecs_service" "streamlit" {
  name            = "llmwiki-streamlit"
  cluster         = aws_ecs_cluster.wiki.id
  task_definition = aws_ecs_task_definition.streamlit.arn
  desired_count   = var.streamlit_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]  # CHANGED
    security_groups  = [aws_security_group.streamlit.id]
    assign_public_ip = false   # CHANGED — private subnet, NAT GW provides egress
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.streamlit.arn
    container_name   = "streamlit"
    container_port   = var.streamlit_port
  }

  depends_on = [aws_lb_listener.http, aws_nat_gateway.wiki]

  lifecycle {
    ignore_changes = [desired_count]
  }
}
```

---

### Option B Terraform — new `vpc_endpoints.tf`

Create `code/terraform/vpc_endpoints.tf` as a new file:

```hcl
# ── Security Group for VPC Interface Endpoints ────────────────────
resource "aws_security_group" "vpc_endpoints" {
  name        = "llmwiki-endpoints-sg"
  description = "HTTPS from ECS tasks to VPC interface endpoints"
  vpc_id      = aws_vpc.wiki.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.streamlit.id]
    description     = "HTTPS from Streamlit tasks"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.wiki.cidr_block]
  }

  tags = { Name = "llmwiki-endpoints-sg" }
}

# ── Interface Endpoints (ECR, Logs, STS, Lambda) ──────────────────
locals {
  interface_endpoints = toset([
    "ecr.api",
    "ecr.dkr",
    "logs",
    "sts",
    "lambda",
  ])
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.wiki.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true   # tasks use standard DNS names, endpoint resolves to private IP

  tags = { Name = "llmwiki-endpoint-${each.value}" }
}

# ── Gateway Endpoints (free — S3 image layers, DynamoDB) ─────────
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.wiki.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]
  tags              = { Name = "llmwiki-endpoint-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.wiki.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]
  tags              = { Name = "llmwiki-endpoint-dynamodb" }
}
```

**Option B also needs these changes in `ecs_streamlit.tf`:**

1. Add the same private subnets (`private_a`, `private_b`) as Option A.
2. Add a **private route table with NO default route** (no NAT GW):

```hcl
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.wiki.id
  # No 0.0.0.0/0 — all AWS calls go via endpoints; S3/DDB gateway endpoints
  # add their own prefix-list routes automatically
  tags = { Name = "llmwiki-private-rt" }
}
```

3. Update ECS service to private subnets with `assign_public_ip = false` (same as Option A).

4. **Tighten ECS security group egress to VPC CIDR only** (Option B exclusive):

```hcl
egress {
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = [aws_vpc.wiki.cidr_block]   # 10.0.0.0/16 — VPC endpoints only
  description = "HTTPS to AWS services via VPC Interface Endpoints"
}
```

5. Update private NACL — completely clean, no `0.0.0.0/0` anywhere:

```hcl
resource "aws_network_acl" "private" {
  vpc_id     = aws_vpc.wiki.id
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  ingress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 8501
    to_port    = 8501
  }
  ingress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 1024
    to_port    = 65535
  }

  egress {
    rule_no    = 100
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"   # VPC endpoint ENI IPs
    from_port  = 443
    to_port    = 443
  }
  egress {
    rule_no    = 110
    protocol   = "tcp"
    action     = "allow"
    cidr_block = "10.0.0.0/16"
    from_port  = 1024
    to_port    = 65535
  }

  tags = { Name = "llmwiki-private-nacl" }
}
```

---

## Deploy / Destroy Workflow

### One-time: manual NACL cleanup after first Terraform apply

After `terraform apply`, Terraform creates new NACLs and reassociates the subnets away from the
manually-edited `acl-080e051365cf6c3f7`. Run this once to clean up the leftover manual rules:

```bash
# Verify subnets are no longer on the old NACL
aws --profile tzg-sandbox ec2 describe-network-acls \
  --network-acl-ids acl-080e051365cf6c3f7 \
  --query 'NetworkAcls[0].Associations'

# Remove the manual rules we added today (now superseded)
for rule in 90 100 110; do
  aws --profile tzg-sandbox ec2 delete-network-acl-entry \
    --network-acl-id acl-080e051365cf6c3f7 --rule-number $rule --ingress
done
for rule in 100 110; do
  aws --profile tzg-sandbox ec2 delete-network-acl-entry \
    --network-acl-id acl-080e051365cf6c3f7 --rule-number $rule --egress
done
```

### Daily workflow — stop tasks to save Fargate cost, keep infrastructure

```bash
# Pause ECS (saves ~$18/month in Fargate compute, ALB still runs at ~$18/month)
cd code/terraform
terraform apply -var="streamlit_desired_count=0" -auto-approve

# Resume
terraform apply -var="streamlit_desired_count=1" -auto-approve
```

### Full destroy — save everything (~$0/month)

```bash
cd code/terraform

# Scale down first (avoids destroy dependency errors on ECS service)
terraform apply -var="streamlit_desired_count=0" -auto-approve

# Full destroy
terraform destroy -auto-approve
```

> **Note on ECR images:** `terraform destroy` deletes the ECR repository and all images.
> After `terraform apply` to recreate, you must push the image again:
> ```bash
> aws ecr get-login-password --region us-east-1 --profile tzg-sandbox \
>   | docker login --username AWS --password-stdin \
>     392568849512.dkr.ecr.us-east-1.amazonaws.com
> docker push 392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-streamlit:latest
> ```

### Terraform state and locking (survive destroy/recreate)

The tfstate S3 bucket (`llmwiki-tfstate-392568849512`) and DynamoDB lock table
(`llmwiki-tfstate-lock`) are **not managed by Terraform** and survive `terraform destroy`.
They cost ~$0.02/month. Do not delete them.

---

## Prisma Suppression Guide — ALB Public Subnet Rules

The four `0.0.0.0/0` rules on the public subnet NACL are architecturally unavoidable for any
internet-facing ALB. Suppress them in Prisma once using this justification template:

| Prisma Finding | Suppression Reason |
|---------------|-------------------|
| NACL allows ingress `0.0.0.0/0` port 80 | Internet-facing ALB — HTTP ingress required. Traffic forward-proxied to private subnet ECS tasks on port 8501 (VPC-only). |
| NACL allows ingress `0.0.0.0/0` port 443 | Internet-facing ALB — HTTPS ingress required. Same scope as port 80. |
| NACL allows ingress `0.0.0.0/0` 1024-65535 | ALB stateless NACL requires explicit ephemeral port rule for TCP return traffic to internet clients. |
| NACL allows egress `0.0.0.0/0` 1024-65535 | ALB must return responses to internet clients on ephemeral ports. Destination is always the initiating client. |

Scope suppressions to: resource tag `Application = LLMWiki`, account `392568849512`, region `us-east-1`.

---

## Summary

| | Option A (NAT GW) | Option B (VPC Endpoints) |
|--|---|---|
| **Implement** | Add to `ecs_streamlit.tf` only | Add to `ecs_streamlit.tf` + new `vpc_endpoints.tf` |
| **Private subnet clean?** | Inbound: ✓ | Inbound + Outbound + SG: ✓ |
| **Always-on add-on** | ~$33/month | ~$73/month |
| **Part-time add-on** | ~$7/month | ~$16/month |
| **terraform destroy** | $0 | $0 |
| **When to choose** | Dev sandbox, cost priority | Pre-prod/prod, strictest Prisma |
