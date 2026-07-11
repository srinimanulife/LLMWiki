"""
Gatekeeper Lambda — validates prerequisites before the UC1 hard harness starts.

Checks:
  1. customer_id is present in the request.
  2. No active harness run (status=running|paused) already exists for this customer.

Returns a structured response the UI renders as the opening conversational message.
Bedrock Claude generates the greeting; a hardcoded fallback is used if that call fails.
"""

import json
import os
import time
import boto3
from decimal import Decimal
from datetime import datetime, timezone

# ── AWS clients ──────────────────────────────────────────────────────────────
_region = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=_region)
bedrock  = boto3.client("bedrock-runtime", region_name=_region)

HARNESS_RUNS_TABLE = os.environ.get("HARNESS_RUNS_TABLE", "llmwiki-harness-runs")
MODEL_ID           = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Phase manifest — returned verbatim to the UI so it can render the workflow map.
PHASES = [
    {"num": 1, "name": "SOW Intake & Extraction",   "type": "programmatic",    "skill": None},
    {"num": 2, "name": "Customer Classification",   "type": "llm_single",      "skill": None},
    {"num": 3, "name": "Gather Handoff Context",    "type": "llm_human_input", "skill": None},
    {"num": 4, "name": "Load Delivery Playbook",    "type": "llm_agent",       "skill": "SK-01"},
    {"num": 5, "name": "Risk & Gap Analysis",       "type": "llm_agent",       "skill": "SK-02"},
    {"num": 6, "name": "Gap Detection & Recording", "type": "llm_batch_agents","skill": "SK-05"},
    {"num": 7, "name": "Template Population",       "type": "llm_agent",       "skill": "SK-04"},
    {"num": 8, "name": "Write Handoff + Report",    "type": "llm_single",      "skill": "SK-03"},
]

_FALLBACK_MESSAGE = (
    "Welcome! You're about to begin the UC1 Sales-to-Service handoff workflow. "
    "This is a HIGH-risk healthcare engagement covering 8 structured phases — "
    "from SOW intake through final handoff report. "
    "All phases are system-enforced and logged. Ready to start? Please confirm."
)


# ── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    # Support both direct invoke and API Gateway body wrapper
    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    customer_id   = (body.get("customer_id")   or "").strip()
    customer_name = (body.get("customer_name")  or "").strip()
    product       = (body.get("product")        or "").strip()
    sow_reference = (body.get("sow_reference")  or "").strip()
    agent_id      = (body.get("agent_id")       or "gatekeeper").strip()

    # ── Check 1: customer_id required ────────────────────────────────────────
    if not customer_id:
        return _ok({
            "ready": False,
            "message": "Please provide a customer ID to begin.",
        })

    # ── Check 2: no active run already exists ────────────────────────────────
    active = _find_active_run(customer_id)
    if active:
        run_id = active.get("run_id", "unknown")
        status = active.get("status", "running")
        return _ok({
            "ready":          False,
            "resume":         True,
            "active_run_id":  run_id,
            "active_status":  status,
            "active_run":     _serialize(active),
            "message": (
                f"An active harness run already exists for {customer_id}. "
                f"Run ID: {run_id}. Use the existing run or reset it."
            ),
        })

    # ── Generate greeting via Bedrock Claude ─────────────────────────────────
    message = _generate_greeting(customer_name, product, sow_reference)

    return _ok({
        "ready":         True,
        "customer_id":   customer_id,
        "customer_name": customer_name,
        "product":       product,
        "sow_reference": sow_reference,
        "message":       message,
        "phases":        PHASES,
    })


# ── DynamoDB helpers ─────────────────────────────────────────────────────────

def _find_active_run(customer_id: str) -> dict | None:
    """
    Query llmwiki-harness-runs for any run with status in {running, paused}.
    The table uses engagement_id (hash) + run_id (range), so we do a Query
    then filter client-side — DynamoDB does not support filter on range key alone.
    """
    try:
        table = dynamodb.Table(HARNESS_RUNS_TABLE)
        resp  = table.query(
            KeyConditionExpression="engagement_id = :eid",
            FilterExpression="#s IN (:r, :p)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":eid": customer_id,
                ":r":   "running",
                ":p":   "paused",
            },
        )
        items = resp.get("Items", [])
        if items:
            # Return the most recently started run
            return sorted(items, key=lambda x: x.get("started_at", ""), reverse=True)[0]
        return None
    except Exception as e:
        print(f"WARN: DynamoDB query failed in gatekeeper (non-fatal): {e}")
        return None


# ── Bedrock greeting ─────────────────────────────────────────────────────────

def _generate_greeting(customer_name: str, product: str, sow_reference: str) -> str:
    """
    Ask Claude to write a concise (<100 word) friendly opener for the workflow.
    Falls back to _FALLBACK_MESSAGE if the Bedrock call fails for any reason.
    """
    name_part = customer_name or "the customer"
    prod_part = product       or "the configured product"
    sow_part  = sow_reference or "the referenced SOW"

    prompt = (
        f"Write a friendly, professional 2–3 sentence opening message (under 100 words) "
        f"for a Sales-to-Service agent workflow. "
        f"Customer: {name_part}. Product: {prod_part}. SOW reference: {sow_part}. "
        f"Mention this is a HIGH-risk healthcare engagement, briefly note the 8-phase "
        f"workflow the agent will now execute, and end by asking for confirmation to proceed. "
        f"Use a warm but precise tone. No bullet points."
    )

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 200},
        }
        resp = bedrock.converse(**_converse_kwargs)
        text = resp["output"]["message"]["content"][0]["text"].strip()
        return text if text else _FALLBACK_MESSAGE
    except Exception as e:
        print(f"WARN: Bedrock greeting generation failed, using fallback: {e}")
        return _FALLBACK_MESSAGE


# ── Response helper ───────────────────────────────────────────────────────────

def _serialize(obj):
    """Recursively convert Decimal → int/float so json.dumps works."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def _ok(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
