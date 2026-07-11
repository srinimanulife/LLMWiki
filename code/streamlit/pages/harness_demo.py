"""
🔒 Hard Harness Demo — Multi-agent workflow runner.
8 system-enforced phases per agent. Locked plan panel shows real-time phase progress.
Business-facing demo: the agent cannot skip or reorder phases.
Supports: UC1 Sales-to-Service · UC-PM Problem Management
"""

import os
import json
import time
import boto3
import streamlit as st
from botocore.config import Config
from datetime import datetime

AWS_REGION       = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
S2S_WIKI_BUCKET  = os.environ.get("WIKI_BUCKET",        "llmwiki-278e7e22")
PM_WIKI_BUCKET   = os.environ.get("PM_WIKI_BUCKET",     "llmwiki-problem-mgnt-278e7e22")
GATEKEEPER_FN    = os.environ.get("GATEKEEPER_FUNCTION",   "llmwiki-gatekeeper")
S2S_HARNESS_FN   = os.environ.get("UC1_HARNESS_FUNCTION",  "llmwiki-uc1-harness")
PM_HARNESS_FN    = os.environ.get("PM_HARNESS_FUNCTION",   "llmwiki-harness-uc-pm")

lambda_client = boto3.client("lambda", region_name=AWS_REGION)
s3_client     = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))

# ── Agent registry — add new agents here ──────────────────────────
AGENTS = {
    "Sales-to-Service (UC1)": {
        "id":          "s2s",
        "harness_fn":  S2S_HARNESS_FN,
        "wiki_bucket": S2S_WIKI_BUCKET,
        "title":       "🔒 UC1 Hard Harness — Sales-to-Service Agent",
        "caption":     "8 system-enforced phases · Customer onboarding handoff · Gatekeeper validates prerequisites",
        "greeting": (
            "👋 Hello! I'm the **UC1 Sales-to-Service Agent**.\n\n"
            "Click **Start Harness** to validate prerequisites and begin the "
            "8-phase handoff workflow."
        ),
        "uses_gatekeeper":           True,
        "start_confirmation_label":  "Engagement",
        "start_hint": (
            "💡 **Hint:** Type `Go ahead` to kick off phases 1 and 2, "
            "or ask any question about the engagement."
        ),
        "chat_placeholder":          "Type 'Go ahead' to start...",
        "followup_placeholder":      "Ask a follow-up question about the engagement...",
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
        ],
        "input_label":       "Customer ID",
        "input2_label":      "Customer Name",
        "input3_label":      "Product in Scope",
        "input4_label":      "SOW Reference",
        "human_input_hint":  (
            "**Example:**\n> No prior attempts. CMO is executive sponsor. "
            "Go-live Q1 2027. HIPAA required; EHR is Epic."
        ),
    },
    "Problem Management (UC-PM)": {
        "id":          "pm",
        "harness_fn":  PM_HARNESS_FN,
        "wiki_bucket": PM_WIKI_BUCKET,
        "title":       "🔒 UC-PM Hard Harness — Problem Management Agent",
        "caption":     "8 system-enforced phases · AI-assisted RCA & KEDB · Cross-product pattern detection across Facets · QNXT · EAM · EDM · TCS · NetworX · FRM",
        "greeting": (
            "👋 Hello! I'm the **UC-PM Problem Management Agent**.\n\n"
            "I run **8 system-enforced phases** to investigate complex problems — including "
            "**cross-product root causes** that span multiple TriZetto systems "
            "(e.g. Facets → EAM → FRM cascade failures).\n\n"
            "**What I do that a simple Q&A cannot:**\n"
            "- 🏷️ **Phase 2:** Classify the problem category, recurrence type, and risk tier (SK-06)\n"
            "- 💬 **Phase 3:** Generate targeted SME questions based on what I find — then **wait for your input**\n"
            "- 📚 **Phase 4:** Search the entire TriZetto knowledge base for prior RCAs, KEDB entries, and playbooks (SK-01)\n"
            "- 🔍 **Phase 5:** Draft the RCA and detect cross-product recurrence patterns across Facets, QNXT, EAM, EDM (SK-02)\n"
            "- 🔭 **Phase 6:** Identify missing evidence gaps that would block permanent fix (SK-05)\n"
            "- 📝 **Phase 7:** Populate standard RCA + KEDB templates — audit-ready, never auto-published (SK-04)\n"
            "- 💾 **Phase 8:** Write draft to wiki and generate HTML report with full evidence pack (SK-03)\n\n"
            "Configure the sidebar with your **Batch ID, Affected Component, Product, and Problem ID**, "
            "then click **Start Harness** and type `Go ahead`."
        ),
        "uses_gatekeeper":           False,
        "start_confirmation_label":  "Problem",
        "start_hint": (
            "💡 Type `Go ahead` to kick off phases 1 & 2 (record load + classification). "
            "Phase 3 will pause and ask you targeted SME questions based on the classification."
        ),
        "chat_placeholder":          "Type 'Go ahead' to start phases 1 & 2...",
        "followup_placeholder":      "Ask a follow-up question about the RCA findings...",
        "default_inputs": {
            "customer_id":   "BATCH-XSYS-2026-06",
            "customer_name": "Claims Adjudication Engine",
            "product":       "Facets",
            "sow_ref":       "PRB-XSYS-001",
        },
        "phases": [
            {"num": 1, "name": "Problem Record Load",                "type": "programmatic",    "skill": None,    "icon": "📥"},
            {"num": 2, "name": "Problem Classification (SK-06)",     "type": "llm_single",      "skill": "SK-06", "icon": "🏷️"},
            {"num": 3, "name": "SME Context Collection ← Human",     "type": "llm_human_input", "skill": None,    "icon": "💬"},
            {"num": 4, "name": "Load Prior Knowledge (SK-01)",       "type": "llm_agent",       "skill": "SK-01", "icon": "📚"},
            {"num": 5, "name": "RCA Draft & Cross-System Patterns",  "type": "llm_agent",       "skill": "SK-02", "icon": "🔍"},
            {"num": 6, "name": "Knowledge Gap Detection (SK-05)",    "type": "llm_agent",       "skill": "SK-05", "icon": "🔭"},
            {"num": 7, "name": "Fill RCA & KEDB Templates (SK-04)",  "type": "llm_single",      "skill": "SK-04", "icon": "📝"},
            {"num": 8, "name": "Write Draft & Route Review (SK-03)", "type": "programmatic",    "skill": "SK-03", "icon": "💾"},
        ],
        "input_label":  "Batch ID",
        "input2_label": "Affected Component",
        "input3_label": "Product (Facets / QNXT / EAM / EDM / TCS)",
        "input4_label": "Problem ID",
        "human_input_hint": (
            "**Cross-System Scenario (recommended for demo):**\n\n"
            "> Month-end claims batch failed at 2:47 AM — **Facets Claims Adjudication Engine** "
            "aborted with NullPointerException on 14,832 Medicare supplemental claims. "
            "Simultaneously, **EAM** shows 3 retrospective prior-auth approvals posted at 2:51 AM "
            "that never propagated downstream — those claims are now denied despite having valid auths. "
            "**FRM** month-end reconciliation is also deadlocked — Facets and QNXT capitation postings "
            "ran concurrently at 3:15 AM and the `fin_ledger_entry` table is locked. "
            "**EDM** encounter submission job scheduled for 4 AM will miss its CMS window if FRM "
            "does not release the lock. No code changes in last 30 days. This exact pattern — "
            "batch null-pointer causing downstream EAM propagation miss and FRM deadlock — "
            "was seen in Q3 2025 (PRB-FAC-001, PRB-EAM-002, PRB-FRM-001) but was closed as "
            "separate tickets rather than a systemic cross-product issue."
        ),
    },
}

def _agent_completion_message(result: dict, agent_id: str) -> str:
    """Build a completion message appropriate for the selected agent."""
    pr       = result.get("phase_results", {})
    p2       = pr.get("phase2", {})
    p5       = pr.get("phase5", {})
    p6       = pr.get("phase6", {})
    p7       = pr.get("phase7", {})
    p8       = pr.get("phase8", {})
    total_ms = int(result.get("total_latency_ms", 0) or 0)

    if agent_id == "pm":
        gaps      = p6.get("gap_count", 0)
        category  = p2.get("normalized_category") or p2.get("category", "—")
        risk_tier = p2.get("risk_tier", "—")
        root_cause = p5.get("root_cause_statement", "") or p5.get("root_cause", "")
        rca_conf  = p5.get("confidence", "—")
        indexed   = p8.get("indexed", False)
        return (
            f"🎉 **All 8 phases complete** in {total_ms:,}ms\n\n"
            f"**RCA Summary:**\n"
            f"- Problem category: **{category}** · Risk tier: **{risk_tier}**\n"
            f"- Root cause: {root_cause[:200] + '…' if len(root_cause) > 200 else root_cause or '(see report)'}\n"
            f"- RCA confidence: **{rca_conf}**\n"
            f"- Knowledge gaps recorded: **{gaps}**\n"
            f"- RCA draft: {'✅ saved to wiki (pending review)' if indexed else '⚠️ pending save'}\n\n"
            f"The RCA report is ready for download. Ask me anything about the problem."
        )
    else:
        gaps     = p6.get("gap_count", 0)
        risks    = len(p5.get("action_items", []))
        fill_pct = p7.get("completion_pct", 0)
        indexed  = p8.get("indexed", False)
        return (
            f"🎉 **All 8 phases complete** in {total_ms:,}ms\n\n"
            f"**Summary:**\n"
            f"- Risk tier: **{p2.get('risk_tier','—')}** ({p2.get('customer_type','—')})\n"
            f"- Delivery risks identified: **{risks}** action items\n"
            f"- Knowledge gaps recorded: **{gaps}**\n"
            f"- Persona template: **{fill_pct}%** complete\n"
            f"- Handoff brief: {'✅ indexed in wiki' if indexed else '⚠️ pending review'}\n\n"
            f"The report is ready for download. Ask me anything about the engagement."
        )

st.set_page_config(
    page_title="LLMWiki — Hard Harness Demo",
    page_icon="🔒",
    layout="wide",
)

# PHASES and WIKI_BUCKET are resolved at render time from the selected agent.
# See AGENTS registry above.

PHASE_TYPE_BADGE = {
    "programmatic":    "🐍 Python",
    "llm_single":      "⚡ Claude",
    "llm_human_input": "💬 Human",
    "llm_agent":       "🤖 Agent",
    "llm_batch_agents":"⚡×N Parallel",
}

# ── ALL helper functions defined first ────────────────────────────

dynamodb_r  = boto3.resource("dynamodb", region_name=AWS_REGION)


def _presign(s3_key: str, wiki_bucket: str = "", expires: int = 3600) -> str:
    """Generate a fresh pre-signed GET URL for an S3 key. Returns '' on failure."""
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
            ExpiresIn=expires,
        )
    except Exception:
        return ""


def _fetch_report_bytes(s3_key: str, wiki_bucket: str = "") -> bytes | None:
    """Download report bytes directly from S3."""
    try:
        bucket = wiki_bucket or S2S_WIKI_BUCKET
        key    = s3_key
        if s3_key.startswith("s3://"):
            parts  = s3_key[5:].split("/", 1)
            bucket = parts[0]
            key    = parts[1] if len(parts) > 1 else ""
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except Exception as e:
        print(f"WARN: _fetch_report_bytes({s3_key}): {e}")
        return None


def _list_runs(engagement_id: str) -> list:
    """Return all harness runs for an engagement, newest first."""
    try:
        table = dynamodb_r.Table("llmwiki-harness-runs")
        resp  = table.query(
            KeyConditionExpression="engagement_id = :eid",
            ExpressionAttributeValues={":eid": engagement_id},
        )
        runs = resp.get("Items", [])
        return sorted(runs, key=lambda x: x.get("started_at", ""), reverse=True)
    except Exception:
        return []


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


def _phase_state(result: dict, phase_num: int) -> str:
    """Returns 'complete'|'running'|'error'|'paused'|'pending' for a phase."""
    if not result:
        return "pending"
    status = result.get("status", "")
    phases_done = len([k for k in result.get("phase_results", {}) if k != "error"])
    if status == "error" and result.get("failed_phase") == phase_num:
        return "error"
    if status == "paused" and result.get("current_phase") == phase_num:
        return "paused"
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
    p = pr.get(f"phase{phase_num}", {})
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
            kb_count  = p.get("kb_passages_count", len(p.get("kb_passages", [])))
            rca_count = p.get("prior_rcas_count", len(p.get("prior_rcas", [])))
            return f"KB passages: {kb_count} · Prior RCAs: {rca_count}"
        return f"Playbook steps: {p.get('playbook_steps',0)} · Pages: {p.get('pages_loaded',0)}"
    if phase_num == 5:
        if agent_id == "pm":
            conf    = p.get("rca_confidence", p.get("confidence", "—"))
            pattern = "🔁 pattern detected" if p.get("pattern_detected") else ""
            cits    = len(p.get("kb_citations", []))
            return f"Confidence: {conf} · KB citations: {cits}" + (f" · {pattern}" if pattern else "")
        return f"Confidence: {p.get('confidence','—')} · Action items: {len(p.get('action_items',[]))}"
    if phase_num == 6:
        if p.get("skipped"):
            return "Skipped — confidence=high"
        return f"Gaps: {p.get('gap_count',0)} · Blocking: {p.get('blocking_count',0)}"
    if phase_num == 7:
        found = p.get("found", False)
        pct   = p.get("completion_pct", 0)
        return f"Template: {'found' if found else 'not found'} · Fill: {pct}%"
    if phase_num == 8:
        if agent_id == "pm":
            return "✅ RCA draft saved" if p.get("indexed") else "⚠️ Save pending"
        return "✅ Handoff indexed" if p.get("indexed") else "⚠️ Index pending"
    return ""


def _telemetry(result: dict) -> dict:
    if not result:
        return {"phases_done": 0, "skills": 0, "gaps": 0, "latency": 0}
    pr = result.get("phase_results", {})
    phases_done = len([k for k in pr if k != "error"])
    skills = sum(1 for k in ["phase4", "phase5", "phase6", "phase7", "phase8"] if k in pr)
    gap_count = pr.get("phase6", {}).get("gap_count", 0)
    return {
        "phases_done": phases_done,
        "skills": skills,
        "gaps": gap_count,
        "latency": int(result.get("total_latency_ms", 0) or 0),
    }


def _completion_message(result: dict, agent_id: str = "s2s") -> str:
    return _agent_completion_message(result, agent_id)


def _is_done(status: str) -> bool:
    """True for any terminal-success status — harness uses 'completed' or 'completed_with_gaps'."""
    return status in ("completed", "completed_with_gaps")


