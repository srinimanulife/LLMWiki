"""
LLMWiki — Neuro SAN Studio
Top-level use-case selector governs all three tabs.
  Tab 1 (Live Demo Toggle): hot-swap NLP variant for agents in the selected use case
  Tab 2 (Agent Chat):       WebSocket streaming chat with the selected use case's network
  Tab 3 (Before vs After):  Hard Harness vs Neuro SAN comparison for the selected use case
"""
import asyncio
import difflib
import json
import os
import queue as _queue
import re
import threading
import time
import uuid

import boto3
import requests
import streamlit as st
import websockets

# ── Import demo variants ───────────────────────────────────────────
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from demo_variants import DEMO_VARIANTS
except ImportError:
    DEMO_VARIANTS = {}

# ── Configuration ──────────────────────────────────────────────────
_AWS_REGION       = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
_WIKI_BUCKET      = os.environ.get("WIKI_BUCKET", "")
_NSFLOW_LOCAL_URL = os.environ.get("NSFLOW_LOCAL_URL", "http://localhost:4173")

# ── Use-case definitions ───────────────────────────────────────────
# Each use case maps to one neuro-san network and a subset of demo-variant agents.
_USE_CASES = {
    "UC1 — Sales to Service": {
        "network":        "uc1_sales_to_service",
        "s3_key":         "neuro-san/registries/llmwiki/uc1_sales_to_service.hocon",
        "local_hocon":    "registries/llmwiki/uc1_sales_to_service.hocon",
        "agent_variants": [
            "UC1 FrontMan (Sales-to-Service)",
            "ContextBootstrap (SK-01)",
            "WikiQuery (SK-02)",
            "GapDetection (SK-05)",
            "ArtifactResolution (SK-04)",
            "WikiContribute (SK-03)",
        ],
        "sample_prompts": [
            "Run UC1 for customer bcbs-mn-001 on TriZetto QNXT SOW-2026-BCBS-MN-001",
            "What are the delivery risks for a new BlueCross MN QNXT implementation?",
            "Create the handoff brief for engagement bcbs-mn-001",
        ],
        "compare_hard_harness": {
            "title": "Hard Harness (Production)",
            "phases": [
                "Phase 1 — SK-01 ContextBootstrap",
                "Phase 2 — SK-02 WikiQuery",
                "Phase 3 — HITL pause if confidence < high",
                "Phase 4 — SK-05 GapDetection if gaps exist",
                "Phase 5 — SK-04 ArtifactResolution",
                "Phase 6 — compose handoff brief (Python)",
                "Phase 7 — SK-03 WikiContribute",
                "Phase 8 — return result",
            ],
            "change_cost": "Edit Python → PR → CI/CD → Lambda redeploy (~30 min)",
            "loc": "~425 lines of orchestration code",
        },
        "compare_neuro_san": {
            "neuro_description": "FrontMan reads NLP instructions, runs full AAOSA Determine → Fulfill → Compile.",
            "change_cost": "Edit text → click Deploy → live in **~5 s**",
            "loc": "~5 NLP instruction blocks",
            "demo_wow": "toggle between 'Full AAOSA Protocol' ↔ 'Executive Fast-Track'",
        },
        "skills_table": {
            "Skill":       ["SK-01", "SK-02", "SK-03", "SK-04", "SK-05"],
            "Lambda": [
                "llmwiki-skill-context-bootstrap",
                "llmwiki-skill-wiki-query",
                "llmwiki-skill-wiki-contribute",
                "llmwiki-skill-artifact-resolution",
                "llmwiki-skill-gap-detection",
            ],
            "Hard Harness": ["Phase 1", "Phase 2", "Phase 7", "Phase 5", "Phase 4"],
            "Neuro SAN":    ["ContextBootstrap", "WikiQuery", "WikiContribute", "ArtifactResolution", "GapDetection"],
        },
    },
    "UC-PM — Problem Management": {
        "network":        "uc_pm_problem_management",
        "s3_key":         "neuro-san/registries/llmwiki/uc_pm_problem_management.hocon",
        "local_hocon":    "registries/llmwiki/uc_pm_problem_management.hocon",
        "agent_variants": [
            "PM FrontMan (Problem Management)",
            "ProblemClassifier (SK-06)",
        ],
        "sample_prompts": [
            "Run RCA for problem PRB0042 on QNXT Batch Processing severity P2",
            "Classify and analyse problem PRB0099 on Facets Integration component",
            "Create RCA draft for problem bcbs-mn-p001 QNXT Eligibility severity P1",
        ],
        "compare_hard_harness": {
            "title": "Hard Harness (Lambda Harness)",
            "phases": [
                "Phase 1 — SK-06 ProblemClassifier",
                "Phase 2 — SK-01 ContextBootstrap",
                "Phase 3 — HITL pause for SME questions (always)",
                "Phase 4 — SK-02 WikiQuery",
                "Phase 5 — SK-05 GapDetection if confidence < high",
                "Phase 6 — SK-04 ArtifactResolution (rca-template)",
                "Phase 7 — SK-03 WikiContribute → DRAFT to review queue",
                "Phase 8 — return RCA draft",
            ],
            "change_cost": "Edit Python → PR → CI/CD → Lambda redeploy (~30 min)",
            "loc": "~380 lines of orchestration code",
        },
        "compare_neuro_san": {
            "neuro_description": "PMFrontMan runs AAOSA: classify first → SME Q&A turn → wiki search → draft RCA → save DRAFT.",
            "change_cost": "Edit text → click Deploy → live in **~5 s**",
            "loc": "~5 NLP instruction blocks",
            "demo_wow": "toggle between 'Full RCA Protocol' ↔ 'Quick Triage Mode'",
        },
        "skills_table": {
            "Skill":    ["SK-01", "SK-02", "SK-03", "SK-04", "SK-05", "SK-06"],
            "Lambda": [
                "llmwiki-skill-context-bootstrap",
                "llmwiki-skill-wiki-query",
                "llmwiki-skill-wiki-contribute",
                "llmwiki-skill-artifact-resolution",
                "llmwiki-skill-gap-detection",
                "llmwiki-skill-problem-classifier",
            ],
            "Hard Harness": ["Phase 2", "Phase 4", "Phase 7", "Phase 6", "Phase 5", "Phase 1"],
            "Neuro SAN":    ["ContextBootstrap", "WikiQuery", "WikiContribute", "ArtifactResolution", "GapDetection", "ProblemClassifier"],
        },
    },
}

