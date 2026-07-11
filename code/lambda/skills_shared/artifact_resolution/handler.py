"""
SK-04 · Template Auto-Fill (ArtifactResolutionSkill)
Retrieves a named artifact template from the wiki and pre-populates it with
available customer / project data using Claude. Returns populated content and
a list of still-missing fields so the agent can surface them for human input.
Standard skill contract: {skill, version, inputs} → {skill, status, outputs, latency_ms}
"""

import json
import os
import re
import time
import boto3
from datetime import datetime, timezone

lambda_client = boto3.client("lambda",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock       = boto3.client("bedrock-runtime",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb      = boto3.resource("dynamodb",
                                region_name=os.environ.get("AWS_REGION", "us-east-1"))

PLAYBOOK_FUNCTION = os.environ.get("PLAYBOOK_FUNCTION", "llmwiki-playbook")
MODEL_ID          = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
LOG_TABLE         = os.environ.get("LOG_TABLE", "llmwiki-log")
SKILL_ID          = "SK-04"
SKILL_NAME        = "ArtifactResolutionSkill"
BUSINESS_NAME     = "Template Auto-Fill"


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs            = body.get("inputs", body)
    artifact_type     = inputs.get("artifact_type", "").strip()
    customer_id       = inputs.get("customer_id", "")
    available_context = inputs.get("available_context", {})
    use_case          = inputs.get("use_case", "UC1")
    version           = body.get("version", "1.0")
    invoked_by        = body.get("invoked_by", "unknown-agent")

    if not artifact_type:
        return _respond(400, {"error": "inputs.artifact_type is required"})

    # Step 1: Fetch artifact template from wiki
    artifact = _get_artifact(artifact_type)
    if not artifact.get("found"):
        latency_ms = int((time.time() - t0) * 1000)
        outputs = {
            "artifact_type":  artifact_type,
            "found":          False,
            "note":           artifact.get("note", "Artifact not found in wiki."),
            "populated_fields": [],
            "missing_fields": [],
            "artifact_content": "",
        }
        _log_telemetry(invoked_by, customer_id, use_case, artifact_type,
                       latency_ms, "not_found")
        return _skill_response(version, "not_found", outputs, latency_ms)

    template_content = artifact.get("content", "")
    s3_key           = artifact.get("s3_key", "")

    # Step 2: Ask Claude to populate the template with available_context
    context_json = json.dumps(available_context, indent=2, default=str)
    populate_prompt = f"""You are populating an artifact template for a business customer.

ARTIFACT TYPE: {artifact_type}
CUSTOMER ID: {customer_id}
USE CASE: {use_case}

AVAILABLE CUSTOMER CONTEXT:
{context_json[:3000]}

TEMPLATE TO POPULATE:
{template_content[:4000]}

Task:
1. Identify every placeholder or blank field in the template (look for [FIELD_NAME], {{field}}, TBD, or empty table cells)
2. Fill in every field you CAN populate from the available context
3. Leave fields you CANNOT fill with the marker [MISSING: <field_name>]
4. Return a JSON object with exactly these keys:
{{
  "populated_content": "<the full template with fields filled in>",
  "populated_fields": ["field1", "field2"],
  "missing_fields": ["field3_description", "field4_description"],
  "completion_pct": 0-100
}}

Return ONLY valid JSON, no preamble."""

    populated_content = template_content
    populated_fields  = []
    missing_fields    = []
    completion_pct    = 0

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": populate_prompt}]}],
            "inferenceConfig": {"maxTokens": 2000},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            populated_content = data.get("populated_content", template_content)
            populated_fields  = data.get("populated_fields", [])
            missing_fields    = data.get("missing_fields", [])
            completion_pct    = data.get("completion_pct", 0)
    except Exception as e:
        print(f"WARN: artifact population failed: {e}")

    latency_ms = int((time.time() - t0) * 1000)
    outputs = {
        "artifact_type":     artifact_type,
        "found":             True,
        "s3_key":            s3_key,
        "artifact_content":  populated_content,
        "populated_fields":  populated_fields,
        "missing_fields":    missing_fields,
        "completion_pct":    completion_pct,
    }

    _log_telemetry(invoked_by, customer_id, use_case, artifact_type,
                   latency_ms, "success")

    return _skill_response(version, "success", outputs, latency_ms, pages_used=1)


def _get_artifact(artifact_type: str) -> dict:
    payload = json.dumps({"action": "get_artifact", "artifact_type": artifact_type})
    try:
        resp = lambda_client.invoke(
            FunctionName=PLAYBOOK_FUNCTION,
            InvocationType="RequestResponse",
            Payload=payload.encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            inner = raw["body"]
            return json.loads(inner) if isinstance(inner, str) else (inner or {})
        return raw
    except Exception as e:
        print(f"WARN: get_artifact invoke failed: {e}")
        return {"found": False}


def _log_telemetry(agent_id, customer_id, use_case, artifact_type,
                   latency_ms, status):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":      now[:10],
            "timestamp_id":  f"{now}#{SKILL_ID}",
            "skill_id":      SKILL_ID,
            "skill_name":    SKILL_NAME,
            "agent_id":      agent_id,
            "customer_id":   customer_id,
            "use_case":      use_case,
            "artifact_type": artifact_type,
            "latency_ms":    latency_ms,
            "status":        status,
            "expires_at":    int(time.time()) + 90 * 86400,
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
