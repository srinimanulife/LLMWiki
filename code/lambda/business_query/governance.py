"""
LLMWiki Governance — cost tracking, semantic caching, rate limiting.

Storage strategy:
- Uses llmwiki-log table (already in Lambda IAM policies) as the primary store.
  Governance rows are prefixed with "governance#" on log_date to keep them
  separate from ingest log rows.
- llmwiki-usage / llmwiki-cache / llmwiki-rate-limits tables are used when
  available (i.e., after IAM is extended to include them).
- All calls fail-open: a governance failure never breaks the Lambda.

Import from any Lambda: from governance import record_usage, cache_get, cache_put, check_rate_limit
"""

import json
import os
import time
import uuid
import hashlib
import boto3
from datetime import datetime, timezone
from decimal import Decimal

_dynamodb = None
_bedrock  = None

def _db():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _dynamodb

def _br():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _bedrock

# Table names — dedicated governance tables (preferred) with log table fallback
USAGE_TABLE    = os.environ.get("USAGE_TABLE",  "llmwiki-usage")
CACHE_TABLE    = os.environ.get("CACHE_TABLE",  "llmwiki-cache")
RATE_TABLE     = os.environ.get("RATE_TABLE",   "llmwiki-rate-limits")
# Log table is always in the Lambda IAM policy — used as fallback for all three
LOG_TABLE      = os.environ.get("DYNAMODB_LOG_TABLE",
                 os.environ.get("DYNAMODB_LOG", "llmwiki-log"))

CACHE_TTL_S      = int(os.environ.get("CACHE_TTL_SECONDS",     "86400"))
SIM_THRESHOLD    = float(os.environ.get("CACHE_SIM_THRESHOLD", "0.92"))
SEMANTIC_ENABLED = os.environ.get("CACHE_SEMANTIC_ENABLED", "true").lower() == "true"
EMBED_MODEL      = "amazon.titan-embed-text-v2:0"

# Bedrock Converse pricing (us-east-1), $/1K tokens
_PRICING = {
    "us.anthropic.claude-sonnet-4-6":        {"in": Decimal("0.003"),  "out": Decimal("0.015")},
    "us.anthropic.claude-haiku-4-5-20251001": {"in": Decimal("0.0008"), "out": Decimal("0.004")},
    "amazon.titan-embed-text-v2:0":          {"in": Decimal("0.0002"), "out": Decimal("0")},
}
_DEFAULT_PRICING = {"in": Decimal("0.003"), "out": Decimal("0.015")}


def _put_with_fallback(primary_table: str, primary_item: dict,
                       fallback_prefix: str, fallback_item_extra: dict = None):
    """
    Try to put to primary_table. On AccessDenied, fall back to llmwiki-log
    using governance#<date> as log_date and a unique timestamp_id.
    """
    try:
        _db().Table(primary_table).put_item(Item=primary_item)
        return True
    except Exception as e:
        if "AccessDenied" not in str(e) and "not authorized" not in str(e):
            print(f"WARN governance._put ({primary_table}): {e}")
            return False
        # Fallback: write to llmwiki-log with governance prefix
        try:
            now = datetime.now(timezone.utc).isoformat()
            log_item = {
                "log_date":     f"governance#{fallback_prefix}#{now[:10]}",
                "timestamp_id": f"{now}#{str(uuid.uuid4())[:8]}",
            }
            log_item.update(primary_item)
            if fallback_item_extra:
                log_item.update(fallback_item_extra)
            _db().Table(LOG_TABLE).put_item(Item=log_item)
            return True
        except Exception as e2:
            print(f"WARN governance._put fallback ({LOG_TABLE}): {e2}")
            return False


def _get_with_fallback(primary_table: str, key: dict, fallback_prefix: str,
                       fallback_date: str) -> dict | None:
    """Try primary table GetItem; fall back to scanning log table prefix."""
    try:
        item = _db().Table(primary_table).get_item(Key=key).get("Item")
        if item:
            return item
    except Exception as e:
        if "AccessDenied" not in str(e) and "not authorized" not in str(e):
            print(f"WARN governance._get ({primary_table}): {e}")
            return None
        # Fallback: query log table
        try:
            resp = _db().Table(LOG_TABLE).query(
                KeyConditionExpression="log_date = :lk",
                ExpressionAttributeValues={":lk": f"governance#{fallback_prefix}#{fallback_date}"},
                Limit=500,
                ScanIndexForward=False,
            )
            # Return the most recent matching item
            items = resp.get("Items", [])
            return items[0] if items else None
        except Exception as e2:
            print(f"WARN governance._get fallback: {e2}")
    return None


