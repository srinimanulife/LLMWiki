"""
LLMWiki Shared Library — common patterns extracted from all Lambda handlers.

Usage in any handler.py:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
    from llmwiki_common import (
        parse_event_body, http_respond, skill_response,
        bedrock_converse, invoke_lambda, s3_presign, log_telemetry
    )

For Lambda deployment, include this file in the zip by setting the archive source_dir
to a directory that contains both handler.py and common/llmwiki_common.py, OR
set the Terraform source_dir to the parent folder and add a data source for common.
See /docs/packaging.md for the recommended approach.
"""

import json
import os
import time
import boto3
from botocore.config import Config
from datetime import datetime, timezone

_region  = os.environ.get("AWS_REGION", "us-east-1")
_bedrock = boto3.client("bedrock-runtime", region_name=_region)
_lambda  = boto3.client("lambda",          region_name=_region)
_s3      = boto3.client("s3",              region_name=_region, config=Config(signature_version="s3v4"))
_ddb     = boto3.resource("dynamodb",      region_name=_region)

LOG_TABLE = os.environ.get("LOG_TABLE", "llmwiki-log")


# ── Event parsing ──────────────────────────────────────────────────────────────

def parse_event_body(event: dict) -> dict:
    """
    Unwrap API Gateway / direct-invoke payload uniformly.
    API Gateway wraps the real payload in event["body"] as a JSON string.
    Direct Lambda invocations pass the payload as the event itself.
    """
    raw = event.get("body") if "body" in event else None
    if raw is not None:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    return event


# ── HTTP response helpers ──────────────────────────────────────────────────────

def http_respond(status_code: int, body: dict) -> dict:
    """Standard API Gateway response envelope with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


def skill_response(skill_name: str, skill_id: str, business_name: str,
                   version: str, status: str, outputs: dict,
                   latency_ms: int, wiki_pages_used: int = 0) -> dict:
    """
    Standard skill contract response envelope.
    All skills return this shape: {skill, skill_id, version, status, outputs, latency_ms}
    """
    payload = {
        "skill":           skill_name,
        "business_name":   business_name,
        "skill_id":        skill_id,
        "version":         version,
        "status":          status,
        "outputs":         outputs,
        "latency_ms":      latency_ms,
        "wiki_pages_used": wiki_pages_used,
    }
    return http_respond(200, payload)


# ── Bedrock Converse API ───────────────────────────────────────────────────────

def bedrock_converse(prompt: str, system: str = "",
                     max_tokens: int = 512, model_id: str = "") -> str:
    """
    Call Bedrock Converse API and return the response text.
    Model-agnostic: works with Claude, Nova, and any future Converse-compatible model.
    Returns empty string on failure (caller decides whether to raise or default).
    """
    model = model_id or os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    kwargs: dict = {
        "modelId": model,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    resp = _bedrock.converse(**kwargs)
    return resp["output"]["message"]["content"][0]["text"]


# ── Lambda invocation ──────────────────────────────────────────────────────────

def invoke_lambda(function_name: str, payload: dict, label: str = "") -> dict | None:
    """
    Invoke a Lambda synchronously and return the unwrapped inner body dict.
    Returns None on any error (caller logs/defaults as needed).
    Unwraps the API Gateway body wrapper if present.
    """
    try:
        resp       = _lambda.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        body_bytes = resp["Payload"].read()
        outer      = json.loads(body_bytes)
        if outer.get("FunctionError"):
            print(f"WARN: {label or function_name} Lambda error: {outer}")
            return None
        body_str = outer.get("body", outer)
        return json.loads(body_str) if isinstance(body_str, str) else body_str
    except Exception as e:
        print(f"WARN: {label or function_name} invocation failed: {e}")
        return None


# ── S3 helpers ─────────────────────────────────────────────────────────────────

def s3_put(bucket: str, key: str, content: str | bytes,
           content_type: str = "application/json") -> None:
    """Write content to S3. Logs warning on failure (non-fatal by default)."""
    if not bucket:
        print(f"WARN: s3_put skipped — bucket not set (key={key})")
        return
    try:
        _s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode() if isinstance(content, str) else content,
            ContentType=content_type,
        )
    except Exception as e:
        print(f"WARN: s3_put failed for {key}: {e}")


def s3_presign(bucket: str, key: str, expiry_seconds: int = 86400) -> str:
    """Generate a presigned GET URL. Returns empty string on failure."""
    if not bucket:
        return ""
    try:
        return _s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry_seconds,
        )
    except Exception as e:
        print(f"WARN: s3_presign failed for {key}: {e}")
        return ""


# ── Telemetry ──────────────────────────────────────────────────────────────────

def log_telemetry(skill_id: str, skill_name: str, agent_id: str,
                  customer_id: str, use_case: str, latency_ms: int,
                  status: str = "success", pages_used: int = 0,
                  extra: dict | None = None) -> None:
    """
    Write a telemetry record to the shared wiki_log DynamoDB table.
    Non-fatal — logs warning on DynamoDB failure but does not raise.
    TTL is 90 days from write time.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        item = {
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
            "expires_at":   int(time.time()) + 90 * 86400,
        }
        if extra:
            item.update(extra)
        _ddb.Table(LOG_TABLE).put_item(Item=item)
    except Exception as e:
        print(f"WARN: log_telemetry failed (non-fatal): {e}")
