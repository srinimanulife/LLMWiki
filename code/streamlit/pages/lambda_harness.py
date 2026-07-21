"""
Lambda Harness — UC1 Sales-to-Service + UC-PM Problem Management
8 system-enforced phases · Gatekeeper validated · Inline traces + metrics
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

import boto3
import streamlit as st
from botocore.config import Config

st.set_page_config(
    page_title="Lambda Harness — LLMWiki",
    page_icon="⚡",
    layout="wide",
)

AWS_REGION       = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
S2S_WIKI_BUCKET  = os.environ.get("WIKI_BUCKET",           "llmwiki-278e7e22")
PM_WIKI_BUCKET   = os.environ.get("PM_WIKI_BUCKET",        "llmwiki-problem-mgnt-278e7e22")
GATEKEEPER_FN    = os.environ.get("GATEKEEPER_FUNCTION",   "llmwiki-gatekeeper")
S2S_HARNESS_FN   = os.environ.get("UC1_HARNESS_FUNCTION",  "llmwiki-uc1-harness")
PM_HARNESS_FN    = os.environ.get("PM_HARNESS_FUNCTION",   "llmwiki-harness-uc-pm")
TRACES_TABLE     = os.environ.get("DYNAMODB_LOG",          "llmwiki-log")
USAGE_TABLE      = os.environ.get("USAGE_TABLE",           "llmwiki-usage")

lambda_client = boto3.client("lambda", region_name=AWS_REGION)
s3_client     = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
dynamodb_r    = boto3.resource("dynamodb", region_name=AWS_REGION)

# ── Agent registry ─────────────────────────────────────────────────
AGENTS = {
    "s2s": {
        "id":          "s2s",
        "label":       "UC1 Sales-to-Service",
        "harness_fn":  S2S_HARNESS_FN,
        "wiki_bucket": S2S_WIKI_BUCKET,
        "title":       "⚡ UC1 — Sales-to-Service",
        "caption":     "8 system-enforced phases · Customer onboarding handoff · Gatekeeper validated",
        "greeting": (
            "👋 I'm the **UC1 Sales-to-Service Agent**.\n\n"
            "Click **Start Harness** to validate prerequisites and begin the 8-phase handoff workflow."
        ),
        "uses_gatekeeper":          True,
        "start_confirmation_label": "Engagement",
        "start_hint": "💡 Type `Go ahead` to start phases 1 and 2.",
        "chat_placeholder":         "Type 'Go ahead' to start...",
        "default_inputs": {
            "customer_id":   "bcbs-mn-001",
            "customer_name": "BlueCross BlueShield Minnesota",
            "product":       "TriZetto QNXT",
            "sow_ref":       "SOW-2026-BCBS-MN-001",
        },
        "phases": [
            {"num": 1, "name": "SOW Intake & Extraction",   "type": "programmatic",    "skill": None,    "icon": "📄"},
            {"num": 2, "name": "Customer Classification",   "type": "llm_single",      "skill": None,    "icon": "🏷️"},
            {"num": 3, "name": "Gather Handoff Context",    "type": "llm_human_input", "skill": None,    "icon": "💬"},
            {"num": 4, "name": "Load Delivery Playbook",    "type": "llm_agent",       "skill": "SK-01", "icon": "📋"},
            {"num": 5, "name": "Risk & Gap Analysis",       "type": "llm_agent",       "skill": "SK-02", "icon": "🔍"},
            {"num": 6, "name": "Gap Detection & Recording", "type": "llm_batch_agents","skill": "SK-05", "icon": "🔭"},
            {"num": 7, "name": "Template Population",       "type": "llm_agent",       "skill": "SK-04", "icon": "📝"},
            {"num": 8, "name": "Write Handoff + Report",    "type": "llm_single",      "skill": "SK-03", "icon": "💾"},
            {"num": 9, "name": "Session Wrap-up",           "type": "programmatic",    "skill": None,    "icon": "📌"},
        ],
        "input_labels": ["Customer ID", "Customer Name", "Product in Scope", "SOW Reference"],
        "human_input_hint": (
            "**Example:**\n> No prior attempts. CMO is executive sponsor. "
            "Go-live Q1 2027. HIPAA required; EHR is Epic."
        ),
    },
    "pm": {
        "id":          "pm",
        "label":       "UC-PM Problem Management",
        "harness_fn":  PM_HARNESS_FN,
        "wiki_bucket": PM_WIKI_BUCKET,
        "title":       "⚡ UC-PM — Problem Management",
        "caption":     "8 system-enforced phases · AI-assisted RCA & KEDB · Cross-product pattern detection",
        "greeting": (
            "👋 I'm the **UC-PM Problem Management Agent**.\n\n"
            "I run **8 system-enforced phases** to investigate complex problems including "
            "cross-product root causes across Facets · QNXT · EAM · EDM · TCS · NetworX · FRM.\n\n"
            "Configure the sidebar, then click **Start Harness** and type `Go ahead`."
        ),
        "uses_gatekeeper":          False,
        "start_confirmation_label": "Problem",
        "start_hint": "💡 Type `Go ahead` to kick off phases 1 & 2.",
        "chat_placeholder":         "Type 'Go ahead' to start phases 1 & 2...",
        "default_inputs": {
            "customer_id":   "BATCH-XSYS-2026-06",
            "customer_name": "Claims Adjudication Engine",
            "product":       "Facets",
            "sow_ref":       "PRB-XSYS-001",
        },
        "phases": [
            {"num": 1, "name": "Problem Record Load",               "type": "programmatic",    "skill": None,    "icon": "📥"},
            {"num": 2, "name": "Problem Classification (SK-06)",    "type": "llm_single",      "skill": "SK-06", "icon": "🏷️"},
            {"num": 3, "name": "SME Context Collection ← Human",    "type": "llm_human_input", "skill": None,    "icon": "💬"},
            {"num": 4, "name": "Load Prior Knowledge (SK-01)",      "type": "llm_agent",       "skill": "SK-01", "icon": "📚"},
            {"num": 5, "name": "RCA Draft & Cross-System Patterns", "type": "llm_agent",       "skill": "SK-02", "icon": "🔍"},
            {"num": 6, "name": "Knowledge Gap Detection (SK-05)",   "type": "llm_agent",       "skill": "SK-05", "icon": "🔭"},
            {"num": 7, "name": "Fill RCA & KEDB Templates (SK-04)", "type": "llm_single",      "skill": "SK-04", "icon": "📝"},
            {"num": 8, "name": "Write Draft & Route Review (SK-03)","type": "programmatic",    "skill": "SK-03", "icon": "💾"},
            {"num": 9, "name": "Session Wrap-up",                   "type": "programmatic",    "skill": None,    "icon": "📌"},
        ],
        "input_labels": ["Batch ID", "Affected Component", "Product (Facets / QNXT / …)", "Problem ID"],
        "human_input_hint": (
            "**Cross-System Scenario (recommended for demo):**\n\n"
            "> Month-end claims batch failed at 2:47 AM — Facets Claims Adjudication Engine "
            "aborted with NullPointerException on 14,832 Medicare supplemental claims."
        ),
    },
}

PHASE_TYPE_BADGE = {
    "programmatic":    "🐍 Python",
    "llm_single":      "⚡ Claude",
    "llm_human_input": "💬 Human",
    "llm_agent":       "🤖 Agent",
    "llm_batch_agents":"⚡×N Parallel",
}


# ── CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.lock-badge { background:#1e3a5f; color:white; padding:4px 12px;
              border-radius:6px; font-size:.85em; font-weight:600;
              display:inline-block; margin-bottom:8px; }
.phase-complete { color:#16a34a; }
.phase-running  { color:#2563eb; }
.phase-error    { color:#dc2626; }
.phase-paused   { color:#d97706; }
.metric-chip { display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0;
               border-radius:6px; padding:4px 12px; font-size:.85em; margin:2px 4px 2px 0; }
</style>
""", unsafe_allow_html=True)


