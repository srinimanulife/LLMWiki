# LLMWiki Governance — Cost Tracking, Caching & Rate Limiting

*Inspired by toko-mo-co (open-source LLM proxy). Adapted for LLMWiki's AWS-native Lambda / Bedrock / DynamoDB stack.*

---

## Why This Matters

LLMWiki has three classes of callers, each with different risk profiles:

| Caller | Entry Point | Risk |
|--------|-------------|------|
| **Human users** | Streamlit UI → Query Lambda | Exploratory queries, moderate volume |
| **AgentCore skills** | Business API (`/wiki/ask`, `/wiki/query/{domain}`) | High-frequency, scripted — can loop |
| **Ingest pipeline** | S3 trigger → Ingest Lambda | Long-running, high token usage per call |

Without governance, a runaway AgentCore skill or a bursty ingest batch can burn hundreds of dollars in Bedrock tokens before anyone notices. These three controls — **cost tracking**, **semantic caching**, and **rate limiting** — are the toko-mo-co proxy's core value proposition, implemented natively inside LLMWiki's existing AWS footprint.

---

## Is This Complementary to AWS AgentCore?

**Yes — it sits around AgentCore, not inside it.** AgentCore handles orchestration (skill routing, memory, tool use, sequential UC handoffs). It does not manage:

- Token-level cost attribution per skill/caller/use-case
- Response caching for repeated or semantically similar queries
- Per-agent rate limits or hard budget ceilings

The governance layer plugs in as a **thin middleware** in two places:

```
AgentCore skill invocation
        │
        ▼
  Governance Interceptor  ←── rate limit check, cache lookup
        │
        ▼ (cache miss)
  Bedrock converse()
        │
        ▼
  Governance Interceptor  ←── token count + cost recording, cache write
        │
        ▼
  AgentCore receives answer
```

From the **user's perspective** (human or agent), governance is invisible on cache hits (faster + free), visible as a `429 Too Many Requests` only when a budget ceiling is genuinely breached, and visible as a cost dashboard in Streamlit's new Governance page.

---

## Architecture Overview

### New AWS Resources

| Resource | Purpose |
|----------|---------|
| `llmwiki-usage` DynamoDB table | Per-request cost ledger |
| `llmwiki-cache` DynamoDB table | Semantic response cache (hash + embedding) |
| `llmwiki-rate-limits` DynamoDB table | Per-caller sliding window counters |
| `/llmwiki/governance/*` SSM parameters | Budget thresholds, cache TTL, limit config |
| CloudWatch Dashboard `LLMWiki-Governance` | Cost + cache hit rate + rate limit hits |

All tables use `PAY_PER_REQUEST` — consistent with the existing DynamoDB design.

---

## Pillar 1 — Cost Tracking

### What to Track

Every `bedrock.converse()` call returns usage in `response["usage"]`:

```python
usage = response.get("usage", {})
input_tokens  = usage.get("inputTokens", 0)
output_tokens = usage.get("outputTokens", 0)
```

Bedrock Converse pricing (us-east-1, Claude Sonnet 4.6):

- Input: $0.003 / 1K tokens
- Output: $0.015 / 1K tokens

### Implementation — `lambda/common/governance.py` (new shared module)