# Agent display-name → HOCON block name
_AGENT_BLOCK = {
    "UC1 FrontMan (Sales-to-Service)":  "UC1SalesToServiceAgent",
    "ContextBootstrap (SK-01)":         "ContextBootstrap",
    "WikiQuery (SK-02)":                "WikiQuery",
    "GapDetection (SK-05)":             "GapDetection",
    "ArtifactResolution (SK-04)":       "ArtifactResolution",
    "WikiContribute (SK-03)":           "WikiContribute",
    "PM FrontMan (Problem Management)": "UCPMProblemManagementAgent",
    "ProblemClassifier (SK-06)":        "ProblemClassifier",
}

# ── S3 helpers ─────────────────────────────────────────────────────
def _s3():
    return boto3.client("s3", region_name=_AWS_REGION)

def _load_hocon(uc_cfg: dict) -> tuple[str, str]:
    """Return (content, source_label). Prefers S3, falls back to local."""
    if _WIKI_BUCKET:
        try:
            resp = _s3().get_object(Bucket=_WIKI_BUCKET, Key=uc_cfg["s3_key"])
            return resp["Body"].read().decode("utf-8"), "📡 S3 (live)"
        except Exception:
            pass
    try:
        with open(uc_cfg["local_hocon"]) as f:
            return f.read(), "📦 local (bundled)"
    except FileNotFoundError:
        return "# HOCON not found", "❌ not found"

def _save_hocon(content: str, uc_cfg: dict) -> bool:
    if not _WIKI_BUCKET:
        return False
    try:
        _s3().put_object(
            Bucket=_WIKI_BUCKET, Key=uc_cfg["s3_key"],
            Body=content.encode("utf-8"), ContentType="text/plain",
        )
        return True
    except Exception as e:
        st.error(f"S3 save failed: {e}")
        return False