def _parse_if_str(val):
    """DynamoDB stores nested JSON as strings — parse them if needed."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return val or {}


def _rebuild_chat_from_run(run: dict, customer_name: str, product: str, agent_id: str = "s2s") -> list:
    """
    Reconstruct a professional conversation history from a prior harness run's
    phase_results so the client sees full context when reconnecting.
    """
    msgs = []
    pr      = _parse_if_str(run.get("phase_results", {}))
    status  = run.get("status", "")
    run_id  = run.get("run_id", "")
    started = run.get("started_at", "")[:16].replace("T", " ") if run.get("started_at") else "earlier"

    msgs.append({
        "role": "assistant",
        "content": (
            f"**Reconnecting to your prior harness run** 🔄\n\n"
            f"Run `{run_id}` was started on **{started} UTC** and is currently "
            f"**{status.upper()}**. I'm restoring the full session below so you "
            f"can pick up exactly where you left off."
        ),
    })

    p1 = pr.get("phase1", {})
    if p1:
        msgs.append({
            "role": "assistant",
            "content": (
                f"**✅ Phase 1 — SOW Intake complete**\n\n"
                f"- Customer wiki status: **{p1.get('customer_status', '—')}**\n"
                f"- Pages found: **{p1.get('pages_found', 0)}**\n"
                + (
                    "\n".join(f"- {f}" for f in p1.get("key_facts", [])[:3])
                    if p1.get("key_facts") else ""
                )
            ),
        })

    p2 = pr.get("phase2", {})
    if p2:
        msgs.append({
            "role": "assistant",
            "content": (
                f"**✅ Phase 2 — Customer Classification complete**\n\n"
                f"**Classification:** {p2.get('customer_type', 'Unknown')} · "
                f"Risk tier: **{p2.get('risk_tier', '—')}** · "
                f"Complexity: {p2.get('implementation_complexity', '—')}\n\n"
                f"_{p2.get('rationale', '')}_"
            ),
        })

    p3 = pr.get("phase3", {})
    if p3 and p3.get("context_provided"):
        msgs.append({
            "role": "assistant",
            "content": (
                f"**✅ Phase 3 — Human Context captured**\n\n"
                f"_{p3.get('summary', 'Context was provided and recorded.')}_"
            ),
        })
    elif status == "paused" and run.get("current_phase") in (3, "3"):
        question = (run.get("phase3_question")
                    or run.get("question")
                    or "Please provide context about this engagement.")
        msgs.append({
            "role": "assistant",
            "content": (
                f"**⏸️ Phase 3 — Waiting for your input**\n\n"
                f"Phases 1 and 2 completed successfully. I need your answers before "
                f"I can proceed with phases 4–8:\n\n{question}"
            ),
        })

    # Use the agent's actual phase names from AGENTS registry if available
    # The run dict may not carry agent info so we use agent_id to look up
    agent_phases = next(
        (a["phases"] for a in AGENTS.values() if a["id"] == agent_id),
        []
    )
    phase_label_map = {ph["num"]: ph["name"] for ph in agent_phases}
    phases_45678 = []
    for num in [4, 5, 6, 7, 8]:
        label = phase_label_map.get(num, f"Phase {num}")
        if pr.get(f"phase{num}"):
            phases_45678.append(f"✅ Phase {num}: {label}")

    if phases_45678:
        summary_lines = "\n".join(f"- {l}" for l in phases_45678)
        msgs.append({
            "role": "assistant",
            "content": f"**Phases 4–8 progress:**\n\n{summary_lines}",
        })

    if _is_done(status):
        msgs.append({
            "role": "assistant",
            "content": _completion_message(run, agent_id),
        })

    return msgs


def _reconnect_to_prior_run(gk: dict, customer_id: str, customer_name: str,
                             product: str, sow_ref: str, agent_id: str = "s2s") -> None:
    """
    Restore session state from a prior run so the UI drops directly into the
    correct stage rather than showing a dead-end error.
    """
    run    = gk.get("active_run", {})
    status = gk.get("active_status", "running")
    run_id = gk.get("active_run_id", "")

    # Normalize phase_results from DynamoDB JSON string to dict once here
    # so every downstream helper (_phase_state, _phase_summary, etc.) gets a dict
    run["phase_results"] = _parse_if_str(run.get("phase_results", {}))

    st.session_state.harness_result      = run
    st.session_state.harness_run_id      = run_id
    st.session_state.gatekeeper_done     = True
    st.session_state.harness_running     = False
    st.session_state.harness_reconnected = True   # show resume-vs-new banner

    current_phase = int(run.get("current_phase") or 0)
    question = (run.get("phase3_question") or run.get("question") or "")

    if _is_done(status):
        st.session_state.phase3_answered  = True
        st.session_state.harness_polling  = False
    elif status == "paused" and current_phase == 3:
        st.session_state.phase3_answered  = False
        st.session_state.harness_polling  = False
        st.session_state.phase3_question  = question
    elif status in ("running", "paused"):
        st.session_state.phase3_answered  = False
        st.session_state.harness_polling  = True

    st.session_state.chat_messages = _rebuild_chat_from_run(run, customer_name, product, agent_id)


def _build_harness_payload(agent_cfg: dict, customer_id: str, customer_name: str,
                            product: str, sow_ref: str, agent_id: str,
                            human_context: str = "", run_id: str = "",
                            action: str = "", severity: str = "P1",
                            record_ids: list = None) -> dict:
    """Build the correct payload shape for UC1 vs PM harness."""
    if agent_cfg["id"] == "pm":
        # Sidebar mapping for PM:
        #   customer_id   → batch_id          (e.g. PM-QNXT-001)
        #   customer_name → component         (e.g. Member Update API)
        #   product       → product platform  (e.g. QNXT)
        #   sow_ref       → problem_id        (e.g. PRB-1001)
        if action == "get_status" and run_id:
            return {"action": "get_status", "run_id": run_id}
        payload: dict = {
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
            "agent_id":      agent_id,
            "human_context": human_context,
        }
        if action == "get_status" and run_id:
            payload["action"]        = "get_status"
            payload["run_id"]        = run_id
        if run_id and not action:
            payload["resume_run_id"] = run_id
        return payload


def _post_harness_answer(question: str, context: str, customer_name: str, product: str,
                          agent_id: str = "s2s") -> str:
    try:
        bedrock  = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
        if agent_id == "pm":
            role_desc = (
                f"You are an RCA expert answering a follow-up question after completing "
                f"the Problem Management RCA workflow for component '{customer_name}' on {product}."
            )
        else:
            role_desc = (
                f"You are a delivery expert answering a follow-up question after completing "
                f"the Sales-to-Service handoff workflow for {customer_name} ({product})."
            )
        prompt = (
            f"{role_desc}\n\n"
            f"Phase results context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer concisely in 2-4 sentences, citing specific phase results where relevant."
        )
        resp = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            }),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(resp["body"].read())["content"][0]["text"].strip()
    except Exception as e:
        return (
            f"I completed the 8-phase harness for {customer_name}. "
            f"For detailed answers, review the phase results in the expanders on the right. "
            f"(Error generating answer: {e})"
        )


# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.lock-badge {
    background: #1e3a5f; color: white; padding: 4px 12px;
    border-radius: 6px; font-size: 0.85em; font-weight: 600;
    display: inline-block; margin-bottom: 8px;
}
.hint-box {
    background: #f0f7ff; border: 1px solid #b3d4f5; border-radius: 6px;
    padding: 10px 14px; margin: 8px 0; font-size: 0.9em;
}
</style>
""", unsafe_allow_html=True)

# ── Skill / Harness spec helpers ──────────────────────────────────

_SPEC_DIR = os.path.join(os.path.dirname(__file__), "..", "skill_specs")