# ── Cost tracking ──────────────────────────────────────────────────

def record_usage(model_id: str, input_tokens: int, output_tokens: int,
                 caller: str = "unknown", operation: str = "query",
                 question_hash: str = "", cache_hit: bool = False) -> float:
    """Write one cost row. Returns cost_usd as float."""
    p = _PRICING.get(model_id, _DEFAULT_PRICING)
    cost = (Decimal(input_tokens) / 1000 * p["in"] +
            Decimal(output_tokens) / 1000 * p["out"])
    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())

    item = {
        "request_id":    rid,
        "timestamp":     now,
        "date":          now[:10],
        "caller":        caller,
        "operation":     operation,
        "model_id":      model_id,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost,
        "question_hash": question_hash,
        "cache_hit":     cache_hit,
    }
    _put_with_fallback(USAGE_TABLE, item, f"usage#{caller}")
    _emit_cost_metric(float(cost), caller)
    return float(cost)


def _emit_cost_metric(cost_usd: float, caller: str):
    try:
        cw = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        cw.put_metric_data(
            Namespace="LLMWiki/Governance",
            MetricData=[{
                "MetricName": "DailyCostUSD",
                "Value": cost_usd,
                "Unit": "None",
                "Dimensions": [{"Name": "Caller", "Value": caller}],
            }],
        )
    except Exception:
        pass  # non-fatal


# ── Cache helpers ──────────────────────────────────────────────────