# ── HOCON instruction extractor/replacer ──────────────────────────
def _extract(hocon: str, agent_block: str) -> tuple[str, str, str]:
    name_m = re.search(rf'"name"\s*:\s*"{re.escape(agent_block)}"', hocon)
    if not name_m:
        return "", hocon, ""
    instr_m = re.search(r'"instructions"\s*:\s*"""(.*?)"""', hocon[name_m.end():], re.DOTALL)
    if not instr_m:
        return "", hocon, ""
    abs_s = name_m.end() + instr_m.start(1)
    abs_e = name_m.end() + instr_m.end(1)
    return hocon[:abs_s], hocon[abs_s:abs_e].strip(), hocon[abs_e:]

def _replace(hocon: str, agent_block: str, new_instructions: str) -> str:
    name_m = re.search(rf'"name"\s*:\s*"{re.escape(agent_block)}"', hocon)
    if not name_m:
        return hocon
    instr_m = re.search(r'("instructions"\s*:\s*""")(.*?)(""")', hocon[name_m.end():], re.DOTALL)
    if not instr_m:
        return hocon
    offset = name_m.end()
    abs_s = offset + instr_m.start(2)
    abs_e = offset + instr_m.end(2)
    return hocon[:abs_s] + "\n" + new_instructions + "\n" + hocon[abs_e:]

