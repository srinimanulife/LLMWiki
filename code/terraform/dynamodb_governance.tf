# ── Governance: Usage / Cost tracking ────────────────────────────
resource "aws_dynamodb_table" "usage" {
  name         = "llmwiki-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute {
    name = "request_id"
    type = "S"
  }
  attribute {
    name = "date"
    type = "S"
  }
  attribute {
    name = "caller"
    type = "S"
  }

  global_secondary_index {
    name            = "date_caller_index"
    hash_key        = "date"
    range_key       = "caller"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ── Governance: Semantic cache ─────────────────────────────────────
resource "aws_dynamodb_table" "cache" {
  name         = "llmwiki-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "cache_key"

  attribute {
    name = "cache_key"
    type = "S"
  }
  attribute {
    name = "cache_domain"
    type = "S"
  }
  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "domain_recency_index"
    hash_key        = "cache_domain"
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
}

# ── Governance: Rate limiting ──────────────────────────────────────
resource "aws_dynamodb_table" "rate_limits" {
  name         = "llmwiki-rate-limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "window_key"

  attribute {
    name = "window_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}
