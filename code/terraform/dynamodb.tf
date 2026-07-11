# ── Wiki index table ──────────────────────────────────────────────
resource "aws_dynamodb_table" "wiki_index" {
  name         = "llmwiki-index"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "page_type"
  range_key    = "page_slug"

  attribute {
    name = "page_type"
    type = "S"
  }

  attribute {
    name = "page_slug"
    type = "S"
  }

  attribute {
    name = "last_updated"
    type = "S"
  }

  global_secondary_index {
    name            = "last_updated_index"
    hash_key        = "page_type"
    range_key       = "last_updated"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ── Operation log table ───────────────────────────────────────────
resource "aws_dynamodb_table" "wiki_log" {
  name         = "llmwiki-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "log_date"
  range_key    = "timestamp_id"

  attribute {
    name = "log_date"
    type = "S"
  }

  attribute {
    name = "timestamp_id"
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

# ── Knowledge Gaps table ──────────────────────────────────────────
# Populated by Query Lambda when KB confidence is low/medium.
# Business users can see the wiki learning in real-time via Expansion Lab.
resource "aws_dynamodb_table" "gaps" {
  name         = "llmwiki-gaps"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "gap_id"

  attribute {
    name = "gap_id"
    type = "S"
  }

  attribute {
    name = "gap_slug"
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
    name            = "slug_index"
    hash_key        = "gap_slug"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "status_index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}

# ── Source registry table ─────────────────────────────────────────
resource "aws_dynamodb_table" "source_registry" {
  name         = "llmwiki-source-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "source_id"

  attribute {
    name = "source_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "ingested_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status_index"
    hash_key        = "status"
    range_key       = "ingested_at"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}
