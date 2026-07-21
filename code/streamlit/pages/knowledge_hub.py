"""
Knowledge Hub — Upload documents, ask questions, explore knowledge gaps.
"""

import io
import json
import os
import boto3
import streamlit as st
from botocore.config import Config
from datetime import datetime

st.set_page_config(
    page_title="Knowledge Hub — LLMWiki",
    page_icon="📖",
    layout="wide",
)

AWS_REGION     = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
WIKI_BUCKET    = os.environ.get("WIKI_BUCKET",    "llmwiki-278e7e22")
PM_WIKI_BUCKET = os.environ.get("PM_WIKI_BUCKET", "llmwiki-problem-mgnt-278e7e22")
QUERY_LAMBDA   = os.environ.get("QUERY_LAMBDA",   "llmwiki-query")
CONVERTER_LAMBDA = os.environ.get("CONVERTER_LAMBDA", "llmwiki-converter")
INGEST_LAMBDA  = "llmwiki-ingest"
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "llmwiki-source-registry")

_s3  = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
_lam = boto3.client("lambda", region_name=AWS_REGION)
_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

BINARY_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
TEXT_EXTS   = {".md", ".txt", ".csv"}

DOMAINS = {
    "📚 Sales-to-Service": {
        "bucket":  WIKI_BUCKET,
        "kb_id":   None,
        "label":   "Sales-to-Service",
        "examples": [
            "What are the key risks in our cloud migration strategy?",
            "What was the Q1 2026 infrastructure spend versus budget?",
            "What are the top generative AI trends in enterprise?",
            "Who attended the May 2026 team meeting and what were the action items?",
            "What is AWS AgentCore and how does it relate to LLMWiki?",
        ],
    },
    "🛠️ Problem Management": {
        "bucket":  PM_WIKI_BUCKET,
        "kb_id":   "C4MNP6NOP2",
        "label":   "Problem Management",
        "examples": [
            "Compare Facets vs QNXT batch processing failures — common patterns?",
            "What are HEDIS reporting errors in Facets vs QNXT and how do they differ?",
            "How does the EAM authorization propagation failure impact Facets and QNXT claims?",
            "What recurring data loss issues exist across Facets enrollment and QNXT eligibility?",
            "What FRM reconciliation failures are caused by upstream Facets and QNXT issues?",
        ],
    },
}

PM_SOURCE_TABS = {
    "🔵 Facets":          ("raw/facets-known-issues.md",    "Facets — Commercial & Medicare Claims System"),
    "🟢 QNXT":            ("raw/qnxt-known-issues.md",      "QNXT — Medicaid & Managed Care Claims System"),
    "🟡 EDM / EAM / TCS": ("raw/edm-eam-tcs-known-issues.md","EDM · EAM · TCS"),
    "🟠 NetworX / FRM":   ("raw/networx-frm-known-issues.md","NetworX · FRM"),
    "📋 All Issues":      ("raw/trizetto-issues.csv",        "Master Issue Register — all 7 products"),
}

# ── CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.answer-card { background:#f0f9f4; border-left:4px solid #16a34a;
               border-radius:8px; padding:16px 20px; margin:10px 0; }
.src-chip { display:inline-block; background:#e0f2fe; color:#075985;
            border:1px solid #bae6fd; border-radius:10px;
            padding:2px 10px; font-size:.8em; margin:2px 3px 2px 0; }
.gap-inline { background:#fefce8; border:1px solid #fde68a; border-radius:8px;
              padding:10px 14px; font-size:.9em; margin:8px 0; }