def _read_spec(filename: str) -> str:
    """Read a spec .md file bundled with the app. Returns empty string on missing."""
    try:
        with open(os.path.join(_SPEC_DIR, filename), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _render_spec(spec_md: str, compact: bool = False):
    """Render a skill/workflow spec .md cleanly — metadata card + formatted body."""
    if not spec_md:
        st.caption("Spec not available.")
        return

    # Parse YAML frontmatter between --- delimiters
    meta = {}
    body = spec_md
    if spec_md.startswith("---"):
        parts = spec_md.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"')
            body = parts[2].strip()

    # Strip the redundant H1 from body (it repeats the title in the card)
    body_lines = body.splitlines()
    if body_lines and body_lines[0].startswith("# "):
        body_lines = body_lines[1:]
    # Also strip the bold metadata lines that duplicate frontmatter
    cleaned = []
    skip_meta_block = True
    for line in body_lines:
        if skip_meta_block and (line.startswith("**Business Name") or line.startswith("**Technical") or
                                line.startswith("**Tier") or line.startswith("**Lambda") or
                                line.startswith("**Version") or line.startswith("**Status")):
            continue
        elif skip_meta_block and line.strip() == "":
            continue
        else:
            skip_meta_block = False
            cleaned.append(line)
    body = "\n".join(cleaned)

    # Metadata card
    if meta:
        sid    = meta.get("skill_id", meta.get("workflow_id", ""))
        bname  = meta.get("business_name", meta.get("title", sid))
        tname  = meta.get("technical_name", "")
        lamb   = meta.get("lambda_function", meta.get("orchestrator_lambda", ""))
        status = meta.get("status", "")
        ver    = meta.get("version", "")
        tier   = meta.get("tier", "")
        tags   = meta.get("use_case_tags", meta.get("use_case", ""))
        date   = meta.get("deployed_date", "")

        badge_color = {"active": "🟢", "draft": "🟡", "deprecated": "🔴"}.get(status, "⚪")
        st.markdown(
            f"**{sid}** — {bname}  \n"
            f"{badge_color} `{status}` · v{ver}"
            + (f" · Tier {tier}" if tier else "")
            + (f" · Deployed {date}" if date and not compact else ""),
        )
        if not compact:
            cols = st.columns(2)
            if tname:
                cols[0].caption(f"**Lambda:** `{lamb or tname}`")
            if tags:
                cols[1].caption(f"**Use cases:** {tags}")
        st.divider()

    # Body — render as markdown with reduced heading levels (## → bold text, not giant H2)
    # Replace ## headers with bold labels to reduce visual weight
    display_lines = []
    for line in body.splitlines():
        if line.startswith("### "):
            display_lines.append(f"**{line[4:]}**")
        elif line.startswith("## "):
            display_lines.append(f"##### {line[3:]}")  # smaller heading
        else:
            display_lines.append(line)
    st.markdown("\n".join(display_lines))

# Maps skill ID → spec filename
SKILL_SPEC_FILES = {
    "SK-01": "sk-01-customer-briefing-loader.md",
    "SK-02": "sk-02-knowledge-finder.md",
    "SK-03": "sk-03-knowledge-recorder.md",
    "SK-04": "sk-04-template-auto-fill.md",
    "SK-05": "sk-05-missing-info-radar.md",
    "SK-06": "sk-06-problem-classifier.md",
}

# Maps agent id → harness workflow spec filename
HARNESS_SPEC_FILES = {
    "s2s": "wf-uc1-sales-to-service.md",
    "pm":  "wf-uc-pm-problem-management.md",
}

# ── Agent selector ─────────────────────────────────────────────────
# Persisted in session state so switching agents resets harness state.
agent_names = list(AGENTS.keys())
if "selected_agent_name" not in st.session_state:
    st.session_state.selected_agent_name = agent_names[0]   # default: Sales-to-Service

selected_name = st.selectbox(
    "**Select Agent**",
    agent_names,
    index=agent_names.index(st.session_state.selected_agent_name),
    key="agent_selector_top",
)

# Reset harness state when agent changes
if selected_name != st.session_state.selected_agent_name:
    for k in ["harness_result", "gatekeeper_done", "harness_running",
              "phase3_question", "phase3_answered", "chat_messages",
              "harness_polling", "harness_run_id", "harness_phase3_ctx",
              "harness_reconnected"]:
        st.session_state.pop(k, None)
    st.session_state.selected_agent_name = selected_name
    st.rerun()

agent_cfg  = AGENTS[selected_name]
PHASES     = agent_cfg["phases"]
HARNESS_FN = agent_cfg["harness_fn"]
WIKI_BUCKET = agent_cfg["wiki_bucket"] or S2S_WIKI_BUCKET

st.title(agent_cfg["title"])
st.caption(agent_cfg["caption"])

tab_harness, tab_upload, tab_catalog, tab_skills = st.tabs([
    "🔒 Hard Harness",
    "📂 Load Documents",
    "🎯 Skills Catalog",
    "🔬 Skill Walk-through",
])

# ── Sidebar config ─────────────────────────────────────────────────
with st.sidebar:
    st.header("Demo Configuration")
    defaults = agent_cfg["default_inputs"]

    if agent_cfg["id"] == "pm":
        customer_id   = st.text_input(
            agent_cfg["input_label"],
            value=defaults["customer_id"],
            help="Unique run identifier for this batch/investigation. E.g. BATCH-XSYS-2026-06",
        )
        customer_name = st.text_input(
            agent_cfg["input2_label"],
            value=defaults["customer_name"],
            help="The specific subsystem or module affected. E.g. Claims Adjudication Engine",
        )
        product = st.text_input(
            agent_cfg["input3_label"],
            value=defaults["product"],
            help="Primary product platform where the problem was detected.",
        )
        sow_ref = st.text_input(
            agent_cfg["input4_label"],
            value=defaults["sow_ref"],
            help="Unique problem ticket ID. E.g. PRB-XSYS-001",
        )
        pm_severity = st.selectbox(
            "Severity",
            ["P1 — Critical (system down)", "P2 — High (major impact)", "P3 — Medium (degraded)"],
            index=0,
            help="P1 = immediate escalation + SNS alert. P2 = same-day resolution. P3 = next sprint.",
        )
        pm_severity = pm_severity.split(" — ")[0]  # extract "P1", "P2", "P3"
        pm_record_ids_raw = st.text_area(
            "Related Record IDs",
            value="",
            height=80,
            help="Optional: paste incident/log record IDs, one per line (e.g. INC-001, LOG-042). Leave blank to auto-generate stubs.",
            placeholder="INC-001\nINC-002\nLOG-042",
        )
        pm_record_ids = [r.strip() for r in pm_record_ids_raw.splitlines() if r.strip()]
    else:
        customer_id   = st.text_input(agent_cfg["input_label"],  value=defaults["customer_id"])
        customer_name = st.text_input(agent_cfg["input2_label"], value=defaults["customer_name"])
        product       = st.text_input(agent_cfg["input3_label"], value=defaults["product"])
        sow_ref       = st.text_input(agent_cfg["input4_label"], value=defaults["sow_ref"])
        pm_severity   = "P1"
        pm_record_ids = []

    agent_id = st.text_input("Agent ID", value=f"{agent_cfg['id']}-harness-v1")

    if agent_cfg["id"] == "pm" and not PM_WIKI_BUCKET:
        st.warning(
            "⚠️ **PM_WIKI_BUCKET** env var not set.\n\n"
            "Run `terraform apply` to create the PM bucket, then redeploy the ECS task."
        )

    st.divider()
    st.markdown('<div class="lock-badge">🔒 LOCKED PLAN</div>', unsafe_allow_html=True)
    st.caption("System enforced. Agent cannot modify.")

    # Live phase status in sidebar
    harness_result = st.session_state.get("harness_result", {})
    for ph in PHASES:
        state   = _phase_state(harness_result, ph["num"])
        icon    = _phase_icon(state)
        summary = _phase_summary(harness_result, ph["num"], agent_cfg["id"])
        lat     = ""
        if state == "complete":
            phase_pr = harness_result.get("phase_results", {}).get(f"phase{ph['num']}", {})
            ms = phase_pr.get("skill_latency_ms") or phase_pr.get("latency_ms")
            if ms:
                lat = f" · {ms}ms"
        st.markdown(
            f"{icon} **{ph['num']}.** {ph['name']}{lat}"
            + (f"  \n  _{summary}_" if summary else ""),
            help=f"Skill: {ph['skill'] or 'n/a'} · Type: {ph['type']}",
        )

    st.divider()
    tel = _telemetry(harness_result)
    phases_done = tel["phases_done"]
    st.progress(phases_done / 8, text=f"**{phases_done}/8 phases complete**")
    c1, c2 = st.columns(2)
    c1.metric("Skills invoked", tel["skills"])
    c2.metric("Gaps found",     tel["gaps"])
    if tel["latency"]:
        st.caption(f"Total time: {int(tel['latency']):,}ms")

    if harness_result.get("report_download_url"):
        st.success("📥 RCA Report ready — download below ↓")

    st.divider()
    if st.button("🔄 Reset Harness", type="secondary"):
        for k in ["harness_result", "gatekeeper_done", "harness_running",
                  "phase3_question", "phase3_answered", "chat_messages",
                  "harness_polling", "harness_run_id", "harness_phase3_ctx"]:
            st.session_state.pop(k, None)
        st.rerun()

# ──────────────────────────────────────────────────────────────────
# TAB: Load Documents
# ──────────────────────────────────────────────────────────────────
with tab_upload:
    INGEST_FN    = os.environ.get("INGEST_FUNCTION",     "llmwiki-ingest")
    CONVERTER_FN = os.environ.get("CONVERTER_FUNCTION",  "llmwiki-converter")
    upload_bucket = agent_cfg["wiki_bucket"] or S2S_WIKI_BUCKET

    st.subheader("📂 Knowledge Base — " + selected_name)
    st.info(f"**Bucket:** `{upload_bucket}`", icon="🪣")

    # ── helper: human-readable file size ──────────────────────────
    def _fmt_size(n):
        if n < 1024:
            return f"{n} B"
        if n < 1024 ** 2:
            return f"{n/1024:.1f} KB"
        return f"{n/1024**2:.1f} MB"

    # ── helper: presigned download URL ────────────────────────────
    def _presign(bucket, key, expires=300):
        try:
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
        except Exception:
            return None

    # ── list raw source files (raw/ + uploads/) ───────────────────
    def _list_source_files(bucket):
        objects = []
        for prefix in ("raw/", "uploads/"):
            try:
                paginator = s3_client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith("/"):
                            continue
                        objects.append({
                            "key":      key,
                            "name":     key.split("/")[-1],
                            "folder":   "/".join(key.split("/")[:-1]),
                            "size":     obj["Size"],
                            "modified": obj["LastModified"],
                        })
            except Exception:
                pass
        objects.sort(key=lambda x: x["modified"], reverse=True)
        return objects

    # ── list wiki output pages ────────────────────────────────────
    def _list_wiki_pages(bucket):
        pages = []
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix="wiki/"):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    pages.append({
                        "key":      key,
                        "name":     key.split("/")[-1],
                        "folder":   "/".join(key.split("/")[:-1]),
                        "size":     obj["Size"],
                        "modified": obj["LastModified"],
                    })
        except Exception:
            pass
        pages.sort(key=lambda x: x["modified"], reverse=True)
        return pages

    # ── session state for delete confirmation ─────────────────────
    if "ld_confirm_delete" not in st.session_state:
        st.session_state.ld_confirm_delete = None
    if "ld_refresh" not in st.session_state:
        st.session_state.ld_refresh = 0

    # ── SECTION 1: Existing source files ─────────────────────────
    col_hdr, col_refresh = st.columns([6, 1])
    col_hdr.markdown("### 📁 Source Files (`raw/` · `uploads/`)")
    if col_refresh.button("↺ Refresh", key="ld_refresh_btn"):
        st.session_state.ld_refresh += 1

    source_files = _list_source_files(upload_bucket)

    if not source_files:
        st.info("No source files yet. Upload files below to get started.")
    else:
        # Group by folder
        from collections import defaultdict
        by_folder = defaultdict(list)
        for f in source_files:
            by_folder[f["folder"]].append(f)

        for folder, files in sorted(by_folder.items()):
            with st.expander(f"📂 `{folder}/`  ({len(files)} file{'s' if len(files)!=1 else ''})", expanded=True):
                for f in files:
                    c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
                    c1.markdown(f"**{f['name']}**")
                    c2.caption(_fmt_size(f["size"]))
                    c3.caption(f["modified"].strftime("%Y-%m-%d"))

                    # Download
                    url = _presign(upload_bucket, f["key"])
                    if url:
                        c4.markdown(
                            f'<a href="{url}" target="_blank" style="'
                            f'display:inline-block;padding:2px 10px;border-radius:4px;'
                            f'background:#e5e7eb;color:#374151;font-size:0.8em;'
                            f'text-decoration:none;">⬇ Download</a>',
                            unsafe_allow_html=True,
                        )

                    # Delete confirmation row
                    confirm_key = f["key"]
                    if st.session_state.ld_confirm_delete == confirm_key:
                        dc1, dc2, dc3 = st.columns([3, 1, 1])
                        dc1.warning(f"Delete `{f['name']}`? This cannot be undone.")
                        if dc2.button("Yes, delete", key=f"del_yes_{confirm_key}", type="primary"):
                            try:
                                s3_client.delete_object(Bucket=upload_bucket, Key=confirm_key)
                                st.session_state.ld_confirm_delete = None
                                st.success(f"Deleted `{confirm_key}`")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete failed: {e}")
                        if dc3.button("Cancel", key=f"del_no_{confirm_key}"):
                            st.session_state.ld_confirm_delete = None
                            st.rerun()
                    else:
                        if st.button(
                            "🗑 Delete", key=f"del_{confirm_key}",
                            help=f"Remove {f['name']} from S3",
                        ):
                            st.session_state.ld_confirm_delete = confirm_key
                            st.rerun()

                    st.divider()

    # ── SECTION 2: Wiki output pages ─────────────────────────────
    st.markdown("### 📄 Wiki Pages & Reports (`wiki/`)")
    wiki_pages = _list_wiki_pages(upload_bucket)

    if not wiki_pages:
        st.caption("No wiki pages generated yet.")
    else:
        # Group by folder
        by_wfolder = defaultdict(list)
        for p in wiki_pages:
            by_wfolder[p["folder"]].append(p)

        for folder, pages in sorted(by_wfolder.items()):
            with st.expander(f"📂 `{folder}/`  ({len(pages)})", expanded=False):
                for p in pages:
                    wc1, wc2, wc3, wc4 = st.columns([4, 1, 1, 1])
                    wc1.markdown(f"`{p['name']}`")
                    wc2.caption(_fmt_size(p["size"]))
                    wc3.caption(p["modified"].strftime("%Y-%m-%d"))
                    url = _presign(upload_bucket, p["key"])
                    if url:
                        wc4.markdown(
                            f'<a href="{url}" target="_blank" style="'
                            f'display:inline-block;padding:2px 10px;border-radius:4px;'
                            f'background:#e5e7eb;color:#374151;font-size:0.8em;'
                            f'text-decoration:none;">⬇ View</a>',
                            unsafe_allow_html=True,
                        )

    # ── SECTION 3: Upload new files ───────────────────────────────
    st.divider()
    st.markdown("### ⬆️ Upload New Files")

    with st.form("upload_doc_form"):
        customer_prefix = st.text_input(
            "Customer / topic prefix (optional)",
            placeholder="e.g. bcbs-mn  or  qnxt-issues",
            help="Prepended to the S3 key so files stay organised by customer",
        )
        src_type = st.selectbox(
            "Source type",
            ["articles", "papers", "notes", "meetings", "runbooks", "data"],
        )
        uploaded_files = st.file_uploader(
            "Choose files",
            type=["pdf", "docx", "pptx", "xlsx", "md", "txt", "csv"],
            accept_multiple_files=True,
        )
        trigger_ingest = st.checkbox("Trigger ingest pipeline after upload", value=True)
        submit_upload = st.form_submit_button("Upload →", type="primary")

    if submit_upload and uploaded_files:
        prefix_part = f"{customer_prefix.strip('/')}/" if customer_prefix.strip() else ""
        for uf in uploaded_files:
            ext = os.path.splitext(uf.name)[1].lower()
            is_md = ext in (".md", ".txt")
            if is_md:
                dest_key = f"raw/{src_type}/{prefix_part}{uf.name}"
            else:
                dest_key = f"uploads/{prefix_part}{uf.name}"

            with st.spinner(f"Uploading {uf.name}..."):
                try:
                    s3_client.put_object(
                        Bucket=upload_bucket,
                        Key=dest_key,
                        Body=uf.read(),
                        ContentType="text/plain" if is_md else "application/octet-stream",
                    )
                    st.success(f"✅ `{dest_key}`")

                    if trigger_ingest and is_md:
                        event = {"Records": [{"s3": {"bucket": {"name": upload_bucket}, "object": {"key": dest_key}}}]}
                        lambda_client.invoke(FunctionName=INGEST_FN, InvocationType="Event", Payload=json.dumps(event).encode())
                        st.info(f"  Ingest triggered for `{dest_key}`")
                    elif trigger_ingest and not is_md:
                        event = {"Records": [{"s3": {"bucket": {"name": upload_bucket}, "object": {"key": dest_key}}}]}
                        lambda_client.invoke(FunctionName=CONVERTER_FN, InvocationType="Event", Payload=json.dumps(event).encode())
                        st.info(f"  Converter triggered for `{dest_key}` ({ext} → Markdown → ingest)")
                except Exception as e:
                    st.error(f"Upload failed: {e}")

        st.session_state.ld_refresh += 1
        st.rerun()

