"""
Benefit Configuration Comparison — UC-BC
Compare two years of EOC PDFs and produce a structured benefit diff report.
"""

import json
import os
import time
from datetime import datetime, timezone

import boto3
import streamlit as st
from botocore.config import Config

st.set_page_config(
    page_title="Benefit Config — LLMWiki",
    page_icon="🏥",
    layout="wide",
)

AWS_REGION     = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
WIKI_BUCKET    = os.environ.get("WIKI_BUCKET", "")
BC_HARNESS_FN  = os.environ.get("BC_HARNESS_FUNCTION", "llmwiki-harness-uc-bc")
BC_RUNS_TABLE  = os.environ.get("BC_RUNS_TABLE", "llmwiki-bc-runs")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "llmwiki-document-registry")

lambda_client = boto3.client("lambda", region_name=AWS_REGION)
s3_client     = boto3.client("s3", region_name=AWS_REGION,
                              config=Config(signature_version="s3v4"))
dynamodb_r    = boto3.resource("dynamodb", region_name=AWS_REGION)

SEV_COLOR   = {"HIGH": "#fee2e2", "MEDIUM": "#fef9c3", "LOW": "#f0fdf4"}
SEV_BADGE   = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}
CAT_LABEL   = {
    "COST_INCREASE":      "💸 Cost Increase",
    "COST_DECREASE":      "✅ Cost Decrease",
    "COVERAGE_REDUCTION": "⬇️ Coverage Reduction",
    "COVERAGE_EXPANSION": "⬆️ Coverage Expansion",
    "ADMINISTRATIVE":     "📋 Administrative",
    "NEW_BENEFIT":        "🆕 New Benefit",
    "REMOVED_BENEFIT":    "❌ Removed Benefit",
}

# ── CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.phase-row { background:#f8fafc; border-left:3px solid #3b82f6;
             border-radius:4px; padding:8px 12px; margin:4px 0; font-size:.9em; }