.upload-card { background:#f8fbff; border:1px solid #d0e4f5; border-left:4px solid #1a6bbd;
               border-radius:8px; padding:14px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────

def _invoke_query(payload: dict) -> dict:
    try:
        resp = _lam.invoke(
            FunctionName=QUERY_LAMBDA,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            return json.loads(raw["body"]) if isinstance(raw["body"], str) else (raw["body"] or {})
        return raw
    except Exception as e:
        return {"error": str(e)}


def _trigger_ingest(bucket: str, key: str, is_text: bool) -> dict:
    fn = INGEST_LAMBDA if is_text else CONVERTER_LAMBDA
    payload = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": 0}}}]}
    try:
        resp = _lam.invoke(FunctionName=fn, InvocationType="Event", Payload=json.dumps(payload).encode())
        return {"status": "queued", "fn": fn}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=60)
def _recent_uploads(bucket: str, limit: int = 5) -> list:
    try:
        resp = _s3.list_objects_v2(Bucket=bucket, Prefix="raw/", MaxKeys=200)
        items = sorted(
            [o for o in resp.get("Contents", []) if not o["Key"].endswith("/")],
            key=lambda x: x["LastModified"],
            reverse=True,
        )
        return [
            {"name": o["Key"].split("/")[-1], "key": o["Key"],
             "date": o["LastModified"].strftime("%Y-%m-%d")}
            for o in items[:limit]
        ]
    except Exception:
        return []


@st.cache_data(ttl=60)
def _gap_count() -> int:
    try:
        result = _invoke_query({"action": "get_gaps", "limit": 1})
        gaps = result.get("gaps", [])
        total = result.get("total_count", len(gaps))
        return int(total)
    except Exception:
        return 0


def _presign(bucket: str, key: str) -> str:
    try:
        return _s3.generate_presigned_url("get_object",
            Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)
    except Exception:
        return ""


# ── Page header ──────────────────────────────────────────────────────
st.markdown("## 📖 Knowledge Hub")
st.caption("Upload documents · Ask questions · Explore what the AI knows")

left_col, right_col = st.columns([35, 65], gap="large")

# ══════════════════════════════════════════════════════════════════
# LEFT COLUMN — Upload + Recent + Gaps
# ══════════════════════════════════════════════════════════════════
with left_col:
    # ── Domain selector (shared with right column) ─────────────────
    domain_key = st.selectbox(
        "Knowledge area",
        list(DOMAINS.keys()),
        key="hub_domain",
        label_visibility="collapsed",
    )
    domain_cfg = DOMAINS[domain_key]
    is_pm = domain_cfg["kb_id"] is not None

    # ── Upload panel ───────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**⬆️ Upload Documents**")
        st.caption("PDF · Word · PowerPoint · Excel · Markdown · CSV")

        cust_prefix = st.text_input(
            "Topic prefix (optional)",
            placeholder="e.g. bcbs-mn-001 or claims-processing",
            key="hub_prefix",
            label_visibility="collapsed",
        )

        src_type = st.selectbox(
            "Category",
            ["Auto-detect", "Articles & Research", "Meeting Notes",
             "Technical Papers", "Data Files", "Runbooks & SOPs"],
            key="hub_srctype",
            label_visibility="collapsed",
        )
        src_map = {
            "Auto-detect": None,
            "Articles & Research": "articles",
            "Meeting Notes": "notes",
            "Technical Papers": "papers",
            "Data Files": "data",
            "Runbooks & SOPs": "runbooks",
        }

        uploaded_files = st.file_uploader(
            "Drop files here",
            type=["pdf", "docx", "pptx", "xlsx", "md", "txt", "csv"],
            accept_multiple_files=True,
            key="hub_uploader",
            label_visibility="collapsed",
        )

        upload_btn = st.button(
            "⬆️ Upload to Knowledge Base",
            type="primary",
            disabled=not uploaded_files,
            use_container_width=True,
            key="hub_upload_btn",
        )

    if upload_btn and uploaded_files:
        bucket = domain_cfg["bucket"]
        for uf in uploaded_files:
            ext = os.path.splitext(uf.name)[1].lower()
            is_text = ext in TEXT_EXTS
            folder = src_map.get(src_type)
            if folder is None:
                folder = ("articles" if ext == ".pdf" else "notes"
                          if ext in (".docx", ".doc", ".txt", ".csv")
                          else "data" if ext in (".xlsx", ".xls") else "articles")
            parts = ["raw"]
            if cust_prefix.strip():
                parts.append(cust_prefix.strip().replace(" ", "-"))
            parts.append(folder)
            dest_key = "/".join(parts) + f"/{uf.name}"

            with st.spinner(f"Uploading {uf.name}…"):
                try:
                    _s3.put_object(
                        Bucket=bucket,
                        Key=dest_key,
                        Body=uf.read(),
                        ContentType="text/plain" if is_text else "application/octet-stream",
                    )
                    ir = _trigger_ingest(bucket, dest_key, is_text)
                    wait = "~30s" if is_text else "~2min"
                    if ir.get("error"):
                        st.warning(f"Uploaded but processing trigger failed: {ir['error']}")
                    else:
                        st.success(f"✅ **{uf.name}** — processing in {wait}")
                except Exception as e:
                    st.error(f"Failed: {e}")
        st.cache_data.clear()

    # ── Recent uploads ─────────────────────────────────────────────
    recent = _recent_uploads(domain_cfg["bucket"])
    if recent:
        st.markdown("**📚 Recent Documents**")
        for doc in recent:
            c1, c2 = st.columns([4, 1])
            c1.caption(f"📄 {doc['name']}")
            c2.caption(doc["date"])

    # ── Gap count badge ────────────────────────────────────────────
    gap_count = _gap_count()
    if gap_count:
        st.markdown(f"""
<div style="background:#fefce8;border:1px solid #fde68a;border-radius:8px;
     padding:10px 14px;margin:8px 0;">
💡 <b>{gap_count} knowledge gap{'s' if gap_count != 1 else ''}</b> detected<br>
<span style="font-size:.85em;color:#78350f;">Upload relevant documents to fill them →</span>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Ask + Answer
# ══════════════════════════════════════════════════════════════════
with right_col:

    # ── Example questions ──────────────────────────────────────────
    if "hub_prefill" not in st.session_state:
        st.session_state.hub_prefill = DOMAINS[domain_key]["examples"][0]

    st.caption("**Try an example:**")
    examples = domain_cfg["examples"]
    row_size = 2 if is_pm else 3
    for row_start in range(0, len(examples), row_size):
        row_qs = examples[row_start: row_start + row_size]
        ex_cols = st.columns(len(row_qs))
        for j, ex in enumerate(row_qs):
            short = ex[:65] + "…" if len(ex) > 67 else ex
            if ex_cols[j].button(short, key=f"hub_ex_{row_start}_{j}",
                                  use_container_width=True, help=ex):
                st.session_state.hub_prefill = ex
                st.rerun()

    # ── Question form ──────────────────────────────────────────────
    with st.form("hub_query_form"):
        question = st.text_area(
            "Question",
            value=st.session_state.hub_prefill,
            height=80,
            placeholder="Type your question here…",
            label_visibility="collapsed",
        )
        submit = st.form_submit_button(
            "🔍 Get Answer", use_container_width=True, type="primary"
        )

    if submit and question.strip():
        st.session_state.hub_prefill = question
        payload = {"q": question, "wiki_bucket": domain_cfg["bucket"]}
        if domain_cfg["kb_id"]:
            payload["kb_id"] = domain_cfg["kb_id"]

        with st.spinner(f"Searching {domain_cfg['label']} knowledge base…"):
            result = _invoke_query(payload)

        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            confidence = result.get("confidence", "unknown")
            conf_color = {"high": "#16a34a", "medium": "#d97706", "low": "#dc2626"}.get(confidence, "#6b7280")
            conf_label = {"high": "🟢 High confidence", "medium": "🟡 Medium confidence",
                          "low": "🔴 Low confidence"}.get(confidence, confidence)

            st.markdown(f"<span style='color:{conf_color};font-weight:600;'>{conf_label}</span>",
                        unsafe_allow_html=True)
            st.markdown(
                f'<div class="answer-card">{result.get("answer", "No answer returned.")}</div>',
                unsafe_allow_html=True,
            )

            sources = result.get("sources", [])
            if sources:
                st.markdown("**Sources:**")
                chip_html = ""
                for src in sources:
                    slug  = src.get("page_slug", "")
                    label = slug.replace("-", " ").title()
                    chip_html += f'<span class="src-chip">📑 {label}</span>'
                st.markdown(chip_html, unsafe_allow_html=True)

                first_prov = sources[0].get("provenance", {}) if sources else {}
                if first_prov and first_prov.get("original_file"):
                    with st.expander("📎 Trace answer to original document"):
                        orig = first_prov.get("original_file", "")
                        raw_md = first_prov.get("raw_markdown", "")
                        chain = []
                        if orig:
                            chain.append(f"1. **Original upload** → `{orig}`")
                        if raw_md and raw_md != orig:
                            chain.append(f"2. **Converted Markdown** → `{raw_md}`")
                        chain.append(f"{len(chain)+1}. **Wiki page** → _(this page)_")
                        st.markdown("\n".join(chain))
                        url = _presign(domain_cfg["bucket"], orig)
                        if url:
                            st.link_button("⬇️ Download Original", url)

            gaps = result.get("gaps_identified", [])
            if gaps:
                gap_titles = ", ".join(
                    f"_{g.get('title', g.get('slug', ''))}_" for g in gaps[:3]
                )
                st.markdown(
                    f'<div class="gap-inline">💡 <b>Knowledge gaps found:</b> {gap_titles}<br>'
                    f'<span style="font-size:.85em;">Upload relevant documents in the panel on the left.</span></div>',
                    unsafe_allow_html=True,
                )

            if result.get("note"):
                st.caption(result["note"])

    # ── PM source files explorer ───────────────────────────────────
    if is_pm:
        with st.expander("📂 Source Knowledge Base — trace any answer to its source"):
            st.caption("Raw source files the AI searched. Use these to validate or audit any answer above.")
            tabs = st.tabs(list(PM_SOURCE_TABS.keys()))
            for tab, (tab_label, (s3_key, tab_title)) in zip(tabs, PM_SOURCE_TABS.items()):
                with tab:
                    st.markdown(f"**{tab_title}**")
                    st.caption(f"`s3://{PM_WIKI_BUCKET}/{s3_key}`")
                    try:
                        obj = _s3.get_object(Bucket=PM_WIKI_BUCKET, Key=s3_key)
                        raw = obj["Body"].read().decode("utf-8", errors="ignore")
                        if s3_key.endswith(".csv"):
                            import pandas as pd
                            df_all = pd.read_csv(io.StringIO(raw))
                            fc1, fc2 = st.columns(2)
                            products = sorted(df_all["product"].dropna().unique().tolist()) if "product" in df_all.columns else []
                            cats     = sorted(df_all["category"].dropna().unique().tolist()) if "category" in df_all.columns else []
                            sel_prod = fc1.multiselect("Product", products, default=products, key=f"hub_prod_{tab_label}")
                            sel_cats = fc2.multiselect("Category", cats, default=cats, key=f"hub_cat_{tab_label}")
                            df = df_all.copy()
                            if sel_prod:
                                df = df[df["product"].isin(sel_prod)]
                            if sel_cats:
                                df = df[df["category"].isin(sel_cats)]
                            st.dataframe(df, use_container_width=True, hide_index=True)
                            st.caption(f"{len(df)} of {len(df_all)} records")
                        else:
                            st.markdown(raw)
                    except Exception as e:
                        st.warning(f"Could not load: {e}")