# ──────────────────────────────────────────────────────────────────
# TAB: Skills Catalog (skills_hub embedded)
# ──────────────────────────────────────────────────────────────────
with tab_catalog:
    st.subheader("🎯 Reusable Skill Catalogue")
    st.caption(
        "Each skill is a Lambda built once and shared by all 10 UC agents. "
        "Click **▶ Run Live** to invoke any skill against AWS right now."
    )

    _SC_SK01 = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
    _SC_SK02 = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
    _SC_SK03 = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
    _SC_SK04 = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
    _SC_SK05 = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")
    _SC_SK06 = os.environ.get("SK06_FUNCTION", "llmwiki-skill-problem-classifier")
    _SC_UC1  = os.environ.get("UC1_FUNCTION",  "llmwiki-uc1-orchestrator")

    sc_customer_id = st.text_input(
        "Customer ID for live demos", value="bcbs-mn-001", key="sc_customer_id"
    )

    from datetime import datetime as _dt_sc

    SC_SKILLS = [
        {
            "id": "SK-01", "tier": 1, "fn": _SC_SK01,
            "name": "Customer Briefing Loader", "icon": "📋",
            "tagline": "Loads customer history + playbook in parallel before any agent action.",
            "when": "Called FIRST — always", "agents": "All 10 UC agents",
            "payload": lambda cid: {"skill": "ContextBootstrapSkill", "version": "1.0", "invoked_by": "skills-catalog-demo", "inputs": {"customer_id": cid, "use_case": "UC1", "agent_id": "skills-catalog-demo"}},
            "output_keys": ["customer_status", "pages_loaded"],
        },
        {
            "id": "SK-02", "tier": 1, "fn": _SC_SK02,
            "name": "Knowledge Finder", "icon": "🔍",
            "tagline": "Searches the knowledge base. Returns cited answer + confidence + action items.",
            "when": "Any time the agent needs to look something up", "agents": "All 10 UC agents",
            "payload": lambda cid: {"skill": "WikiQuerySkill", "version": "1.0", "invoked_by": "skills-catalog-demo", "inputs": {"question": "What are the key steps in the Sales-to-Service handoff process?", "domain": "customer-onboarding", "customer_id": cid, "use_case": "UC1"}},
            "output_keys": ["confidence", "wiki_page_count"],
        },
        {
            "id": "SK-05", "tier": 2, "fn": _SC_SK05,
            "name": "Missing Info Radar", "icon": "🔭",
            "tagline": "Detects what the wiki doesn't know. Records gaps, escalates blocking ones.",
            "when": "When SK-02 returns confidence=low", "agents": "UC1, UC2, UC5, UC8–UC10",
            "payload": lambda cid: {"skill": "GapDetectionSkill", "version": "1.0", "invoked_by": "skills-catalog-demo", "inputs": {"question": "What is the contracted SLA for claims turnaround for a new insurance customer?", "domain": "customer-onboarding", "use_case": "UC1", "customer_id": cid, "low_confidence_response": {"confidence": "low", "gaps_detected": []}}},
            "output_keys": ["gap_count", "blocking"],
        },
        {
            "id": "SK-04", "tier": 2, "fn": _SC_SK04,
            "name": "Template Auto-Fill", "icon": "📝",
            "tagline": "Finds a template and pre-populates every field with customer data. No manual copying.",
            "when": "When the agent needs to produce a standard document", "agents": "UC1–UC3, UC5–UC9",
            "payload": lambda cid: {"skill": "ArtifactResolutionSkill", "version": "1.0", "invoked_by": "skills-catalog-demo", "inputs": {"artifact_type": "persona-template", "customer_id": cid, "use_case": "UC1", "available_context": {"customer_id": cid, "products": ["TriZetto Facets"], "handoff_summary": "New healthcare payer implementation"}}},
            "output_keys": ["found", "completion_pct"],
        },
        {
            "id": "SK-03", "tier": 1, "fn": _SC_SK03,
            "name": "Knowledge Recorder", "icon": "💾",
            "tagline": "Saves agent-generated knowledge back to the wiki for the next agent in the chain.",
            "when": "At END of session — and mid-session for partial contributions", "agents": "All 10 UC agents",
            "payload": lambda cid: {"skill": "WikiContributeSkill", "version": "1.0", "invoked_by": "skills-catalog-demo", "inputs": {"page_type": "customers", "page_slug": f"{cid}-catalog-demo-{_dt_sc.now().strftime('%Y%m%d%H%M%S')}", "content": f"---\ntitle: Skills Catalog Demo — {cid}\ndate: {_dt_sc.now().strftime('%Y-%m-%d')}\ncustomer_id: {cid}\nuse_case_tags: [UC1]\ndomain: customer-onboarding\ncontributing_agent: skills-catalog-demo\nstatus: active\n---\n# Skills Catalog Demo\nCreated by Skills Catalog tab on {_dt_sc.now().strftime('%Y-%m-%d')}.", "agent_id": "skills-catalog-demo", "customer_id": cid, "use_case": "UC1"}},
            "output_keys": ["status", "s3_uri"],
        },
        {
            "id": "SK-06", "tier": 3, "fn": _SC_SK06,
            "name": "Problem Classifier", "icon": "🏷️",
            "tagline": "Classifies problems into 9 categories, detects recurrence, alerts ops for P1/High.",
            "when": "Phase 2 of Problem Management — after records loaded", "agents": "UC-PM Problem Management",
            "payload": lambda cid: {"inputs": {"problem_id": "PRB-DEMO-001", "product": "QNXT", "component": "Member Update API", "severity": "P2", "problem_summary": "Intermittent timeout in eligibility batch processing", "related_records": [{"source_type": "Incident", "summary_title": "Eligibility timeout", "raw_excerpt": "Batch failed after partial commit", "solution": "Workaround applied", "normalized_issue_category": "Batch Processing"}], "ingest_batch_id": "PM-DEMO-001"}, "invoked_by": "skills-catalog-demo"},
            "output_keys": ["normalized_category", "recurrence_type", "risk_tier"],
        },
    ]

    TIER_BADGE = {1: "🔵 Universal", 2: "🟡 Common", 3: "🟠 Domain"}

    def _sc_invoke(fn: str, payload: dict) -> tuple[dict, int]:
        try:
            t0   = time.time()
            resp = lambda_client.invoke(FunctionName=fn, InvocationType="RequestResponse", Payload=json.dumps(payload).encode())
            raw  = json.loads(resp["Payload"].read())
            ms   = int((time.time() - t0) * 1000)
            result = json.loads(raw["body"]) if "body" in raw and isinstance(raw.get("body"), str) else raw.get("body") or raw
            return result, result.get("latency_ms", ms)
        except Exception as e:
            err = str(e)
            if "ResourceNotFoundException" in err or "Function not found" in err:
                return {"_not_deployed": True, "error": f"`{fn}` not yet deployed"}, 0
            return {"_error": True, "error": err}, 0

    # ── Spec-first intro ─────────────────────────────────────────
    st.info(
        "**📄 Business-Defined Skills** — Every skill below was defined first as a plain-English "
        "Markdown spec by a business analyst. The spec describes *what* the skill must do, "
        "its inputs/outputs, and business rules — with zero code. "
        "In future iterations, the LLM reads these specs and auto-generates the Lambda implementation. "
        "Click **📄 View Skill Spec** on any skill to see the business-authored definition.",
        icon="💡",
    )

    # Summary metrics
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("POC Skills", "5")
    mc2.metric("UC Agents Covered", "10/10")
    mc3.metric("Capability Coverage", "88%")
    mc4.metric("Phase 3 Remaining", "4")
    st.divider()

    for sk in SC_SKILLS:
        sid  = sk["id"]
        rkey = f"sc_result_{sid}"
        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 3, 1])
            h1.markdown(f"### {sk['icon']} {sk['id']} — {sk['name']}")
            h1.caption(f"{TIER_BADGE[sk['tier']]} · {sk['agents']}")
            h2.markdown(f"**{sk['tagline']}**")
            h2.caption(f"📅 When: {sk['when']}")
            with h3:
                if st.button("▶ Run Live", key=f"sc_run_{sid}", type="primary", use_container_width=True):
                    with st.spinner(f"Invoking {sk['name']}..."):
                        result, ms = _sc_invoke(sk["fn"], sk["payload"](sc_customer_id))
                    st.session_state[rkey] = {"result": result, "ms": ms}

            if rkey in st.session_state:
                r  = st.session_state[rkey]["result"]
                ms = st.session_state[rkey]["ms"]
                st.divider()
                if r.get("_not_deployed") or r.get("_error"):
                    st.warning(f"⚠️ {r.get('error','Lambda not deployed')}")
                else:
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Status",  "✅ success" if r.get("status") == "success" else f"⚠️ {r.get('status','—')}")
                    sc2.metric("Latency", f"{ms}ms")
                    sc3.metric("Pages",   r.get("wiki_pages_used", 0))
                    outputs = r.get("outputs", {})
                    if outputs:
                        ok = [k for k in sk["output_keys"] if k in outputs]
                        oc = st.columns(max(len(ok), 1))
                        for i, k in enumerate(ok):
                            val = outputs[k]
                            if k == "confidence":
                                val = {"high": "🟢 HIGH", "medium": "🟡 MED", "low": "🔴 LOW"}.get(str(val).lower(), val)
                            oc[i].metric(k.replace("_", " ").title(), str(val))
                        # SK-02: show answer
                        if sid == "SK-02" and outputs.get("answer"):
                            with st.expander("📖 Answer"):
                                st.markdown(outputs["answer"][:500])
                        # SK-05: show gaps
                        if sid == "SK-05":
                            for g in outputs.get("gaps", [])[:3]:
                                st.markdown(f"{'🚨' if g.get('blocking') else '⚠️'} **{g.get('title','?')}** — `{g.get('gap_type','?')}`")
                        # SK-04: show fill %
                        if sid == "SK-04" and outputs.get("found"):
                            st.progress(min(outputs.get("completion_pct", 0) / 100, 1.0))
                        # SK-03: show S3 URI
                        if sid == "SK-03" and outputs.get("s3_uri"):
                            st.success(f"✅ Indexed: `{outputs['s3_uri']}`")
                    with st.expander("🔬 Full JSON"):
                        st.json(r)

            # ── Skill spec viewer ─────────────────────────────────
            spec_file = SKILL_SPEC_FILES.get(sid)
            if spec_file:
                spec_md = _read_spec(spec_file)
                if spec_md:
                    _spec_col, _dl_col = st.columns([5, 1])
                    with _spec_col:
                        with st.expander(f"📄 Skill Spec — {sid}: {sk['name']}", expanded=False):
                            st.caption(
                                "Written by a business analyst before any code. "
                                "Defines the skill contract in plain English — inputs, outputs, and business rules."
                            )
                            _render_spec(spec_md)
                    with _dl_col:
                        st.download_button(
                            label="⬇️ .md",
                            data=spec_md.encode("utf-8"),
                            file_name=spec_file,
                            mime="text/markdown",
                            key=f"dl_skill_spec_{sid}_catalog",
                            help=f"Download {spec_file} — use as template for a new use case.",
                            use_container_width=True,
                        )
                else:
                    st.caption(f"_(Spec file not found: `{spec_file}`)_")

    st.divider()
    st.subheader("🚀 UC1 Full Orchestrator — All 5 Skills in Sequence")
    st.markdown("Runs all 5 skills end-to-end and writes the customer handoff brief to the wiki in one call.")
    oc1, oc2 = st.columns([3, 1])
    oc1.markdown(f"**Customer:** `{sc_customer_id}` · **Use Case:** UC1 Sales-to-Service")
    with oc2:
        if st.button("🚀 Run Full UC1", type="primary", use_container_width=True, key="sc_uc1_run"):
            with st.spinner("Running UC1 orchestrator..."):
                r, ms = _sc_invoke(_SC_UC1, {"customer_id": sc_customer_id})
            st.session_state["sc_uc1_result"] = r
    if "sc_uc1_result" in st.session_state:
        r = st.session_state["sc_uc1_result"]
        if r.get("_not_deployed") or r.get("_error"):
            st.warning(r.get("error", "Not deployed"))
        else:
            u1, u2, u3, u4 = st.columns(4)
            u1.metric("Total ms",     r.get("total_latency_ms", 0))
            u2.metric("Skills Used",  len(r.get("skills_used", [])))
            u3.metric("Wiki Indexed", "✅" if r.get("wiki_indexed") else "⚠️")
            u4.metric("Template Fill", f"{r.get('template_completion_pct', 0)}%")
            st.success(r.get("summary", "UC1 complete"))
            for entry in r.get("skill_execution_log", []):
                skip = "Skipped" in entry.get("outcome", "")
                with st.expander(f"{'⏭️' if skip else '✅'} Step {entry['step']}: {entry['skill_id']} — {entry['business_name']} ({entry.get('latency_ms',0)}ms)"):
                    st.markdown(f"**Outcome:** {entry['outcome']}")
            with st.expander("🔬 Full JSON"):
                st.json(r)