def _cache_key(question: str, domain: str = "", kb_id: str = "") -> str:
    payload = json.dumps(
        {"q": question.lower().strip(), "domain": domain, "kb": kb_id},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _embed(text: str) -> list:
    try:
        resp = _br().invoke_model(
            modelId=EMBED_MODEL,
            body=json.dumps({"inputText": text[:8000]}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(resp["body"].read())["embedding"]
    except Exception as e:
        print(f"WARN governance._embed: {e}")
        return []


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    try:
        dot = sum(x * y for x, y in zip(a, b))
        na  = sum(x * x for x in a) ** 0.5
        nb  = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0
    except Exception:
        return 0.0


# ── Cache get / put ────────────────────────────────────────────────

def cache_get(question: str, domain: str = "", kb_id: str = "") -> dict | None:
    """Return cached result dict or None."""
    key  = _cache_key(question, domain, kb_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Exact hash lookup in primary cache table
    try:
        item = _db().Table(CACHE_TABLE).get_item(Key={"cache_key": key}).get("Item")
        if item:
            return json.loads(item["response_json"])
    except Exception as e:
        if "AccessDenied" not in str(e) and "not authorized" not in str(e):
            print(f"WARN governance.cache_get exact: {e}")
        else:
            # Try fallback log table — look for cached entry by hash in governance log
            try:
                resp = _db().Table(LOG_TABLE).query(
                    KeyConditionExpression="log_date = :lk",
                    ExpressionAttributeValues={":lk": f"governance#cache#{today}"},
                    FilterExpression="cache_key = :ck",
                    ExpressionAttributeNames={},
                    Limit=500,
                )
                for candidate in resp.get("Items", []):
                    if candidate.get("cache_key") == key and candidate.get("response_json"):
                        return json.loads(candidate["response_json"])
            except Exception:
                pass

    if not SEMANTIC_ENABLED:
        return None

    # 2. Semantic similarity in primary cache table
    try:
        q_emb = _embed(question)
        if not q_emb:
            return None
        resp = _db().Table(CACHE_TABLE).query(
            IndexName="domain_recency_index",
            KeyConditionExpression="cache_domain = :d",
            ExpressionAttributeValues={":d": domain or "all"},
            ScanIndexForward=False,
            Limit=300,
        )
        for candidate in resp.get("Items", []):
            c_emb = json.loads(candidate.get("embedding_json") or "[]")
            if c_emb and _cosine(q_emb, c_emb) >= SIM_THRESHOLD:
                print(f"  Cache semantic hit for '{question[:60]}'")
                return json.loads(candidate["response_json"])
    except Exception as e:
        if "AccessDenied" not in str(e) and "not authorized" not in str(e):
            print(f"WARN governance.cache_get semantic: {e}")

    return None


def cache_put(question: str, result: dict, domain: str = "",
              kb_id: str = "", embedding: list = None):
    """Store result in cache table with TTL."""
    key = _cache_key(question, domain, kb_id)
    now = datetime.now(timezone.utc).isoformat()
    emb = embedding or ([] if not SEMANTIC_ENABLED else _embed(question))

    item = {
        "cache_key":      key,
        "cache_domain":   domain or "all",
        "question":       question[:500],
        "response_json":  json.dumps(result, default=str),
        "embedding_json": json.dumps(emb),
        "created_at":     now,
        "expires_at":     int(time.time()) + CACHE_TTL_S,
    }
    _put_with_fallback(CACHE_TABLE, item, "cache")


# ── Rate limiting ──────────────────────────────────────────────────

def check_rate_limit(caller: str, window_minutes: int = 1,
                     max_requests: int = 30) -> tuple:
    """Sliding window counter. Returns (allowed: bool, info: dict)."""
    window_key = f"{caller}#{int(time.time() // (window_minutes * 60))}"
    try:
        resp = _db().Table(RATE_TABLE).update_item(
            Key={"window_key": window_key},
            UpdateExpression="ADD #cnt :one SET #ttl = :exp",
            ExpressionAttributeNames={"#cnt": "count", "#ttl": "expires_at"},
            ExpressionAttributeValues={
                ":one": 1,
                ":exp": int(time.time()) + (window_minutes * 60 * 2),
            },
            ReturnValues="ALL_NEW",
        )
        count   = int(resp["Attributes"]["count"])
        allowed = count <= max_requests
        return allowed, {
            "caller": caller, "count": count,
            "limit": max_requests, "window_minutes": window_minutes,
        }
    except Exception as e:
        if "AccessDenied" in str(e) or "not authorized" in str(e):
            # Fallback: use llmwiki-log for rate counter
            try:
                now = datetime.now(timezone.utc).isoformat()
                resp = _db().Table(LOG_TABLE).update_item(
                    Key={
                        "log_date":     f"governance#rate#{caller[:40]}",
                        "timestamp_id": window_key,
                    },
                    UpdateExpression="ADD #cnt :one SET #ttl = :exp, #ts = :ts",
                    ExpressionAttributeNames={"#cnt": "count", "#ttl": "expires_at", "#ts": "updated_at"},
                    ExpressionAttributeValues={
                        ":one": 1,
                        ":exp": int(time.time()) + (window_minutes * 60 * 2),
                        ":ts":  now,
                    },
                    ReturnValues="ALL_NEW",
                )
                count = int(resp["Attributes"]["count"])
                return count <= max_requests, {"caller": caller, "count": count, "limit": max_requests}
            except Exception as e2:
                print(f"WARN governance.check_rate_limit fallback: {e2}")
        else:
            print(f"WARN governance.check_rate_limit: {e}")
        return True, {"caller": caller, "error": str(e)}  # fail open


def check_budget_ceiling(caller: str, daily_limit_usd: float = 5.0) -> bool:
    """Return True if caller's daily spend is below the ceiling."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        resp = _db().Table(USAGE_TABLE).query(
            IndexName="date_caller_index",
            KeyConditionExpression="#d = :date AND #c = :caller",
            ExpressionAttributeNames={"#d": "date", "#c": "caller"},
            ExpressionAttributeValues={":date": today, ":caller": caller},
            ProjectionExpression="cost_usd",
        )
        total = sum(float(i.get("cost_usd", 0)) for i in resp.get("Items", []))
        return total < daily_limit_usd
    except Exception as e:
        if "AccessDenied" not in str(e) and "not authorized" not in str(e):
            print(f"WARN governance.check_budget_ceiling: {e}")
        return True  # fail open — never block on IAM error
