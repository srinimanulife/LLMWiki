"""
SK-02 · Knowledge Finder (WikiQuerySkill)
Domain-scoped, customer-aware wiki query with intent detection,
automatic retry on low confidence, and telemetry logging.
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

BQ_FUNCTION = os.environ.get("BUSINESS_QUERY_FUNCTION", "llmwiki-business-query")
LOG_TABLE   = os.environ.get("LOG_TABLE", "llmwiki-log")
SKILL_ID    = "SK-02"
SKILL_NAME  = "WikiQuerySkill"
BUSINESS_NAME = "Knowledge Finder"


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs      = body.get("inputs", body)
    question    = inputs.get("question", "").strip()
    domain      = inputs.get("domain", "")
    customer_id = inputs.get("customer_id", "")
    use_case    = inputs.get("use_case", "")
    intent      = inputs.get("intent", "")
    max_results = int(inputs.get("max_results", 5))
    version     = body.get("version", "1.0")
    invoked_by  = body.get("invoked_by", "unknown-agent")

    if not question:
        return _respond(400, {"error": "inputs.question is required"})

    # First attempt — domain-scoped
    result = _invoke_business_query(question, domain, customer_id, use_case, max_results)
    confidence = result.get("confidence", "low")

    # Retry once with broader scope if low confidence
    if confidence == "low" and domain:
        result_broad = _invoke_business_query(question, "", customer_id, use_case, max_results)
        if result_broad.get("confidence", "low") in ("high", "medium"):
            result = result_broad
            result["_note"] = "Domain filter broadened on retry (original domain had no confident results)"
            confidence = result_broad.get("confidence", "medium")

    latency_ms  = int((time.time() - t0) * 1000)
    pages_used  = result.get("wiki_page_count", 0)

    _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                   question, confidence, latency_ms, pages_used)

    return _skill_response(version, "success", result, latency_ms, pages_used)


def _invoke_business_query(question, domain, customer_id, use_case, max_results):
    payload = json.dumps({
        "question":    question,
        "domain":      domain,
        "customer_id": customer_id,
        "use_case":    use_case,
        "max_results": max_results,
        "include_action_items": True,
    })
    try:
        resp = lambda_client.invoke(
            FunctionName=BQ_FUNCTION,
            InvocationType="RequestResponse",
            Payload=payload.encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            inner = raw["body"]
            return json.loads(inner) if isinstance(inner, str) else (inner or {})
        return raw
    except Exception as e:
        print(f"WARN: business query invoke failed: {e}")
        return {"answer": "", "confidence": "low", "action_items": [], "sources": [],
                "gaps_detected": [], "wiki_page_count": 0}


def _log_telemetry(skill_id, skill_name, agent_id, customer_id, use_case,
                   question, confidence, latency_ms, pages_used):
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
            "question":     question[:200],
            "confidence":   confidence,
            "latency_ms":   latency_ms,
            "pages_used":   pages_used,
            "status":       "success",
            "expires_at":   int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: telemetry log failed (non-fatal): {e}")


def _skill_response(version, status, outputs, latency_ms, pages_used=0):
    payload = {
        "skill":           SKILL_NAME,
        "business_name":   BUSINESS_NAME,
        "skill_id":        SKILL_ID,
        "version":         version,
        "status":          status,
        "outputs":         outputs,
        "latency_ms":      latency_ms,
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