# ──────────────────────────────────────────────────────────────────
# TAB: Skill Walk-through (agent_demo embedded)
# ──────────────────────────────────────────────────────────────────
with tab_skills:
    st.subheader("🔬 UC1 Skill Walk-through — Step by Step")
    st.caption("Powered by SK-01 → SK-02 → SK-05 → SK-04 → SK-03")

    SK01 = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
    SK02 = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
    SK03 = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
    SK04 = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
    SK05 = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")

    SKILL_META_SW = {
        SK01: {"id": "SK-01", "name": "Customer Briefing Loader",  "icon": "📋"},
        SK02: {"id": "SK-02", "name": "Knowledge Finder",          "icon": "🔍"},
        SK03: {"id": "SK-03", "name": "Knowledge Recorder",        "icon": "💾"},
        SK04: {"id": "SK-04", "name": "Template Auto-Fill",        "icon": "📝"},
        SK05: {"id": "SK-05", "name": "Missing Info Radar",        "icon": "🔭"},
    }

    # Demo inputs from sidebar defaults
    sw_defaults   = AGENTS["Sales-to-Service (UC1)"]["default_inputs"]
    sw_customer_id   = sw_defaults["customer_id"]
    sw_customer_name = sw_defaults["customer_name"]
    sw_product       = sw_defaults["product"]
    sw_sow_ref       = sw_defaults["sow_ref"]
    sw_agent_id      = "sales-to-service-agent-v1"

    if "sw_step" not in st.session_state:
        st.session_state.sw_step = 0
    if "sw_results" not in st.session_state:
        st.session_state.sw_results = {}

    TOTAL_SW = 6
    sw_step = st.session_state.sw_step
    st.progress(min(sw_step / TOTAL_SW, 1.0), text=f"Step {sw_step} of {TOTAL_SW}")
    col_rst, _ = st.columns([1, 5])
    with col_rst:
        if st.button("↺ Reset Walk-through", type="secondary", key="sw_reset"):
            st.session_state.sw_step = 0
            st.session_state.sw_results = {}
            st.rerun()
    st.divider()

    def sw_advance():
        st.session_state.sw_step += 1

    def sw_invoke(fn_name: str, payload: dict) -> tuple[dict, int]:
        try:
            t0   = time.time()
            resp = lambda_client.invoke(
                FunctionName=fn_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode(),
            )
            raw = json.loads(resp["Payload"].read())
            result = json.loads(raw["body"]) if "body" in raw and isinstance(raw.get("body"), str) else raw.get("body") or raw
            ms = result.get("latency_ms", int((time.time() - t0) * 1000))
            return result, ms
        except Exception as e:
            err = str(e)
            if "ResourceNotFoundException" in err or "Function not found" in err:
                return {"_not_deployed": True, "error": f"`{fn_name}` not yet deployed"}, 0
            return {"_invoke_error": True, "error": err}, 0

    def sw_check_nd(result: dict) -> bool:
        if result.get("_not_deployed") or result.get("_invoke_error"):
            st.warning(f"⚠️ Lambda not yet deployed: `{result.get('error','')}`")
            return True
        return False

    def sw_badge(result: dict):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Skill",      result.get("skill_id", "—"))
        c2.metric("Status",     result.get("status", "—").upper())
        c3.metric("Latency",    f"{result.get('latency_ms', 0)}ms")
        c4.metric("Pages Used", result.get("wiki_pages_used", 0))

    # ── Step 0 — Intro ─────────────────────────────────────────────
    if sw_step == 0:
        st.markdown(f"""
**Scenario:** *{sw_customer_name}* signs a SOW for {sw_product}. The agent runs 5 skills automatically.

| Step | Skill | What it does |
|------|-------|-------------|
| 1 | 📋 SK-01 | Load customer history + playbook |
| 2 | 🔍 SK-02 | Query wiki for delivery risks |
| 3 | 🔭 SK-05 | Detect knowledge gaps |
| 4 | 📝 SK-04 | Populate persona template |
| 5 | 💾 SK-03 | Write handoff brief to wiki |
""")
        st.button("▶ Start Walk-through", type="primary", on_click=sw_advance, key="sw_start")

    # ── Step 1 — SK-01 ────────────────────────────────────────────
    elif sw_step == 1:
        meta = SKILL_META_SW[SK01]
        st.markdown(f"### Step 1 of 5 — {meta['icon']} **{meta['id']} · {meta['name']}**")
        st.caption("Loads customer history and UC1 playbook in parallel")
        with st.spinner("📋 SK-01 fetching context..."):
            result, _ = sw_invoke(SK01, {
                "inputs": {"customer_id": sw_customer_id, "use_case": "UC1", "agent_id": sw_agent_id},
                "invoked_by": sw_agent_id,
            })
            st.session_state.sw_results["sk01"] = result
        if sw_check_nd(result):
            st.button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw1b")
        else:
            sw_badge(result)
            outputs = result.get("outputs", {})
            if outputs.get("customer_status") == "no-history":
                st.warning(f"⚠️ New customer — no prior history for `{sw_customer_id}`")
            else:
                st.success(f"✅ Found {outputs.get('pages_loaded', 0)} pages (history + playbook)")
            with st.expander("🔬 Full response"):
                st.json(result)
            c1, c2 = st.columns(2)
            c1.button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw1b")
            c2.button("▶ Next: SK-02 Knowledge Finder", type="primary", on_click=sw_advance, key="sw1n")

    # ── Step 2 — SK-02 ────────────────────────────────────────────
    elif sw_step == 2:
        meta = SKILL_META_SW[SK02]
        st.markdown(f"### Step 2 of 5 — {meta['icon']} **{meta['id']} · {meta['name']}**")
        q2 = st.text_area("Question", value=f"What are the key delivery risks for a new {sw_product} implementation for a healthcare payer?", height=80, key="sw_q2")
        if st.button("🔍 Call SK-02", type="primary", key="sw2_run"):
            with st.spinner("Querying wiki..."):
                result, _ = sw_invoke(SK02, {
                    "inputs": {"question": q2, "domain": "customer-onboarding", "customer_id": sw_customer_id, "use_case": "UC1", "intent": "handoff-preparation"},
                    "invoked_by": sw_agent_id,
                })
                st.session_state.sw_results["sk02"] = result
                st.session_state.sw_results["sk02_q"] = q2
        if "sk02" in st.session_state.sw_results:
            result = st.session_state.sw_results["sk02"]
            if not sw_check_nd(result):
                sw_badge(result)
                outputs = result.get("outputs", {})
                conf = outputs.get("confidence", "unknown")
                st.metric("Confidence", {"high": "🟢 HIGH", "medium": "🟡 MEDIUM", "low": "🔴 LOW"}.get(conf, conf))
                st.markdown(outputs.get("answer", "_No answer_"))
                with st.expander("🔬 Full response"):
                    st.json(result)
                c1, c2 = st.columns(2)
                c1.button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw2b")
                c2.button("▶ Next: SK-05 Gap Detector", type="primary", on_click=sw_advance, key="sw2n")
        else:
            st.button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw2b2")

    # ── Step 3 — SK-05 ────────────────────────────────────────────
    elif sw_step == 3:
        meta = SKILL_META_SW[SK05]
        st.markdown(f"### Step 3 of 5 — {meta['icon']} **{meta['id']} · {meta['name']}**")
        sk02_out = st.session_state.sw_results.get("sk02", {}).get("outputs", {})
        conf = sk02_out.get("confidence", "medium")
        if conf == "low":
            st.markdown("SK-02 returned `confidence=low` — SK-05 will classify and record the gaps.")
            if st.button("🔭 Run SK-05", type="primary", key="sw3_run"):
                with st.spinner("Detecting gaps..."):
                    result, _ = sw_invoke(SK05, {
                        "inputs": {"question": st.session_state.sw_results.get("sk02_q", ""), "domain": "customer-onboarding", "use_case": "UC1", "customer_id": sw_customer_id, "low_confidence_response": sk02_out},
                        "invoked_by": sw_agent_id,
                    })
                    st.session_state.sw_results["sk05"] = result
            if "sk05" in st.session_state.sw_results and not sw_check_nd(st.session_state.sw_results["sk05"]):
                sw_badge(st.session_state.sw_results["sk05"])
                gaps = st.session_state.sw_results["sk05"].get("outputs", {}).get("gaps", [])
                for g in gaps:
                    st.markdown(f"{'🚨' if g.get('blocking') else '⚠️'} **{g.get('title')}** — `{g.get('gap_type')}`")
        else:
            st.success(f"Wiki answered with `confidence={conf}` — no gaps to record. SK-05 returns `gaps=[]`.")
            if "sk05" not in st.session_state.sw_results:
                st.session_state.sw_results["sk05"] = {"skill_id": "SK-05", "status": "success", "outputs": {"gaps": [], "gap_count": 0, "blocking": False}, "latency_ms": 0, "wiki_pages_used": 0}
        c1, c2 = st.columns(2)
        c1.button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw3b")
        c2.button("▶ Next: SK-04 Template Fill", type="primary", on_click=sw_advance, key="sw3n")

    # ── Step 4 — SK-04 ────────────────────────────────────────────
    elif sw_step == 4:
        meta = SKILL_META_SW[SK04]
        st.markdown(f"### Step 4 of 5 — {meta['icon']} **{meta['id']} · {meta['name']}**")
        artifact_type = st.selectbox("Artifact", ["persona-template", "bom-template", "sow-review-checklist"], key="sw4_art")
        sk01_out = st.session_state.sw_results.get("sk01", {}).get("outputs", {})
        sk02_out = st.session_state.sw_results.get("sk02", {}).get("outputs", {})
        if st.button("📝 Call SK-04", type="primary", key="sw4_run"):
            with st.spinner("Filling template..."):
                result, _ = sw_invoke(SK04, {
                    "inputs": {"artifact_type": artifact_type, "customer_id": sw_customer_id, "available_context": {"customer_id": sw_customer_id, "customer_name": sw_customer_name, "product": sw_product, "delivery_risks": sk02_out.get("answer", ""), "action_items": sk02_out.get("action_items", [])}, "use_case": "UC1"},
                    "invoked_by": sw_agent_id,
                })
                st.session_state.sw_results["sk04"] = result
        if "sk04" in st.session_state.sw_results:
            result = st.session_state.sw_results["sk04"]
            if not sw_check_nd(result):
                sw_badge(result)
                outputs = result.get("outputs", {})
                if result.get("status") == "not_found":
                    st.warning("Artifact template not yet in wiki — upload template to `raw/` first.")
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Populated", len(outputs.get("populated_fields", [])))
                    c2.metric("Missing",   len(outputs.get("missing_fields", [])))
                    c3.metric("Fill %",    f"{outputs.get('completion_pct', 0)}%")
                with st.expander("🔬 Full response"):
                    st.json(result)
        cols = st.columns(2)
        cols[0].button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw4b")
        cols[1].button("▶ Next: SK-03 Write to Wiki", type="primary", on_click=sw_advance, key="sw4n")

    # ── Step 5 — SK-03 ────────────────────────────────────────────
    elif sw_step == 5:
        meta = SKILL_META_SW[SK03]
        st.markdown(f"### Step 5 of 5 — {meta['icon']} **{meta['id']} · {meta['name']}**")
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")
        sk02_out = st.session_state.sw_results.get("sk02", {}).get("outputs", {})
        default_content = f"""---
title: {sw_customer_name} — Sales-to-Service Handoff Brief {today[:4]}
date: {today}
customer_id: {sw_customer_id}
use_case_tags: [UC1]
domain: customer-onboarding
contributing_agent: {sw_agent_id}
---
# {sw_customer_name} — Handoff Brief
Generated by {sw_agent_id} on {today}

## Delivery Risks
{sk02_out.get('answer', '_Run Step 2 first_')}

## Action Items
{chr(10).join('- ' + a for a in sk02_out.get('action_items', ['Review SOW', 'Schedule kickoff']))}
"""
        content = st.text_area("Handoff brief", value=default_content, height=250, key="sw5_content")
        if st.button("💾 Write to Wiki via SK-03", type="primary", key="sw5_run"):
            with st.spinner("Writing to wiki..."):
                result, _ = sw_invoke(SK03, {
                    "inputs": {"page_type": "customers", "page_slug": f"{sw_customer_id}-handoff-{today[:4]}", "content": content, "agent_id": sw_agent_id, "customer_id": sw_customer_id, "use_case": "UC1", "human_review_required": False},
                    "invoked_by": sw_agent_id,
                })
                st.session_state.sw_results["sk03"] = result
        if "sk03" in st.session_state.sw_results:
            result = st.session_state.sw_results["sk03"]
            if not sw_check_nd(result):
                sw_badge(result)
                status = result.get("outputs", {}).get("status", "")
                if status == "indexed":
                    st.success("✅ Handoff brief indexed — immediately available to UC2 agent!")
                elif status == "pending-review":
                    st.warning("⏳ Pending human review (wiki/pending/)")
                with st.expander("🔬 Full response"):
                    st.json(result)
        cols = st.columns(2)
        cols[0].button("◀ Back", on_click=lambda: setattr(st.session_state, "sw_step", sw_step - 1), key="sw5b")
        if "sk03" in st.session_state.sw_results:
            cols[1].button("▶ Results", type="primary", on_click=sw_advance, key="sw5n")

    # ── Step 6 — Results ──────────────────────────────────────────
    elif sw_step >= 6:
        st.success("**Walk-through complete!** The wiki now has the handoff brief — UC2 agent reads it automatically.")
        sk_lats = [(k, st.session_state.sw_results.get(k, {}).get("latency_ms", 0)) for k in ["sk01", "sk02", "sk05", "sk04", "sk03"]]
        total_lat = sum(v for _, v in sk_lats)
        c1, c2, c3 = st.columns(3)
        c1.metric("Skills Run", "5/5")
        c2.metric("Total Latency", f"{total_lat}ms")
        c3.metric("Human Effort", "0 min")
        st.button("↺ Run Again", type="secondary", on_click=lambda: (setattr(st.session_state, "sw_step", 0), setattr(st.session_state, "sw_results", {})), key="sw_again")

