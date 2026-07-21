"""
Shared config for all Phoenix eval steps.
Override any value with environment variables.
"""
import os

PHOENIX_ENDPOINT   = os.environ.get("PHOENIX_ENDPOINT",   "http://localhost:6006")
PHOENIX_GRPC_PORT  = os.environ.get("PHOENIX_GRPC_PORT",  "4317")
PHOENIX_COLLECTOR  = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT",
                                    f"http://localhost:{PHOENIX_GRPC_PORT}")

# Phoenix project names — keep Lambda and Neuro SAN traces separate
PROJECT_LAMBDA     = os.environ.get("PHOENIX_PROJECT_LAMBDA",    "llmwiki-query")
PROJECT_NEURO      = os.environ.get("PHOENIX_PROJECT_NEURO_SAN", "neuro-san-agents")

# AWS
AWS_PROFILE        = os.environ.get("AWS_PROFILE",   "tzg-sandbox")
AWS_REGION         = os.environ.get("AWS_REGION",    "us-east-1")
BEDROCK_MODEL_ID   = os.environ.get("BEDROCK_MODEL_ID",
                                    "us.anthropic.claude-sonnet-4-6")
NOVA_PRO_MODEL_ID  = os.environ.get("NOVA_PRO_MODEL_ID",
                                    "us.amazon.nova-pro-v1:0")
LAMBDA_NAME        = os.environ.get("LAMBDA_NAME",   "llmwiki-query")

# Faithfulness threshold for CI gate
FAITHFULNESS_THRESHOLD = float(os.environ.get("FAITHFULNESS_THRESHOLD", "0.70"))
