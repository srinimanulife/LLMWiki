# ── Governance SSM parameters ──────────────────────────────────────
resource "aws_ssm_parameter" "cache_ttl" {
  name  = "/llmwiki/governance/cache_ttl_seconds"
  type  = "String"
  value = "86400"
}

resource "aws_ssm_parameter" "cache_sim_threshold" {
  name  = "/llmwiki/governance/cache_sim_threshold"
  type  = "String"
  value = "0.92"
}

resource "aws_ssm_parameter" "cache_semantic_enabled" {
  name  = "/llmwiki/governance/cache_semantic_enabled"
  type  = "String"
  value = "true"
}

resource "aws_ssm_parameter" "rate_limit_per_minute" {
  name  = "/llmwiki/governance/rate_limit_per_minute"
  type  = "String"
  value = "30"
}

resource "aws_ssm_parameter" "daily_budget_default" {
  name  = "/llmwiki/governance/daily_budget_usd_default"
  type  = "String"
  value = "5.0"
}

resource "aws_ssm_parameter" "daily_budget_ingest" {
  name  = "/llmwiki/governance/daily_budget_usd_ingest"
  type  = "String"
  value = "20.0"
}
