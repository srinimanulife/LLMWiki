"""
LLMWiki Streamlit UI
Ask questions, explore answers, run agents, watch the wiki grow.
"""

import os
import json
import boto3
import streamlit as st
from botocore.config import Config
from datetime import datetime

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
WIKI_BUCKET    = os.environ.get("WIKI_BUCKET",    "")
PM_WIKI_BUCKET = os.environ.get("PM_WIKI_BUCKET", "llmwiki-problem-mgnt-278e7e22")
QUERY_LAMBDA   = os.environ.get("QUERY_LAMBDA",   "llmwiki-query")
CONVERTER_LAMBDA = os.environ.get("CONVERTER_LAMBDA", "llmwiki-converter")
DYNAMODB_INDEX = os.environ.get("DYNAMODB_INDEX", "llmwiki-index")
DYNAMODB_LOG = os.environ.get("DYNAMODB_LOG", "llmwiki-log")
GAPS_TABLE = os.environ.get("GAPS_TABLE", "llmwiki-gaps")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "llmwiki-source-registry")
SK01_FUNCTION = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
SK02_FUNCTION = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
SK03_FUNCTION = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
SK04_FUNCTION = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
SK05_FUNCTION        = os.environ.get("SK05_FUNCTION",        "llmwiki-skill-gap-detection")
UC1_FUNCTION         = os.environ.get("UC1_FUNCTION",         "llmwiki-uc1-orchestrator")
GATEKEEPER_FUNCTION  = os.environ.get("GATEKEEPER_FUNCTION",  "llmwiki-gatekeeper")
UC1_HARNESS_FUNCTION = os.environ.get("UC1_HARNESS_FUNCTION", "llmwiki-uc1-harness")

s3 = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