.phase-done { border-left-color:#16a34a; background:#f0fdf4; }
.diff-high   { background:#fee2e2; border-radius:4px; padding:6px 10px; margin:3px 0; }
.diff-med    { background:#fef9c3; border-radius:4px; padding:6px 10px; margin:3px 0; }
.diff-low    { background:#f0fdf4; border-radius:4px; padding:6px 10px; margin:3px 0; }
.metric-chip { display:inline-block; background:#e0f2fe; color:#075985;
               border:1px solid #bae6fd; border-radius:10px;
               padding:2px 12px; font-size:.85em; margin:2px; }
.warn-box    { background:#fefce8; border:1px solid #fde68a; border-radius:6px;
               padding:10px 14px; font-size:.9em; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# Session state init
# ════════════════════════════════════════════════════════════════════════════

def _s():
    return st.session_state

for key, default in {
    "bc_run_id":      None,
    "bc_status":      "idle",
    "bc_phase4_data": None,
    "bc_phase6_data": None,
    "bc_phase8_data": None,
    "bc_log":         [],
    "bc_error":       None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def _log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    st.session_state.bc_log.append(f"`{ts}` {msg}")


def _invoke_harness(payload):
    try:
        resp      = lambda_client.invoke(
            FunctionName=BC_HARNESS_FN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        body_b    = resp["Payload"].read()
        outer     = json.loads(body_b)
        body_s    = outer.get("body", outer)
        result    = json.loads(body_s) if isinstance(body_s, str) else body_s
        status_c  = outer.get("statusCode", 200)
        return status_c, result
    except Exception as e:
        return 500, {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("# 🏥 Benefit Config")
    st.caption("Annual plan comparison — UC-BC")
    st.divider()

    st.markdown("### Plan Details")
    plan_id = st.text_input("Plan ID", value="UHC-UT-0003",
                             help="e.g. UHC-UT-0003, AETNA-TX-001")
    year_a  = st.selectbox("Year A (baseline)", ["2024", "2023", "2022"],
                            help="Older year — the 'before'")
    year_b  = st.selectbox("Year B (compare)", ["2025", "2024", "2023"],
                            help="Newer year — the 'after'")

    st.markdown("### Options")
    chapter_filter = st.multiselect(
        "Limit to chapters (leave blank = all)",
        ["Chapter 1: Getting Started", "Chapter 2: Resources",
         "Chapter 4: Medical Benefits", "Chapter 6: Part D",
         "Chapter 9: Appeals", "Chapter 11: Legal",
         "Chapter 12: Definitions"],
        help="Scope the comparison to specific chapters"
    )

    st.divider()
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/lambda_harness.py", label="⚡ Lambda Harness")

    if st.session_state.bc_log:
        st.divider()
        st.markdown("### Run Log")
        for line in st.session_state.bc_log[-12:]:
            st.markdown(line)


# ════════════════════════════════════════════════════════════════════════════
# Main panel
# ════════════════════════════════════════════════════════════════════════════

st.markdown("## 🏥 Benefit Configuration Comparison")
st.caption(f"Plan: `{plan_id}` · Comparing `{year_a}` → `{year_b}` · UC-BC Harness")

st.markdown("""<div class="warn-box">
⚠️ All outputs are <strong>DRAFT</strong> — AI-generated and pending analyst review.
Do not distribute to members before human sign-off.
</div>""", unsafe_allow_html=True)

st.markdown("---")

# ── Phase status strip ────────────────────────────────────────────
phases_meta = [
    (1, "Validate document index"),
    (2, f"Extract {year_a} benefit values"),
    (3, f"Extract {year_b} benefit values"),
    (4, "Claude diff synthesis"),
    (5, "Gap detection (SK-05)"),
    (6, "Categorise & rank differences"),
    (7, "Write diff draft to wiki (SK-03)"),
    (8, "Generate report + CSV + URLs"),
]

status = st.session_state.bc_status
ph4    = st.session_state.bc_phase4_data or {}
ph6    = st.session_state.bc_phase6_data or {}
ph8    = st.session_state.bc_phase8_data or {}

diffs_4 = ph4.get("differences", [])
diffs_6 = ph6.get("differences", [])
diffs   = diffs_6 or diffs_4

completed_phases = set()
if status in ("paused", "completed"):
    completed_phases = {1, 2, 3, 4}
if status == "completed":
    completed_phases = {1, 2, 3, 4, 5, 6, 7, 8}

cols = st.columns(4)
for i, (pnum, plabel) in enumerate(phases_meta):
    done = pnum in completed_phases
    icon = "✅" if done else ("⏳" if status == "running" and pnum == max(completed_phases or {0}) + 1 else "⭕")
    cols[i % 4].markdown(
        f"<div class='phase-row {'phase-done' if done else ''}'>"
        f"{icon} <strong>P{pnum}</strong> {plabel}</div>",
        unsafe_allow_html=True
    )

st.markdown("---")

# ════════════════════════════════════════════════════════════════════════════
# ACTION: Start
# ════════════════════════════════════════════════════════════════════════════

col_start, col_resume, col_reset = st.columns([1, 1, 1])

with col_start:
    start_disabled = status in ("running", "paused", "completed")
    if st.button("▶ Start Comparison", disabled=start_disabled,
                 use_container_width=True, type="primary"):
        st.session_state.bc_status      = "running"
        st.session_state.bc_phase4_data = None
        st.session_state.bc_phase6_data = None
        st.session_state.bc_phase8_data = None
        st.session_state.bc_error       = None
        st.session_state.bc_log         = []

        _log(f"Starting comparison — {plan_id} {year_a} vs {year_b}")

        chapters = [c.split(":")[0].strip() for c in chapter_filter] if chapter_filter else []
        payload = {
            "action":   "start",
            "plan_id":  plan_id,
            "year_a":   year_a,
            "year_b":   year_b,
            "chapters": chapters,
        }

        with st.spinner("Running phases 1–4… (Bedrock synthesis may take ~30s)"):
            t0   = time.time()
            code, result = _invoke_harness(payload)
            elapsed = int((time.time() - t0) * 1000)

        if code != 200 or "error" in result:
            st.session_state.bc_status = "error"
            st.session_state.bc_error  = result.get("error", str(result))
            _log(f"❌ Error: {st.session_state.bc_error}")
        else:
            st.session_state.bc_run_id      = result.get("run_id")
            st.session_state.bc_status      = "paused"
            st.session_state.bc_phase4_data = result
            _log(f"✅ Phases 1–4 done in {elapsed}ms — found {result.get('differences_found', 0)} differences")
            _log(f"   run_id: `{result.get('run_id')}`")

        st.rerun()

with col_resume:
    resume_disabled = status != "paused"
    if st.button("⏩ Generate Full Report", disabled=resume_disabled,
                 use_container_width=True):
        st.session_state.bc_status = "running"
        _log("Resuming — phases 5–8…")

        payload = {
            "action":  "resume",
            "plan_id": plan_id,
            "year_a":  year_a,
            "year_b":  year_b,
            "run_id":  st.session_state.bc_run_id,
        }

        with st.spinner("Running phases 5–8… generating HTML report and CSV…"):
            t0   = time.time()
            code, result = _invoke_harness(payload)
            elapsed = int((time.time() - t0) * 1000)

        if code != 200 or "error" in result:
            st.session_state.bc_status = "error"
            st.session_state.bc_error  = result.get("error", str(result))
            _log(f"❌ Resume error: {st.session_state.bc_error}")
        else:
            st.session_state.bc_status      = "completed"
            st.session_state.bc_phase6_data = result
            st.session_state.bc_phase8_data = result.get("artifacts", {})
            _log(f"✅ Complete in {elapsed}ms — {result.get('differences_found', 0)} diffs, "
                 f"{result.get('high_severity_count', 0)} HIGH")

        st.rerun()

with col_reset:
    if st.button("🔄 Reset", use_container_width=True):
        for key in ["bc_run_id", "bc_phase4_data", "bc_phase6_data",
                    "bc_phase8_data", "bc_error"]:
            st.session_state[key] = None
        st.session_state.bc_status = "idle"
        st.session_state.bc_log    = []
        st.rerun()

# ── Error banner ──────────────────────────────────────────────────
if st.session_state.bc_error:
    st.error(f"**Error:** {st.session_state.bc_error}")

# ════════════════════════════════════════════════════════════════════════════
# Results — Phase 4 preview (paused)
# ════════════════════════════════════════════════════════════════════════════

if status in ("paused", "completed") and ph4:
    st.markdown("---")
    st.markdown("### 🔍 Phase 4 — Preliminary Diff Results")

    c1, c2, c3 = st.columns(3)
    c1.metric("Year A items extracted", ph4.get("year_a_items", "—"))
    c2.metric("Year B items extracted", ph4.get("year_b_items", "—"))
    c3.metric("Differences found",      ph4.get("differences_found", len(diffs_4)))

    if diffs_4:
        with st.expander(f"Preview first 10 differences ({len(diffs_4)} total)", expanded=False):
            for d in diffs_4[:10]:
                st.markdown(
                    f"**{d.get('section_category', '?')}** "
                    f"({d.get('chapter', '')})  \n"
                    f"  `{year_a}:` {d.get('year_a_value', '')}  "
                    f"→ `{year_b}:` {d.get('year_b_value', '')}  \n"
                    f"  _{d.get('summary', '')}_"
                )
                st.divider()

    if status == "paused":
        st.info("Phases 1–4 complete. Click **Generate Full Report** to run categorisation, "
                "write to wiki, and produce the downloadable HTML + CSV report.")

# ════════════════════════════════════════════════════════════════════════════
# Results — Full report (completed)
# ════════════════════════════════════════════════════════════════════════════

if status == "completed":
    st.markdown("---")
    st.markdown("### ✅ Full Report — Complete")

    result    = st.session_state.bc_phase6_data or {}
    artifacts = st.session_state.bc_phase8_data or result.get("artifacts", {})

    total = result.get("differences_found", len(diffs_6))
    high  = result.get("high_severity_count", 0)
    gaps  = result.get("gaps_detected", 0)

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total differences",    total)
    mc2.metric("🔴 High severity",     high)
    mc3.metric("Knowledge gaps",       gaps)
    mc4.metric("Run ID", st.session_state.bc_run_id or "—")

    # Download buttons
    st.markdown("#### Download Artifacts")
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        html_url = artifacts.get("html_report", "")
        if html_url:
            st.link_button("📄 HTML Report", html_url, use_container_width=True)
        else:
            st.button("📄 HTML Report", disabled=True, use_container_width=True)
    with dc2:
        csv_url = artifacts.get("xlsx_report", "")
        if csv_url:
            st.link_button("📊 CSV Differences", csv_url, use_container_width=True)
        else:
            st.button("📊 CSV Differences", disabled=True, use_container_width=True)
    with dc3:
        summary_url = artifacts.get("member_summary", "")
        if summary_url:
            st.link_button("📋 Member Summary", summary_url, use_container_width=True)
        else:
            st.button("📋 Member Summary", disabled=True, use_container_width=True)

    wiki_uri = artifacts.get("wiki_draft", "")
    if wiki_uri:
        st.info(f"📝 Wiki draft written to: `{wiki_uri}` (pending analyst review)")

    # ── Detailed diff table ───────────────────────────────────────
    if diffs_6:
        st.markdown("---")
        st.markdown("### All Differences")

        # Filter controls
        fc1, fc2 = st.columns(2)
        with fc1:
            sev_filter = st.multiselect(
                "Filter by severity", ["HIGH", "MEDIUM", "LOW"],
                default=["HIGH", "MEDIUM", "LOW"]
            )
        with fc2:
            cat_filter = st.multiselect(
                "Filter by category",
                list(CAT_LABEL.keys()),
                default=list(CAT_LABEL.keys()),
                format_func=lambda x: CAT_LABEL.get(x, x)
            )

        filtered = [
            d for d in diffs_6
            if d.get("severity", "LOW") in sev_filter
            and d.get("category", "ADMINISTRATIVE") in cat_filter
        ]
        st.caption(f"Showing {len(filtered)} of {len(diffs_6)} differences")

        for d in filtered:
            sev   = d.get("severity", "LOW")
            cat   = d.get("category", "")
            color = SEV_COLOR.get(sev, "#f8fafc")
            badge = SEV_BADGE.get(sev, "⚪")
            cat_l = CAT_LABEL.get(cat, cat)

            st.markdown(
                f"<div style='background:{color};border-radius:6px;"
                f"padding:10px 14px;margin:6px 0;border-left:4px solid "
                f"{'#dc2626' if sev=='HIGH' else '#d97706' if sev=='MEDIUM' else '#16a34a'};'>"
                f"<strong>{badge} {d.get('section_category', '')}</strong> "
                f"<span style='font-size:.8em;color:#64748b;'>{d.get('chapter', '')}</span>"
                f"<span style='float:right;font-size:.8em;'>{cat_l}</span>"
                f"<br/>"
                f"<code>{year_a}:</code> {d.get('year_a_value', '')} &nbsp;→&nbsp; "
                f"<code>{year_b}:</code> {d.get('year_b_value', '')}<br/>"
                f"<em>{d.get('summary', '')}</em>"
                f"</div>",
                unsafe_allow_html=True
            )

# ════════════════════════════════════════════════════════════════════════════
# Upload helper
# ════════════════════════════════════════════════════════════════════════════

with st.expander("📤 Upload EOC PDFs to S3 (first-time setup)", expanded=False):
    st.markdown(
        "Upload both year PDFs here so the Converter Lambda can index them "
        "into the Bedrock Knowledge Base before running the comparison."
    )
    uf1, uf2 = st.columns(2)
    with uf1:
        file_a = st.file_uploader(f"Upload {year_a} EOC PDF", type=["pdf"], key="upload_a")
        if file_a and st.button(f"Upload {year_a} PDF", key="btn_upload_a"):
            if not WIKI_BUCKET:
                st.error("WIKI_BUCKET env var not set.")
            else:
                key = f"uploads/benefit-config/{plan_id}/{year_a}-eoc.pdf"
                try:
                    s3_client.upload_fileobj(file_a, WIKI_BUCKET, key)
                    st.success(f"Uploaded → `s3://{WIKI_BUCKET}/{key}`")
                    st.info("Converter Lambda will index this within ~2 minutes.")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
    with uf2:
        file_b = st.file_uploader(f"Upload {year_b} EOC PDF", type=["pdf"], key="upload_b")
        if file_b and st.button(f"Upload {year_b} PDF", key="btn_upload_b"):
            if not WIKI_BUCKET:
                st.error("WIKI_BUCKET env var not set.")
            else:
                key = f"uploads/benefit-config/{plan_id}/{year_b}-eoc.pdf"
                try:
                    s3_client.upload_fileobj(file_b, WIKI_BUCKET, key)
                    st.success(f"Uploaded → `s3://{WIKI_BUCKET}/{key}`")
                    st.info("Converter Lambda will index this within ~2 minutes.")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