```python
import boto3, os, uuid
from datetime import datetime, timezone
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "llmwiki-usage")

# Bedrock Converse pricing map — update when model changes
COST_PER_1K = {
    "us.anthropic.claude-sonnet-4-6": {"input": Decimal("0.003"), "output": Decimal("0.015")},
    "us.anthropic.claude-haiku-4-5":  {"input": Decimal("0.0008"), "output": Decimal("0.004")},
    "amazon.titan-embed-text-v2:0":   {"input": Decimal("0.0002"), "output": Decimal("0")},
}

def record_usage(model_id: str, input_tokens: int, output_tokens: int,
                 caller: str, operation: str, question_hash: str = "",
                 cache_hit: bool = False):
    """Write one row to llmwiki-usage. Called after every bedrock.converse()."""
    pricing = COST_PER_1K.get(model_id, {"input": Decimal("0.003"), "output": Decimal("0.015")})
    cost_usd = (
        Decimal(input_tokens)  / 1000 * pricing["input"] +
        Decimal(output_tokens) / 1000 * pricing["output"]
    )
    now = datetime.now(timezone.utc).isoformat()
    dynamodb.Table(USAGE_TABLE).put_item(Item={
        "request_id":    str(uuid.uuid4()),
        "timestamp":     now,
        "date":          now[:10],           # GSI partition key for daily reports
        "caller":        caller,             # "streamlit", "agentcore/uc1", "ingest", etc.
        "operation":     operation,          # "query", "ingest", "business_ask", "gap_detect"
        "model_id":      model_id,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost_usd,
        "question_hash": question_hash,
        "cache_hit":     cache_hit,
    })
    return float(cost_usd)
```

### Wire Into Existing Lambdas

In `lambda/query/handler.py`, wrap the `bedrock.converse()` call:

```python
# Before (existing):
response = bedrock.converse(**_converse_kwargs)
answer   = response["output"]["message"]["content"][0]["text"].strip()

# After (add 3 lines):
response = bedrock.converse(**_converse_kwargs)
answer   = response["output"]["message"]["content"][0]["text"].strip()
from governance import record_usage
record_usage(MODEL_ID, response["usage"]["inputTokens"],
             response["usage"]["outputTokens"],
             caller=body.get("caller", "streamlit"), operation="query")
```

Apply the same pattern in:
- `lambda/ingest/handler.py` → operation `"ingest"`
- `lambda/business_query/handler.py` → operation `"business_ask"`, caller from `body.get("agent_id", "agentcore")`
- `lambda/query/handler.py` `identify_and_record_gaps()` → operation `"gap_detect"`

### DynamoDB Schema — `llmwiki-usage`

```hcl
resource "aws_dynamodb_table" "usage" {
  name         = "llmwiki-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute { name = "request_id" type = "S" }
  attribute { name = "date"       type = "S" }
  attribute { name = "caller"     type = "S" }

  global_secondary_index {
    name            = "date_caller_index"
    hash_key        = "date"
    range_key       = "caller"
    projection_type = "ALL"
  }

  ttl { attribute_name = "expires_at" enabled = true }  # 90-day retention
  server_side_encryption { enabled = true }
}
```

### CloudWatch Cost Alarm

```hcl
resource "aws_cloudwatch_metric_alarm" "daily_cost" {
  alarm_name          = "llmwiki-daily-bedrock-cost"
  namespace           = "LLMWiki/Governance"
  metric_name         = "DailyCostUSD"
  statistic           = "Sum"
  period              = 86400
  threshold           = 10.0          # $10/day — adjust for your budget
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

Lambda functions emit this metric via `boto3.client("cloudwatch").put_metric_data()` inside `record_usage()`.

---

## Pillar 2 — Semantic Caching

### Strategy

LLMWiki already has S3 Vectors for semantic search in the KB. The same embedding model (`amazon.titan-embed-text-v2:0`) can power the cache. A cached hit returns the stored answer **without calling Bedrock**, achieving:

- **Zero cost** for repeated or near-identical questions
- **Sub-100ms response** vs. 2–4s for a live KB+Claude call
- **Consistent answers** for the same question across agent invocations (important for UC handoffs)

Cache applies to **Query Lambda** and **Business Query Lambda** — not Ingest (each document is unique).

### Cache Key

```python
import hashlib, json

def make_cache_key(question: str, domain: str = "", kb_id: str = "") -> str:
    payload = json.dumps({"q": question.lower().strip(), "domain": domain, "kb": kb_id},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
```

### Semantic Similarity Check

For near-duplicate detection, embed the query and compare cosine similarity against recent cache entries:

```python
import numpy as np

def cosine_sim(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def embed(text: str) -> list:
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text[:8000]}),
        contentType="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]
```

### Cache Lookup + Write

```python
# In governance.py

