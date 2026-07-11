# ── Harness Runs table ────────────────────────────────────────────
# Tracks every test-harness execution: one item per (engagement, run).
# status_index        — query all runs by status (e.g. "running", "done")
# engagement_status_index — query all runs for an engagement filtered by status

resource "aws_dynamodb_table" "harness_runs" {
  name         = "llmwiki-harness-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "engagement_id"
  range_key    = "run_id"

  attribute {
    name = "engagement_id"
    type = "S"
  }

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "started_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status_index"
    hash_key        = "status"
    range_key       = "started_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "engagement_status_index"
    hash_key        = "engagement_id"
    range_key       = "status"
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

# ── Workspace Files table ─────────────────────────────────────────
# Stores per-phase intermediate files generated during a harness run.
# phase_index — query all files produced by a given phase within an engagement.

resource "aws_dynamodb_table" "workspace_files" {
  name         = "llmwiki-workspace-files"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "engagement_id"
  range_key    = "file_path"

  attribute {
    name = "engagement_id"
    type = "S"
  }

  attribute {
    name = "file_path"
    type = "S"
  }

  attribute {
    name = "phase_num"
    type = "N"
  }

  global_secondary_index {
    name            = "phase_index"
    hash_key        = "engagement_id"
    range_key       = "phase_num"
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