# ── Diff HTML renderer ─────────────────────────────────────────────
def _diff_html(old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    differ = difflib.SequenceMatcher(None, old_lines, new_lines)
    html_parts = [
        "<div style='font-family:monospace;font-size:13px;"
        "border:1px solid #444;border-radius:6px;"
        "max-height:420px;overflow-y:auto;padding:8px;'>"
    ]
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(
                    f"<div style='padding:1px 4px;color:#ccc;'>{escaped or '&nbsp;'}</div>"
                )
        elif tag in ("replace", "delete"):
            for line in old_lines[i1:i2]:
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(
                    f"<div style='padding:1px 4px;background:#3d0000;color:#ff8080;"
                    f"text-decoration:line-through;'>"
                    f"<span style='color:#ff4444;margin-right:6px;'>−</span>{escaped or '&nbsp;'}</div>"
                )
            if tag == "replace":
                for line in new_lines[j1:j2]:
                    escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_parts.append(
                        f"<div style='padding:1px 4px;background:#003d00;color:#88ff88;'>"
                        f"<span style='color:#44ff44;margin-right:6px;'>+</span>{escaped or '&nbsp;'}</div>"
                    )
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(
                    f"<div style='padding:1px 4px;background:#003d00;color:#88ff88;'>"
                    f"<span style='color:#44ff44;margin-right:6px;'>+</span>{escaped or '&nbsp;'}</div>"
                )
    html_parts.append("</div>")
    return "".join(html_parts)

# ── nsflow helpers ─────────────────────────────────────────────────
_WS_URL = _NSFLOW_LOCAL_URL.replace("http://", "ws://").replace("https://", "wss://")

def _nsflow_healthy() -> bool:
    try:
        return requests.get(f"{_NSFLOW_LOCAL_URL}/api/v1/networks/", timeout=3).status_code == 200
    except Exception:
        return False

def _list_networks() -> list:
    try:
        r = requests.get(f"{_NSFLOW_LOCAL_URL}/api/v1/networks/", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("networks", list(data.keys()))
    except Exception:
        pass
    return ["uc1_sales_to_service", "uc_pm_problem_management"]


class _AgentSession:
    """
    Persistent WebSocket session for one agent network.
    Keeps a single WS connection alive across multiple Streamlit chat turns
    so the agent can ask follow-up questions (HUMAN-type messages).
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.session_id = uuid.uuid4().hex
        self._send_q: _queue.Queue = _queue.Queue()
        self._recv_q: _queue.Queue = _queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def send(self, message: str):
        self._send_q.put(message)

    def recv_stream(self, placeholder, timeout: int = 600) -> tuple[str, bool]:
        accumulated: list[str] = []
        deadline = time.time() + timeout
        waiting_for_human = False
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                accumulated.append("\n\n⚠️ No response after 600 s — the agent may still be running.")
                break
            try:
                item = self._recv_q.get(timeout=min(remaining, 1.0))
            except _queue.Empty:
                continue
            kind = item.get("kind")
            if kind == "text":
                accumulated.append(item["text"])
                placeholder.markdown("\n\n---\n\n".join(accumulated) + "\n\n▌")
            elif kind == "turn_end":
                waiting_for_human = item.get("waiting_for_human", False)
                break
            elif kind == "error":
                accumulated.append(f"⚠️ {item['text']}")
                break
        final = "\n\n---\n\n".join(accumulated)
        placeholder.markdown(final)
        return final, waiting_for_human

    def close(self):
        self._send_q.put(None)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        ws_uri = f"{_WS_URL}/api/v1/ws/chat/{self.agent_name}/{self.session_id}"
        try:
            async with websockets.connect(ws_uri, open_timeout=15, ping_interval=60, ping_timeout=120) as ws:
                while True:
                    msg = await self._loop.run_in_executor(None, self._send_q.get)
                    if msg is None:
                        break
                    await ws.send(json.dumps({"message": msg, "sly_data": {}, "chat_context": {}}))
                    waiting_for_human = False
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=600)
                        except asyncio.TimeoutError:
                            self._recv_q.put({"kind": "error", "text": "Agent timed out after 600 s."})
                            break
                        except websockets.exceptions.ConnectionClosed:
                            self._recv_q.put({"kind": "error", "text": "WebSocket connection closed."})
                            return
                        data = json.loads(raw)
                        msg_obj = data.get("message", {})
                        if not isinstance(msg_obj, dict):
                            break
                        text = msg_obj.get("text", "")
                        if text:
                            self._recv_q.put({"kind": "text", "text": text})
                        msg_type = msg_obj.get("type", "")
                        if msg_type == "HUMAN":
                            waiting_for_human = True
                            break
                        if msg_type == "AI":
                            try:
                                extra = await asyncio.wait_for(ws.recv(), timeout=1.5)
                                extra_obj = json.loads(extra).get("message", {})
                                extra_text = extra_obj.get("text", "")
                                if extra_text:
                                    self._recv_q.put({"kind": "text", "text": extra_text})
                            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                                pass
                            break
                    self._recv_q.put({"kind": "turn_end", "waiting_for_human": waiting_for_human})
        except Exception as e:
            self._recv_q.put({"kind": "error", "text": f"Connection error: {e}"})


def _get_or_create_session(agent_name: str) -> "_AgentSession":
    key = f"_ns_session_{agent_name}"
    existing: "_AgentSession | None" = st.session_state.get(key)
    if existing is None or not existing._thread.is_alive():
        if existing is not None:
            existing.close()
        session = _AgentSession(agent_name)
        st.session_state[key] = session
    return st.session_state[key]


# ══════════════════════════════════════════════════════════════════
# PAGE SETUP
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Neuro SAN Studio | LLMWiki",
    page_icon="🧠",
    layout="wide",
)

st.title("🧠 Neuro SAN Studio")
st.caption(
    "Hot-swap NLP instructions live — no code, no CI/CD, no restart. "
    "Changes propagate in **~5 seconds** via S3 sync."
)

# ── TOP-LEVEL USE CASE SELECTOR ─────────────────────────────────
st.markdown("---")
col_sel, col_info = st.columns([2, 5])
with col_sel:
    use_case_name = st.selectbox(
        "**Select use case**",
        options=list(_USE_CASES.keys()),
        key="selected_use_case",
        help="Governs all tabs: which agent network runs in Chat, which agents appear in Live Demo Toggle, and which comparison shows in Before vs After.",
    )

uc = _USE_CASES[use_case_name]
network_name = uc["network"]

with col_info:
    uc_badge_color = "#1a6b2e" if "UC1" in use_case_name else "#1a3f6b"
    st.markdown(
        f"<div style='padding:8px 16px;background:{uc_badge_color};border-radius:8px;"
        f"border-left:4px solid #fff;margin-top:4px;'>"
        f"<span style='font-size:15px;font-weight:700;color:#fff;'>{use_case_name}</span>"
        f"<span style='color:#ccc;font-size:13px;margin-left:12px;'>network: <code style='color:#adf'>{network_name}</code></span>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

tab_editor, tab_chat, tab_compare = st.tabs([
    "✏️ Live Demo Toggle",
    "💬 Agent Chat",
    "🔄 Before vs After",
])


# ══════════════════════════════════════════════════════════════════
# TAB 1 — Live Demo Toggle
# ══════════════════════════════════════════════════════════════════
with tab_editor:

    if not DEMO_VARIANTS:
        st.error("demo_variants.py not found. Ensure `streamlit/demo_variants.py` exists.")
        st.stop()

    # Restrict agent list to the selected use case
    uc_agent_names = uc["agent_variants"]

    selected_agent = st.selectbox(
        "**Select agent to hot-swap**",
        options=uc_agent_names,
        help="Only agents belonging to the selected use case are shown.",
    )
    meta       = DEMO_VARIANTS[selected_agent]
    block_name = _AGENT_BLOCK[selected_agent]
    hocon_cache_key  = f"hocon_cache_{network_name}"
    hocon_source_key = f"hocon_source_{network_name}"

    va_name = meta["version_a_name"]
    vb_name = meta["version_b_name"]
    va_desc = meta["version_a_desc"]
    vb_desc = meta["version_b_desc"]
    va_text = meta["version_a"]
    vb_text = meta["version_b"]

    # Load HOCON for this use case
    if st.session_state.get(hocon_cache_key) is None:
        with st.spinner("Loading live HOCON from S3…"):
            content, source = _load_hocon(uc)
            st.session_state[hocon_cache_key] = content
            st.session_state[hocon_source_key] = source

    hocon = st.session_state[hocon_cache_key]
    _, live_instructions, _ = _extract(hocon, block_name)

    live_is_a = (live_instructions.strip() == va_text.strip())
    live_is_b = (live_instructions.strip() == vb_text.strip())
    if live_is_a:
        live_label = va_name
        live_color = "#1a6b2e"
    elif live_is_b:
        live_label = vb_name
        live_color = "#1a3f6b"
    else:
        live_label = "🔧 Custom (manually edited)"
        live_color = "#5a3f00"

    st.markdown(
        f"<div style='padding:10px 16px;background:{live_color};border-radius:8px;"
        f"border-left:4px solid #fff;margin-bottom:16px;'>"
        f"<span style='font-size:16px;font-weight:700;color:#fff;'>🔴 LIVE NOW → {live_label}</span>"
        f"<span style='color:#ccc;font-size:13px;margin-left:16px;'>"
        f"Source: {st.session_state.get(hocon_source_key, '')}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    col_a, col_gap, col_b = st.columns([5, 1, 5])

    with col_a:
        border_a = "3px solid #2ea043" if live_is_a else "1px solid #444"
        st.markdown(
            f"<div style='border:{border_a};border-radius:10px;padding:12px 16px;"
            f"background:#0d1117;margin-bottom:8px;'>"
            f"<span style='font-size:20px;font-weight:800;color:#2ea043;'>{va_name}</span><br>"
            f"<span style='font-size:13px;color:#8b949e;'>{va_desc}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if live_is_a:
            st.success("✅ Currently live")
        else:
            if st.button(f"🚀 Deploy  {va_name}", key="deploy_a", type="primary", use_container_width=True):
                with st.spinner(f"Deploying {va_name}…"):
                    new_hocon = _replace(hocon, block_name, va_text)
                    if _save_hocon(new_hocon, uc):
                        st.session_state[hocon_cache_key] = new_hocon
                        time.sleep(0.3)
                        st.success(f"✅ **{va_name}** deployed!\nServer hot-reloads in ~5 s.")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("Save failed — check WIKI_BUCKET / S3 permissions.")

    with col_gap:
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:center;"
            "height:100%;font-size:28px;color:#555;padding-top:40px;'>⇄</div>",
            unsafe_allow_html=True,
        )

    with col_b:
        border_b = "3px solid #1f6feb" if live_is_b else "1px solid #444"
        st.markdown(
            f"<div style='border:{border_b};border-radius:10px;padding:12px 16px;"
            f"background:#0d1117;margin-bottom:8px;'>"
            f"<span style='font-size:20px;font-weight:800;color:#1f6feb;'>{vb_name}</span><br>"
            f"<span style='font-size:13px;color:#8b949e;'>{vb_desc}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if live_is_b:
            st.success("✅ Currently live")
        else:
            if st.button(f"🚀 Deploy  {vb_name}", key="deploy_b", type="primary", use_container_width=True):
                with st.spinner(f"Deploying {vb_name}…"):
                    new_hocon = _replace(hocon, block_name, vb_text)
                    if _save_hocon(new_hocon, uc):
                        st.session_state[hocon_cache_key] = new_hocon
                        time.sleep(0.3)
                        st.success(f"✅ **{vb_name}** deployed!\nServer hot-reloads in ~5 s.")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("Save failed — check WIKI_BUCKET / S3 permissions.")

    st.markdown("---")

    with st.expander("🔍 What changed — line-by-line diff", expanded=True):
        st.markdown(
            "<div style='font-size:12px;color:#8b949e;margin-bottom:6px;'>"
            "<span style='color:#ff4444;'>▬ removed</span>"
            " &nbsp;&nbsp; "
            "<span style='color:#44ff44;'>▬ added</span>"
            " &nbsp;&nbsp; unchanged shown in grey"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(_diff_html(va_text, vb_text), unsafe_allow_html=True)

    with st.expander("📋 View full instructions text"):
        subcol_a, subcol_b = st.columns(2)
        with subcol_a:
            st.markdown(f"**{va_name}**")
            st.code(va_text, language="text")
        with subcol_b:
            st.markdown(f"**{vb_name}**")
            st.code(vb_text, language="text")

    with st.expander("⚙️ How the hot-reload works"):
        st.markdown(
            f"""
            1. **Deploy button** → writes the new HOCON to
               `s3://{_WIKI_BUCKET or 'wiki-bucket'}/{uc['s3_key']}`
            2. **sync_registries.sh** (ECS sidecar) polls S3 every **3 seconds**
               and overwrites `/app/registries/`
            3. `AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=5` — neuro-san re-reads HOCON every 5 s
            4. **Total latency: ~8 seconds** from click to active

            No code change. No PR. No Lambda redeploy. No container restart.
            """
        )

    if st.button("🔄 Reload HOCON from S3", key="reload_hocon"):
        st.session_state[hocon_cache_key] = None
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 2 — Agent Chat
# ══════════════════════════════════════════════════════════════════
with tab_chat:
    st.subheader(f"Agent Chat — {use_case_name}")

    healthy = _nsflow_healthy()
    if healthy:
        st.success("✅ neuro-san sidecar ready")
    else:
        st.warning(
            "⏳ neuro-san sidecar not yet reachable — typically needs 60–90 s to start. "
            "Refresh to re-check, or send a message to try anyway."
        )

    # Show which network is active
    st.info(
        f"**Active network:** `{network_name}` — "
        f"change the **use case selector** at the top to switch agents.",
        icon="🔌",
    )

    # Suggested prompts for this use case
    st.markdown("**Suggested prompts:**")
    for p in uc["sample_prompts"]:
        st.markdown(f"- `{p}`")

    # ── Demo script (copy-paste answers) ──────────────────────────
    if "UC1" in use_case_name:
        with st.expander("📋 Demo script — copy-paste answers for UC1", expanded=False):
            st.markdown("**Step 1 — Opening prompt** (paste into chat input to start)")
            st.code(
                "Run UC1 for customer bcbs-mn-001 on TriZetto QNXT SOW-2026-BCBS-MN-001",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "The agent will load context and ask about delivery risks. "
                "When it asks **what specific QNXT risks you want explored**, paste:"
            )
            st.code(
                "Focus on eligibility processing and batch job reliability risks. "
                "The customer is new to QNXT — they are migrating from a legacy Facets platform "
                "and have aggressive go-live timeline of Q3 2026.",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "When the agent asks whether to **proceed with the full handoff brief** (Steps 4–6), paste:"
            )
            st.code(
                "Yes, proceed with the full handoff brief. "
                "Customer contact is Sarah Chen (VP IT, sarah.chen@bcbs-mn.org). "
                "Delivery lead assigned is Raj Patel. Priority rating is HIGH.",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "If the agent asks for **missing template fields** (ArtifactResolution completion < 70%), paste:"
            )
            st.code(
                "Contract value is 2.4M USD. Implementation start date is August 1 2026. "
                "Go-live date is October 31 2026. "
                "Key integration points: HIPAA 837/835 EDI, state Medicaid portal, "
                "and internal claims data warehouse.",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "**If GapDetection reports blocking gaps** — the agent will pause and list the gap IDs. "
                "Paste this answer for **Gap 1 — TriZetto QNXT ↔ Epic EHR Integration Architecture** "
                "(gap type: unknown-configuration):"
            )
            st.code(
                "BCBS-MN runs Epic 2024.2.1 on-premises at their Eden Prairie data center. "
                "The QNXT-to-Epic integration uses Epic Interconnect (HL7 FHIR R4) for real-time "
                "patient demographics and eligibility sync. "
                "BCBS-MN already has a Rhapsody interface engine managing 14 active HL7 interfaces "
                "in production — the QNXT-Epic bidirectional feed will route through Rhapsody. "
                "Epic team lead: Mark Thompson (mark.thompson@bcbs-mn.org). "
                "Authorization approvals flow via Epic MyChart to members; "
                "QNXT receives auth decisions via HL7 v2.x ADT notification feed. "
                "BCBS-MN has completed one prior QNXT integration for their Colorado subsidiary "
                "and the interface specs are documented and available.",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "Paste this answer for **Gap 2 — BCBS MN Legacy System Complexity & Data Migration Scope** "
                "(gap type: missing-customer-history):"
            )
            st.code(
                "BCBS-MN is migrating from Facets 5.2.1 (TriZetto hosted). "
                "Active member records: 3.2 million. "
                "Claims history migration scope: 18 months (January 2025 through June 2026). "
                "127 custom benefit configuration tables require mapping to QNXT benefit plan structures — "
                "the benefit config team lead has provided a draft crosswalk for 89 of the 127 tables. "
                "Parallel run period: 90 days minimum per contract SLA. "
                "Data migration will use TriZetto standard ETL toolkit with a BCBS-MN DBA on-site during cutover. "
                "Data quality assessment complete (ref: BCBS-MN-DQ-2026-03) — "
                "14,200 member records flagged with incomplete address data requiring remediation before go-live.",
                language="text",
            )

    else:
        with st.expander("📋 Demo script — copy-paste answers for UC-PM", expanded=False):
            st.markdown("**Step 1 — Opening prompt** (paste into chat input to start)")
            st.code(
                "Run RCA for problem PRB0042 on QNXT Batch Processing severity P2",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "The agent calls ProblemClassifier first (automatic). "
                "It then asks **SME questions** about the incident. "
                "When it asks about **observable symptom and timeline**, paste:"
            )
            st.code(
                "The nightly eligibility batch job QNXT_ELIG_NIGHTLY began hanging at the "
                "pre-adjudication validation phase at 02:14 AM ET on July 8. "
                "Jobs were not aborting — they remained in RUNNING status indefinitely with no progress. "
                "47 jobs were stuck. First alert fired at 03:00 AM when the SLA watchdog detected "
                "no completions after 45 minutes. Service was restored at 06:30 AM ET — "
                "total downtime approximately 4 hours 16 minutes.",
                language="text",
            )
            st.markdown("---")
            st.markdown("When the agent asks about **recent changes**, paste:")
            st.code(
                "On July 7 at 6:00 PM ET the QNXT database team applied schema migration DB-2241 "
                "which added two nullable columns to the member_eligibility table and updated "
                "three stored procedures used by the pre-adjudication validator. "
                "No code deployment was made to the batch processor. "
                "Migration was marked low-risk and was not flagged for batch regression testing.",
                language="text",
            )
            st.markdown("---")
            st.markdown("When the agent asks about **workarounds applied**, paste:")
            st.code(
                "On-call DBA manually killed the 47 stuck batch threads via the QNXT Job Control "
                "Console at 05:45 AM. The stored procedure was temporarily rolled back using "
                "DB-2241-rollback script. All 47 jobs requeued and completed by 06:30 AM. "
                "Workaround fully resolved the issue but required manual DBA intervention — "
                "no automatic retry fired because jobs were in RUNNING state not FAILED.",
                language="text",
            )
            st.markdown("---")
            st.markdown("When the agent asks about **impact scope**, paste:")
            st.code(
                "Claims Auto-Adjudication pipeline CAA-001 was blocked for 4+ hours — "
                "it depends on eligibility batch completion before starting. "
                "12,400 member eligibility records were not refreshed on schedule. "
                "Three payer clients affected: BCBS-MN, Aetna-CO, and Humana-TN. "
                "BCBS-MN SLA threshold is 08:00 AM ET which was not breached. "
                "However 2,100 claims missed same-day adjudication and pushed to next-day processing.",
                language="text",
            )
            st.markdown("---")
            st.markdown(
                "When the agent asks whether to **proceed with saving the RCA draft**, paste:"
            )
            st.code(
                "Yes, proceed. Save the RCA draft to the review queue. "
                "Assign review to the QNXT platform team lead.",
                language="text",
            )

    # Per-use-case session state
    chat_key    = f"ns_messages_{network_name}"
    waiting_key = f"ns_waiting_{network_name}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []
    if waiting_key not in st.session_state:
        st.session_state[waiting_key] = False

    # Render chat history
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state[waiting_key]:
        st.info(
            "💬 **The agent is waiting for your reply** — type your answer below and press Enter.",
            icon="🤖",
        )

    hint = "Reply to the agent…" if st.session_state[waiting_key] else "Ask the agent network…"

    if prompt := st.chat_input(hint, key="neuro_san_input"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        session = _get_or_create_session(network_name)
        session.send(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("⏳ *AAOSA negotiation in progress — responses stream as each agent round completes…*")
            answer, waiting = session.recv_stream(placeholder)

        st.session_state[chat_key].append({"role": "assistant", "content": answer})
        st.session_state[waiting_key] = waiting
        st.rerun()

    col_clear, col_new = st.columns([1, 1])
    with col_clear:
        if st.session_state[chat_key]:
            if st.button("🗑️ Clear chat", key="clear_neuro_san"):
                key = f"_ns_session_{network_name}"
                s = st.session_state.pop(key, None)
                if s:
                    s.close()
                st.session_state[chat_key] = []
                st.session_state[waiting_key] = False
                st.rerun()
    with col_new:
        if st.session_state[chat_key]:
            if st.button("🔁 New conversation", key="new_neuro_san"):
                key = f"_ns_session_{network_name}"
                s = st.session_state.pop(key, None)
                if s:
                    s.close()
                st.session_state[chat_key] = []
                st.session_state[waiting_key] = False
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 3 — Before vs After
# ══════════════════════════════════════════════════════════════════
with tab_compare:
    st.subheader(f"Hard Harness vs Neuro SAN — {use_case_name}")

    hh = uc["compare_hard_harness"]
    ns = uc["compare_neuro_san"]

    st.markdown(
        "Both systems call **the exact same Lambda skills**. "
        "The difference is **who orchestrates** the calls:"
    )

    col_hard, col_neuro = st.columns(2)

    with col_hard:
        st.markdown(f"### 🔧 {hh['title']}")
        st.markdown(f"**Orchestration:** Python code in a Lambda handler\n\n**Flow (fixed pipeline):**")
        for phase in hh["phases"]:
            st.markdown(f"  - {phase}")
        st.markdown(f"\n**To change behavior:** {hh['change_cost']}")
        st.markdown(f"**Lines of orchestration code:** {hh['loc']}")
        st.success("✅ Production-stable, audited, hardcoded safety")

    with col_neuro:
        st.markdown("### 🧠 Neuro SAN (Next-Gen Demo)")
        st.markdown(f"**Orchestration:** NLP instructions in `{network_name}.hocon`\n\n**Flow (LLM-driven AAOSA):**")
        st.markdown(f"  - {ns['neuro_description']}")
        st.markdown(f"\n**To change behavior:** {ns['change_cost']}")
        st.markdown(f"**Lines of orchestration code:** {ns['loc']}")
        st.markdown(f"**Demo wow factor:** {ns['demo_wow']} on the **Live Demo Toggle** tab.")
        st.info("🚀 Business-analyst editable, hot-reloadable, LLM-driven")

    st.markdown("---")
    st.markdown("### HITL comparison")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "**Hard Harness HITL:**\n"
            "- Explicit pause in Python handler\n"
            "- `WikiContributeTool` has `_HITL_PAGE_TYPES` hardcoded\n"
            "- Human sees Streamlit input prompt\n"
            "- Resume button triggers next phase"
        )
    with col2:
        st.markdown(
            "**Neuro SAN HITL:**\n"
            "- Tool returns `human_review_required=true`\n"
            "- FrontMan LLM reads this, asks the user in chat\n"
            "- User types answer in Agent Chat tab\n"
            "- FrontMan continues AAOSA negotiation automatically"
        )

    st.markdown("---")
    st.markdown("### Lambda skills used in this use case")
    st.table(uc["skills_table"])