CACHE_TABLE  = os.environ.get("CACHE_TABLE", "llmwiki-cache")
CACHE_TTL_S  = int(os.environ.get("CACHE_TTL_SECONDS", 86400))   # 24h default
SIM_THRESHOLD = float(os.environ.get("CACHE_SIM_THRESHOLD", "0.92"))

def cache_get(question: str, domain: str = "", kb_id: str = "") -> dict | None:
    """Return cached result if exact hash matches or semantic similarity ≥ threshold."""
    key = make_cache_key(question, domain, kb_id)
    table = dynamodb.Table(CACHE_TABLE)

    # Exact match first (free, fast)
    item = table.get_item(Key={"cache_key": key}).get("Item")
    if item:
        return json.loads(item["response_json"])

    # Semantic match — scan recent entries (limit to last 500 by recency GSI)
    # Only worthwhile if embedding cost < cache miss cost
    if os.environ.get("CACHE_SEMANTIC_ENABLED", "true") == "true":
        q_emb = embed(question)
        resp  = table.query(
            IndexName="domain_recency_index",
            KeyConditionExpression="cache_domain = :d",
            ExpressionAttributeValues={":d": domain or "all"},
            ScanIndexForward=False, Limit=500,
        )
        for candidate in resp.get("Items", []):
            c_emb = json.loads(candidate.get("embedding_json", "[]"))
            if c_emb and cosine_sim(q_emb, c_emb) >= SIM_THRESHOLD:
                return json.loads(candidate["response_json"])
    return None


def cache_put(question: str, result: dict, domain: str = "", kb_id: str = "",
              embedding: list = None):
    """Store a result in the cache."""
    import time
    key  = make_cache_key(question, domain, kb_id)
    now  = datetime.now(timezone.utc).isoformat()
    item = {
        "cache_key":      key,
        "cache_domain":   domain or "all",
        "question":       question[:500],
        "response_json":  json.dumps(result, default=str),
        "embedding_json": json.dumps(embedding or []),
        "created_at":     now,
        "expires_at":     int(time.time()) + CACHE_TTL_S,
    }
    dynamodb.Table(CACHE_TABLE).put_item(Item=item)
```

### Wire Into Query Lambda

```python
# In answer_question() — before KB retrieval:

from governance import cache_get, cache_put, record_usage

cached = cache_get(question, domain="", kb_id=kb_id)
if cached:
    record_usage(MODEL_ID, 0, 0, caller=caller, operation="query", cache_hit=True)
    cached["cache_hit"] = True
    return cached

# ... existing KB retrieve + Claude synthesis ...

