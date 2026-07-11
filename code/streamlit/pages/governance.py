"""
LLMWiki Governance — Cost Tracking, Cache Hit Rate, Rate Limit Monitoring.
Prerequisites: llmwiki-usage and llmwiki-cache DynamoDB tables must exist (Phase A/B of governance rollout).
"""

import os
import json
import boto3
import streamlit as st
from boto3.dynamodb.conditions import Attr
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

AWS_REGION  = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "llmwiki-usage")
CACHE_TABLE = os.environ.get("CACHE_TABLE", "llmwiki-cache")
RATE_TABLE  = os.environ.get("RATE_TABLE",  "llmwiki-rate-limits")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

st.set_page_config(page_title="Governance — LLMWiki", page_icon="📊", layout="wide")
st.title("📊 LLMWiki Governance")
st.caption("Cost tracking · Semantic caching · Rate limiting · Per-caller attribution")

# ── Helpers ────────────────────────────────────────────────────────

def _float(v):
    try:
        return float(v)
    except Exception:
        return 0.0


LOG_TABLE = os.environ.get("DYNAMODB_LOG", "llmwiki-log")


@st.cache_data(ttl=60)
def load_usage_items(days: int = 30) -> list:
    """
    Load usage rows from llmwiki-usage (primary) or llmwiki-log fallback.
    Governance rows in llmwiki-log have log_date starting with 'governance#usage#'.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Try primary usage table
    try:
        table = dynamodb.Table(USAGE_TABLE)
        items = []
        resp  = table.scan()
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        filtered = [i for i in items if i.get("date", "9999") >= cutoff]
        if filtered:
            return filtered
    except Exception:
        pass  # fall through to log table

    # Fallback: read governance rows from llmwiki-log
    try:
        log_table = dynamodb.Table(LOG_TABLE)
        items = []
        resp = log_table.scan(
            FilterExpression=Attr("log_date").begins_with("governance#usage#"),
        )
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = log_table.scan(
                FilterExpression=Attr("log_date").begins_with("governance#usage#"),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))
        filtered = [i for i in items if i.get("date", "9999") >= cutoff]
        if filtered:
            return filtered
    except Exception as e:
        return [{"__error__": str(e)}]

    return []


@st.cache_data(ttl=60)
def load_cache_stats() -> dict:
    """Count total cache entries and how many are still live (not expired)."""
    try:
        table = dynamodb.Table(CACHE_TABLE)
        resp  = table.scan(ProjectionExpression="cache_key, expires_at")
        items = resp.get("Items", [])
        now_ts = int(datetime.now(timezone.utc).timestamp())
        live  = sum(1 for i in items if int(i.get("expires_at", 0)) > now_ts)
        return {"total_entries": len(items), "live_entries": live}
    except Exception:
        return {"total_entries": 0, "live_entries": 0}


# ── Load data ──────────────────────────────────────────────────────

days_filter = st.sidebar.slider("Show last N days", 1, 90, 30)
items = load_usage_items(days_filter)

errors = [i for i in items if "__error__" in i]
if errors:
    st.error(f"Could not load usage table: {errors[0]['__error__']}. "
             "Ensure the governance Lambda modules are deployed (Phase A).")
    st.stop()

if not items:
    st.info(
        "No usage data yet. Run a query via **Ask a Question** to see cost metrics appear here.  \n"
        "If you have just deployed Phase A governance, the first row will appear after the next query."
    )
    st.stop()

# ── Aggregate ──────────────────────────────────────────────────────

total_cost    = sum(_float(i.get("cost_usd", 0)) for i in items)
total_req     = len(items)
cache_hits    = sum(1 for i in items if i.get("cache_hit"))
total_input   = sum(int(i.get("input_tokens", 0)) for i in items)
total_output  = sum(int(i.get("output_tokens", 0)) for i in items)

hit_rate_pct  = (cache_hits / max(total_req, 1)) * 100
cost_saved    = cache_hits * 0.02   # rough estimate: avg $0.02 saved per cache hit

by_date   = defaultdict(float)
by_caller = defaultdict(float)
by_op     = defaultdict(float)
by_model  = defaultdict(int)

for i in items:
    by_date[i.get("date", "unknown")]   += _float(i.get("cost_usd", 0))
    by_caller[i.get("caller", "unknown")] += _float(i.get("cost_usd", 0))
    by_op[i.get("operation", "unknown")]  += _float(i.get("cost_usd", 0))
    by_model[i.get("model_id", "unknown")] += 1

cache_meta = load_cache_stats()

# ── KPI row ────────────────────────────────────────────────────────

st.markdown("### Summary")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Cost", f"${total_cost:.4f}", help="Bedrock Converse charges, last N days")
k2.metric("Requests",    total_req)
k3.metric("Cache Hit Rate", f"{hit_rate_pct:.1f}%",
          delta=f"${cost_saved:.2f} saved" if cost_saved > 0 else None)
k4.metric("Input Tokens",  f"{total_input:,}")
k5.metric("Output Tokens", f"{total_output:,}")
k6.metric("Live Cache Entries", cache_meta["live_entries"],
          help="Unexpired entries in llmwiki-cache (24h TTL)")

st.divider()

# ── Charts ─────────────────────────────────────────────────────────

import pandas as pd

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("#### Daily Cost (USD)")
    if by_date:
        df_d = pd.DataFrame(
            sorted(by_date.items()), columns=["Date", "Cost (USD)"]
        ).set_index("Date")
        st.bar_chart(df_d)
    else:
        st.caption("No daily data.")

with col_right:
    st.markdown("#### Cost by Caller")
    if by_caller:
        df_c = pd.DataFrame(
            sorted(by_caller.items(), key=lambda x: -x[1]),
            columns=["Caller", "Cost (USD)"]
        ).set_index("Caller")
        st.bar_chart(df_c)
    else:
        st.caption("No caller data.")

col_op, col_mod = st.columns(2)

with col_op:
    st.markdown("#### Cost by Operation")
    if by_op:
        df_o = pd.DataFrame(
            sorted(by_op.items(), key=lambda x: -x[1]),
            columns=["Operation", "Cost (USD)"]
        ).set_index("Operation")
        st.bar_chart(df_o)

with col_mod:
    st.markdown("#### Requests by Model")
    if by_model:
        df_m = pd.DataFrame(
            sorted(by_model.items(), key=lambda x: -x[1]),
            columns=["Model", "Requests"]
        ).set_index("Model")
        st.bar_chart(df_m)

st.divider()

# ── Raw request table ──────────────────────────────────────────────

st.markdown("#### Recent Requests")
show_count = st.slider("Rows to show", 10, 200, 50)
sorted_items = sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)[:show_count]

rows = []
for i in sorted_items:
    rows.append({
        "Timestamp":    i.get("timestamp", "")[:19],
        "Caller":       i.get("caller", ""),
        "Operation":    i.get("operation", ""),
        "Model":        i.get("model_id", "")[-20:],   # truncate long model IDs
        "Input Tok":    int(i.get("input_tokens", 0)),
        "Output Tok":   int(i.get("output_tokens", 0)),
        "Cost ($)":     f"{_float(i.get('cost_usd', 0)):.5f}",
        "Cache Hit":    "✅" if i.get("cache_hit") else "—",
    })

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.caption("No requests in selected period.")

# ── Cache health ───────────────────────────────────────────────────

st.divider()
st.markdown("#### Cache Health")

cc1, cc2, cc3 = st.columns(3)
cc1.metric("Total Cache Entries (all time)", cache_meta["total_entries"])
cc2.metric("Live (unexpired)",               cache_meta["live_entries"])
cc3.metric("Expired / Evicted",
           cache_meta["total_entries"] - cache_meta["live_entries"])

st.caption(
    "Cache TTL is 24 hours (configurable via `/llmwiki/governance/cache_ttl_seconds` SSM parameter).  \n"
    "Semantic similarity threshold: 0.92 (configurable via `/llmwiki/governance/cache_sim_threshold`)."
)

# ── Refresh button ─────────────────────────────────────────────────
st.divider()
if st.button("↺ Refresh metrics", type="secondary"):
    st.cache_data.clear()
    st.rerun()