# ──────────────────────────────────────────────────────────────────
# TAB: Hard Harness
# ──────────────────────────────────────────────────────────────────
with tab_harness:

    # ── OKF Knowledge Context panel ───────────────────────────────
    def _okf_context_for_harness(wiki_bucket: str, customer_id: str, product: str, agent_id: str):
        """
        Scan the wiki for pages most relevant to this harness run.
        S2S: wiki/{type}/{slug}.md — uses [[wikilinks]] as edges.
        PM:  kb/*.md (products), specs/*.md (skills),
             wiki/pm/drafts/PRB-*/rca-draft.json (problem records).
             Edges from product name mentions in contributing_factors.
        Returns (nodes, by_type, edges, inbound).
        """
        import re, json as _json
        from collections import defaultdict
        nodes, by_type, edges, inbound = {}, defaultdict(list), [], defaultdict(int)

        if agent_id != "pm":
            # ── S2S: standard wiki/ wikilink scan ─────────────────
            try:
                resp = s3_client.list_objects_v2(Bucket=wiki_bucket, Prefix="wiki/", MaxKeys=300)
            except Exception:
                return nodes, by_type, edges, inbound
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".md"):
                    continue
                parts = key.replace("wiki/", "").replace(".md", "").split("/")
                if len(parts) != 2:
                    continue
                page_type, slug = parts
                try:
                    body = s3_client.get_object(Bucket=wiki_bucket, Key=key)["Body"].read().decode("utf-8", errors="ignore")
                except Exception:
                    continue
                title = slug.replace("-", " ").title()
                if body.startswith("---"):
                    end = body.find("---", 3)
                    if end > 0:
                        for line in body[3:end].split("\n"):
                            if line.startswith("title:"):
                                title = line.split(":", 1)[1].strip().strip('"\'')
                nodes[slug] = {"slug": slug, "title": title, "type": page_type}
                by_type[page_type].append(slug)
                for link in re.findall(r"\[\[([^\]]+)\]\]", body):
                    target = link.split("|")[0].strip()
                    if target != slug:
                        edges.append((slug, target))
                        inbound[target] += 1
            return nodes, by_type, edges, inbound

        # ── PM: kb/ + specs/ + wiki/pm/drafts/ PRB JSON ───────────
        PM_PRODUCTS = ["Facets", "QNXT", "EDM", "EAM", "TCS", "NetworX", "FRM"]
        PM_KB_KEYS  = {
            "Facets":        "kb/facets.md",
            "QNXT":          "kb/qnxt.md",
            "EDM-EAM-TCS":   "kb/edm-eam-tcs.md",
            "NetworX-FRM":   "kb/networx-frm.md",
        }

        # Product KB nodes
        for prod, key in PM_KB_KEYS.items():
            try:
                body = s3_client.get_object(Bucket=wiki_bucket, Key=key)["Body"].read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            slug = prod.lower()
            nodes[slug] = {"slug": slug, "title": prod, "type": "product", "body": body[:2000]}
            by_type["product"].append(slug)

        # Skill spec nodes (specs/)
        try:
            spec_resp = s3_client.list_objects_v2(Bucket=wiki_bucket, Prefix="specs/", MaxKeys=20)
        except Exception:
            spec_resp = {}
        for obj in spec_resp.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".md"):
                continue
            slug = key.replace("specs/", "").replace(".md", "")
            try:
                body = s3_client.get_object(Bucket=wiki_bucket, Key=key)["Body"].read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            title = slug.replace("-", " ").title()
            if body.startswith("---"):
                end = body.find("---", 3)
                if end > 0:
                    for line in body[3:end].split("\n"):
                        if line.startswith("title:") or line.startswith("business_name:"):
                            title = line.split(":", 1)[1].strip().strip('"\'')
                            break
            nodes[slug] = {"slug": slug, "title": title, "type": "skill"}
            by_type["skill"].append(slug)

        # Problem record nodes from wiki/pm/drafts/PRB-*/rca-draft.json
        try:
            prb_resp = s3_client.list_objects_v2(Bucket=wiki_bucket, Prefix="wiki/pm/drafts/", MaxKeys=50)
        except Exception:
            prb_resp = {}
        for obj in prb_resp.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("rca-draft.json"):
                continue
            parts = key.split("/")
            prb_id = parts[3] if len(parts) >= 4 else "PRB-?"
            try:
                body = s3_client.get_object(Bucket=wiki_bucket, Key=key)["Body"].read().decode("utf-8", errors="ignore")
                data = _json.loads(body)
            except Exception:
                data = {}
            slug = prb_id.lower()
            title = f"{prb_id} — {data.get('title', data.get('category', 'RCA Draft'))[:50]}"
            risk  = data.get("risk_tier", "medium")
            prod  = data.get("product", "Facets")
            nodes[slug] = {"slug": slug, "title": title, "type": "problem",
                           "risk": risk, "product": prod}
            by_type["problem"].append(slug)

            # Edge: PRB → primary product
            prod_slug = prod.lower()
            if prod_slug in nodes or any(prod.lower() in k for k in nodes):
                match = next((k for k in nodes if prod.lower() in k and nodes[k]["type"] == "product"), None)
                if match:
                    edges.append((slug, match))
                    inbound[match] += 1

            # Edges: PRB → secondary products from contributing_factors
            for factor in data.get("contributing_factors", []):
                for p in PM_PRODUCTS:
                    if p.lower() in factor.lower() and p.lower() != prod.lower():
                        match2 = next((k for k in nodes if p.lower() in k and nodes[k]["type"] == "product"), None)
                        if match2:
                            edges.append((slug, match2))
                            inbound[match2] += 1

        return nodes, by_type, edges, inbound

    # Show OKF context before run
    _PHASE_TYPE_MAP = {
        "s2s": ["sources", "concepts", "customers", "entities"],
        "pm":  ["product", "skill", "problem"],
    }
    _TYPE_COLORS_H = {
        # S2S types
        "sources": "#3b82f6", "concepts": "#f59e0b", "entities": "#8b5cf6",
        "questions": "#ef4444", "customers": "#10b981",
        # PM types
        "product": "#1a6bbd", "skill": "#7c3aed", "problem": "#dc2626",
    }
    _TYPE_ICONS_H = {
        "sources": "📑", "concepts": "💡", "entities": "🏢", "questions": "❓", "customers": "👤",
        "product": "🏭", "skill": "🔧", "problem": "🔴",
    }
    _TYPE_LABELS_H = {
        "sources": "Source Summaries", "concepts": "Concepts", "entities": "Entities",
        "questions": "Knowledge Gaps", "customers": "Customers",
        "product": "Product Knowledge Base", "skill": "Skill Specs", "problem": "Problem Records (RCAs)",
    }

    with st.expander("🕸️ OKF Knowledge Context — what the AI knows before Phase 1", expanded=False):
        st.caption(
            "The Open Knowledge Format index tells the harness exactly which wiki pages exist, "
            "how they connect, and which are most authoritative (highest inbound links). "
            "This context is pre-loaded before Phase 1 so the AI doesn't start from a blank slate."
        )
        _wiki_bkt = agent_cfg["wiki_bucket"] or S2S_WIKI_BUCKET
        if not _wiki_bkt:
            st.warning("Wiki bucket not configured for this agent.")
        else:
            _okf_nodes, _okf_by_type, _okf_edges, _okf_inbound = _okf_context_for_harness(
                _wiki_bkt, customer_id, product, agent_cfg["id"]
            )
            if not _okf_nodes:
                st.warning(
                    "No knowledge nodes found. "
                    + ("Check that the PM bucket is accessible and contains `kb/`, `specs/`, or `wiki/pm/drafts/` files."
                       if agent_cfg["id"] == "pm"
                       else "Ingest documents first to populate the wiki.")
                )
            else:
                # Stats row
                _aid = agent_cfg["id"]
                _relevant_types = _PHASE_TYPE_MAP.get(_aid, ["sources", "concepts"])
                _mc = st.columns(4)
                _total_pages = len(_okf_nodes)
                _total_links = len(_okf_edges)
                _relevant_pages = sum(len(_okf_by_type.get(t, [])) for t in _relevant_types)
                _top_page = max(_okf_inbound, key=_okf_inbound.get) if _okf_inbound else None
                _page_label = "Knowledge nodes" if _aid == "pm" else "Total wiki pages"
                _link_label = "Cross-system links" if _aid == "pm" else "Knowledge links"
                _mc[0].metric(_page_label, _total_pages)
                _mc[1].metric(_link_label, _total_links)
                _mc[2].metric("Relevant to this harness", _relevant_pages)
                _mc[3].metric(
                    "Most-referenced" if _aid == "pm" else "Most-linked page",
                    _okf_nodes.get(_top_page, {}).get("title", "—")[:25] if _top_page else "—"
                )

                st.markdown("**Knowledge loaded per phase:**")
                _phase_cols = st.columns(len(_relevant_types))
                for _ci, _t in enumerate(_relevant_types):
                    _slugs = sorted(_okf_by_type.get(_t, []),
                                    key=lambda s: -_okf_inbound.get(s, 0))
                    _icon  = _TYPE_ICONS_H.get(_t, "📄")
                    _color = _TYPE_COLORS_H.get(_t, "#94a3b8")
                    _label = _TYPE_LABELS_H.get(_t, _t.title())
                    with _phase_cols[_ci]:
                        st.markdown(
                            f"<span style='background:{_color}20;color:{_color};"
                            f"border-radius:4px;padding:2px 8px;font-size:.8em;"
                            f"font-weight:600;'>{_icon} {_label}</span>",
                            unsafe_allow_html=True,
                        )
                        # For PM problem records show risk tier badge
                        for _s in _slugs[:6]:
                            _n  = _okf_nodes.get(_s, {})
                            _ib = _okf_inbound.get(_s, 0)
                            _risk_icon = (
                                {"high":"🔴","P1":"🔴","medium":"🟠","P2":"🟠"}.get(_n.get("risk",""), "🟡")
                                if _n.get("type") == "problem" else ""
                            )
                            _star = "⭐ " if (_t != "problem" and _ib >= 5) or (_t == "problem" and _ib >= 2) else ""
                            st.markdown(
                                f"<span style='font-size:.8em;'>{_star}{_risk_icon}"
                                f"{_n.get('title', _s)[:32]}</span>",
                                unsafe_allow_html=True,
                            )
                        if len(_slugs) > 6:
                            st.caption(f"+ {len(_slugs)-6} more")

                # For PM: show which product is in focus
                if agent_cfg["id"] == "pm" and product:
                    _prod_match = next(
                        (s for s in _okf_nodes if product.lower() in s
                         and _okf_nodes[s]["type"] == "product"), None
                    )
                    if _prod_match:
                        _prb_for_prod = [
                            s for s in _okf_by_type.get("problem", [])
                            if _okf_nodes[s].get("product","").lower() == product.lower()
                        ]
                        st.markdown(
                            f"**Primary focus: `{product}`** — "
                            f"{len(_prb_for_prod)} problem record(s) in this domain · "
                            f"{_okf_inbound.get(_prod_match,0)} cross-system references"
                        )

                # For S2S: show customer-specific pages
                elif agent_cfg["id"] != "pm":
                    _cust_q = customer_id.lower().replace("_", "-")
                    _cust_pages = [
                        s for s in _okf_nodes
                        if _cust_q in s or any(_cust_q in t for t in [s, _okf_nodes[s].get("title","").lower()])
                    ]
                    if _cust_pages:
                        st.markdown(f"**Existing pages for `{customer_id}`:**")
                        for _s in _cust_pages[:5]:
                            _n = _okf_nodes.get(_s, {})
                            st.markdown(
                                f"<span style='font-size:.83em;'>📎 {_n.get('title', _s)}"
                                f" — `{_n.get('type','?')}`</span>",
                                unsafe_allow_html=True,
                            )
                        st.caption("These pages will be loaded automatically in Phase 4.")

    # ── Link to Knowledge Graph (passes harness as query param) ──
    _kg_param = "pm" if agent_cfg["id"] == "pm" else "s2s"
    _kg_label = "Problem Management" if agent_cfg["id"] == "pm" else "Sales-to-Service"
    st.markdown(
        f"<small>🕸️ "
        f"<a href='/knowledge_graph?harness={_kg_param}' target='_blank'>"
        f"View full {_kg_label} knowledge graph →</a>"
        f"</small>",
        unsafe_allow_html=True,
    )

    # ── Session state init ─────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "gatekeeper_done" not in st.session_state:
        st.session_state.gatekeeper_done = False
    if "harness_running" not in st.session_state:
        st.session_state.harness_running = False
    if "harness_result" not in st.session_state:
        st.session_state.harness_result = {}
    if "phase3_answered" not in st.session_state:
        st.session_state.phase3_answered = False

    # ── Main two-column layout ─────────────────────────────────────
    col_chat, col_plan = st.columns([6, 4], gap="large")

    # ══════════════════════════════════════════════════════════════════
    # LEFT — Conversation stream
    # ══════════════════════════════════════════════════════════════════
    with col_chat:
        st.subheader("💬 Agent Conversation")

        # Render chat history
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # ── Reconnect banner — shown once after auto-resuming a prior run ─
        if st.session_state.get("harness_reconnected"):
            run_id = st.session_state.get("harness_run_id", "")
            status = st.session_state.harness_result.get("status", "")
            st.info(
                f"**Prior run detected** — `{run_id}` ({status.upper()})\n\n"
                "You are viewing the restored session above. Choose an option:"
            )
            col_resume, col_fresh = st.columns(2)
            with col_resume:
                if st.button("▶ Continue this run", type="primary", key="btn_resume"):
                    st.session_state.harness_reconnected = False
                    st.rerun()
            with col_fresh:
                if st.button("🔄 Start a fresh run", type="secondary", key="btn_fresh"):
                    for k in ["harness_result", "gatekeeper_done", "harness_running",
                              "phase3_question", "phase3_answered", "chat_messages",
                              "harness_polling", "harness_run_id", "harness_phase3_ctx",
                              "harness_reconnected"]:
                        st.session_state.pop(k, None)
                    st.rerun()
            st.stop()

        # ── Stage 1: Start / Gatekeeper ───────────────────────────────
        if not st.session_state.gatekeeper_done and not st.session_state.harness_running:
            with st.chat_message("assistant"):
                st.markdown(agent_cfg["greeting"])

            if st.button("▶ Start Harness", type="primary", key="start_btn"):
                if agent_cfg["uses_gatekeeper"]:
                    with st.spinner("Gatekeeper validating prerequisites..."):
                        gk = _invoke(GATEKEEPER_FN, {
                            "customer_id":   customer_id,
                            "customer_name": customer_name,
                            "product":       product,
                            "sow_reference": sow_ref,
                            "agent_id":      agent_id,
                        })

                    if gk.get("_not_deployed") or gk.get("_error"):
                        st.error(f"⚠️ Gatekeeper Lambda error: {gk.get('error')}")
                        st.stop()

                    if not gk.get("ready") and gk.get("resume"):
                        _reconnect_to_prior_run(gk, customer_id, customer_name, product, sow_ref,
                                                agent_cfg["id"])
                        st.rerun()

                    if not gk.get("ready"):
                        st.warning(f"🚫 Not ready: {gk.get('message')}")
                        st.stop()

                    msg_txt = gk.get("message", "Prerequisites validated. Ready to begin.")
                    confirm_label = agent_cfg["start_confirmation_label"]
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": (
                            f"**Prerequisites validated ✅**\n\n{msg_txt}\n\n"
                            f"**{confirm_label}:** {customer_name} · {product} · {sow_ref}\n\n"
                            "Type **'Go ahead'** to start the 8-phase workflow."
                        ),
                    })
                else:
                    # PM and future agents without a gatekeeper: go straight to confirmation
                    confirm_label = agent_cfg["start_confirmation_label"]
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": (
                            f"**Ready to begin ✅**\n\n"
                            f"**{confirm_label}:** {sow_ref} · {customer_name} · {product}\n\n"
                            "Type **'Go ahead'** to start the 8-phase workflow."
                        ),
                    })
                st.session_state.gatekeeper_done = True
                st.rerun()

        # ── Stage 2: User confirms → harness starts ────────────────────
        elif (st.session_state.gatekeeper_done
              and not st.session_state.harness_running
              and not st.session_state.harness_result
              and not st.session_state.phase3_answered):

            with st.chat_message("assistant"):
                st.markdown(agent_cfg["start_hint"])

            user_input = st.chat_input(agent_cfg["chat_placeholder"])
            if user_input:
                st.session_state.chat_messages.append({"role": "user", "content": user_input})
                st.session_state.harness_running = True
                st.rerun()

        # ── Stage 3: Run harness phases 1-2 then pause at phase 3 ──────
        elif st.session_state.harness_running and not st.session_state.harness_result:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": f"🔒 **Harness started.** Running phases 1 and 2 for {agent_cfg['title']}...",
            })

            with st.spinner("Running Phase 1 and Phase 2..."):
                result = _invoke(HARNESS_FN, _build_harness_payload(
                    agent_cfg, customer_id, customer_name, product, sow_ref, agent_id,
                    severity=pm_severity, record_ids=pm_record_ids,
                ))

            if result.get("_not_deployed") or result.get("_error"):
                st.error(f"⚠️ Harness Lambda error: {result.get('error')}")
                st.session_state.harness_running = False
                st.stop()

            st.session_state.harness_result = result
            st.session_state.harness_running = False

            status = result.get("status", "")
            pr     = result.get("phase_results", {})

            if status == "paused" and result.get("current_phase") == 3:
                # PM harness returns classification + questions list; UC1 returns question string
                if agent_cfg["id"] == "pm":
                    cls        = result.get("classification", {})
                    questions  = result.get("questions", [])
                    q_text     = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions)) or "Please provide SME context."
                    cls_msg = (
                        f"**Phases 1–2 complete ✅**\n\n"
                        f"**Classification:** {cls.get('normalized_category','—')} · "
                        f"Recurrence: **{cls.get('recurrence_type','—')}** · "
                        f"Risk tier: **{cls.get('risk_tier','—')}** · "
                        f"Confidence: {cls.get('classification_confidence','—')}\n\n"
                        f"---\n\n"
                        f"**⏸️ Phase 3 — SME input required before phases 4–8:**\n\n"
                        f"{q_text}"
                    )
                    st.session_state.phase3_question = q_text
                else:
                    cls = pr.get("phase2", {})
                    cls_msg = (
                        f"**Phases 1–2 complete ✅**\n\n"
                        f"**Classification:** {cls.get('customer_type','Unknown')} · "
                        f"Risk tier: **{cls.get('risk_tier','—')}** · "
                        f"Complexity: {cls.get('implementation_complexity','—')}\n\n"
                        f"_{cls.get('rationale','')}_\n\n"
                        f"---\n\n"
                        f"**⏸️ Phase 3 — I need your input before analysing risks:**\n\n"
                        f"{result.get('question', 'Please provide context about this engagement.')}"
                    )
                    st.session_state.phase3_question = result.get("question", "")
                st.session_state.chat_messages.append({"role": "assistant", "content": cls_msg})

            elif _is_done(status):
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": _completion_message(result, agent_cfg["id"]),
                })

            elif status == "error":
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"❌ Error at Phase {result.get('failed_phase')}: {result.get('error')}",
                })

            st.rerun()

        # ── Stage 4: Awaiting Phase 3 human context ────────────────────
        elif (st.session_state.harness_result.get("status") == "paused"
              and not st.session_state.get("phase3_answered")
              and not st.session_state.get("harness_polling")):

            # Show the questions again prominently
            question_text = st.session_state.get("phase3_question", "")
            if question_text:
                with st.chat_message("assistant"):
                    st.markdown("**⏸️ Waiting for your input to continue phases 4–8:**")
                    st.markdown(question_text)

            st.info(
                "💡 **How to answer:** Reply to the numbered questions above. "
                "One sentence per question is fine.\n\n"
                + agent_cfg["human_input_hint"]
            )

            # ── Demo answer bank (copy-paste for smooth demo) ──────────
            if agent_cfg["id"] == "pm":
                with st.expander("📋 Demo answer bank — copy-paste for smooth demo", expanded=False):
                    st.markdown("**Recommended SME context answer for UC-PM demo** (cross-system scenario)")
                    st.code(
                        "Month-end claims batch failed at 2:47 AM — Facets Claims Adjudication Engine "
                        "aborted with NullPointerException on 14,832 Medicare supplemental claims. "
                        "Simultaneously, EAM shows 3 retrospective prior-auth approvals posted at 2:51 AM "
                        "that never propagated downstream — those claims are now denied despite having valid auths. "
                        "FRM month-end reconciliation is also deadlocked — Facets and QNXT capitation postings "
                        "ran concurrently at 3:15 AM and the fin_ledger_entry table is locked. "
                        "EDM encounter submission job scheduled for 4 AM will miss its CMS window if FRM "
                        "does not release the lock. No code changes in last 30 days. This exact pattern — "
                        "batch null-pointer causing downstream EAM propagation miss and FRM deadlock — "
                        "was seen in Q3 2025 but closed as separate tickets rather than a systemic cross-product issue.",
                        language="text",
                    )
            else:
                with st.expander("📋 Demo answer bank — copy-paste for smooth demo", expanded=False):
                    st.markdown("**Step 3 — SME context** (paste into the text area below to proceed through phases 4–8)")
                    st.code(
                        "No prior QNXT implementation attempts for BCBS-MN. "
                        "CMO Sarah Chen is executive sponsor — high organizational visibility. "
                        "Committed go-live is Q3 2026 (hard deadline, tied to contract penalty clause). "
                        "HIPAA 837/835 EDI is required; customer EHR is Epic 2024.2.1 on-premises. "
                        "Customer is migrating from Facets 5.2.1 — 3.2M member records, "
                        "18 months claims history in scope. Parallel run period: 90 days minimum.",
                        language="text",
                    )
                    st.markdown("---")
                    st.markdown(
                        "**If Phase 6 reports blocking gaps** — the agent will continue automatically, "
                        "but if a follow-up asks about them, paste these answers:"
                    )
                    st.markdown("**Gap 1 — TriZetto QNXT ↔ Epic EHR Integration Architecture** (unknown-configuration)")
                    st.code(
                        "BCBS-MN runs Epic 2024.2.1 on-premises at Eden Prairie data center. "
                        "QNXT-to-Epic integration uses Epic Interconnect (HL7 FHIR R4) for bidirectional "
                        "patient demographics and eligibility sync. "
                        "Rhapsody interface engine is in place managing 14 active HL7 interfaces. "
                        "Authorization decisions flow via HL7 v2.x ADT notification feed from Epic to QNXT. "
                        "BCBS-MN completed one prior QNXT integration for their Colorado subsidiary — "
                        "interface specs are documented and available.",
                        language="text",
                    )
                    st.markdown("**Gap 2 — BCBS MN Legacy System Complexity & Data Migration Scope** (missing-customer-history)")
                    st.code(
                        "Migrating from Facets 5.2.1 (TriZetto hosted). "
                        "3.2 million active member records. "
                        "Claims history: 18 months (January 2025 – June 2026). "
                        "127 custom benefit configuration tables — crosswalk drafted for 89 of 127. "
                        "Parallel run: 90 days minimum per contract SLA. "
                        "TriZetto standard ETL toolkit with BCBS-MN DBA on-site during cutover. "
                        "Data quality assessment complete (ref: BCBS-MN-DQ-2026-03) — "
                        "14,200 member records flagged with incomplete address data requiring remediation.",
                        language="text",
                    )

            _p3_placeholder = (
                "Null pointer exceptions appear during peak batch hours (2–4 AM). "
                "No recent code changes deployed. Connection pool exhaustion suspected."
                if agent_cfg["id"] == "pm"
                else
                "No prior attempts. CMO is executive sponsor. Go-live Q1 2027. HIPAA required; EHR is Epic."
            )
            user_context_input = st.text_area(
                "Your answers (address each numbered question above):",
                height=120,
                placeholder=_p3_placeholder,
                key="phase3_textarea",
            )
            if st.button("▶ Submit answers & run phases 4–8", type="primary", key="phase3_submit"):
                user_context = user_context_input.strip()
            else:
                user_context = None

            if user_context:
                st.session_state.chat_messages.append({"role": "user", "content": user_context})
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": (
                        "✅ **Context received.**\n\n"
                        "🔒 Firing phases 4–8 in the background. "
                        "Watch the **Locked Plan panel** on the right — each phase lights up ✅ as it completes. "
                        "No need to wait — this page will refresh automatically every few seconds."
                    ),
                })
                prior  = st.session_state.harness_result
                run_id = prior.get("run_id", "")

                # Fire Lambda asynchronously (Event = fire-and-forget)
                lambda_client.invoke(
                    FunctionName=HARNESS_FN,
                    InvocationType="Event",          # async — returns immediately
                    Payload=json.dumps(
                        _build_harness_payload(
                            agent_cfg, customer_id, customer_name, product, sow_ref, agent_id,
                            human_context=user_context, run_id=run_id,
                            severity=pm_severity, record_ids=pm_record_ids,
                        ),
                        default=str,
                    ).encode(),
                )

                st.session_state.harness_polling    = True
                st.session_state.harness_run_id     = run_id
                st.session_state.harness_phase3_ctx = user_context
                st.session_state.harness_poll_start = time.time()
                st.rerun()

        # ── Stage 4b: Polling — phases running in background ───────────
        elif st.session_state.get("harness_polling") and not st.session_state.get("phase3_answered"):
            run_id     = st.session_state.get("harness_run_id", "")
            poll_start = st.session_state.get("harness_poll_start", time.time())
            elapsed    = int(time.time() - poll_start)

            # Poll via get_status action
            poll = _invoke(HARNESS_FN, _build_harness_payload(
                agent_cfg, customer_id, customer_name, product, sow_ref, agent_id,
                run_id=run_id, action="get_status",
            ))

            phases_done        = poll.get("phases_done", 0)
            poll_status        = poll.get("status", "running")
            phase_results_live = poll.get("phase_results", {})

            # Merge live results into session state so right panel updates
            if phase_results_live:
                existing = st.session_state.harness_result
                existing["phase_results"] = phase_results_live
                existing["status"]        = poll_status
                st.session_state.harness_result = existing

            # ── Per-phase contextual messages + time estimates ─────────
            # Each entry: (cumulative_seconds_start, description, what_claude_is_doing)
            # PM: Phase4(SK-01 wiki query)~15s, Phase5(RCA draft LLM)~35s,
            #     Phase6(gap detect)~10s, Phase7(template fill)~8s, Phase8(S3 write)~5s
            PHASE_TIMELINE = {
                "pm": [
                    # (phase_num, starts_at_elapsed_sec, label, detail)
                    (4,  0,  "📚 Load Prior Knowledge",
                     "**SK-01** is querying the wiki for prior RCAs, KEDB entries, and known failure patterns for this component…"),
                    (5,  15, "🧠 RCA Draft & Pattern Detection",
                     "**Claude** is analysing the incident records, SME context, and prior RCAs to draft the root cause statement and timeline…"),
                    (6,  50, "🔭 Knowledge Gap Detection",
                     "**SK-05** is scanning the RCA draft for undocumented failure modes and missing resolution steps…"),
                    (7,  65, "📝 Fill RCA & KEDB Templates",
                     "**SK-04** is populating the standard RCA and KEDB templates with the confirmed root cause and remediation steps…"),
                    (8,  75, "💾 Write Draft & Route for Review",
                     "**SK-03** is saving the RCA draft to the wiki and generating the downloadable HTML report…"),
                ],
                "s2s": [
                    (4,  0,  "📋 Load Delivery Playbook",
                     "**SK-01** is retrieving the customer briefing, product playbook, and prior delivery commitments…"),
                    (5,  15, "🔍 Risk & Gap Analysis",
                     "**Claude** is reviewing the SOW against known delivery risks and wiki knowledge for this product…"),
                    (6,  45, "🔭 Gap Detection & Recording",
                     "**SK-05** is spawning sub-agents to identify and record knowledge gaps that could block delivery…"),
                    (7,  60, "📝 Template Population",
                     "**SK-04** is filling the handoff persona template with classification and risk findings…"),
                    (8,  70, "💾 Write Handoff + Report",
                     "**SK-03** is indexing the handoff brief to the wiki and generating the downloadable report…"),
                ],
            }
            timeline = PHASE_TIMELINE.get(agent_cfg["id"], PHASE_TIMELINE["s2s"])

            # Determine which phase to display: use DynamoDB confirmed count first,
            # then fall back to elapsed-time estimate so the screen is never frozen.
            # Phase 4 is always "active" from t=0 (background run just started).
            active_phase_num = 4  # default: Phase 4 is always running at the start
            for (ph_num, starts_at, _label, _detail) in timeline:
                if phases_done >= ph_num:
                    active_phase_num = min(ph_num + 1, 8)   # confirmed done → next is active
                elif elapsed >= starts_at and phases_done < ph_num:
                    active_phase_num = ph_num                # time-estimated

            # Clamp to max 8
            active_phase_num = min(active_phase_num, 8)

            # Pick the contextual message for the active phase
            active_label  = f"Phase {active_phase_num}"
            active_detail = "AI agents working in sequence…"
            for (ph_num, _starts, label, detail) in timeline:
                if ph_num == active_phase_num:
                    active_label  = label
                    active_detail = detail
                    break

            # Progress bar — smooth from 0 to 100 over expected total duration
            total_expected = timeline[-1][1] + 15   # last phase start + ~15s to finish
            elapsed_pct    = min(elapsed / total_expected, 0.97) if poll_status == "running" else 1.0
            # Snap forward if DynamoDB confirms more phases done than time would suggest
            confirmed_pct  = max(0, phases_done - 3) / 5
            progress_pct   = max(elapsed_pct, confirmed_pct)

            mins, secs     = divmod(elapsed, 60)
            elapsed_str    = f"{mins}m {secs}s" if mins else f"{secs}s"
            remaining      = max(0, total_expected - elapsed)

            with st.chat_message("assistant"):
                st.markdown(f"### ⚙️ Phases 4–8 — AI agents running")

                if poll_status == "running":
                    st.info(f"**{active_label}**\n\n{active_detail}")
                    st.progress(
                        max(progress_pct, 0.03),
                        text=(
                            f"Elapsed: **{elapsed_str}**"
                            + (f" · ~{remaining}s remaining" if remaining > 5 else " · almost done…")
                            + f" · {phases_done}/8 phases confirmed"
                        ),
                    )
                elif _is_done(poll_status):
                    st.success("🎉 All 8 phases complete!")
                elif poll_status == "error":
                    st.error(f"❌ Error: {poll.get('error', 'Unknown')}")

                # Phase grid — two clean rows of 4
                st.markdown("---")
                row1_cols = st.columns(4)
                row2_cols = st.columns(4)
                all_cols  = row1_cols + row2_cols

                for ph in PHASES:
                    num  = ph["num"]
                    name = ph["name"]
                    col  = all_cols[num - 1]
                    if num <= phases_done:
                        col.success(f"✅ {num}. {name}")
                    elif num == active_phase_num and poll_status == "running":
                        col.info(f"🔵 {num}. {name}")
                    elif num < active_phase_num:
                        # Time-estimated as done but not yet DynamoDB-confirmed
                        col.success(f"✅~ {num}. {name}")
                    else:
                        col.caption(f"⬜ {num}. {name}")

            if _is_done(poll_status):
                # Fetch full result now that Lambda is done
                full = _invoke(HARNESS_FN, _build_harness_payload(
                    agent_cfg, customer_id, customer_name, product, sow_ref, agent_id,
                    run_id=run_id, action="get_status",
                ))
                pr_full = full.get("phase_results", {})
                p8      = pr_full.get("phase8", {})
                completed_result = {
                    "status":              poll_status,   # preserve completed_with_gaps
                    "engagement_id":       customer_id,
                    "run_id":              run_id,
                    "total_latency_ms":    full.get("total_latency_ms", 0),
                    "phases_completed":    8,
                    "phase_results":       pr_full,
                    "report_s3_key":       p8.get("report_html_s3_key", p8.get("report_s3_key", "")),
                    "report_download_url": p8.get("report_download_url", full.get("report_download_url", "")),
                }
                st.session_state.harness_result  = completed_result
                st.session_state.phase3_answered = True
                st.session_state.harness_polling = False
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": _completion_message(completed_result, agent_cfg["id"]),
                })
                st.rerun()

            elif poll_status == "error":
                st.session_state.harness_polling  = False
                st.session_state.phase3_answered  = True
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"❌ Harness error: {poll.get('error', 'Unknown failure')}",
                })
                st.rerun()

            else:
                # Still running — auto-refresh every 3 seconds
                time.sleep(3)
                st.rerun()

        # ── Stage 5: Harness complete — post-harness chat ──────────────
        elif _is_done(st.session_state.harness_result.get("status", "")):
            result   = st.session_state.harness_result
            p8       = result.get("phase_results", {}).get("phase8", {})
            s3_key   = p8.get("report_s3_key", "")
            presign  = p8.get("report_download_url", "")

            report_bytes  = _fetch_report_bytes(s3_key, WIKI_BUCKET) if s3_key else None
            date_str      = datetime.now().strftime("%Y%m%d")
            report_kind   = "rca-report" if agent_cfg["id"] == "pm" else "handoff-report"
            report_label  = "📄 Download RCA Report" if agent_cfg["id"] == "pm" else "📄 Download Handoff Report"
            html_name     = f"{customer_id}-{report_kind}-{date_str}.html"

            if report_bytes:
                st.download_button(
                    label=report_label,
                    data=report_bytes,
                    file_name=html_name,
                    mime="text/html",
                    type="primary",
                )
            elif presign:
                st.markdown(
                    f'<a href="{presign}" target="_blank" style="'
                    'display:inline-block;background:#1a6bbd;color:white;padding:8px 20px;'
                    'border-radius:6px;text-decoration:none;font-weight:600;font-size:0.95em">'
                    f'{report_label}</a>',
                    unsafe_allow_html=True,
                )
            elif s3_key:
                st.caption(f"Report available at: `{s3_key}`")

            if agent_cfg["id"] == "pm":
                st.info(
                    "💡 **Post-harness:** Ask a follow-up question about the RCA — "
                    "e.g. *'What is the root cause?'*, *'What knowledge gaps were found?'*, "
                    "*'What should the KEDB entry say?'*"
                )
            else:
                st.info(
                    "💡 **Post-harness:** Ask a follow-up question about the engagement — "
                    "e.g. *'What are the top 3 risks?'*, *'Who should own the data migration?'*, "
                    "*'What gaps need to be filled before go-live?'*"
                )

            follow_up = st.chat_input(agent_cfg["followup_placeholder"])
            if follow_up:
                st.session_state.chat_messages.append({"role": "user", "content": follow_up})
                pr      = result.get("phase_results", {})
                context = json.dumps(pr, default=str)[:3000]
                answer  = _post_harness_answer(follow_up, context, customer_name, product, agent_cfg["id"])
                st.session_state.chat_messages.append({"role": "assistant", "content": answer})
                st.rerun()


    # ══════════════════════════════════════════════════════════════════
    # RIGHT — Locked Plan Panel
    # ══════════════════════════════════════════════════════════════════
    with col_plan:
        st.markdown('<div class="lock-badge">🔒 LOCKED PLAN — System Enforced</div>',
                    unsafe_allow_html=True)
        st.caption("The agent executes within each phase. It cannot skip, reorder, or bypass phases.")

        # ── Workflow Spec viewer ───────────────────────────────────────
        wf_spec_file = HARNESS_SPEC_FILES.get(agent_cfg["id"])
        wf_spec_md   = _read_spec(wf_spec_file) if wf_spec_file else ""
        if wf_spec_md:
            # Download button always visible — outside the expander
            _wf_hdr, _wf_dl = st.columns([5, 1])
            with _wf_hdr:
                _wf_exp = st.expander("📋 Workflow Spec — how this harness is orchestrated", expanded=False)
            with _wf_dl:
                st.download_button(
                    label="⬇️ .md",
                    data=wf_spec_md.encode("utf-8"),
                    file_name=wf_spec_file,
                    mime="text/markdown",
                    key=f"dl_wf_spec_{agent_cfg['id']}",
                    help=f"Download {wf_spec_file} — adapt for a new use case.",
                    use_container_width=True,
                )

            with _wf_exp:
                st.caption(
                    "Business-authored spec. Defines every phase, the skill called, inputs, outputs, "
                    "and rules. The harness Lambda is the executable version of this document."
                )

                # Get all skill IDs referenced by this workflow's phases
                workflow_skill_ids = sorted({ph["skill"] for ph in PHASES if ph.get("skill")})

                # Tabs: full workflow + per-skill drill-down
                sk_labels = []
                for sid in workflow_skill_ids:
                    ph_meta = next((ph for ph in PHASES if ph["skill"] == sid), {})
                    sk_labels.append(f"{ph_meta.get('icon','')} {sid}")
                wf_tabs = st.tabs(["📋 Full Workflow"] + sk_labels)

                with wf_tabs[0]:
                    _render_spec(wf_spec_md)

                for tab_idx, sid in enumerate(workflow_skill_ids, start=1):
                    with wf_tabs[tab_idx]:
                        sk_spec_file = SKILL_SPEC_FILES.get(sid)
                        sk_spec_md   = _read_spec(sk_spec_file) if sk_spec_file else ""
                        ph_meta = next((ph for ph in PHASES if ph["skill"] == sid), {})
                        if sk_spec_md:
                            # Skill download button above the spec content
                            _sk_hdr2, _sk_dl2 = st.columns([5, 1])
                            with _sk_hdr2:
                                st.caption(
                                    f"Phase {ph_meta.get('num','?')}: **{ph_meta.get('name','')}** "
                                    "calls this skill."
                                )
                            with _sk_dl2:
                                st.download_button(
                                    label="⬇️ .md",
                                    data=sk_spec_md.encode("utf-8"),
                                    file_name=sk_spec_file,
                                    mime="text/markdown",
                                    key=f"dl_sk_spec_{sid}_harness",
                                    help=f"Download {sk_spec_file}",
                                    use_container_width=True,
                                )
                            _render_spec(sk_spec_md, compact=True)
                        else:
                            st.info(f"Skill spec for `{sid}` not yet authored.")

        harness_result = st.session_state.get("harness_result", {})
        pr = harness_result.get("phase_results", {})

        for ph in PHASES:
            state      = _phase_state(harness_result, ph["num"])
            icon       = _phase_icon(state)
            summary    = _phase_summary(harness_result, ph["num"], agent_cfg["id"])
            skill      = f" · **{ph['skill']}**" if ph["skill"] else ""
            phase_data = pr.get(f"phase{ph['num']}", {})

            with st.expander(
                f"{icon} Phase {ph['num']}: {ph['icon']} {ph['name']}"
                + (f" — _{summary}_" if summary and state == "complete" else ""),
                expanded=(state in ("running", "paused", "error")),
            ):
                c1, c2 = st.columns(2)
                c1.caption(f"Type: `{ph['type']}`")
                c2.caption(f"Skill: `{ph['skill'] or 'built-in'}`")

                if state == "pending":
                    st.caption("⬜ Waiting for prior phases to complete")

                elif state == "running":
                    st.info("🔵 Running now...")
                    if ph["type"] == "llm_batch_agents":
                        st.progress(0.3, text="Spawning sub-agents...")

                elif state == "paused":
                    st.warning("⏸️ Waiting for your input in the conversation panel ←")

                elif state == "error":
                    st.error(f"❌ {harness_result.get('error', 'Phase failed')}")

                elif state == "complete" and phase_data:
                    if ph["num"] == 1:
                        if agent_cfg["id"] == "pm":
                            st.metric("Records Loaded", phase_data.get("records_loaded", phase_data.get("pages_found", 0)))
                            st.metric("Problem ID", phase_data.get("problem_id", "—"))
                            if phase_data.get("related_records"):
                                st.caption(f"Related records: {len(phase_data['related_records'])}")
                        else:
                            st.metric("Customer Status", phase_data.get("customer_status", "—"))
                            st.metric("Pages Found", phase_data.get("pages_found", 0))
                            if phase_data.get("key_facts"):
                                st.markdown("**Key facts:**")
                                for fact in phase_data["key_facts"][:3]:
                                    st.markdown(f"- {fact}")

                    elif ph["num"] == 2:
                        if agent_cfg["id"] == "pm":
                            cols = st.columns(3)
                            cols[0].metric("Category",    phase_data.get("normalized_category", phase_data.get("category", "—")))
                            cols[1].metric("Risk Tier",   phase_data.get("risk_tier", "—"))
                            cols[2].metric("Recurrence",  phase_data.get("recurrence_type", "—"))
                            if phase_data.get("classification_confidence"):
                                st.caption(f"Confidence: {phase_data['classification_confidence']}")
                            if phase_data.get("alert_sent"):
                                st.warning("⚠️ High-severity SNS alert sent")
                        else:
                            cols = st.columns(3)
                            cols[0].metric("Risk Tier",  phase_data.get("risk_tier", "—"))
                            cols[1].metric("Urgency",    phase_data.get("go_live_urgency", "—"))
                            cols[2].metric("Complexity", phase_data.get("implementation_complexity", "—"))
                            if phase_data.get("rationale"):
                                st.caption(phase_data["rationale"][:250])

                    elif ph["num"] == 3:
                        if phase_data.get("context_provided"):
                            st.success("Human context captured")
                            st.caption(phase_data.get("summary", "")[:250])

                    elif ph["num"] == 4:
                        if agent_cfg["id"] == "pm":
                            cols = st.columns(3)
                            kb_count  = phase_data.get("kb_passages_count", len(phase_data.get("kb_passages", [])))
                            rca_count = phase_data.get("prior_rcas_count",  len(phase_data.get("prior_rcas", [])))
                            conf      = phase_data.get("prior_knowledge_confidence", "—")
                            cols[0].metric("KB Passages",   kb_count,  help="Semantic matches from PM Bedrock KB")
                            cols[1].metric("Prior RCAs",    rca_count, help="Matching wiki RCA pages (SK-01)")
                            cols[2].metric("KB Confidence", conf)
                            if kb_count > 0:
                                st.success(f"🔍 Semantic KB returned {kb_count} relevant passages — cross-system patterns will be analysed")
                            else:
                                st.warning("KB retrieval returned no results — RCA will rely on SME context only")
                        else:
                            cols = st.columns(2)
                            cols[0].metric("Playbook Steps", phase_data.get("playbook_steps", 0))
                            cols[1].metric("Pages Loaded",   phase_data.get("pages_loaded", 0))

                    elif ph["num"] == 5:
                        if agent_cfg["id"] == "pm":
                            conf      = phase_data.get("rca_confidence", phase_data.get("confidence", "—"))
                        else:
                            conf      = phase_data.get("confidence", "—")
                        badge_map = {"high": "🟢", "medium": "🟡", "low": "🔴"}
                        st.metric("Confidence", f"{badge_map.get(conf,'⚪')} {conf.upper()}")
                        if agent_cfg["id"] == "pm":
                            root_cause = phase_data.get("root_cause_statement", phase_data.get("root_cause", ""))
                            if root_cause:
                                st.markdown("**Root cause:**")
                                st.caption(root_cause[:400])
                            if phase_data.get("pattern_detected"):
                                linked = ", ".join(phase_data.get("linked_problem_ids", []))
                                st.warning(f"🔁 **Cross-system recurrence detected** — linked to: {linked or 'prior incidents'}")
                            kb_cits = phase_data.get("kb_citations", [])
                            if kb_cits:
                                st.caption(f"KB citations used: {', '.join(kb_cits)}")
                            items = phase_data.get("contributing_factors", phase_data.get("action_items", []))
                        else:
                            st.metric("Wiki Pages", phase_data.get("wiki_page_count", 0))
                            items = phase_data.get("action_items", [])
                        if items:
                            st.markdown("**Action items:**" if agent_cfg["id"] != "pm" else "**Contributing factors:**")
                            for item in items[:3]:
                                st.markdown(f"- {item}")

                    elif ph["num"] == 6:
                        if phase_data.get("skipped"):
                            st.success("Skipped — wiki answered with high confidence")
                        else:
                            cols = st.columns(3)
                            cols[0].metric("Gaps",       phase_data.get("gap_count", 0))
                            cols[1].metric("Blocking",   phase_data.get("blocking_count", 0))
                            cols[2].metric("Agents Run", phase_data.get("sub_agents_run", 0))
                            for g in phase_data.get("gaps", [])[:3]:
                                badge = "🚨" if g.get("blocking") else "⚠️"
                                st.markdown(f"{badge} {g.get('title','Gap')} — `{g.get('gap_type','')}`")

                    elif ph["num"] == 7:
                        found = phase_data.get("found", False)
                        pct   = phase_data.get("completion_pct", 0)
                        st.metric("Template Found", "✅" if found else "⚠️ Not found")
                        if found:
                            st.metric("Fill %", f"{pct}%")
                            st.progress(min(pct / 100, 1.0))
                            populated = phase_data.get("populated_fields", [])
                            missing   = phase_data.get("missing_fields", [])
                            if populated:
                                st.caption(f"Filled: {', '.join(populated[:4])}")
                            if missing:
                                st.caption(f"Missing: {', '.join(str(m)[:30] for m in missing[:3])}")

                    elif ph["num"] == 8:
                        indexed = phase_data.get("indexed", False)
                        label = "RCA Draft Saved" if agent_cfg["id"] == "pm" else "Wiki Indexed"
                        st.metric(label, "✅" if indexed else "⚠️ Pending")
                        s3_uri = phase_data.get("s3_uri", "")
                        if s3_uri:
                            st.caption(f"`{s3_uri}`")
                        rkey    = phase_data.get("report_s3_key", "")
                        presign = phase_data.get("report_download_url", "")
                        if rkey:
                            rbytes = _fetch_report_bytes(rkey, WIKI_BUCKET)
                            fname  = rkey.split("/")[-1]
                            if rbytes:
                                st.download_button(
                                    "📄 Download Report",
                                    data=rbytes,
                                    file_name=fname,
                                    mime="text/html",
                                    key=f"dl_phase8_{ph['num']}",
                                )
                            elif presign:
                                st.markdown(
                                    f'<a href="{presign}" target="_blank" style="'
                                    'display:inline-block;background:#1a6bbd;color:white;'
                                    'padding:6px 14px;border-radius:5px;text-decoration:none;'
                                    'font-size:0.88em;font-weight:600">📄 Download Report</a>',
                                    unsafe_allow_html=True,
                                )

        # ── Telemetry summary ──────────────────────────────────────────
        if harness_result:
            st.divider()
            st.subheader("📊 Telemetry")
            tel = _telemetry(harness_result)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Phases Done", f"{tel['phases_done']}/8")
            c2.metric("Skills Used", tel["skills"])
            c3.metric("Gaps Logged", tel["gaps"])
            c4.metric("Total ms",    f"{int(tel['latency'] or 0):,}")

            with st.expander("🔬 Full harness JSON"):
                st.json(harness_result)

        # ── Prior Runs ─────────────────────────────────────────────────
        st.divider()
        st.subheader("📋 Prior Runs")
        prior_runs = _list_runs(customer_id)
        if not prior_runs:
            st.caption("No prior runs found for this customer ID.")
        else:
            for run in prior_runs:
                run_id_r   = run.get("run_id", "")
                status_r   = run.get("status", "unknown")
                started_r  = run.get("started_at", "")[:16].replace("T", " ")
                phases_r   = run.get("current_phase", "—")
                latency_r  = int(run.get("total_latency_ms") or 0)
                pr_r       = _parse_if_str(run.get("phase_results", {}))
                rkey       = pr_r.get("phase8", {}).get("report_s3_key", "")
                status_icon = {"completed": "✅", "completed_with_gaps": "✅", "paused": "⏸️", "running": "🔵", "error": "❌"}.get(status_r, "⬜")

                with st.expander(
                    f"{status_icon} {started_r} UTC — `{run_id_r}`",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Status",   status_r.upper())
                    c2.metric("Phase",    f"{phases_r}/8")
                    c3.metric("Time",     f"{latency_r:,}ms" if latency_r else "—")

                    if _is_done(status_r) and rkey:
                        rbytes  = _fetch_report_bytes(rkey, WIKI_BUCKET)
                        fname   = rkey.split("/")[-1]
                        presign = pr_r.get("phase8", {}).get("report_download_url", "")
                        if rbytes:
                            st.download_button(
                                label="📄 Download Report",
                                data=rbytes,
                                file_name=fname,
                                mime="text/html" if fname.endswith(".html") else "text/plain",
                                key=f"dl_prior_{run_id_r}",
                                type="primary",
                            )
                        elif presign:
                            st.markdown(
                                f'<a href="{presign}" target="_blank" style="'
                                'display:inline-block;background:#1a6bbd;color:white;'
                                'padding:6px 14px;border-radius:5px;text-decoration:none;'
                                'font-size:0.88em;font-weight:600">📄 Download Report</a>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.caption("Report not yet available.")
                    elif status_r == "paused":
                        st.info("This run is paused at Phase 3 — click **Start Harness** to resume.")
                    elif status_r == "running":
                        st.info("This run is currently executing.")

        # ── Explainer ──────────────────────────────────────────────────
        with st.expander("ℹ️ Why is this better than a chatbot?"):
            st.markdown("""
    **The agent cannot skip or reorder these phases** — they are enforced by the system, not by prompting the LLM to "please do step 4 next."

    | Chatbot approach | Hard Harness approach |
    |---|---|
    | LLM decides what to do | System enforces what to do |
    | Can skip due diligence | Every phase must complete before next starts |
    | Declares victory whenever it wants | Deliverable only accepted after verification |
    | No human input at the right moment | Phase 3 pauses *after* classification — asks informed questions |
    | Output is text in chat | Output is indexed wiki page + downloadable report |

    **Stripe Minions** (1,000+ PRs/week), **Anthropic research**, and **AI Automators Ep 6** all converge on this pattern: *the model is commoditised — structured enforcement of process is the moat.*
            """)
