"""
LLMWiki — Platform
Operations view: Cost & Usage, Governance, Configuration.
Not customer-facing.
"""

import json
import os
import time
import boto3
import streamlit as st
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from collections import defaultdict
from datetime import datetime, timezone, timedelta

# ── set_page_config MUST be first Streamlit call ──────────────────
st.set_page_config(
    page_title="Platform — LLMWiki",
    page_icon="⚙️",
    layout="wide",
)

# ── Configuration ──────────────────────────────────────────────────
_AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
USAGE_TABLE    = os.environ.get("USAGE_TABLE",    "llmwiki-usage")
CACHE_TABLE    = os.environ.get("CACHE_TABLE",    "llmwiki-cache")
RATE_TABLE     = os.environ.get("RATE_TABLE",     "llmwiki-rate-limits")
DYNAMODB_LOG   = os.environ.get("DYNAMODB_LOG",   "llmwiki-log")
WIKI_BUCKET    = os.environ.get("WIKI_BUCKET",    "llmwiki-278e7e22")
PM_WIKI_BUCKET = os.environ.get("PM_WIKI_BUCKET", "llmwiki-problem-mgnt-278e7e22")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "llmwiki-source-registry")
GAPS_TABLE     = os.environ.get("GAPS_TABLE",     "llmwiki-gaps")
QUERY_LAMBDA   = os.environ.get("QUERY_LAMBDA",   "llmwiki-query")

_dynamodb = boto3.resource("dynamodb", region_name=_AWS_REGION)
_lambda   = boto3.client("lambda", region_name=_AWS_REGION)
_s3       = boto3.client("s3", region_name=_AWS_REGION, config=Config(signature_version="s3v4"))

_HEALTH_FUNCTIONS = [
    "llmwiki-query",
    "llmwiki-ingest",
    "llmwiki-converter",
    "llmwiki-gatekeeper",
    "llmwiki-skill-context-bootstrap",
]

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Platform")

# ── Page title ─────────────────────────────────────────────────────
st.title("⚙️ Platform")
st.caption("Operations view — Cost & Usage, Governance, Configuration.")