# ── Core helper functions ──────────────────────────────────────────

def _invoke(fn_name: str, payload: dict) -> dict:
    try:
        resp = lambda_client.invoke(
            FunctionName=fn_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload, default=str).encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            b = raw["body"]
            return json.loads(b) if isinstance(b, str) else (b or {})
        return raw
    except Exception as e:
        err = str(e)
        if "ResourceNotFoundException" in err or "Function not found" in err:
            return {"_not_deployed": True, "error": f"`{fn_name}` not yet deployed"}
        return {"_error": True, "error": err}


def _is_done(status: str) -> bool:
    return status in ("completed", "completed_with_gaps")


def _parse_if_str(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return val or {}


def _phase_state(result: dict, phase_num: int) -> str:
    if not result:
        return "pending"
    status = result.get("status", "")
    phases_done = len([k for k in result.get("phase_results", {}) if k != "error"])
    if status == "error" and result.get("failed_phase") == phase_num:
        return "error"
    if status == "paused" and result.get("current_phase") == phase_num:
        return "paused"
    # Phase 9 is the wrap-up — marks complete when entire run is done
    if phase_num == 9:
        return "complete" if _is_done(status) else "pending"
    if phase_num <= phases_done:
        return "complete"
    if _is_done(status):
        return "complete"
    if phase_num == phases_done + 1 and status == "running":
        return "running"
    return "pending"


def _phase_icon(state: str) -> str:
    return {"complete": "✅", "running": "🔵", "error": "❌", "paused": "⏸️", "pending": "⬜"}[state]


def _phase_summary(result: dict, phase_num: int, agent_id: str = "s2s") -> str:
    pr = result.get("phase_results", {})
    p  = pr.get(f"phase{phase_num}", {})
    if not p:
        return ""
    if phase_num == 1:
        if agent_id == "pm":
            return f"Problem: {p.get('problem_id','—')} · {p.get('records_loaded', p.get('pages_found',0))} records"
        return f"Customer: {p.get('customer_status','—')} · {p.get('pages_found',0)} pages"
    if phase_num == 2:
        if agent_id == "pm":
            return f"Category: {p.get('normalized_category', p.get('category','—'))} · Risk: {p.get('risk_tier','—')}"
        return f"Risk tier: {p.get('risk_tier','—')} · Type: {p.get('customer_type','—')}"
    if phase_num == 3:
        return "Context captured" if p.get("context_provided") else "Awaiting input"
    if phase_num == 4:
        if agent_id == "pm":
            return f"KB passages: {p.get('kb_passages_count', len(p.get('kb_passages',[])))} · Prior RCAs: {p.get('prior_rcas_count', len(p.get('prior_rcas',[])))}"
        return f"Playbook steps: {p.get('playbook_steps',0)} · Pages: {p.get('pages_loaded',0)}"
    if phase_num == 5:
        if agent_id == "pm":
            return f"Confidence: {p.get('rca_confidence', p.get('confidence','—'))} · Citations: {len(p.get('kb_citations',[]))}"
        return f"Confidence: {p.get('confidence','—')} · Actions: {len(p.get('action_items',[]))}"
    if phase_num == 6:
        if p.get("skipped"):
            return "Skipped — confidence=high"
        return f"Gaps: {p.get('gap_count',0)} · Blocking: {p.get('blocking_count',0)}"
    if phase_num == 7:
        return f"Template: {'found' if p.get('found') else 'not found'} · Fill: {p.get('completion_pct',0)}%"
    if phase_num == 8:
        if agent_id == "pm":
            return "✅ RCA draft saved" if p.get("indexed") else "⚠️ Save pending"
        return "✅ Handoff indexed" if p.get("indexed") else "⚠️ Index pending"
    if phase_num == 9:
        if _is_done(result.get("status", "")):
            return "✅ Session record written to llmwiki-log"
        return ""
    return ""


def _telemetry(result: dict) -> dict:
    if not result:
        return {"phases_done": 0, "skills": 0, "gaps": 0, "latency": 0}
    pr = result.get("phase_results", {})
    phases_done = len([k for k in pr if k != "error"])
    skills = sum(1 for k in ["phase4", "phase5", "phase6", "phase7", "phase8"] if k in pr)
    return {
        "phases_done": phases_done,
        "skills":      skills,
        "gaps":        pr.get("phase6", {}).get("gap_count", 0),
        "latency":     int(result.get("total_latency_ms", 0) or 0),
        "confidence":  pr.get("phase5", {}).get("confidence",
                       pr.get("phase5", {}).get("rca_confidence", "")),
    }


def _build_harness_payload(agent_cfg: dict, customer_id: str, customer_name: str,
                            product: str, sow_ref: str, agent_id_val: str,
                            human_context: str = "", run_id: str = "",
                            action: str = "", severity: str = "P1",
                            record_ids: list = None) -> dict:
    if agent_cfg["id"] == "pm":
        if action == "get_status" and run_id:
            return {"action": "get_status", "run_id": run_id}
        payload = {
            "batch_id":           customer_id,
            "problem_id":         sow_ref,
            "product":            product,
            "severity":           severity,
            "component":          customer_name,
            "related_record_ids": record_ids or [],
        }
        if human_context:
            payload["sme_context"] = human_context
        return payload
    else:
        payload = {
            "engagement_id": customer_id,
            "customer_id":   customer_id,
            "customer_name": customer_name,
            "product":       product,
            "sow_reference": sow_ref,
            "agent_id":      agent_id_val,
            "human_context": human_context,
        }
        if action == "get_status" and run_id:
            payload["action"] = "get_status"
            payload["run_id"] = run_id
        if run_id and not action:
            payload["resume_run_id"] = run_id
        return payload


def _completion_message(result: dict, agent_id: str) -> str:
    pr       = result.get("phase_results", {})
    p2       = pr.get("phase2", {})
    p5       = pr.get("phase5", {})
    p6       = pr.get("phase6", {})
    p7       = pr.get("phase7", {})
    p8       = pr.get("phase8", {})
    total_ms = int(result.get("total_latency_ms", 0) or 0)
    if agent_id == "pm":
        root_cause = p5.get("root_cause_statement", "") or p5.get("root_cause", "")
        return (
            f"🎉 **All 8 phases complete** in {total_ms:,}ms\n\n"
            f"**RCA Summary:**\n"
            f"- Problem category: **{p2.get('normalized_category', p2.get('category','—'))}** · Risk: **{p2.get('risk_tier','—')}**\n"
            f"- Root cause: {root_cause[:200] + '…' if len(root_cause) > 200 else root_cause or '(see report)'}\n"
            f"- RCA confidence: **{p5.get('confidence','—')}**\n"
            f"- Knowledge gaps recorded: **{p6.get('gap_count',0)}**\n"
            f"- RCA draft: {'✅ saved to wiki (pending review)' if p8.get('indexed') else '⚠️ pending save'}\n\n"
            f"The RCA report is ready for download. Ask me anything about the problem."
        )
    else:
        return (
            f"🎉 **All 8 phases complete** in {total_ms:,}ms\n\n"
            f"**Summary:**\n"
            f"- Risk tier: **{p2.get('risk_tier','—')}** ({p2.get('customer_type','—')})\n"
            f"- Delivery risks: **{len(p5.get('action_items',[]))}** action items\n"
            f"- Knowledge gaps recorded: **{p6.get('gap_count',0)}**\n"
            f"- Template: **{p7.get('completion_pct',0)}%** complete\n"
            f"- Handoff brief: {'✅ indexed in wiki' if p8.get('indexed') else '⚠️ pending review'}\n\n"
            f"The report is ready for download. Ask me anything about the engagement."
        )


def _post_harness_answer(question: str, context: str, customer_name: str,
                          product: str, agent_id: str) -> str:
    try:
        bedrock  = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
        role = (
            f"RCA expert for component '{customer_name}' on {product}"
            if agent_id == "pm"
            else f"delivery expert for {customer_name} ({product})"
        )
        prompt = (
            f"You are a {role}.\n\nPhase results:\n{context}\n\n"
            f"Question: {question}\n\nAnswer concisely in 2-4 sentences."
        )
        resp = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            }),
            contentType="application/json", accept="application/json",
        )
        return json.loads(resp["body"].read())["content"][0]["text"].strip()
    except Exception as e:
        return (f"Phase results are available in the panel on the right. (Error: {e})")