cache_put(question, result, kb_id=kb_id)
```

### Cache Config in SSM

```
/llmwiki/governance/cache_ttl_seconds      → 86400
/llmwiki/governance/cache_sim_threshold    → 0.92
/llmwiki/governance/cache_semantic_enabled → true
```

### DynamoDB Schema — `llmwiki-cache`

```hcl
resource "aws_dynamodb_table" "cache" {
  name         = "llmwiki-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "cache_key"

  attribute { name = "cache_key"    type = "S" }
  attribute { name = "cache_domain" type = "S" }
  attribute { name = "created_at"   type = "S" }

  global_secondary_index {
    name            = "domain_recency_index"
    hash_key        = "cache_domain"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  ttl { attribute_name = "expires_at" enabled = true }
  server_side_encryption { enabled = true }
}
```

---

## Pillar 3 — Rate Limiting

### Two Layers

**Layer A — API Gateway Usage Plans** (for human callers via Streamlit + direct API consumers):

```hcl
resource "aws_api_gateway_usage_plan" "llmwiki_default" {
  name = "llmwiki-default"

  throttle_settings {
    burst_limit = 10     # max concurrent requests
    rate_limit  = 2      # sustained requests/second
  }

  quota_settings {
    limit  = 500         # requests/day
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan" "llmwiki_agent" {
  name = "llmwiki-agent"

  throttle_settings {
    burst_limit = 20
    rate_limit  = 5
  }

  quota_settings {
    limit  = 2000        # higher quota for AgentCore skills
    period = "DAY"
  }
}
```

**Layer B — Per-Caller DynamoDB Counters** (for direct Lambda invocations from AgentCore, which bypass API Gateway):

```python
# In governance.py

RATE_TABLE = os.environ.get("RATE_TABLE", "llmwiki-rate-limits")

def check_rate_limit(caller: str, window_minutes: int = 1,
                     max_requests: int = 30) -> tuple[bool, dict]:
    """
    Sliding window counter using DynamoDB atomic ADD.
    Returns (allowed: bool, info: dict).
    """
    import time
    window_key = f"{caller}#{int(time.time() // (window_minutes * 60))}"
    table = dynamodb.Table(RATE_TABLE)

    resp = table.update_item(
        Key={"window_key": window_key},
        UpdateExpression="ADD #cnt :one SET #ttl = :exp",
        ExpressionAttributeNames={"#cnt": "count", "#ttl": "expires_at"},
        ExpressionAttributeValues={
            ":one": 1,
            ":exp": int(time.time()) + (window_minutes * 60 * 2),
        },
        ReturnValues="ALL_NEW",
    )
    count = int(resp["Attributes"]["count"])
    allowed = count <= max_requests
    return allowed, {"caller": caller, "count": count, "limit": max_requests,
                     "window_minutes": window_minutes}


def check_budget_ceiling(caller: str, daily_limit_usd: float = 5.0) -> bool:
    """Block caller if their daily spend already exceeds the configured ceiling."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    table = dynamodb.Table(USAGE_TABLE)
    resp = table.query(
        IndexName="date_caller_index",
        KeyConditionExpression="#d = :date AND #c = :caller",
        ExpressionAttributeNames={"#d": "date", "#c": "caller"},
        ExpressionAttributeValues={":date": today, ":caller": caller},
        ProjectionExpression="cost_usd",
    )
    total = sum(float(item.get("cost_usd", 0)) for item in resp.get("Items", []))
    return total < daily_limit_usd
```

### Wire Into Business Query Lambda

```python
# At the top of lambda_handler() in business_query/handler.py:

from governance import check_rate_limit, check_budget_ceiling

caller    = body.get("agent_id", event.get("requestContext", {}).get("identity", {}).get("sourceIp", "unknown"))
allowed, info = check_rate_limit(caller, window_minutes=1, max_requests=30)
if not allowed:
    return respond(429, {"error": "Rate limit exceeded", "detail": info})

if not check_budget_ceiling(caller, daily_limit_usd=5.0):
    return respond(429, {"error": "Daily cost ceiling reached", "detail": {"caller": caller}})
```

### Rate Limit Config in SSM

```
/llmwiki/governance/rate_limit_per_minute    → 30
/llmwiki/governance/daily_budget_usd_default → 5.0
/llmwiki/governance/daily_budget_usd_ingest  → 20.0
```

### DynamoDB Schema — `llmwiki-rate-limits`

```hcl
resource "aws_dynamodb_table" "rate_limits" {
  name         = "llmwiki-rate-limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "window_key"

  attribute { name = "window_key" type = "S" }

  ttl { attribute_name = "expires_at" enabled = true }
  server_side_encryption { enabled = true }
}
```

---

## Streamlit — Governance Page

Add a new page `streamlit/pages/governance.py`:

```python
import streamlit as st
import boto3, json
from datetime import datetime, timezone
from collections import defaultdict

st.set_page_config(page_title="Governance", page_icon="📊")
st.title("LLMWiki Governance")

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
USAGE_TABLE = "llmwiki-usage"

@st.cache_data(ttl=60)
def load_usage(days: int = 7):
    table = dynamodb.Table(USAGE_TABLE)
    items = table.scan().get("Items", [])
    return items

items = load_usage()
if not items:
    st.info("No usage data yet. Start querying the wiki to see cost metrics.")
    st.stop()

# Aggregate by date + caller
daily = defaultdict(float)
by_caller = defaultdict(float)
cache_hits = sum(1 for i in items if i.get("cache_hit"))
total_requests = len(items)

for i in items:
    daily[i["date"]] += float(i.get("cost_usd", 0))
    by_caller[i["caller"]] += float(i.get("cost_usd", 0))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Cost (all time)", f"${sum(daily.values()):.4f}")
col2.metric("Cache Hit Rate", f"{cache_hits/max(total_requests,1)*100:.1f}%")
col3.metric("Total Requests", total_requests)
col4.metric("Cost Saved (est.)", f"${cache_hits * 0.02:.4f}")

st.subheader("Daily Cost")
import pandas as pd
df_daily = pd.DataFrame(sorted(daily.items()), columns=["Date", "Cost (USD)"])
st.bar_chart(df_daily.set_index("Date"))

st.subheader("Cost by Caller")
df_caller = pd.DataFrame(sorted(by_caller.items(), key=lambda x: -x[1]),
                          columns=["Caller", "Cost (USD)"])
st.dataframe(df_caller, use_container_width=True)
```

---

## Implementation Checklist

### Phase A — Cost Tracking (1 day)
- [ ] Create `lambda/common/governance.py` with `record_usage()`
- [ ] Add `llmwiki-usage` DynamoDB table to `terraform/dynamodb.tf`
- [ ] Wire `record_usage()` into `query/handler.py`, `business_query/handler.py`, `ingest/handler.py`
- [ ] Add IAM `dynamodb:PutItem` permission on `llmwiki-usage` to Lambda execution role
- [ ] Add `streamlit/pages/governance.py` Governance page
- [ ] Deploy and validate: run a query, check DynamoDB for cost row

### Phase B — Caching (1 day)
- [ ] Add `cache_get()` / `cache_put()` to `governance.py`
- [ ] Add `llmwiki-cache` DynamoDB table to `terraform/dynamodb.tf`
- [ ] Wire cache check into `query/handler.py::answer_question()` and `business_query/handler.py`
- [ ] Add SSM params for cache config
- [ ] Add IAM permissions on `llmwiki-cache`
- [ ] Test: run same question twice, confirm second call shows `cache_hit: true`

### Phase C — Rate Limiting (half day)
- [ ] Add `check_rate_limit()` / `check_budget_ceiling()` to `governance.py`
- [ ] Add `llmwiki-rate-limits` DynamoDB table to `terraform/dynamodb.tf`
- [ ] Wire into `business_query/handler.py` entry point
- [ ] Add API Gateway usage plans in `terraform/api_gateway_business.tf`
- [ ] Add SSM params for limit config
- [ ] Test: fire 31 requests in 1 minute, confirm 31st returns 429

---

## Cost Impact Estimate

| Scenario | Without Governance | With Caching (60% hit rate) |
|----------|--------------------|------------------------------|
| 1,000 queries/day | ~$15–30/day | ~$6–12/day |
| 10 AgentCore UC agents active | Unbounded | Capped by budget ceiling |
| Runaway skill loop (500 calls) | ~$75 undetected | Blocked at 30/min |

The embedding cost for semantic cache lookup (`Titan v2: $0.0002/1K tokens`) is ~100x cheaper than a cache miss, making semantic caching clearly net-positive at any scale.

---

## E2E Testing — Playwright UI Test

### Test file
`/tmp/governance_e2e_test.py`

Run it after deploying any governance phase:

```bash
python3 /tmp/governance_e2e_test.py
```

### What the test covers (7 checks)

| # | Test | Phase required |
|---|------|---------------|
| 1 | Governance page loads, title visible, sidebar link present | Streamlit deploy |
| 2 | Ask a question → Requests metric increases, Total Cost > $0, request row in table | Phase A |
| 3 | Ask same question again → Cache Hit Rate metric appears, `✅` row visible in table | Phase B |
| 4 | Cache Health section renders with Live/Expired metrics | Phase B |
| 5 | Day-range slider in sidebar changes displayed data without crashing | Streamlit deploy |
| 6 | Refresh button clears cache and page re-renders correctly | Streamlit deploy |
| 7 | Governance sidebar link navigates to the Governance page | Streamlit deploy |

### Selector reference for this page

| Element | Selector |
|---------|---------|
| KPI metrics | `[data-testid='stMetric']` |
| Metric label | `[data-testid='stMetricLabel']` |
| Metric value | `[data-testid='stMetricValue']` |
| Day slider | `[data-testid='stSidebar'] [data-testid='stSlider']` |
| Recent requests table | `[data-testid='stMain'] table` |
| Refresh button | `button` matching `"Refresh metrics"` |
| Governance sidebar link | `[data-testid='stSidebar'] a[href*='governance']` |

### Expected test output (all phases deployed)

```
============================================================
  LLMWiki Governance E2E Test
  Target: http://llmwiki-alb-1382316210.us-east-1.elb.amazonaws.com
============================================================

→ Test 1 — Governance page structure
  ✓ Title visible
  ✓ Page renders content (metrics or info)
  ✓ Governance sidebar link present

→ Test 2 — Ask question → usage row tracked
  ✓ Ask question succeeds
  ✓ Usage row recorded (Requests > 0) — Requests = 1
  ✓ Total cost > $0 after query — Cost = $0.00420
  ✓ Recent requests table has rows — 1 rows

→ Test 3 — Repeat question → cache hit tracked
  ✓ Second ask (cache candidate) succeeds
  ✓ Cache Hit Rate metric exists on page
  ✓ Cache hit row (✅) visible in recent requests table

→ Test 4 — Cache health section
  ✓ Cache Health section rendered
  ✓ Live cache entries metric present

→ Test 5 — Day-range slider interaction
  ✓ Day-range slider present in sidebar
  ✓ Slider click accepted (no crash)

→ Test 6 — Refresh button
  ✓ Refresh button present
  ✓ Page still renders after Refresh click

→ Test 7 — Sidebar navigation to Governance
  ✓ Governance link navigates correctly

============================================================
  Results (17 checks)
============================================================
  17/17 passed  |  0 failed
```

### Phased failures (expected before full rollout)

| Failure | Root cause | Fix |
|---------|-----------|-----|
| "Usage row recorded" fails | Phase A not deployed | Deploy `governance.py`, `llmwiki-usage` table, wire `record_usage()` |
| "Cache hit row (✅)" fails | Phase B not deployed | Deploy cache tables + `cache_get/put()` wiring |
| "Live cache entries" fails | Phase B not deployed | Same as above |
| "Governance sidebar link" fails | `app.py` not redeployed | Rebuild + push Streamlit Docker image |

### Redeploying Streamlit after changes

```bash
cd "/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code"
docker build -f streamlit/Dockerfile -t llmwiki-streamlit:latest .
aws ecr get-login-password --region us-east-1 --profile tzg-sandbox \
  | docker login --username AWS --password-stdin 392568849512.dkr.ecr.us-east-1.amazonaws.com
docker tag llmwiki-streamlit:latest \
  392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-streamlit:latest
docker push 392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-streamlit:latest
aws ecs update-service \
  --cluster llmwiki-cluster --service llmwiki-streamlit \
  --force-new-deployment --profile tzg-sandbox
aws ecs wait services-stable \
  --cluster llmwiki-cluster --services llmwiki-streamlit --profile tzg-sandbox
```

---

## Relation to AgentCore Skill Architecture

| AgentCore Concern | Governance Contribution |
|-------------------|------------------------|
| UC1 → UC2 sequential handoff | Cache carries UC1 answers into UC2's context queries for free |
| 10 skills × multiple invocations | Per-skill cost attribution via `agent_id` in `caller` field |
| Gap detection on every low-confidence query | Cache prevents redundant gap-detection calls for repeated queries |
| `wiki_ask` MCP tool | Rate limit enforcement inside `business_query` Lambda before any Bedrock call |
| Agentic loops (e.g. claim readiness checking) | Budget ceiling breaks infinite loops before they cost real money |

*The governance module is a shared library — import it from any existing or new Lambda without changing the Lambda's business logic beyond adding 3–5 lines.*
