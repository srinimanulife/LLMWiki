"""
SK-05 · Missing Info Radar (GapDetectionSkill)
When the wiki cannot answer confidently, identifies, classifies, and records
knowledge gaps. Blocking gaps (confidence=low AND action required) escalate
via SNS. All gaps recorded in llmwiki-gaps DynamoDB table.
Standard skill contract: {skill, version, inputs} → {skill, status, outputs, latency_ms}
"""

import json
import os
import re
import time
import uuid
import boto3
from datetime import datetime, timezone

bedrock  = boto3.client("bedrock-runtime",
                         region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb",
                           region_name=os.environ.get("AWS_REGION", "us-east-1"))
sns      = boto3.client("sns",
                         region_name=os.environ.get("AWS_REGION", "us-east-1"))

MODEL_ID        = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
GAPS_TABLE      = os.environ.get("GAPS_TABLE", "llmwiki-gaps")
LOG_TABLE       = os.environ.get("LOG_TABLE", "llmwiki-log")
SNS_TOPIC_ARN   = os.environ.get("GAPS_SNS_TOPIC_ARN", "")
SKILL_ID        = "SK-05"
SKILL_NAME      = "GapDetectionSkill"
BUSINESS_NAME   = "Missing Info Radar"


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs                  = body.get("inputs", body)
    question                = inputs.get("question", "").strip()
    domain                  = inputs.get("domain", "")
    use_case                = inputs.get("use_case", "")
    customer_id             = inputs.get("customer_id", "")
    low_confidence_response = inputs.get("low_confidence_response", {})
    version                 = body.get("version", "1.0")
    invoked_by              = body.get("invoked_by", "unknown-agent")

    if not question:
        return _respond(400, {"error": "inputs.question is required"})

    gaps = _classify_gaps(question, domain, use_case, customer_id,
                          low_confidence_response)

    # Persist each gap and escalate blocking ones
    persisted = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        gap_id = _persist_gap(gap, question, domain, use_case, customer_id, invoked_by)
        gap["gap_id"] = gap_id
        if gap.get("blocking") and SNS_TOPIC_ARN:
            _escalate_gap(gap, question, customer_id, invoked_by)
            gap["escalated"] = True
        else:
            gap["escalated"] = False
        persisted.append(gap)

    latency_ms = int((time.time() - t0) * 1000)
    _log_telemetry(invoked_by, customer_id, use_case, latency_ms, len(persisted))

    outputs = {
        "gaps":        persisted,
        "gap_count":   len(persisted),
        "blocking":    any(g.get("blocking") for g in persisted),
        "escalated":   any(g.get("escalated") for g in persisted),
    }

    return _skill_response(version, "success", outputs, latency_ms)


def _classify_gaps(question, domain, use_case, customer_id,
                   low_confidence_response) -> list:
    existing_gaps_text = ""
    if low_confidence_response:
        prev = low_confidence_response.get("gaps_detected", [])
        if prev:
            existing_gaps_text = f"\nPreviously detected gaps: {json.dumps(prev)}"

    prompt = f"""A business agent asked a question the wiki could not answer confidently.

QUESTION: {question}
DOMAIN: {domain or "general"}
USE CASE: {use_case or "not specified"}
CUSTOMER: {customer_id or "not specified"}
CONFIDENCE RETURNED: {low_confidence_response.get("confidence", "low")}{existing_gaps_text}

Identify 1-3 specific, actionable knowledge gaps that are preventing a confident answer.
For each gap determine whether it is BLOCKING (agent cannot proceed without this info).

Return ONLY a JSON array:
[
  {{
    "gap_type": "missing-customer-history|missing-artifact|missing-standard|missing-evidence|unknown-configuration",
    "slug": "kebab-case-slug",
    "title": "Human-readable gap title",
    "blocking": true|false,
    "human_prompt": "Exact question to ask a human to fill this gap"
  }}
]"""

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 512},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(m.group())[:3] if m else []
    except Exception as e:
        print(f"WARN: gap classification failed: {e}")
        return [{
            "gap_type": "missing-standard",
            "slug": "unclassified-gap",
            "title": "Unclassified Knowledge Gap",
            "blocking": False,
            "human_prompt": f"Please provide information to answer: {question[:200]}",
        }]


def _persist_gap(gap, question, domain, use_case, customer_id, agent_id) -> str:
    try:
        now    = datetime.now(timezone.utc).isoformat()
        gap_id = str(uuid.uuid4())
        dynamodb.Table(GAPS_TABLE).put_item(Item={
            "gap_id":      gap_id,
            "gap_slug":    gap.get("slug", "unknown"),
            "gap_type":    gap.get("gap_type", "missing-standard"),
            "title":       gap.get("title", ""),
            "blocking":    gap.get("blocking", False),
            "human_prompt": gap.get("human_prompt", ""),
            "question":    question[:500],
            "domain":      domain,
            "use_case":    use_case,
            "customer_id": customer_id,
            "detected_by": agent_id,
            "status":      "open",
            "created_at":  now,
        })
        return gap_id
    except Exception as e:
        print(f"WARN: gap persist failed (non-fatal): {e}")
        return ""


def _escalate_gap(gap, question, customer_id, agent_id):
    try:
        message = (
            f"BLOCKING Knowledge Gap Detected\n\n"
            f"Agent: {agent_id}\n"
            f"Customer: {customer_id}\n"
            f"Gap: {gap.get('title')}\n"
            f"Type: {gap.get('gap_type')}\n"
            f"Question: {question[:300]}\n\n"
            f"Action Required: {gap.get('human_prompt')}"
        )
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[LLMWiki] Blocking Gap: {gap.get('title', 'Unknown')}",
            Message=message,
        )
    except Exception as e:
        print(f"WARN: SNS escalation failed (non-fatal): {e}")


def _log_telemetry(agent_id, customer_id, use_case, latency_ms, gap_count):
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
            "gap_count":    gap_count,
            "latency_ms":   latency_ms,
            "status":       "success",
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
        "logged_to_gaps_table": True,
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
