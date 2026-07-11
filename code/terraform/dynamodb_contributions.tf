# ── Contributions audit table ──────────────────────────────────────
# Records every agent write-back for governance and lineage tracking.
resource "aws_dynamodb_table" "contributions" {
  name         = "llmwiki-contributions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "contribution_id"

  attribute {
    name = "contribution_id"
    type = "S"
  }

  attribute {
    name = "agent_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "agent_index"
    hash_key        = "agent_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "customer_index"
    hash_key        = "customer_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}