def _rebuild_chat_from_run(run: dict, customer_name: str, agent_id: str) -> list:
    msgs = []
    pr     = _parse_if_str(run.get("phase_results", {}))
    status = run.get("status", "")
    run_id = run.get("run_id", "")
    started = run.get("started_at", "")[:16].replace("T", " ") or "earlier"
    msgs.append({"role": "assistant", "content": (
        f"**Reconnecting to prior harness run** 🔄\n\n"
        f"Run `{run_id}` started **{started} UTC** — status: **{status.upper()}**."
    )})
    if pr.get("phase1"):
        p1 = pr["phase1"]
        msgs.append({"role": "assistant", "content": (
            f"**✅ Phase 1 complete** — {p1.get('customer_status', p1.get('problem_id','—'))}"
        )})
    if pr.get("phase2"):
        p2 = pr["phase2"]
        msgs.append({"role": "assistant", "content": (
            f"**✅ Phase 2 complete** — {p2.get('customer_type', p2.get('normalized_category','—'))} "
            f"· Risk tier: **{p2.get('risk_tier','—')}**"
        )})
    if _is_done(status):
        msgs.append({"role": "assistant", "content": _completion_message(run, agent_id)})
    return msgs


def _reconnect(gk: dict, customer_id: str, customer_name: str,
               product: str, sow_ref: str, agent_id: str, pfx: str) -> None:
    run    = gk.get("active_run", {})
    status = gk.get("active_status", "running")
    run_id = gk.get("active_run_id", "")
    run["phase_results"] = _parse_if_str(run.get("phase_results", {}))
    st.session_state[f"{pfx}_result"]      = run
    st.session_state[f"{pfx}_run_id"]      = run_id
    st.session_state[f"{pfx}_gk_done"]     = True
    st.session_state[f"{pfx}_running"]     = False
    st.session_state[f"{pfx}_reconnected"] = True
    current_phase = int(run.get("current_phase") or 0)
    question = run.get("phase3_question") or run.get("question") or ""
    if _is_done(status):
        st.session_state[f"{pfx}_p3_answered"] = True
        st.session_state[f"{pfx}_polling"]     = False
    elif status == "paused" and current_phase == 3:
        st.session_state[f"{pfx}_p3_answered"] = False
        st.session_state[f"{pfx}_polling"]     = False
        st.session_state[f"{pfx}_p3_question"] = question
    elif status in ("running", "paused"):
        st.session_state[f"{pfx}_p3_answered"] = False
        st.session_state[f"{pfx}_polling"]     = True
    st.session_state[f"{pfx}_chat"] = _rebuild_chat_from_run(run, customer_name, agent_id)


