"""
SK-03 · Knowledge Recorder (WikiContributeSkill)
Saves agent-generated knowledge back to the wiki. Adds human-review routing,
invocation audit, and standard skill contract wrapping around the Contribute Lambda.
Standard skill contract: {skill, version, inputs} → {skill, status, outputs, latency_ms}
"""

import json
import os
import time
import boto3
from datetime import datetime, timezone

lambda_client = boto3.client("lambda",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb      = boto3.resource("dynamodb",
                                region_name=os.environ.get("AWS_REGION", "us-east-1"))

CONTRIBUTE_FUNCTION = os.environ.get("CONTRIBUTE_FUNCTION", "llmwiki-contribute")
LOG_TABLE           = os.environ.get("LOG_TABLE", "llmwiki-log")
SKILL_ID            = "SK-03"
SKILL_NAME          = "WikiContributeSkill"
BUSINESS_NAME       = "Knowledge Recorder"

# Page types that always require human review
HIGH_RISK_PAGE_TYPES = {"decisions", "evidence"}


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs       = body.get("inputs", body)
    page_type    = inputs.get("page_type", "").strip()
    page_slug    = inputs.get("page_slug", "").strip()
    content      = inputs.get("content", "").strip()
    agent_id     = inputs.get("agent_id", body.get("invoked_by", "unknown-agent"))
    customer_id  = inputs.get("customer_id", "")
    use_case     = inputs.get("use_case", "")
    human_review = inputs.get("human_review_required", False)
    version      = body.get("version", "1.0")
    invoked_by   = body.get("invoked_by", agent_id)

    if not page_type or not page_slug or not content:
        return _respond(400, {"error": "inputs.page_type, page_slug, and content are required"})

    # Auto-escalate high-risk page types
    if page_type in HIGH_RISK_PAGE_TYPES:
        human_review = True

    contribute_payload = json.dumps({
        "page_type":             page_type,
        "page_slug":             page_slug,
        "content":               content,
        "agent_id":              agent_id,
        "customer_id":           customer_id,
        "use_case":              use_case,
        "human_review_required": human_review,
    })

    result = {}
    try:
        resp = lambda_client.invoke(
            FunctionName=CONTRIBUTE_FUNCTION,
            InvocationType="RequestResponse",
            Payload=contribute_payload.encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            inner = raw["body"]
            result = json.loads(inner) if isinstance(inner, str) else (inner or {})
        else:
            result = raw
    except Exception as e:
        print(f"ERROR: contribute invoke failed: {e}")
        latency_ms = int((time.time() - t0) * 1000)
        _log_telemetry(invoked_by, customer_id, use_case, page_type, page_slug,
                       latency_ms, "error")
        return _skill_response(version, "error",
                               {"error": str(e), "page_slug": page_slug},
                               latency_ms)

    latency_ms = int((time.time() - t0) * 1000)
    result["human_review_required"] = human_review
    result["_skill_note"] = (
        "Routed to pending/ for human review — high-risk page type"
        if human_review else "Indexed immediately and KB sync triggered"
    )

    _log_telemetry(invoked_by, customer_id, use_case, page_type, page_slug,
                   latency_ms, result.get("status", "indexed"))

    return _skill_response(version, "success", result, latency_ms)


def _log_telemetry(agent_id, customer_id, use_case, page_type, page_slug,
                   latency_ms, status):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":     now[:10],
            "timestamp_id": f"{now}#{SKILL_ID}",
            "skill_id":     SKILL_ID,
            "skill_name":   SKILL_NAME,
            "agent_id":     agent_id,
            "customer_id":  customer_id,
            "use_case":     use_case,
            "page_type":    page_type,
            "page_slug":    page_slug,
            "latency_ms":   latency_ms,
            "status":       status,
            "expires_at":   int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: telemetry log failed (non-fatal): {e}")


def _skill_response(version, status, outputs, latency_ms):
    payload = {
        "skill":           SKILL_NAME,
        "business_name":   BUSINESS_NAME,
        "skill_id":        SKILL_ID,
        "version":         version,
        "status":          status,
        "outputs":         outputs,
        "latency_ms":      latency_ms,
        "wiki_pages_used": 0,
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(payload, default=str),
    }


def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