tab_cost, tab_gov, tab_config = st.tabs([
    "📊 Cost & Usage",
    "🔒 Governance",
    "🔧 Configuration",
])

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _float(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _lambda_invoke(fn: str, payload: dict) -> dict:
    try:
        resp = _lambda.invoke(
            FunctionName=fn,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload, default=str).encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if raw.get("FunctionError"):
            return {"_error": True, "error": str(raw)}
        body = raw.get("body", raw)
        return json.loads(body) if isinstance(body, str) else (body or {})
    except Exception as e:
        return {"_error": True, "error": str(e)}


def _fmt_size(n: int) -> str:
    if n < 1024:        return f"{n} B"
    if n < 1_048_576:   return f"{n/1024:.1f} KB"
    return f"{n/1_048_576:.1f} MB"


def _friendly(key: str) -> str:
    import re
    base = key.split("/")[-1]
    stem = re.sub(r"\.[^.]+$", "", base)
    return re.sub(r"[-_]+", " ", stem).title()


# ══════════════════════════════════════════════════════════════════
# TAB 1 — COST & USAGE  (sourced from governance.py)
# ══════════════════════════════════════════════════════════════════
with tab_cost:
    import pandas as pd

    days_filter = st.slider("Show last N days", 1, 90, 30, key="plat_days")

    @st.cache_data(ttl=60)
    def _load_usage(days: int) -> list:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        # Try primary usage table
        try:
            tbl = _dynamodb.Table(USAGE_TABLE)
            items, resp = [], tbl.scan()
            items.extend(resp.get("Items", []))
            while "LastEvaluatedKey" in resp:
                resp = tbl.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items.extend(resp.get("Items", []))
            filtered = [i for i in items if i.get("date", "9999") >= cutoff]
            if filtered:
                return filtered
        except Exception:
            pass
        # Fallback: governance rows in llmwiki-log
        try:
            log_tbl = _dynamodb.Table(DYNAMODB_LOG)
            items, resp = [], log_tbl.scan(
                FilterExpression=Attr("log_date").begins_with("governance#usage#")
            )
            items.extend(resp.get("Items", []))
            while "LastEvaluatedKey" in resp:
                resp = log_tbl.scan(
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
    def _load_cache_stats() -> dict:
        try:
            tbl   = _dynamodb.Table(CACHE_TABLE)
            resp  = tbl.scan(ProjectionExpression="cache_key, expires_at")
            items = resp.get("Items", [])
            now_ts = int(datetime.now(timezone.utc).timestamp())
            live  = sum(1 for i in items if int(i.get("expires_at", 0)) > now_ts)
            return {"total": len(items), "live": live}
        except Exception:
            return {"total": 0, "live": 0}

    items = _load_usage(days_filter)
    errors = [i for i in items if "__error__" in i]

    if errors:
        st.error(
            f"Could not load usage table: {errors[0]['__error__']}. "
            "Ensure the governance Lambda modules are deployed."
        )
    elif not items:
        st.info(
            "No usage data yet. Run a query via Ask a Question to see cost metrics here. "
            "Data appears after the first query once Phase A governance is deployed."
        )
    else:
        total_cost   = sum(_float(i.get("cost_usd", 0)) for i in items)
        total_req    = len(items)
        cache_hits   = sum(1 for i in items if i.get("cache_hit"))
        total_input  = sum(int(i.get("input_tokens", 0)) for i in items)
        total_output = sum(int(i.get("output_tokens", 0)) for i in items)
        hit_rate_pct = (cache_hits / max(total_req, 1)) * 100
        cost_saved   = cache_hits * 0.02

        cache_meta = _load_cache_stats()

        with st.container(border=True):
            st.markdown("**Summary**")
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("Total Cost",        f"${total_cost:.4f}")
            k2.metric("Requests",           total_req)
            k3.metric("Cache Hit Rate",     f"{hit_rate_pct:.1f}%",
                      delta=f"${cost_saved:.2f} saved" if cost_saved > 0 else None)
            k4.metric("Input Tokens",       f"{total_input:,}")
            k5.metric("Output Tokens",      f"{total_output:,}")
            k6.metric("Live Cache Entries", cache_meta["live"])

        by_date   = defaultdict(float)
        by_caller = defaultdict(float)
        by_op     = defaultdict(float)
        by_model  = defaultdict(int)
        for i in items:
            by_date[i.get("date", "unknown")]     += _float(i.get("cost_usd", 0))
            by_caller[i.get("caller", "unknown")] += _float(i.get("cost_usd", 0))
            by_op[i.get("operation", "unknown")]  += _float(i.get("cost_usd", 0))
            by_model[i.get("model_id", "unknown")] += 1

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("#### Daily Cost (USD)")
            if by_date:
                df_d = pd.DataFrame(sorted(by_date.items()), columns=["Date", "Cost (USD)"]).set_index("Date")
                st.bar_chart(df_d)
        with col_r:
            st.markdown("#### Cost by Caller")
            if by_caller:
                df_c = pd.DataFrame(
                    sorted(by_caller.items(), key=lambda x: -x[1]),
                    columns=["Caller", "Cost (USD)"]
                ).set_index("Caller")
                st.bar_chart(df_c)

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
        st.markdown("#### Recent Requests")
        show_count = st.slider("Rows to show", 10, 200, 50, key="plat_rows")
        sorted_items = sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)[:show_count]
        rows = []
        for i in sorted_items:
            rows.append({
                "Timestamp":  i.get("timestamp", "")[:19],
                "Caller":     i.get("caller", ""),
                "Operation":  i.get("operation", ""),
                "Model":      i.get("model_id", "")[-20:],
                "Input Tok":  int(i.get("input_tokens", 0)),
                "Output Tok": int(i.get("output_tokens", 0)),
                "Cost ($)":   f"{_float(i.get('cost_usd', 0)):.5f}",
                "Cache Hit":  "✅" if i.get("cache_hit") else "—",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        with st.container(border=True):
            st.markdown("**Cache Health**")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Total Cache Entries",  cache_meta["total"])
            cc2.metric("Live (unexpired)",      cache_meta["live"])
            cc3.metric("Expired / Evicted",     cache_meta["total"] - cache_meta["live"])
            st.caption(
                "Cache TTL: 24 h (SSM `/llmwiki/governance/cache_ttl_seconds`). "
                "Similarity threshold: 0.92 (SSM `/llmwiki/governance/cache_sim_threshold`)."
            )

    if st.button("↺ Refresh metrics", key="plat_refresh_cost"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 2 — GOVERNANCE
# ══════════════════════════════════════════════════════════════════
with tab_gov:
    import pandas as pd
    import re as _re

    # ── Bucket selector ────────────────────────────────────────────
    _AGENT_BUCKETS = [
        {"label": "Sales-to-Service Wiki",   "env": "WIKI_BUCKET",    "default": WIKI_BUCKET,    "icon": "📚"},
        {"label": "Problem Management Wiki", "env": "PM_WIKI_BUCKET", "default": PM_WIKI_BUCKET, "icon": "🛠️"},
    ]
    agent_labels = [f"{a['icon']} {a['label']}" for a in _AGENT_BUCKETS]
    sel_idx = st.selectbox(
        "Knowledge base",
        range(len(_AGENT_BUCKETS)),
        format_func=lambda i: agent_labels[i],
        key="plat_bucket_sel",
        label_visibility="collapsed",
    )
    _agent = _AGENT_BUCKETS[sel_idx]
    _bucket_name = os.environ.get(_agent["env"], _agent["default"])

    gov_kb, gov_activity, gov_gaps = st.tabs([
        "📚 Source Registry",
        "📋 Activity Log",
        "🔭 Knowledge Gaps",
    ])

    # ── Source Registry ────────────────────────────────────────────
    with gov_kb:
        st.caption("Source documents and wiki pages generated from each. Delete removes all derived pages.")

        col_hdr, col_ref = st.columns([6, 1])
        if col_ref.button("↺ Refresh", key="plat_kb_refresh"):
            st.rerun()

        if "plat_confirm_slug" not in st.session_state:
            st.session_state.plat_confirm_slug = None

        @st.cache_data(ttl=30)
        def _registry_items(limit: int = 200) -> list:
            try:
                tbl   = _dynamodb.Table(REGISTRY_TABLE)
                items = []
                resp  = tbl.scan(Limit=limit)
                items.extend(resp.get("Items", []))
                while "LastEvaluatedKey" in resp and len(items) < limit:
                    resp = tbl.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], Limit=limit - len(items))
                    items.extend(resp.get("Items", []))
                return items
            except Exception:
                return []

        PAGE_TYPE_LABELS = {
            "sources":   ("📑", "Summary"),
            "entities":  ("🏢", "Entity"),
            "concepts":  ("💡", "Concept"),
            "questions": ("❓", "Gap"),
            "runbooks":  ("📋", "Runbook"),
            "customers": ("👤", "Customer"),
            "decisions": ("⚖️", "Decision"),
            "sops":      ("📌", "SOP"),
            "evidence":  ("🔒", "Evidence"),
            "artifacts": ("📦", "Artifact"),
        }

        def _presign(bucket: str, key: str) -> str:
            try:
                return _s3.generate_presigned_url(
                    "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
                )
            except Exception:
                return ""

        def _do_cascade_delete(bucket: str, source_key: str, info: dict) -> dict:
            deleted_s3, deleted_ddb, errors = [], 0, []
            orig_key = info.get("original_upload", "")
            keys_to_delete = [source_key]
            if orig_key and orig_key != source_key:
                keys_to_delete.append(orig_key)
            if info.get("raw_assets") and info["raw_assets"] not in keys_to_delete:
                keys_to_delete.append(info["raw_assets"])
            ddb_pairs = []
            for page_path in info.get("pages_created", []):
                parts = page_path.split("/", 1)
                if len(parts) == 2:
                    page_type, page_slug = parts
                    keys_to_delete.append(f"wiki/{page_type}/{page_slug}.md")
                    ddb_pairs.append((page_type, page_slug))
            for key in keys_to_delete:
                try:
                    _s3.delete_object(Bucket=bucket, Key=key)
                    deleted_s3.append(key)
                except Exception as e:
                    errors.append(f"S3 {key}: {e}")
            idx_tbl = _dynamodb.Table(os.environ.get("DYNAMODB_INDEX", "llmwiki-index"))
            for page_type, page_slug in ddb_pairs:
                try:
                    idx_tbl.delete_item(Key={"page_type": page_type, "page_slug": page_slug})
                    deleted_ddb += 1
                except Exception as e:
                    errors.append(f"DDB {page_type}/{page_slug}: {e}")
            try:
                _dynamodb.Table(REGISTRY_TABLE).delete_item(Key={"source_id": info["slug"]})
            except Exception as e:
                errors.append(f"Registry {info['slug']}: {e}")
            return {"deleted_s3": deleted_s3, "deleted_ddb": deleted_ddb, "errors": errors}

        reg_items = _registry_items()
        if not reg_items:
            st.info("No documents processed yet. Upload a document via Wiki Manager to get started.")
        else:
            reg_items.sort(key=lambda x: x.get("ingested_at", ""), reverse=True)
            for item in reg_items:
                source_id    = item.get("source_id", "")
                source_key   = item.get("source_key", item.get("original_upload_key", source_id))
                orig_key     = item.get("original_upload_key", source_key)
                pages        = item.get("pages_created", [])
                ingested     = item.get("ingested_at", "")[:10]
                n_pages      = len(pages)
                status       = item.get("status", "unknown")
                display_name = _friendly(orig_key or source_key)
                file_ext     = (orig_key or source_key).rsplit(".", 1)[-1].upper() if "." in (orig_key or source_key) else "DOC"
                is_deleting  = (st.session_state.plat_confirm_slug == source_id)

                if is_deleting:
                    with st.container(border=True):
                        st.warning(f"Delete **{display_name}** and all {n_pages} derived wiki pages?")
                        items_to_delete = []
                        if source_key:
                            items_to_delete.append(("📄", "Source file", source_key))
                        if orig_key and orig_key != source_key:
                            items_to_delete.append(("📎", "Original upload", orig_key))
                        for page_path in pages:
                            parts = page_path.split("/", 1)
                            if len(parts) == 2:
                                pt, ps = parts
                                icon, label = PAGE_TYPE_LABELS.get(pt, ("📄", pt.title()))
                                items_to_delete.append((icon, f"{label} page", f"wiki/{pt}/{ps}.md"))
                        for icon, label, key in items_to_delete[:8]:
                            st.caption(f"{icon} {label} — `{key}`")
                        if len(items_to_delete) > 8:
                            st.caption(f"… and {len(items_to_delete) - 8} more")
                        dc1, dc2 = st.columns(2)
                        if dc1.button(
                            f"🗑 Delete all {len(items_to_delete)} items",
                            type="primary",
                            key=f"plat_del_confirm_{source_id}",
                        ):
                            cascade_info = {
                                "slug": source_id,
                                "pages_created": pages,
                                "original_upload": orig_key,
                                "raw_assets": item.get("raw_assets_key", ""),
                            }
                            with st.spinner("Deleting…"):
                                result = _do_cascade_delete(_bucket_name, source_key, cascade_info)
                            if result["errors"]:
                                st.warning(f"Deleted with warnings: {'; '.join(result['errors'][:2])}")
                            else:
                                st.success(
                                    f"Deleted {display_name} — "
                                    f"{len(result['deleted_s3'])} files, {result['deleted_ddb']} index entries."
                                )
                            st.session_state.plat_confirm_slug = None
                            time.sleep(0.5)
                            st.rerun()
                        if dc2.button("Cancel", key=f"plat_del_cancel_{source_id}"):
                            st.session_state.plat_confirm_slug = None
                            st.rerun()
                    continue

                with st.container():
                    c_info, c_actions = st.columns([6, 1])
                    with c_info:
                        status_dot = "🟢" if status == "wiki-page-created" else "🟡"
                        st.markdown(
                            f"**{display_name}** "
                            f"<span style='background:#e5e7eb;color:#374151;border-radius:4px;"
                            f"padding:1px 7px;font-size:.78em;'>{file_ext}</span> {status_dot}",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Ingested {ingested} · {n_pages} wiki page{'s' if n_pages != 1 else ''}")
                        if pages:
                            chips = ""
                            for page_path in pages[:6]:
                                parts = page_path.split("/", 1)
                                if len(parts) == 2:
                                    pt, ps = parts
                                    icon, label = PAGE_TYPE_LABELS.get(pt, ("📄", pt.title()))
                                    chips += (
                                        f"<span style='display:inline-block;background:#e8f4ed;"
                                        f"color:#1a5c35;border:1px solid #b5ddc5;border-radius:10px;"
                                        f"padding:2px 9px;font-size:.75em;margin:2px;'>"
                                        f"{icon} {_friendly(ps)}</span>"
                                    )
                            if len(pages) > 6:
                                chips += (
                                    f"<span style='font-size:.75em;color:#6b7280;margin-left:4px'>"
                                    f"+{len(pages)-6} more</span>"
                                )
                            st.markdown(chips, unsafe_allow_html=True)
                    with c_actions:
                        url = _presign(_bucket_name, source_key)
                        if url:
                            st.markdown(
                                f'<a href="{url}" target="_blank" style="display:block;text-align:center;'
                                f'padding:4px 8px;border-radius:4px;background:#f3f4f6;color:#374151;'
                                f'font-size:.8em;text-decoration:none;margin-bottom:6px;">⬇ Download</a>',
                                unsafe_allow_html=True,
                            )
                        if st.button("🗑", key=f"plat_del_start_{source_id}",
                                     help="Delete document and all generated pages"):
                            st.session_state.plat_confirm_slug = source_id
                            st.rerun()
                    st.divider()

    # ── Activity Log ───────────────────────────────────────────────
    with gov_activity:
        st.caption("Ingest operations completed today.")
        col_ah, col_ar = st.columns([6, 1])
        if col_ar.button("↺ Refresh", key="plat_act_refresh"):
            st.rerun()

        def _recent_log(limit: int = 30) -> list:
            try:
                tbl   = _dynamodb.Table(DYNAMODB_LOG)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                resp  = tbl.query(
                    KeyConditionExpression="log_date = :d",
                    FilterExpression="#op = :ingest",
                    ExpressionAttributeNames={"#op": "operation"},
                    ExpressionAttributeValues={":d": today, ":ingest": "ingest"},
                    Limit=200,
                    ScanIndexForward=False,
                )
                return resp.get("Items", [])[:limit]
            except Exception as e:
                return [{"_error": str(e)}]

        log = _recent_log(limit=30)
        if not log:
            st.info("No processing activity today.")
        elif "_error" in log[0]:
            st.warning(f"Could not read activity log: {log[0]['_error']}")
        else:
            for entry in log:
                ts_raw  = entry.get("timestamp_id", "")
                ts      = ts_raw.split("#")[0][:16].replace("T", " ") if ts_raw else "—"
                src     = entry.get("source_slug", entry.get("source_key", "unknown"))
                pages   = entry.get("pages_created", [])
                n_pages = len(pages)
                ok      = n_pages > 0
                lc1, lc2 = st.columns([6, 1])
                with lc1:
                    st.markdown(
                        f"{'✅' if ok else '⚠️'} **{_friendly(src)}** — "
                        f"{'Generated ' + str(n_pages) + ' page' + ('s' if n_pages != 1 else '') if ok else 'No pages generated'}"
                        f"<span style='color:#6b7280;font-size:.83em;margin-left:8px;'>{ts} UTC</span>",
                        unsafe_allow_html=True,
                    )
                    if pages:
                        names = "  ·  ".join(_friendly(p.split("/")[-1]) for p in pages[:4])
                        extra = f"  + {len(pages)-4} more" if len(pages) > 4 else ""
                        st.caption(f"{names}{extra}")
                lc2.caption(ts.split(" ")[1] if " " in ts else "")
                st.divider()

    # ── Knowledge Gaps ─────────────────────────────────────────────
    with gov_gaps:
        st.caption("Knowledge gaps recorded by GapDetection (SK-05).")

        col_gh, col_gr = st.columns([6, 1])
        status_filter = col_gh.selectbox(
            "Status filter",
            ["All", "suggested", "acknowledged", "resolved"],
            key="plat_gap_status",
            label_visibility="collapsed",
        )
        if col_gr.button("↺ Refresh", key="plat_gaps_refresh"):
            st.rerun()

        def _get_gaps(sf: str = None, limit: int = 100) -> list:
            payload: dict = {"action": "get_gaps", "limit": limit}
            if sf and sf != "All":
                payload["status_filter"] = sf
            try:
                resp = _lambda.invoke(
                    FunctionName=QUERY_LAMBDA,
                    InvocationType="RequestResponse",
                    Payload=json.dumps(payload).encode(),
                )
                raw = json.loads(resp["Payload"].read())
                body = raw.get("body", raw)
                parsed = json.loads(body) if isinstance(body, str) else (body or {})
                return parsed.get("gaps", [])
            except Exception as e:
                return [{"_error": str(e)}]

        gaps = _get_gaps(status_filter)

        if not gaps:
            st.info("No knowledge gaps recorded yet.")
        elif "_error" in gaps[0]:
            st.warning(f"Could not load gaps: {gaps[0]['_error']}")
        else:
            blocking     = [g for g in gaps if g.get("blocking")]
            non_blocking = [g for g in gaps if not g.get("blocking")]
            g_col1, g_col2, g_col3 = st.columns(3)
            g_col1.metric("Total Gaps",   len(gaps))
            g_col2.metric("Blocking",     len(blocking),
                          delta=f"{len(blocking)} critical" if blocking else None,
                          delta_color="inverse")
            g_col3.metric("Non-blocking", len(non_blocking))

            GAP_ICON     = {"entity": "🏢", "concept": "💡", "question": "❓"}
            STATUS_COLOR = {
                "suggested":    "#d97706",
                "acknowledged": "#1a6bbd",
                "resolved":     "#16a34a",
            }

            for gap in gaps:
                g_type      = gap.get("gap_type", "question")
                g_status    = gap.get("status", "suggested")
                g_block     = gap.get("blocking", False)
                g_title     = gap.get("title", gap.get("gap_title", "Untitled gap"))
                g_rationale = gap.get("gap_rationale", gap.get("rationale", ""))
                g_uc        = gap.get("use_case", "")
                g_cust      = gap.get("customer_id", "")
                color       = STATUS_COLOR.get(g_status, "#6b7280")
                border_left = "#dc2626" if g_block else color

                st.markdown(
                    f"<div style='border-left:4px solid {border_left};background:#f8fafc;"
                    f"border-radius:8px;padding:10px 16px;margin:6px 0;'>"
                    f"<span style='font-weight:700;'>{GAP_ICON.get(g_type, '📌')} {g_title}</span>"
                    f"{'  🔴 <b>BLOCKING</b>' if g_block else ''}"
                    f"<span style='background:{color};color:#fff;border-radius:6px;"
                    f"padding:2px 8px;font-size:.75em;margin-left:10px;'>{g_status}</span>"
                    f"<span style='background:#e5e7eb;color:#374151;border-radius:6px;"
                    f"padding:2px 8px;font-size:.75em;margin-left:6px;'>{g_type}</span>"
                    f"{'<span style=\"color:#6b7280;font-size:.8em;margin-left:8px;\">' + g_uc + '</span>' if g_uc else ''}"
                    f"{'<span style=\"color:#6b7280;font-size:.8em;margin-left:8px;\">' + g_cust + '</span>' if g_cust else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if g_rationale:
                    st.caption(g_rationale[:200] + ("…" if len(g_rationale) > 200 else ""))


# ══════════════════════════════════════════════════════════════════
# TAB 3 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════
with tab_config:
    import pandas as pd

    # ── Config table ───────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Environment Configuration**")
        st.caption("Current settings read from environment variables and SSM (where available).")

        def _ssm_get(param_name: str) -> str:
            try:
                ssm = boto3.client("ssm", region_name=_AWS_REGION)
                resp = ssm.get_parameter(Name=param_name, WithDecryption=False)
                return resp["Parameter"]["Value"]
            except Exception:
                return ""

        cfg_rows = []

        def _cfg(category: str, key: str, env_var: str, ssm_path: str = "") -> None:
            env_val = os.environ.get(env_var, "")
            ssm_val = _ssm_get(ssm_path) if ssm_path else ""
            value   = ssm_val or env_val or "(not set)"
            source  = "SSM" if ssm_val else ("env" if env_val else "default")
            cfg_rows.append({"Category": category, "Key": key, "Value": value, "Source": source})

        _cfg("AWS",       "Region",                  "AWS_DEFAULT_REGION",  "/llmwiki/region")
        _cfg("S3",        "Main Wiki Bucket",         "WIKI_BUCKET",         "/llmwiki/wiki_bucket")
        _cfg("S3",        "PM Wiki Bucket",           "PM_WIKI_BUCKET",      "/llmwiki/pm_wiki_bucket")
        _cfg("DynamoDB",  "Index Table",              "DYNAMODB_INDEX",      "")
        _cfg("DynamoDB",  "Log Table",                "DYNAMODB_LOG",        "")
        _cfg("DynamoDB",  "Registry Table",           "REGISTRY_TABLE",      "")
        _cfg("DynamoDB",  "Gaps Table",               "GAPS_TABLE",          "")
        _cfg("DynamoDB",  "Usage Table",              "USAGE_TABLE",         "")
        _cfg("DynamoDB",  "Cache Table",              "CACHE_TABLE",         "")
        _cfg("Lambda",    "Query Function",           "QUERY_LAMBDA",        "/llmwiki/query_lambda")
        _cfg("Lambda",    "Ingest Function",          "INGEST_LAMBDA",       "/llmwiki/ingest_lambda")
        _cfg("Lambda",    "Converter Function",       "CONVERTER_LAMBDA",    "")
        _cfg("Lambda",    "Gatekeeper Function",      "GATEKEEPER_FUNCTION", "")
        _cfg("Skill",     "SK-01 ContextBootstrap",   "SK01_FUNCTION",       "")
        _cfg("Skill",     "SK-02 WikiQuery",          "SK02_FUNCTION",       "")
        _cfg("Skill",     "SK-03 WikiContribute",     "SK03_FUNCTION",       "")
        _cfg("Skill",     "SK-04 ArtifactResolution", "SK04_FUNCTION",       "")
        _cfg("Skill",     "SK-05 GapDetection",       "SK05_FUNCTION",       "")
        _cfg("Bedrock",   "KB ID (Main)",             "BEDROCK_KB_ID",       "/llmwiki/bedrock_kb_id")
        _cfg("Bedrock",   "KB ID (PM)",               "BEDROCK_PM_KB_ID",    "/llmwiki/bedrock_pm_kb_id")
        _cfg("Neuro SAN", "nsflow URL",               "NSFLOW_LOCAL_URL",    "")
        _cfg("Neuro SAN", "Phoenix Endpoint",         "PHOENIX_ENDPOINT",    "")

        st.dataframe(pd.DataFrame(cfg_rows), use_container_width=True, hide_index=True)

    # ── Health check ───────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Lambda Health Check**")
        st.caption("Pings each Lambda with `{\"action\": \"health\"}` and reports status.")

        if st.button("Run Health Check", type="primary", key="plat_health_run"):
            results = {}
            prog = st.progress(0, text="Checking Lambdas…")
            for idx, fn in enumerate(_HEALTH_FUNCTIONS):
                prog.progress((idx + 1) / len(_HEALTH_FUNCTIONS), text=f"Pinging {fn}…")
                t0   = time.time()
                resp = _lambda_invoke(fn, {"action": "health"})
                ms   = int((time.time() - t0) * 1000)
                if resp.get("_error"):
                    results[fn] = {"ok": False, "latency_ms": ms, "detail": resp.get("error", "error")}
                else:
                    results[fn] = {"ok": True,  "latency_ms": ms, "detail": resp.get("status", "ok")}
            prog.empty()
            st.session_state["plat_health_results"] = results

        if "plat_health_results" in st.session_state:
            results = st.session_state["plat_health_results"]
            all_ok  = all(v["ok"] for v in results.values())
            if all_ok:
                st.success("All Lambdas healthy")
            else:
                n_fail = sum(1 for v in results.values() if not v["ok"])
                st.error(f"{n_fail} Lambda(s) unreachable")

            rows = []
            for fn, r in results.items():
                rows.append({
                    "Function":   fn,
                    "Status":     "✅ OK" if r["ok"] else "❌ Error",
                    "Latency ms": r["latency_ms"],
                    "Detail":     str(r["detail"])[:80],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Click Run Health Check to ping all Lambdas.")