@st.cache_data(ttl=10)
def _get_lambda_traces(days_back: int = 3, limit: int = 10) -> list:
    rows = []
    today = datetime.now(timezone.utc)
    table = dynamodb_r.Table(TRACES_TABLE)
    for delta in range(days_back):
        day = (today - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            resp = table.query(
                KeyConditionExpression="log_date = :lk",
                ExpressionAttributeValues={":lk": f"traces#llmwiki-query#{day}"},
                ScanIndexForward=False,
                Limit=limit,
            )
            for item in resp.get("Items", []):
                try:
                    attrs = json.loads(item.get("attributes", "{}"))
                except Exception:
                    attrs = {}
                rows.append({
                    "Time":       item.get("timestamp_id", "")[:16],
                    "Span":       item.get("span_id", "")[:10],
                    "Question":   str(attrs.get("input.value", ""))[:80],
                    "Confidence": attrs.get("llmwiki.confidence", ""),
                    "Caller":     attrs.get("llmwiki.caller", ""),
                    "_raw":       item,
                })
        except Exception:
            pass
    return rows[:limit]


@st.cache_data(ttl=30)
def _session_usage(days: int = 30) -> dict:
    try:
        table = dynamodb_r.Table(USAGE_TABLE)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp  = table.query(
            KeyConditionExpression="log_date = :d",
            ExpressionAttributeValues={":d": today},
            ScanIndexForward=False,
            Limit=50,
        )
        items = resp.get("Items", [])
        total_cost  = sum(float(i.get("cost_usd", 0)) for i in items)
        total_calls = len(items)
        return {"calls": total_calls, "cost_usd": round(total_cost, 4)}
    except Exception:
        return {"calls": 0, "cost_usd": 0.0}


def _presign(s3_key: str, wiki_bucket: str = "") -> str:
    if not s3_key:
        return ""
    try:
        bucket = wiki_bucket or S2S_WIKI_BUCKET
        if s3_key.startswith("s3://"):
            parts  = s3_key[5:].split("/", 1)
            bucket = parts[0]
            s3_key = parts[1] if len(parts) > 1 else ""
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=3600,
        )
    except Exception:
        return ""