st.set_page_config(
    page_title="LLMWiki",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global styles ─────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar nav label */
.nav-section { font-size:.78em; font-weight:700; color:#6b7280;
               text-transform:uppercase; letter-spacing:.05em;
               margin:12px 0 4px 0; }
/* Answer block */
.answer-card { background:#f0f9f4; border-left:4px solid #16a34a;
               border-radius:8px; padding:16px 20px; margin:10px 0; }
/* Source chip */
.src-chip { display:inline-block; background:#e0f2fe; color:#075985;
            border:1px solid #bae6fd; border-radius:10px;
            padding:2px 10px; font-size:.8em; margin:2px 3px 2px 0; }
/* Gap banner */
.gap-banner { background:#fefce8; border:1px solid #fde68a; border-radius:8px;
              padding:12px 16px; font-size:.9em; margin:8px 0; }
</style>
""", unsafe_allow_html=True)

# Curated test questions for Expansion Lab
TEST_QUESTIONS = {
    "Strategy": [
        "What is our 3-year cloud roadmap and key milestones?",
        "What are our cost reduction targets for 2026?",
        "What are the key risks in our cloud migration strategy?",
    ],
    "Infrastructure": [
        "Which EC2 instances are candidates for right-sizing?",
        "What is our current S3 storage cost breakdown?",
        "What was Q1 2026 total cloud spend versus budget?",
    ],
    "AI & Technology": [
        "What generative AI tools are we evaluating for enterprise use?",
        "How does AWS AgentCore work and what problems does it solve?",
        "What is an LLM-maintained knowledge wiki and how does it differ from RAG?",
    ],
    "People & Teams": [
        "Who leads the cloud migration initiative?",
        "What teams are involved in the AI strategy rollout?",
        "Who attended the May 2026 team meeting and what were the action items?",
    ],
    "Knowledge Gaps (intentionally hard)": [
        "What is our disaster recovery plan and RTO/RPO targets?",
        "What are our data governance and data classification policies?",
        "Who owns our security compliance program and what certifications are we targeting?",
        "What is our multi-cloud or hybrid cloud strategy?",
    ],
}

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 📚 LLMWiki")
    st.caption("Your AI-powered knowledge base")
    st.divider()

    page = st.radio(
        "Navigate",
        ["🔍 Ask a Question", "📄 Browse Knowledge", "🔬 Discover Gaps"],
        label_visibility="collapsed",
        key="page_nav",
    )

    st.divider()
    st.markdown('<p class="nav-section">Explore</p>', unsafe_allow_html=True)
    st.page_link("pages/knowledge_graph.py", label="🕸️ Knowledge Graph", icon="🕸️")

    st.divider()
    st.markdown('<p class="nav-section">Manage</p>', unsafe_allow_html=True)
    st.page_link("pages/wiki_manager.py", label="🗂️ Upload Documents", icon="🗂️")

    st.divider()
    st.markdown('<p class="nav-section">Agents</p>', unsafe_allow_html=True)
    st.page_link("pages/harness_demo.py", label="🤖 Run Agent Workflow", icon="🤖")
    st.page_link("pages/skill_studio.py", label="🧠 AI Skill Studio", icon="🧠")

    st.divider()
    st.markdown('<p class="nav-section">Platform</p>', unsafe_allow_html=True)
    st.page_link("pages/governance.py", label="📊 Governance", icon="📊")

    st.divider()
    st.caption(f"Region: `{AWS_REGION}`")


# ── Helper functions ──────────────────────────────────────────────

def invoke_query_lambda(payload: dict) -> dict:
    try:
        response = lambda_client.invoke(
            FunctionName=QUERY_LAMBDA,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        result = json.loads(response["Payload"].read())
        if "body" in result:
            return json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
        return result
    except Exception as e:
        return {"error": str(e)}


def list_s3_wiki_pages(prefix: str = "wiki/") -> list:
    try:
        response = s3.list_objects_v2(Bucket=WIKI_BUCKET, Prefix=prefix, MaxKeys=200)
        return [obj["Key"] for obj in response.get("Contents", [])]
    except Exception as e:
        st.error(f"S3 error: {e}")
        return []


def read_s3_page(key: str) -> str:
    try:
        response = s3.get_object(Bucket=WIKI_BUCKET, Key=key)
        return response["Body"].read().decode("utf-8")
    except Exception as e:
        return f"Error reading {key}: {e}"


def get_wiki_status() -> dict:
    return invoke_query_lambda({"action": "status"})


def get_recent_log(limit: int = 20) -> list:
    try:
        table = dynamodb.Table(DYNAMODB_LOG)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        response = table.query(
            KeyConditionExpression="log_date = :d",
            ExpressionAttributeValues={":d": today},
            Limit=limit,
            ScanIndexForward=False,
        )
        return response.get("Items", [])
    except Exception as e:
        return [{"error": str(e)}]


def generate_presigned_url(s3_key: str, expiry: int = 3600) -> str:
    """Generate a temporary download URL for an S3 object."""
    if not s3_key:
        return ""
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": WIKI_BUCKET, "Key": s3_key},
            ExpiresIn=expiry,
        )
    except Exception:
        return ""


def get_page_provenance(page_slug: str) -> dict:
    """Read source_provenance from DynamoDB index for a wiki source page."""
    try:
        table = dynamodb.Table(DYNAMODB_INDEX)
        resp = table.get_item(Key={"page_type": "sources", "page_slug": page_slug})
        raw = resp.get("Item", {}).get("source_provenance", "")
        if raw:
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass
    return {}


def get_gaps(status_filter: str = None, limit: int = 50) -> list:
    """Fetch knowledge gaps from Lambda."""
    payload = {"action": "get_gaps", "limit": limit}
    if status_filter:
        payload["status_filter"] = status_filter
    return invoke_query_lambda(payload).get("gaps", [])


def render_provenance(prov: dict, compact: bool = False):
    """Render a source provenance chain."""
    if not prov or not any(prov.values()):
        st.caption("No provenance data for this page.")
        return

    orig_file = prov.get("original_file", "")
    raw_md = prov.get("raw_markdown", "")

    if compact:
        cols = st.columns([3, 1])
        if orig_file:
            cols[0].caption(f"Original: `{orig_file}`")
            url = generate_presigned_url(orig_file)
            if url:
                cols[1].link_button("⬇️ Download", url)
        return

    st.markdown("**Provenance chain:**")
    chain = []
    if orig_file:
        chain.append(f"1. **Original upload** → `{orig_file}`")
    if raw_md and raw_md != orig_file:
        chain.append(f"2. **Converted Markdown** → `{raw_md}`")
    chain.append(f"{'3' if len(chain) == 2 else '2'}. **Wiki page** → _(this page)_")
    st.markdown("\n".join(chain))

    if orig_file:
        url = generate_presigned_url(orig_file)
        if url:
            st.link_button("⬇️ Download Original File", url)
        else:
            st.caption(f"Original file: `{orig_file}`")

    assets_key = prov.get("raw_assets", "")
    if assets_key and assets_key != orig_file:
        url2 = generate_presigned_url(assets_key)
        if url2:
            st.link_button("⬇️ Download Binary Copy (assets/)", url2)


def render_gap_badge(gap_type: str) -> str:
    return {"entity": "🏢", "concept": "💡", "question": "❓"}.get(gap_type, "📌")


# ── Page: Ask a Question ─────────────────────────────────────────
if page == "🔍 Ask a Question":
    st.markdown("## 🔍 Ask a Question")
    st.markdown("Type any question in plain English — the wiki finds the answer and shows exactly which documents it used.")

    # ── Domain selector ───────────────────────────────────────────
    DOMAINS = {
        "📚 Sales-to-Service (Main Wiki)": {
            "bucket":  WIKI_BUCKET,
            "kb_id":   None,   # use SSM default
            "label":   "Sales-to-Service",
            "examples": [
                "What are the key risks in our cloud migration strategy?",
                "What was the Q1 2026 infrastructure spend and how does it compare to budget?",
                "What are the top generative AI trends in enterprise?",
                "Who attended the May 2026 team meeting and what were the action items?",
                "What is AWS AgentCore and how does it relate to LLMWiki?",
            ],
        },
        "🛠️ Problem Management (UC-PM)": {
            "bucket":  PM_WIKI_BUCKET,
            "kb_id":   "C4MNP6NOP2",  # Bedrock semantic KB for PM — TriZetto cross-product issues
            "label":   "Problem Management",
            "examples": [
                "Compare Facets vs QNXT batch processing failures — what are the common patterns?",
                "What are HEDIS reporting errors in Facets vs QNXT and how do they differ?",
                "How does the EAM authorization propagation failure impact both Facets and QNXT claims?",
                "What recurring data loss issues exist across Facets enrollment and QNXT eligibility?",
                "What FRM reconciliation failures are caused by upstream Facets and QNXT issues?",
                "What NetworX fee schedule and contract problems affect downstream claim adjudication?",
                "What are known TCS claims intake failures and how do they cascade to Facets and QNXT?",
            ],
        },
    }

    # ── Source files available for PM domain drill-down ──────────────
    PM_SOURCE_FILES = {
        "Facets": {
            "key": "raw/facets-known-issues.md",
            "icon": "🔵",
            "desc": "Claims source system — commercial & Medicare claims",
        },
        "QNXT": {
            "key": "raw/qnxt-known-issues.md",
            "icon": "🟢",
            "desc": "Claims source system — Medicaid & managed care",
        },
        "EDM / EAM / TCS": {
            "key": "raw/edm-eam-tcs-known-issues.md",
            "icon": "🟡",
            "desc": "Encounter submission, authorization, claims intake",
        },
        "NetworX / FRM": {
            "key": "raw/networx-frm-known-issues.md",
            "icon": "🟠",
            "desc": "Fee schedules, contracts, financial reconciliation",
        },
        "All Issues (CSV)": {
            "key": "raw/trizetto-issues.csv",
            "icon": "📋",
            "desc": "Master issue register — all 7 products",
        },
    }

    if "ask_domain" not in st.session_state:
        st.session_state.ask_domain = list(DOMAINS.keys())[0]
    if "ask_prefill" not in st.session_state:
        st.session_state.ask_prefill = ""

    # ── Domain selector (clean, not cluttered) ───────────────────
    domain_col, _ = st.columns([2, 3])
    with domain_col:
        selected_domain_key = st.selectbox(
            "Knowledge area",
            list(DOMAINS.keys()),
            index=list(DOMAINS.keys()).index(st.session_state.ask_domain),
            key="ask_domain_select",
        )

    if selected_domain_key != st.session_state.ask_domain:
        st.session_state.ask_domain = selected_domain_key
        st.session_state.ask_prefill = ""
        st.rerun()

    domain_cfg = DOMAINS[selected_domain_key]
    is_pm = domain_cfg.get("kb_id") not in (None, "none") and "PM" in selected_domain_key

    # ── Example questions ─────────────────────────────────────────
    EXAMPLE_QUESTIONS = domain_cfg["examples"]
    if not st.session_state.ask_prefill:
        st.session_state.ask_prefill = EXAMPLE_QUESTIONS[0]

    st.caption("**Try an example:**")
    row_size = 2 if is_pm else 3
    for row_start in range(0, len(EXAMPLE_QUESTIONS), row_size):
        row_qs = EXAMPLE_QUESTIONS[row_start: row_start + row_size]
        ex_cols = st.columns(len(row_qs))
        for j, ex in enumerate(row_qs):
            i = row_start + j
            short = ex[:70] + "…" if len(ex) > 72 else ex
            if ex_cols[j].button(short, key=f"ex_{i}", use_container_width=True, help=ex):
                st.session_state.ask_prefill = ex
                st.rerun()

    # ── Question box + submit ─────────────────────────────────────
    with st.form("query_form"):
        question = st.text_area(
            "Your question",
            value=st.session_state.ask_prefill,
            height=90,
            label_visibility="collapsed",
            placeholder="Type your question here…",
        )
        submit = st.form_submit_button("🔍 Get Answer", use_container_width=True, type="primary")

    if submit and question.strip():
        st.session_state.ask_prefill = question
        payload = {"q": question, "wiki_bucket": domain_cfg["bucket"]}
        if domain_cfg["kb_id"]:
            payload["kb_id"] = domain_cfg["kb_id"]

        with st.spinner(f"Searching {domain_cfg['label']} knowledge base…"):
            result = invoke_query_lambda(payload)

        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            confidence = result.get("confidence", "unknown")
            conf_label = {"high": "🟢 High confidence", "medium": "🟡 Medium confidence", "low": "🔴 Low confidence"}.get(confidence, confidence)

            # ── Answer ────────────────────────────────────────────
            st.markdown(f"**{conf_label}**")
            st.markdown(
                f'<div class="answer-card">{result.get("answer", "No answer returned.")}</div>',
                unsafe_allow_html=True,
            )

            # ── Sources (clean, no clutter) ───────────────────────
            sources = result.get("sources", [])
            if sources:
                st.markdown("**Sources used:**")
                chip_html = ""
                for src in sources:
                    slug  = src.get("page_slug", "")
                    score = float(src.get("relevance_score", 0))
                    prov  = src.get("provenance", {})
                    label = slug.replace("-", " ").title()
                    chip_html += f'<span class="src-chip">📑 {label}</span>'
                st.markdown(chip_html, unsafe_allow_html=True)

                # Trace provenance for first source only — avoids clutter
                first_prov = sources[0].get("provenance", {}) if sources else {}
                if first_prov and first_prov.get("original_file"):
                    with st.expander("📎 Trace answer to original document"):
                        render_provenance(first_prov, compact=False)

            # ── Gaps ──────────────────────────────────────────────
            gaps = result.get("gaps_identified", [])
            if gaps:
                gap_titles = ", ".join(f"_{g.get('title', g.get('slug', ''))}_" for g in gaps[:3])
                st.markdown(
                    f'<div class="gap-banner">💡 <b>The wiki doesn\'t fully know about:</b> {gap_titles}.<br>'
                    f'Upload relevant documents to teach it — visit <b>Upload Documents</b> in the sidebar.</div>',
                    unsafe_allow_html=True,
                )

            if result.get("note"):
                st.caption(result["note"])

    # ── PM domain: source file explorer tabs ─────────────────────
    if is_pm:
        st.divider()
        col_hdr, col_hint = st.columns([3, 2])
        col_hdr.markdown("#### 📂 Source Knowledge Base — Trace Any Answer to Its Source")
        col_hint.caption(
            "💡 Each tab is a raw source file the AI searched. "
            "Use these to validate, audit, or drill into any answer above."
        )

        # Tab labels include short product description for non-technical audiences
        TAB_META = {
            "🔵 Facets":          ("raw/facets-known-issues.md",    "Facets — Commercial & Medicare Claims System"),
            "🟢 QNXT":            ("raw/qnxt-known-issues.md",      "QNXT — Medicaid & Managed Care Claims System"),
            "🟡 EDM / EAM / TCS": ("raw/edm-eam-tcs-known-issues.md","EDM Encounter Submission · EAM Authorization · TCS Claims Intake"),
            "🟠 NetworX / FRM":   ("raw/networx-frm-known-issues.md","NetworX Fee Schedules & Contracts · FRM Financial Reconciliation"),
            "📋 All Issues":      ("raw/trizetto-issues.csv",        "Master Issue Register — 38 records across all 7 TriZetto products"),
        }
        tabs = st.tabs(list(TAB_META.keys()))
        for tab, (tab_label, (s3_key, tab_title)) in zip(tabs, TAB_META.items()):
            with tab:
                st.markdown(f"**{tab_title}**")
                st.caption(f"Source: `s3://{PM_WIKI_BUCKET}/{s3_key}`")
                try:
                    import io, pandas as pd
                    obj = s3.get_object(Bucket=PM_WIKI_BUCKET, Key=s3_key)
                    raw = obj["Body"].read().decode("utf-8", errors="ignore")
                    if s3_key.endswith(".csv"):
                        df_all = pd.read_csv(io.StringIO(raw))
                        fc1, fc2 = st.columns(2)
                        products = sorted(df_all["product"].dropna().unique().tolist()) if "product" in df_all.columns else []
                        sel_prod = fc1.multiselect("Filter by product", products, default=products, key=f"prod_{tab_label}")
                        cats = sorted(df_all["category"].dropna().unique().tolist()) if "category" in df_all.columns else []
                        sel_cats = fc2.multiselect("Filter by category", cats, default=cats, key=f"cat_{tab_label}")
                        df = df_all.copy()
                        if sel_prod:
                            df = df[df["product"].isin(sel_prod)]
                        if sel_cats:
                            df = df[df["category"].isin(sel_cats)]
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        st.caption(f"Showing {len(df)} of {len(df_all)} records · Use filters above to narrow by product or issue category")
                        st.download_button(
                            label="⬇️ Download as CSV",
                            data=df.to_csv(index=False).encode(),
                            file_name="trizetto-issues-filtered.csv",
                            mime="text/csv",
                            key=f"dl_{tab_label}",
                        )
                    else:
                        st.markdown(raw)
                except Exception as e:
                    st.warning(f"Could not load source file: {e}")


# ── Page: Browse Knowledge ───────────────────────────────────────
elif page == "📄 Browse Knowledge":
    st.markdown("## 📄 Browse Knowledge")
    st.markdown("Explore what the AI has learned from your documents.")

    TYPE_LABELS = {
        "All":       ("All pages", ""),
        "sources":   ("📑 Document summaries", "One page per ingested document"),
        "entities":  ("🏢 People & Organizations", "Extracted entities"),
        "concepts":  ("💡 Ideas & Concepts", "Frameworks and methodologies"),
        "questions": ("❓ Knowledge Gaps", "Topics the wiki can't fully answer yet"),
    }

    filter_col, _ = st.columns([2, 3])
    with filter_col:
        page_type_filter = st.selectbox(
            "Show",
            list(TYPE_LABELS.keys()),
            format_func=lambda k: TYPE_LABELS[k][0],
            label_visibility="collapsed",
        )

    prefix = "wiki/" if page_type_filter == "All" else f"wiki/{page_type_filter}/"
    all_pages = [p for p in list_s3_wiki_pages(prefix) if not p.endswith("index.md")]

    col1, col2 = st.columns([1, 2], gap="large")

    with col1:
        if not all_pages:
            st.info("Nothing here yet. Upload documents to get started.")
            selected_page = None
        else:
            st.caption(f"{len(all_pages)} page{'s' if len(all_pages) != 1 else ''}")
            selected_page = st.radio(
                "Select",
                all_pages,
                format_func=lambda k: k.replace("wiki/", "").replace(".md", "").split("/")[-1].replace("-", " ").title(),
                label_visibility="collapsed",
            )

    with col2:
        if selected_page:
            label = selected_page.replace("wiki/", "").replace(".md", "").replace("/", " › ").replace("-", " ").title()
            st.markdown(f"#### {label}")

            content = read_s3_page(selected_page)
            st.markdown(content)

            parts = selected_page.replace("wiki/", "").replace(".md", "").split("/")
            if len(parts) == 2 and parts[0] == "sources":
                prov = get_page_provenance(parts[1])
                if prov and any(prov.values()):
                    with st.expander("📎 Trace back to original document"):
                        render_provenance(prov)
            elif len(parts) == 2 and parts[0] == "questions":
                st.markdown(
                    '<div class="gap-banner">❓ <b>Knowledge gap</b> — upload a relevant document to fill this in automatically.</div>',
                    unsafe_allow_html=True,
                )
        elif not all_pages:
            pass
        else:
            st.info("Select a page on the left to read it here.")


# ── Page: Discover Gaps ──────────────────────────────────────────
elif page == "🔬 Discover Gaps":
    st.markdown("## 🔬 Discover Gaps")
    st.markdown("See what the wiki knows, what it doesn't, and how to teach it more.")

    with st.spinner("Loading…"):
        status = get_wiki_status()

    total_pages = status.get("total_pages", 0)
    by_type     = status.get("pages_by_type", {})
    gap_counts  = status.get("gaps_by_status", {})
    open_gaps   = gap_counts.get("suggested", 0) + gap_counts.get("stub_created", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total pages in wiki", total_pages)
    m2.metric("Source documents", by_type.get("sources", 0))
    m3.metric("Concepts & entities", by_type.get("concepts", 0) + by_type.get("entities", 0))
    m4.metric("Open knowledge gaps", open_gaps)

    st.divider()

    # ── Gap list ──────────────────────────────────────────────────
    col_gaps, col_tests = st.columns([1, 1], gap="large")

    with col_gaps:
        st.markdown("#### Knowledge Gaps")
        st.caption("Topics the wiki has been asked about but couldn't fully answer.")
        if st.button("↺ Refresh", key="gaps_refresh"):
            st.rerun()
        all_gaps = get_gaps(limit=30)
        if not all_gaps:
            st.success("No open gaps — the wiki can answer everything it's been asked so far!")
        else:
            for gap in all_gaps[:15]:
                g_slug     = gap.get("gap_slug", "")
                g_title    = gap.get("gap_title", g_slug.replace("-", " ").title())
                g_priority = int(gap.get("priority_score", 1))
                g_status   = gap.get("status", "suggested")
                g_rationale= gap.get("gap_rationale", "")
                status_icon= {"suggested": "💡", "stub_created": "📄", "resolved": "✅"}.get(g_status, "❓")

                with st.expander(f"{status_icon} {g_title}  (priority {g_priority})"):
                    if g_rationale:
                        st.markdown(f"**Why this matters:** {g_rationale}")
                    st.caption(f"First asked: _{gap.get('source_query', '—')}_")
                    c1, c2 = st.columns(2)
                    if g_status not in ("resolved", "dismissed"):
                        if c1.button("🚫 Dismiss", key=f"dismiss_{gap.get('gap_id', g_slug)}"):
                            invoke_query_lambda({"action": "dismiss_gap", "gap_id": gap.get("gap_id", "")})
                            st.success("Gap dismissed.")
                            st.rerun()
                    c2.info("→ Upload a document to fill this gap automatically")

    with col_tests:
        st.markdown("#### Test Questions")
        st.caption("Run these to discover what the wiki knows and doesn't know.")
        for category, questions in TEST_QUESTIONS.items():
            is_gap = "Gap" in category
            with st.expander(f"{'🔴 ' if is_gap else ''}{category}", expanded=False):
                for qi, q in enumerate(questions):
                    key = f"tq_{category}_{qi}"
                    result_key = f"tq_result_{category}_{qi}"
                    if st.button(q[:80], key=key, use_container_width=True):
                        with st.spinner("Asking…"):
                            r = invoke_query_lambda({"q": q})
                        st.session_state[result_key] = r
                    if result_key in st.session_state:
                        r = st.session_state[result_key]
                        conf = r.get("confidence", "?")
                        badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")
                        st.markdown(f"{badge} `{conf}` — {len(r.get('sources', []))} sources")
                        gaps = r.get("gaps_identified", [])
                        if gaps:
                            st.caption("Gaps found: " + ", ".join(g.get("title", "") for g in gaps[:2]))

elif page == "__legacy_upload__":
    st.header("⬆️ Upload Documents")
    st.caption("Upload PDF, DOCX, PPTX, XLSX, or Markdown files. The wiki builds automatically.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Upload a file")
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "docx", "pptx", "xlsx", "md", "txt", "csv"],
            help="PDF/Office files will be converted to Markdown first, then ingested."
        )

        source_type = st.selectbox(
            "Source type",
            ["articles", "papers", "notes", "meetings", "data"],
            help="Determines which raw/ subfolder the document lands in"
        )

        if st.button("Upload & Ingest →", type="primary", use_container_width=True, disabled=uploaded_file is None):
            if uploaded_file:
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                is_markdown = ext in (".md", ".txt")

                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    if is_markdown:
                        dest_key = f"raw/{source_type}/{uploaded_file.name}"
                    else:
                        dest_key = f"uploads/{uploaded_file.name}"

                    s3.put_object(
                        Bucket=WIKI_BUCKET,
                        Key=dest_key,
                        Body=uploaded_file.read(),
                        ContentType="text/plain" if is_markdown else "application/octet-stream",
                    )

                st.success(f"Uploaded to `s3://{WIKI_BUCKET}/{dest_key}`")

                if is_markdown:
                    st.info("Markdown file uploaded. Ingest Lambda triggered automatically via S3 event.")
                else:
                    st.info(
                        f"File uploaded to `uploads/`. Converter Lambda will convert {ext} → Markdown → ingest automatically.  \n"
                        "The full upload path will be traceable from every wiki page generated from this document."
                    )

    with col2:
        st.subheader("Upload a URL")
        url_input = st.text_input("Web URL", placeholder="https://example.com/article")
        url_type = st.selectbox("URL type", ["articles", "papers"])

        if st.button("Fetch & Ingest URL →", use_container_width=True):
            if url_input:
                with st.spinner("Fetching URL content..."):
                    result = invoke_query_lambda({
                        "action": "fetch_url",
                        "url": url_input,
                        "source_type": url_type
                    })
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success("URL fetched and queued for ingestion.")

    st.divider()
    st.subheader("Sample documents in the wiki")
    st.caption("These were pre-loaded during deployment. Try asking questions about them:")

    samples = {
        "raw/papers/cloud-strategy-2026.md": "Cloud Strategy 2026 — migration plan, budget, KPIs",
        "raw/notes/team-meeting-2026-05-01.md": "Team Meeting Notes — action items, decisions",
        "raw/articles/generative-ai-enterprise-trends.md": "Gen AI Enterprise Trends — 2026 survey data",
        "raw/notes/infrastructure-metrics-q1-2026.md": "Infrastructure Metrics Q1 2026 — cost breakdown",
        "raw/articles/agentcore-architecture-overview.md": "AWS AgentCore Architecture Overview",
    }

    for key, desc in samples.items():
        st.markdown(f"- `{key}` — {desc}")


# ── Page: Wiki Status ─────────────────────────────────────────────
elif page == "📊 Wiki Status":
    st.header("📊 Wiki Status")

    if st.button("Refresh Status", type="primary"):
        st.rerun()

    with st.spinner("Loading wiki status..."):
        status = get_wiki_status()

    if "error" in status:
        st.error(f"Error: {status['error']}")
    else:
        total = status.get("total_pages", 0)
        by_type = status.get("pages_by_type", {})
        gap_counts = status.get("gaps_by_status", {})
        total_gaps = sum(gap_counts.values())

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Pages", total)
        col2.metric("Source Pages", by_type.get("sources", 0))
        col3.metric("Entity Pages", by_type.get("entities", 0))
        col4.metric("Concept Pages", by_type.get("concepts", 0))
        col5.metric("Knowledge Gaps", total_gaps)

        st.divider()
        st.subheader("Pages by Type")
        if by_type:
            import pandas as pd
            df = pd.DataFrame(
                [{"Type": k, "Pages": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])]
            )
            st.bar_chart(df.set_index("Type"))
        else:
            st.info("No pages indexed yet.")

        if gap_counts:
            st.subheader("Gaps by Status")
            gap_df = pd.DataFrame(
                [{"Status": k, "Count": v} for k, v in gap_counts.items()]
            )
            st.bar_chart(gap_df.set_index("Status"))

        st.divider()
        st.subheader("Configuration")
        st.code(f"""
Wiki Bucket:  {status.get('wiki_bucket', WIKI_BUCKET)}
Model:        {status.get('model', 'unknown')}
Region:       {AWS_REGION}
Index Table:  {DYNAMODB_INDEX}
Gaps Table:   {GAPS_TABLE}
        """)

    st.subheader("Wiki Index")
    index_content = read_s3_page("wiki/index.md")
    if index_content and not index_content.startswith("Error"):
        st.markdown(index_content)
    else:
        st.info("Index not yet generated. Upload and ingest documents first.")


# ── Page: Activity Log ────────────────────────────────────────────
elif page == "📋 Activity Log":
    st.header("📋 Activity Log")
    st.caption("Recent ingest operations")

    log_entries = get_recent_log(30)

    if not log_entries:
        st.info("No log entries yet. Ingest some documents first.")
    else:
        for entry in log_entries:
            if "error" in entry:
                st.error(entry["error"])
                continue

            ts = entry.get("timestamp_id", "").split("#")[0]
            op = entry.get("operation", "unknown")
            source = entry.get("source_slug", "unknown")
            pages = entry.get("pages_created", [])

            with st.expander(f"[{ts[:19]}] {op.upper()} — {source} → {len(pages)} pages"):
                st.write(f"**Source key:** `{entry.get('source_key', '')}`")
                st.write(f"**Pages created:** {len(pages)}")
                if pages:
                    for p in pages:
                        st.markdown(f"  - `{p}`")


# ── Page: Expansion Lab ───────────────────────────────────────────
elif page == "🔬 Expansion Lab":
    st.header("🔬 Expansion Lab")
    st.caption(
        "Watch the wiki learn and grow in real-time. "
        "Ask questions, discover knowledge gaps, and teach the wiki new topics."
    )

    # ── Section A: Wiki Growth Counter ───────────────────────────
    with st.spinner("Loading wiki status..."):
        status = get_wiki_status()

    total_pages = status.get("total_pages", 0)
    by_type = status.get("pages_by_type", {})
    stub_count = by_type.get("questions", 0)
    gap_counts = status.get("gaps_by_status", {})

    # Track growth within this browser session
    if "expansion_start_count" not in st.session_state:
        st.session_state.expansion_start_count = total_pages
    if "session_gaps" not in st.session_state:
        st.session_state.session_gaps = []

    growth = total_pages - st.session_state.expansion_start_count

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Wiki Pages (Total)", total_pages)
    col2.metric("Knowledge Stubs", stub_count, help="Auto-created gap pages waiting to be filled")
    col3.metric("Session Growth", f"+{growth}", delta=growth if growth > 0 else None)
    col4.metric("Open Gaps", gap_counts.get("suggested", 0) + gap_counts.get("stub_created", 0))

    if growth > 0:
        st.success(f"The wiki grew by **{growth} page{'s' if growth != 1 else ''}** during this session!")

    st.divider()

    # ── Section B: Test Questions ─────────────────────────────────
    st.subheader("Test Questions")
    st.caption(
        "Click any question to run it against the wiki. "
        "Questions in **Knowledge Gaps** are intentionally hard — watch the wiki identify what it doesn't know."
    )

    for category, questions in TEST_QUESTIONS.items():
        is_gap_category = "Gap" in category
        header = f"{'🔴 ' if is_gap_category else ''}{category}"
        with st.expander(header, expanded=is_gap_category):
            if is_gap_category:
                st.caption("These questions test topics NOT in the wiki — gaps will be auto-detected and stub pages created.")
            for qi, q in enumerate(questions):
                key = f"tq_{category}_{qi}"
                result_key = f"tq_result_{category}_{qi}"
                if st.button(q, key=key, use_container_width=True):
                    with st.spinner(f"Asking: {q[:60]}..."):
                        r = invoke_query_lambda({"q": q})
                    st.session_state[result_key] = r
                    # Track gaps found this session
                    new_gaps = r.get("gaps_identified", [])
                    for g in new_gaps:
                        if not any(x.get("slug") == g.get("slug") for x in st.session_state.session_gaps):
                            st.session_state.session_gaps.append(g)

                if result_key in st.session_state:
                    r = st.session_state[result_key]
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        confidence = r.get("confidence", "unknown")
                        badge = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}.get(confidence, confidence)
                        src_count = len(r.get("sources", []))
                        st.markdown(f"**Confidence:** {badge} &nbsp; **Sources:** {src_count}")
                        with st.expander("View Answer"):
                            st.markdown(r.get("answer", ""))
                            gaps = r.get("gaps_identified", [])
                            if gaps:
                                st.warning("Gaps found: " + ", ".join(
                                    f"{render_gap_badge(g.get('type'))} {g.get('title', g.get('slug'))}"
                                    for g in gaps
                                ))
                st.markdown("")

    st.divider()

    # ── Section C: Live Gap Dashboard ────────────────────────────
    st.subheader("Knowledge Gap Dashboard")

    tab_all, tab_session = st.tabs(["All Gaps", "This Session"])

    with tab_all:
        if st.button("Refresh Gaps", key="refresh_all_gaps"):
            st.rerun()
        all_gaps = get_gaps(limit=50)
        if not all_gaps:
            st.info("No knowledge gaps recorded yet. Ask some questions to discover what the wiki doesn't know.")
        else:
            for gap in all_gaps:
                g_slug = gap.get("gap_slug", "")
                g_title = gap.get("gap_title", g_slug)
                g_type = gap.get("gap_type", "question")
                g_priority = int(gap.get("priority_score", 1))
                g_status = gap.get("status", "suggested")
                g_query = gap.get("source_query", "")
                g_rationale = gap.get("gap_rationale", "")

                status_icon = {"suggested": "💡", "stub_created": "📄", "resolved": "✅", "dismissed": "🚫"}.get(g_status, "❓")
                label = f"{render_gap_badge(g_type)} {g_title}  {status_icon} priority: {g_priority}"

                with st.expander(label):
                    st.markdown(f"**Type:** {g_type}  |  **Status:** {g_status}  |  **Priority:** {g_priority}")
                    if g_rationale:
                        st.markdown(f"**Why this is needed:** {g_rationale}")
                    if g_query:
                        st.caption(f"First discovered from: *{g_query}*")

                    c1, c2, c3 = st.columns(3)
                    if g_status not in ("resolved", "dismissed"):
                        if c1.button("📄 View Stub", key=f"stub_{g_slug}"):
                            stub_key = f"wiki/questions/{g_slug}.md"
                            content = read_s3_page(stub_key)
                            if not content.startswith("Error"):
                                st.markdown(content)
                            else:
                                st.info("Stub page not yet created.")

                        if c2.button("🚫 Dismiss", key=f"dismiss_{gap.get('gap_id', g_slug)}"):
                            invoke_query_lambda({"action": "dismiss_gap", "gap_id": gap.get("gap_id", "")})
                            st.success("Gap dismissed.")
                            st.rerun()

                    if c3.button("➕ Upload Doc", key=f"upload_{g_slug}"):
                        st.info(f"Go to **⬆️ Upload Documents** and upload a document about: **{g_title}**")

    with tab_session:
        session_gaps = st.session_state.get("session_gaps", [])
        if not session_gaps:
            st.info("No gaps discovered yet this session. Try the test questions above.")
        else:
            st.caption(f"{len(session_gaps)} gap(s) found during this session:")
            for g in session_gaps:
                badge = render_gap_badge(g.get("type", "question"))
                st.markdown(f"- {badge} **{g.get('title', g.get('slug', ''))}** — `{g.get('slug', '')}`")
            if st.button("Refresh total gap count"):
                st.rerun()

    st.divider()

    # ── Section D: How to Teach the Wiki ─────────────────────────
    st.subheader("How to Teach the Wiki")
    st.markdown("""
The wiki learns automatically through use. Here's the lifecycle:

| Step | What Happens |
|------|-------------|
| 1. User asks a question | Wiki searches its knowledge base |
| 2. Low/medium confidence | Claude identifies 2–3 knowledge gaps |
| 3. Stub pages created | `wiki/questions/` pages appear in Browse Pages |
| 4. You upload a document | PDF/DOCX → converted → wiki pages generated |
| 5. Gap auto-resolved | Stub is overwritten with real content |
| 6. KB re-indexed | Future queries return confident, cited answers |

**To fill a gap:** Upload a relevant document via **⬆️ Upload Documents**.
The wiki will auto-detect the document covers the gap and mark it resolved.
""")
