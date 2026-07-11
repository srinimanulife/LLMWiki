"""
SK-01 · Customer Briefing Loader (ContextBootstrapSkill)
Loads customer history + playbook in parallel before any UC agent action.
Standard skill contract: {skill, version, inputs} → {skill, status, outputs, latency_ms}
"""

import json
import os
import time
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

lambda_client = boto3.client("lambda",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb      = boto3.resource("dynamodb",
                                region_name=os.environ.get("AWS_REGION", "us-east-1"))

PLAYBOOK_FUNCTION = os.environ.get("PLAYBOOK_FUNCTION", "llmwiki-playbook")
LOG_TABLE         = os.environ.get("LOG_TABLE", "llmwiki-log")
SKILL_ID          = "SK-01"
SKILL_NAME        = "ContextBootstrapSkill"
BUSINESS_NAME     = "Customer Briefing Loader"


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs      = body.get("inputs", body)
    customer_id = inputs.get("customer_id", "")
    use_case    = inputs.get("use_case", "UC1").upper()
    agent_id    = inputs.get("agent_id", "unknown-agent")
    version     = body.get("version", "1.0")
    invoked_by  = body.get("invoked_by", agent_id)

    if not customer_id:
        return _respond(400, {"error": "inputs.customer_id is required"})

    # Load customer context and playbook in parallel
    customer_payload  = json.dumps({"action": "get_customer", "customer_id": customer_id})
    playbook_payload  = json.dumps({"action": "get_playbook",  "use_case": use_case})

    customer_result, playbook_result = {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_cust = pool.submit(_invoke_lambda, PLAYBOOK_FUNCTION, customer_payload)
        f_pb   = pool.submit(_invoke_lambda, PLAYBOOK_FUNCTION, playbook_payload)
        customer_result = f_cust.result()
        playbook_result = f_pb.result()

    customer_status    = customer_result.get("status", "no-history")
    pages_loaded       = customer_result.get("pages_found", 0) + 1  # +1 for playbook
    prior_contributions = customer_result.get("related_pages", [])
    latency_ms         = int((time.time() - t0) * 1000)

    outputs = {
        "customer_status":      customer_status,
        "customer_context":     customer_result,
        "prior_contributions":  prior_contributions,
        "playbook":             playbook_result,
        "pages_loaded":         pages_loaded,
    }

    _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                   latency_ms, "success", pages_loaded)

    return _skill_response(version, "success", outputs, latency_ms, pages_loaded)


def _invoke_lambda(fn_name: str, payload: str) -> dict:
    try:
        resp = lambda_client.invoke(
            FunctionName=fn_name,
            InvocationType="RequestResponse",
            Payload=payload.encode(),
        )
        raw = json.loads(resp["Payload"].read())
        # Unwrap API Gateway body wrapper
        if "body" in raw:
            inner = raw["body"]
            return json.loads(inner) if isinstance(inner, str) else (inner or {})
        return raw
    except Exception as e:
        print(f"WARN: Lambda invoke {fn_name} failed: {e}")
        return {}


def _log_telemetry(skill_id, skill_name, agent_id, customer_id, use_case,
                   latency_ms, status, pages_used):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":     now[:10],
            "timestamp_id": f"{now}#{skill_id}",
            "skill_id":     skill_id,
            "skill_name":   skill_name,
            "agent_id":     agent_id,
            "customer_id":  customer_id,
            "use_case":     use_case,
            "latency_ms":   latency_ms,
            "status":       status,
            "pages_used":   pages_used,
            "expires_at":   int(time.time()) + 90 * 86400,  # 90-day TTL
        })
    except Exception as e:
        print(f"WARN: telemetry log failed (non-fatal): {e}")


def _skill_response(version, status, outputs, latency_ms, pages_used=0):
    payload = {
        "skill":          SKILL_NAME,
        "business_name":  BUSINESS_NAME,
        "skill_id":       SKILL_ID,
        "version":        version,
        "status":         status,
        "outputs":        outputs,
        "latency_ms":     latency_ms,
        "wiki_pages_used": pages_used,
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