# ── Page header ──────────────────────────────────────────────────────
st.markdown("## ⚡ Lambda Harness")
st.caption("Hard harness · 8 system-enforced phases · Gatekeeper validated")

# ── Agent tabs ────────────────────────────────────────────────────────
tab_s2s, tab_pm = st.tabs(["🏢 UC1 Sales-to-Service", "🔧 UC-PM Problem Management"])

for tab_widget, agent_key in [(tab_s2s, "s2s"), (tab_pm, "pm")]:
    with tab_widget:
        agent_cfg   = AGENTS[agent_key]
        PHASES      = agent_cfg["phases"]
        HARNESS_FN  = agent_cfg["harness_fn"]
        WIKI_BUCKET = agent_cfg["wiki_bucket"] or S2S_WIKI_BUCKET
        pfx         = agent_key  # session state prefix per agent

        # ── Per-agent sidebar config ──────────────────────────────────
        with st.sidebar:
            if agent_key == "s2s":
                st.markdown("## ⚡ Lambda Harness")
                st.caption("Configure each use case here.")
                st.divider()

            st.markdown(f"**{agent_cfg['label']}**")
            defaults = agent_cfg["default_inputs"]
            labels   = agent_cfg["input_labels"]

            customer_id   = st.text_input(labels[0], value=defaults["customer_id"],   key=f"{pfx}_cid")
            customer_name = st.text_input(labels[1], value=defaults["customer_name"], key=f"{pfx}_cname")
            product       = st.text_input(labels[2], value=defaults["product"],       key=f"{pfx}_prod")
            sow_ref       = st.text_input(labels[3], value=defaults["sow_ref"],       key=f"{pfx}_sow")
            agent_id_val  = st.text_input("Agent ID", value=f"{pfx}-harness-v1",       key=f"{pfx}_aid")

            pm_severity  = "P1"
            pm_record_ids = []
            if agent_key == "pm":
                pm_severity = st.selectbox(
                    "Severity",
                    ["P1 — Critical", "P2 — High", "P3 — Medium"],
                    key="pm_sev",
                ).split(" — ")[0]
                pm_raw = st.text_area("Related Record IDs (one per line)", height=60,
                                      key="pm_rids", placeholder="INC-001\nLOG-042")
                pm_record_ids = [r.strip() for r in pm_raw.splitlines() if r.strip()]

            st.divider()
            if st.button("🔄 Reset Harness", type="secondary", key=f"{pfx}_reset"):
                for k in [f"{pfx}_result", f"{pfx}_gk_done", f"{pfx}_running",
                          f"{pfx}_p3_question", f"{pfx}_p3_answered", f"{pfx}_chat",
                          f"{pfx}_polling", f"{pfx}_run_id", f"{pfx}_p3_ctx", f"{pfx}_reconnected"]:
                    st.session_state.pop(k, None)
                st.rerun()

        # ── Session state init ─────────────────────────────────────────
        for k, default in [
            (f"{pfx}_chat",        []),
            (f"{pfx}_gk_done",     False),
            (f"{pfx}_running",     False),
            (f"{pfx}_result",      {}),
            (f"{pfx}_p3_answered", False),
        ]:
            if k not in st.session_state:
                st.session_state[k] = default

        harness_result = st.session_state.get(f"{pfx}_result", {})

        # ── Two-column layout ─────────────────────────────────────────
        col_chat, col_right = st.columns([55, 45], gap="large")

        # ══════════════════════════════════════════════════════════════
        # LEFT — Conversation
        # ══════════════════════════════════════════════════════════════
        with col_chat:
            for msg in st.session_state[f"{pfx}_chat"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Reconnect banner
            if st.session_state.get(f"{pfx}_reconnected"):
                run_id = st.session_state.get(f"{pfx}_run_id", "")
                status = harness_result.get("status", "")
                st.info(f"**Prior run detected** — `{run_id}` ({status.upper()})")
                cr1, cr2 = st.columns(2)
                if cr1.button("▶ Continue this run", type="primary", key=f"{pfx}_continue"):
                    st.session_state[f"{pfx}_reconnected"] = False
                    st.rerun()
                if cr2.button("🔄 Start fresh", key=f"{pfx}_fresh"):
                    for k in [f"{pfx}_result", f"{pfx}_gk_done", f"{pfx}_running",
                              f"{pfx}_p3_question", f"{pfx}_p3_answered", f"{pfx}_chat",
                              f"{pfx}_polling", f"{pfx}_run_id", f"{pfx}_reconnected"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                st.stop()

            # Stage 1: Start button
            if not st.session_state[f"{pfx}_gk_done"] and not st.session_state[f"{pfx}_running"]:
                with st.chat_message("assistant"):
                    st.markdown(agent_cfg["greeting"])
                if st.button("▶ Start Harness", type="primary", key=f"{pfx}_start"):
                    if agent_cfg["uses_gatekeeper"]:
                        with st.spinner("Gatekeeper validating prerequisites…"):
                            gk = _invoke(GATEKEEPER_FN, {
                                "customer_id":   customer_id,
                                "customer_name": customer_name,
                                "product":       product,
                                "sow_reference": sow_ref,
                                "agent_id":      agent_id_val,
                            })
                        if gk.get("_not_deployed") or gk.get("_error"):
                            st.error(f"⚠️ Gatekeeper error: {gk.get('error')}")
                            st.stop()
                        if not gk.get("ready") and gk.get("resume"):
                            _reconnect(gk, customer_id, customer_name, product, sow_ref,
                                       agent_cfg["id"], pfx)
                            st.rerun()
                        if not gk.get("ready"):
                            st.warning(f"🚫 Not ready: {gk.get('message')}")
                            st.stop()
                        msg_txt = gk.get("message", "Prerequisites validated.")
                        st.session_state[f"{pfx}_chat"].append({
                            "role": "assistant",
                            "content": (
                                f"**Prerequisites validated ✅**\n\n{msg_txt}\n\n"
                                f"**Engagement:** {customer_name} · {product} · {sow_ref}\n\n"
                                "Type **'Go ahead'** to start the 8-phase workflow."
                            ),
                        })
                    else:
                        st.session_state[f"{pfx}_chat"].append({
                            "role": "assistant",
                            "content": (
                                f"**Ready to begin ✅**\n\n"
                                f"**{agent_cfg['start_confirmation_label']}:** {sow_ref} · {customer_name} · {product}\n\n"
                                "Type **'Go ahead'** to start the 8-phase workflow."
                            ),
                        })
                    st.session_state[f"{pfx}_gk_done"] = True
                    st.rerun()

            # Stage 2: Confirm → fire harness
            elif (st.session_state[f"{pfx}_gk_done"]
                  and not st.session_state[f"{pfx}_running"]
                  and not st.session_state[f"{pfx}_result"]
                  and not st.session_state[f"{pfx}_p3_answered"]):
                with st.chat_message("assistant"):
                    st.markdown(agent_cfg["start_hint"])
                user_input = st.chat_input(agent_cfg["chat_placeholder"], key=f"{pfx}_ci1")
                if user_input:
                    st.session_state[f"{pfx}_chat"].append({"role": "user", "content": user_input})
                    st.session_state[f"{pfx}_running"] = True
                    st.rerun()

            # Stage 3: Run phases 1-2
            elif st.session_state[f"{pfx}_running"] and not st.session_state[f"{pfx}_result"]:
                st.session_state[f"{pfx}_chat"].append({
                    "role": "assistant",
                    "content": f"🔒 **Harness started.** Running phases 1 and 2…",
                })
                with st.spinner("Running Phase 1 and Phase 2…"):
                    result = _invoke(HARNESS_FN, _build_harness_payload(
                        agent_cfg, customer_id, customer_name, product, sow_ref, agent_id_val,
                        severity=pm_severity, record_ids=pm_record_ids,
                    ))
                if result.get("_not_deployed") or result.get("_error"):
                    st.error(f"⚠️ Harness error: {result.get('error')}")
                    st.session_state[f"{pfx}_running"] = False
                    st.stop()
                st.session_state[f"{pfx}_result"]  = result
                st.session_state[f"{pfx}_running"] = False
                status = result.get("status", "")
                pr     = result.get("phase_results", {})
                if status == "paused" and result.get("current_phase") == 3:
                    if agent_cfg["id"] == "pm":
                        cls = result.get("classification", {})
                        questions = result.get("questions", [])
                        q_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions)) or "Please provide SME context."
                        cls_msg = (
                            f"**Phases 1–2 complete ✅**\n\n"
                            f"**Classification:** {cls.get('normalized_category','—')} · "
                            f"Risk: **{cls.get('risk_tier','—')}** · "
                            f"Recurrence: {cls.get('recurrence_type','—')}\n\n---\n\n"
                            f"**⏸️ Phase 3 — SME input required:**\n\n{q_text}"
                        )
                        st.session_state[f"{pfx}_p3_question"] = q_text
                    else:
                        cls = pr.get("phase2", {})
                        cls_msg = (
                            f"**Phases 1–2 complete ✅**\n\n"
                            f"**Classification:** {cls.get('customer_type','Unknown')} · "
                            f"Risk: **{cls.get('risk_tier','—')}**\n\n"
                            f"_{cls.get('rationale','')}_\n\n---\n\n"
                            f"**⏸️ Phase 3 — I need your input:**\n\n"
                            f"{result.get('question', 'Please provide engagement context.')}"
                        )
                        st.session_state[f"{pfx}_p3_question"] = result.get("question", "")
                    st.session_state[f"{pfx}_chat"].append({"role": "assistant", "content": cls_msg})
                elif _is_done(status):
                    st.session_state[f"{pfx}_chat"].append({
                        "role": "assistant",
                        "content": _completion_message(result, agent_cfg["id"]),
                    })
                elif status == "error":
                    st.session_state[f"{pfx}_chat"].append({
                        "role": "assistant",
                        "content": f"❌ Error at Phase {result.get('failed_phase')}: {result.get('error')}",
                    })
                st.rerun()

            # Stage 4: Awaiting Phase 3 input
            elif (st.session_state.get(f"{pfx}_result", {}).get("status") == "paused"
                  and not st.session_state.get(f"{pfx}_p3_answered")
                  and not st.session_state.get(f"{pfx}_polling")):
                q_text = st.session_state.get(f"{pfx}_p3_question", "")
                if q_text:
                    with st.chat_message("assistant"):
                        st.markdown("**⏸️ Waiting for your input:**")
                        st.markdown(q_text)
                st.info("💡 " + agent_cfg["human_input_hint"])
                ctx_input = st.text_area(
                    "Your answers:", height=120,
                    placeholder="Answer the numbered questions above…",
                    key=f"{pfx}_p3_ta",
                )
                if st.button("▶ Submit & run phases 4–8", type="primary", key=f"{pfx}_p3_sub"):
                    ctx = ctx_input.strip()
                    if ctx:
                        st.session_state[f"{pfx}_chat"].append({"role": "user", "content": ctx})
                        st.session_state[f"{pfx}_chat"].append({"role": "assistant", "content": (
                            "✅ **Context received.** Firing phases 4–8 — "
                            "watch the phase tracker on the right."
                        )})
                        prior  = st.session_state[f"{pfx}_result"]
                        run_id = prior.get("run_id", "")
                        lambda_client.invoke(
                            FunctionName=HARNESS_FN,
                            InvocationType="Event",
                            Payload=json.dumps(
                                _build_harness_payload(
                                    agent_cfg, customer_id, customer_name, product, sow_ref,
                                    agent_id_val, human_context=ctx, run_id=run_id,
                                    severity=pm_severity, record_ids=pm_record_ids,
                                ), default=str,
                            ).encode(),
                        )
                        st.session_state[f"{pfx}_polling"]     = True
                        st.session_state[f"{pfx}_run_id"]      = run_id
                        st.session_state[f"{pfx}_p3_ctx"]      = ctx
                        st.session_state[f"{pfx}_poll_start"]  = time.time()
                        st.rerun()

            # Stage 4b: Polling
            elif st.session_state.get(f"{pfx}_polling") and not st.session_state.get(f"{pfx}_p3_answered"):
                run_id  = st.session_state.get(f"{pfx}_run_id", "")
                elapsed = int(time.time() - st.session_state.get(f"{pfx}_poll_start", time.time()))
                poll = _invoke(HARNESS_FN, _build_harness_payload(
                    agent_cfg, customer_id, customer_name, product, sow_ref, agent_id_val,
                    run_id=run_id, action="get_status",
                ))
                poll_status        = poll.get("status", "running")
                phase_results_live = poll.get("phase_results", {})
                if phase_results_live:
                    existing = st.session_state[f"{pfx}_result"]
                    existing["phase_results"] = phase_results_live
                    existing["status"]        = poll_status
                    st.session_state[f"{pfx}_result"] = existing
                    harness_result = existing

                if _is_done(poll_status):
                    final = _invoke(HARNESS_FN, _build_harness_payload(
                        agent_cfg, customer_id, customer_name, product, sow_ref, agent_id_val,
                        run_id=run_id, action="get_status",
                    ))
                    st.session_state[f"{pfx}_result"]      = final
                    st.session_state[f"{pfx}_polling"]     = False
                    st.session_state[f"{pfx}_p3_answered"] = True
                    st.session_state[f"{pfx}_chat"].append({
                        "role": "assistant",
                        "content": _completion_message(final, agent_cfg["id"]),
                    })
                    harness_result = final
                    st.rerun()
                elif poll_status == "error":
                    st.session_state[f"{pfx}_polling"] = False
                    st.rerun()
                else:
                    phases_done = len([k for k in phase_results_live if k != "error"])
                    st.info(f"⏳ Phases running… {phases_done}/8 complete ({elapsed}s elapsed)")
                    time.sleep(4)
                    st.rerun()

            # Stage 5: Complete — follow-up Q&A
            elif (_is_done(harness_result.get("status", ""))
                  and st.session_state.get(f"{pfx}_p3_answered")):
                report_key = harness_result.get("report_s3_key") or harness_result.get("phase_results", {}).get("phase8", {}).get("report_s3_key", "")
                handoff_url_direct = (
                    harness_result.get("handoff_md_url")
                    or harness_result.get("phase_results", {}).get("phase8", {}).get("handoff_md_url", "")
                )
                _dl_c1, _dl_c2 = st.columns(2)
                if report_key:
                    url = _presign(report_key, WIKI_BUCKET)
                    if url:
                        _dl_c1.link_button("📥 Download Report", url, type="primary")
                if handoff_url_direct:
                    _dl_c2.link_button("📄 Session Handoff", handoff_url_direct)

                followup = st.chat_input("Ask a follow-up question…", key=f"{pfx}_fu")
                if followup:
                    st.session_state[f"{pfx}_chat"].append({"role": "user", "content": followup})
                    with st.spinner("Thinking…"):
                        ctx = json.dumps(harness_result.get("phase_results", {}), default=str)[:3000]
                        answer = _post_harness_answer(followup, ctx, customer_name, product, agent_cfg["id"])
                    st.session_state[f"{pfx}_chat"].append({"role": "assistant", "content": answer})
                    st.rerun()

        # ══════════════════════════════════════════════════════════════
        # RIGHT — Phase tracker + metrics + traces
        # ══════════════════════════════════════════════════════════════
        with col_right:

            # ── Phase tracker ──────────────────────────────────────────
            with st.container(border=True):
                st.markdown(
                    '<span class="lock-badge">🔒 LOCKED PLAN</span>',
                    unsafe_allow_html=True,
                )
                tel = _telemetry(harness_result)
                phases_done = tel["phases_done"]
                display_done = phases_done + (1 if _is_done(harness_result.get("status", "")) else 0)
                st.progress(display_done / 9, text=f"**{display_done}/9 phases**")

                for ph in PHASES:
                    state   = _phase_state(harness_result, ph["num"])
                    icon    = _phase_icon(state)
                    summary = _phase_summary(harness_result, ph["num"], agent_cfg["id"])
                    ph_pr   = harness_result.get("phase_results", {}).get(f"phase{ph['num']}", {})
                    lat     = ph_pr.get("skill_latency_ms") or ph_pr.get("latency_ms")
                    lat_str = f" · {lat}ms" if lat else ""
                    st.markdown(
                        f"{icon} **{ph['num']}.** {ph['name']}{lat_str}"
                        + (f"  \n  _{summary}_" if summary else ""),
                        help=f"Skill: {ph['skill'] or 'n/a'} · Type: {ph['type']}",
                    )

            # ── Session metrics ────────────────────────────────────────
            if tel["phases_done"] > 0:
                with st.container(border=True):
                    st.markdown("**📊 This Session**")
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("Skills invoked", tel["skills"])
                    mc2.metric("Gaps found",     tel["gaps"])
                    if tel["latency"]:
                        mc3.metric("Duration", f"{tel['latency']:,}ms")
                    conf = tel.get("confidence", "")
                    if conf:
                        conf_badge = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}.get(
                            str(conf).lower(), str(conf)
                        )
                        st.caption(f"Confidence: {conf_badge}")

            # ── Lambda traces (inline) ─────────────────────────────────
            with st.container(border=True):
                tc1, tc2 = st.columns([3, 1])
                tc1.markdown("**⚡ Lambda Traces** (DynamoDB)")
                if tc2.button("↺", key=f"{pfx}_ref_traces", help="Refresh traces"):
                    st.cache_data.clear()

                traces = _get_lambda_traces(limit=8)
                if traces:
                    import pandas as pd
                    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_raw"} for r in traces])
                    df = df.loc[:, (df != "").any(axis=0)]
                    st.dataframe(df, use_container_width=True, hide_index=True, height=180)
                    with st.expander("🔍 Inspect span"):
                        sel = st.selectbox(
                            "Span", range(len(traces)),
                            format_func=lambda i: f"{traces[i].get('Span','?')} — {traces[i].get('Question','')[:40]}",
                            key=f"{pfx}_span_sel",
                        )
                        st.json(traces[sel].get("_raw", traces[sel]))
                else:
                    st.caption("No traces yet — run the harness to see spans.")

            # ── Session Handoff card (shown on completion) ──────────────
            if _is_done(harness_result.get("status", "")):
                with st.container(border=True):
                    st.markdown("**📌 Session Handoff**")
                    pr = harness_result.get("phase_results", {})
                    p6 = pr.get("phase6", {})
                    p8 = pr.get("phase8", {})

                    # Next best step
                    nbs = p8.get("next_best_step", "Review the generated report and assign a delivery lead.")
                    st.info(f"**Next best step:** {nbs}")

                    # Open items / gaps
                    gaps = p6.get("gaps", [])
                    if gaps:
                        st.markdown(f"**Open items ({len(gaps)}):**")
                        for g in gaps[:5]:
                            label = g.get("title") or g.get("area") or g.get("human_prompt", "")
                            blocking = " 🔴" if g.get("blocking") else ""
                            st.markdown(f"- {label}{blocking}")
                        if len(gaps) > 5:
                            st.caption(f"…and {len(gaps) - 5} more — see report")
                    else:
                        st.success("No open items — all gaps resolved")

                    # Handoff markdown download
                    handoff_url = (
                        harness_result.get("handoff_md_url")
                        or p8.get("handoff_md_url", "")
                    )
                    if handoff_url:
                        st.link_button("📄 Download session-handoff.md", handoff_url)

            # ── Phase results expanders ────────────────────────────────
            if harness_result.get("phase_results"):
                with st.expander("📋 Phase results detail"):
                    for phase_key, phase_data in harness_result["phase_results"].items():
                        if phase_key == "error":
                            continue
                        pnum = phase_key.replace("phase", "")
                        ph_match = next((p for p in PHASES if str(p["num"]) == pnum), None)
                        ph_name  = ph_match["name"] if ph_match else phase_key
                        with st.expander(f"Phase {pnum} — {ph_name}", expanded=False):
                            st.json(phase_data if isinstance(phase_data, dict) else {"raw": str(phase_data)})
