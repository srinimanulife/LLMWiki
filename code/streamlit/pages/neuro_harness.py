"""
LLMWiki — Neuro Harness
Customer-facing Neuro SAN AAOSA agent page.
Two harnesses side by side (UC1 Sales-to-Service, UC-PM Problem Management) as st.tabs.
Two-column layout: chat left (55%), skills + traces right (45%).
"""
import asyncio
import difflib
import json
import os
import queue as _queue
import re
import threading
import time
import urllib.request
import urllib.error
import uuid

import boto3
import requests
import streamlit as st
import websockets

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from demo_variants import DEMO_VARIANTS
except ImportError:
    DEMO_VARIANTS = {}

# ── set_page_config MUST be first Streamlit call ──────────────────
st.set_page_config(
    page_title="Neuro Harness — LLMWiki",
    page_icon="🧠",
    layout="wide",
)

# ── Configuration ──────────────────────────────────────────────────
_AWS_REGION        = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
_WIKI_BUCKET       = os.environ.get("WIKI_BUCKET", "")
# Server-side URLs (container-internal; never rendered as browser links)
_NSFLOW_LOCAL_URL  = os.environ.get("NSFLOW_LOCAL_URL", "http://localhost:4173")
_PHOENIX_ENDPOINT  = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006")
# Browser-facing URLs — default to same-host relative paths via nginx proxy
_NSFLOW_BROWSER_URL  = os.environ.get("NSFLOW_BROWSER_URL",  "/agents")
_PHOENIX_BROWSER_URL = os.environ.get("PHOENIX_BROWSER_URL", "/phoenix")
_PROJECT_NEURO       = os.environ.get("PHOENIX_PROJECT_NEURO_SAN", "neuro-san-agents")

# ── Use-case definitions ───────────────────────────────────────────
_USE_CASES = {
    "UC1 — Sales to Service": {
        "network":        "uc1_sales_to_service",
        "s3_key":         "wiki/neuro-san/registries/llmwiki/uc1_sales_to_service.hocon",
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
        "aaosa_chain": [
            ("ContextBootstrap", "SK-01", "#1a6bbd"),
            ("WikiQuery",        "SK-02", "#7c3aed"),
            ("ArtifactResolution","SK-04","#d97706"),
            ("GapDetection",     "SK-05", "#dc2626"),
            ("WikiContribute",   "SK-03", "#16a34a"),
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
            "change_cost": "Edit text → click Deploy → live in ~5 s",
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
        "s3_key":         "wiki/neuro-san/registries/llmwiki/uc_pm_problem_management.hocon",
        "local_hocon":    "registries/llmwiki/uc_pm_problem_management.hocon",
        "agent_variants": [
            "PM FrontMan (Problem Management)",
            "ProblemClassifier (SK-06)",
            "ContextBootstrap (SK-01)",
            "WikiQuery (SK-02)",
            "GapDetection (SK-05)",
            "ArtifactResolution (SK-04)",
            "WikiContribute (SK-03)",
        ],
        "sample_prompts": [
            "Run RCA for problem PRB0042 on QNXT Batch Processing severity P2",
            "Classify and analyse problem PRB0099 on Facets Integration component",
            "Create RCA draft for problem bcbs-mn-p001 QNXT Eligibility severity P1",
        ],
        "aaosa_chain": [
            ("ProblemClassifier", "SK-06", "#dc2626"),
            ("ContextBootstrap",  "SK-01", "#1a6bbd"),
            ("WikiQuery",         "SK-02", "#7c3aed"),
            ("ArtifactResolution","SK-04", "#d97706"),
            ("GapDetection",      "SK-05", "#b45309"),
            ("WikiContribute",    "SK-03", "#16a34a"),
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
            "change_cost": "Edit text → click Deploy → live in ~5 s",
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

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.nh-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #1a6bbd;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.nh-card-green {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 4px solid #16a34a;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.nh-card-amber {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-left: 4px solid #d97706;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.skill-chain-item {
    display: flex;
    align-items: center;
    padding: 7px 12px;
    border-radius: 8px;
    margin: 4px 0;
    font-size: 0.88em;
    font-weight: 600;
}
.metric-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 10px;
    font-size: 0.78em;
    font-weight: 600;
    margin: 2px 3px;
}
.section-label {
    font-size: 0.72em;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── S3 helpers ─────────────────────────────────────────────────────
def _s3_client():
    return boto3.client("s3", region_name=_AWS_REGION)

def _load_hocon(uc_cfg: dict) -> tuple[str, str]:
    if _WIKI_BUCKET:
        try:
            resp = _s3_client().get_object(Bucket=_WIKI_BUCKET, Key=uc_cfg["s3_key"])
            return resp["Body"].read().decode("utf-8"), "S3 (live)"
        except Exception:
            pass
    try:
        with open(uc_cfg["local_hocon"]) as f:
            return f.read(), "local (bundled)"
    except FileNotFoundError:
        return "# HOCON not found", "not found"

def _save_hocon(content: str, uc_cfg: dict) -> bool:
    if not _WIKI_BUCKET:
        return False
    try:
        _s3_client().put_object(
            Bucket=_WIKI_BUCKET, Key=uc_cfg["s3_key"],
            Body=content.encode("utf-8"), ContentType="text/plain",
        )
        return True
    except Exception as e:
        st.error(f"S3 save failed: {e}")
        return False

def _extract_instructions(hocon: str, agent_block: str) -> tuple[str, str, str]:
    name_m = re.search(rf'"name"\s*:\s*"{re.escape(agent_block)}"', hocon)
    if not name_m:
        return "", hocon, ""
    instr_m = re.search(r'"instructions"\s*:\s*"""(.*?)"""', hocon[name_m.end():], re.DOTALL)
    if not instr_m:
        return "", hocon, ""
    abs_s = name_m.end() + instr_m.start(1)
    abs_e = name_m.end() + instr_m.end(1)
    return hocon[:abs_s], hocon[abs_s:abs_e].strip(), hocon[abs_e:]

def _replace_instructions(hocon: str, agent_block: str, new_instructions: str) -> str:
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

# ── Diff HTML ──────────────────────────────────────────────────────
def _diff_html(old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    differ = difflib.SequenceMatcher(None, old_lines, new_lines)
    parts = [
        "<div style='font-family:monospace;font-size:13px;"
        "border:1px solid #e2e8f0;border-radius:6px;"
        "max-height:380px;overflow-y:auto;padding:8px;background:#f8fafc;'>"
    ]
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(f"<div style='padding:1px 4px;color:#6b7280;'>{esc or '&nbsp;'}</div>")
        elif tag in ("replace", "delete"):
            for line in old_lines[i1:i2]:
                esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(
                    f"<div style='padding:1px 4px;background:#fee2e2;color:#dc2626;"
                    f"text-decoration:line-through;'>"
                    f"<span style='margin-right:6px;'>−</span>{esc or '&nbsp;'}</div>"
                )
            if tag == "replace":
                for line in new_lines[j1:j2]:
                    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    parts.append(
                        f"<div style='padding:1px 4px;background:#dcfce7;color:#16a34a;'>"
                        f"<span style='margin-right:6px;'>+</span>{esc or '&nbsp;'}</div>"
                    )
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(
                    f"<div style='padding:1px 4px;background:#dcfce7;color:#16a34a;'>"
                    f"<span style='margin-right:6px;'>+</span>{esc or '&nbsp;'}</div>"
                )
    parts.append("</div>")
    return "".join(parts)

# ── nsflow / WebSocket helpers ─────────────────────────────────────
_WS_URL = _NSFLOW_LOCAL_URL.replace("http://", "ws://").replace("https://", "wss://")

def _nsflow_healthy() -> bool:
    try:
        return requests.get(f"{_NSFLOW_LOCAL_URL}/api/v1/networks/", timeout=3).status_code == 200
    except Exception:
        return False


class _AgentSession:
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
    existing = st.session_state.get(key)
    if existing is None or not existing._thread.is_alive():
        if existing is not None:
            existing.close()
        session = _AgentSession(agent_name)
        st.session_state[key] = session
    return st.session_state[key]

# ── Phoenix trace helpers ──────────────────────────────────────────
def _phoenix_get(path: str) -> dict:
    url = f"{_PHOENIX_ENDPOINT}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"error": str(exc)}

@st.cache_data(ttl=5)
def _get_neuro_spans(limit: int = 10) -> list:
    # Resolve project
    probe = _phoenix_get(f"/v1/projects/{_PROJECT_NEURO}/spans?limit=1")
    project = _PROJECT_NEURO if "error" not in probe else "default"
    data = _phoenix_get(f"/v1/projects/{project}/spans?limit={limit}")
    if "error" in data:
        return []
    rows = []
    for s in data.get("data", []):
        attrs = s.get("attributes", {})
        if isinstance(attrs, list):
            attrs = {a["key"]: (a.get("value") or {}).get("stringValue", "") for a in attrs}
        ctx = s.get("context", {})
        if not attrs.get("neuro_san.tool") and not attrs.get("neuro_san.skill"):
            if "neuro_san" not in s.get("name", ""):
                continue
        question = str(attrs.get("input.value", ""))
        rows.append({
            "Span":     (ctx.get("span_id") or s.get("id", ""))[:12],
            "Name":     s.get("name", ""),
            "Tool":     attrs.get("neuro_san.tool", ""),
            "Question": question[:60] + ("…" if len(question) > 60 else ""),
        })
    return rows

# ══════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════
st.title("🧠 Neuro Harness")
st.caption("Live AAOSA agent chat — UC1 Sales-to-Service and UC-PM Problem Management.")

# ── Use-case tabs ──────────────────────────────────────────────────
tab_uc1, tab_pm = st.tabs([
    "UC1 — Sales to Service",
    "UC-PM — Problem Management",
])

# ══════════════════════════════════════════════════════════════════
# SHARED RENDERER — called once per UC tab
# ══════════════════════════════════════════════════════════════════
def _render_uc_harness(use_case_name: str):
    uc           = _USE_CASES[use_case_name]
    network_name = uc["network"]

    col_chat, col_right = st.columns([55, 45])

    # ──────────────────────────────────────────────────────────────
    # LEFT — Chat
    # ──────────────────────────────────────────────────────────────
    with col_chat:
        # Connection status
        healthy = _nsflow_healthy()
        if healthy:
            st.success("neuro-san sidecar ready", icon="✅")
        else:
            st.warning(
                "neuro-san sidecar not reachable — typically needs 60–90 s to start. "
                "Send a message to try anyway.",
                icon="⏳",
            )

        st.markdown(
            f"<div style='padding:7px 14px;background:#eff6ff;border-radius:8px;"
            f"border-left:3px solid #1a6bbd;font-size:0.88em;margin-bottom:10px;'>"
            f"Active network: <code>{network_name}</code></div>",
            unsafe_allow_html=True,
        )

        # Suggested prompts
        with st.expander("Suggested prompts", expanded=False):
            for p in uc["sample_prompts"]:
                st.code(p, language="text")

        # Per-network session state
        chat_key    = f"nh_messages_{network_name}"
        waiting_key = f"nh_waiting_{network_name}"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []
        if waiting_key not in st.session_state:
            st.session_state[waiting_key] = False

        # Render history
        for msg in st.session_state[chat_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if st.session_state[waiting_key]:
            st.info("The agent is waiting for your reply — type your answer below.", icon="🤖")

        hint = "Reply to the agent…" if st.session_state[waiting_key] else "Ask the agent network…"
        prompt_key = f"nh_input_{network_name}"

        if prompt := st.chat_input(hint, key=prompt_key):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            session = _get_or_create_session(network_name)
            session.send(prompt)

            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("⏳ *AAOSA negotiation in progress…*")
                answer, waiting = session.recv_stream(placeholder)

            st.session_state[chat_key].append({"role": "assistant", "content": answer})
            st.session_state[waiting_key] = waiting
            st.rerun()

        # Clear / New conversation controls
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.session_state[chat_key]:
                if st.button("🗑️ Clear chat", key=f"nh_clear_{network_name}"):
                    s = st.session_state.pop(f"_ns_session_{network_name}", None)
                    if s:
                        s.close()
                    st.session_state[chat_key] = []
                    st.session_state[waiting_key] = False
                    st.rerun()
        with btn_col2:
            if st.session_state[chat_key]:
                if st.button("🔁 New conversation", key=f"nh_new_{network_name}"):
                    s = st.session_state.pop(f"_ns_session_{network_name}", None)
                    if s:
                        s.close()
                    st.session_state[chat_key] = []
                    st.session_state[waiting_key] = False
                    st.rerun()

        # Before/After comparison in expander
        with st.expander("Before vs After — Hard Harness vs Neuro SAN", expanded=False):
            hh = uc["compare_hard_harness"]
            ns = uc["compare_neuro_san"]
            c_hard, c_neuro = st.columns(2)
            with c_hard:
                st.markdown(f"**{hh['title']}**")
                for phase in hh["phases"]:
                    st.markdown(f"- {phase}")
                st.caption(f"Change cost: {hh['change_cost']}")
                st.caption(f"Orchestration: {hh['loc']}")
            with c_neuro:
                st.markdown("**Neuro SAN (NLP-driven)**")
                st.markdown(f"- {ns['neuro_description']}")
                st.caption(f"Change cost: {ns['change_cost']}")
                st.caption(f"Orchestration: {ns['loc']}")
            st.markdown("---")
            st.markdown("**Lambda skills used in this use case**")
            import pandas as pd
            st.dataframe(pd.DataFrame(uc["skills_table"]), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────────────────────────
    # RIGHT — Skills + Traces + Variant Switcher
    # ──────────────────────────────────────────────────────────────
    with col_right:

        # ── Active Skills panel ────────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-label">Active Skills — AAOSA Chain</p>', unsafe_allow_html=True)
            for agent_name, sk_id, color in uc["aaosa_chain"]:
                st.markdown(
                    f"<div class='skill-chain-item' style='background:{color}18;"
                    f"border-left:3px solid {color};color:#1a2f4a;'>"
                    f"<span style='background:{color};color:#fff;border-radius:6px;"
                    f"padding:2px 8px;font-size:0.75em;margin-right:10px;'>{sk_id}</span>"
                    f"{agent_name}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # ── Live Traces panel ──────────────────────────────────────
        with st.container(border=True):
            trace_hdr, trace_btn = st.columns([3, 1])
            trace_hdr.markdown('<p class="section-label" style="margin-bottom:0">Live Traces — Phoenix</p>', unsafe_allow_html=True)
            if trace_btn.button("↺", key=f"nh_refresh_traces_{network_name}", help="Refresh traces"):
                st.cache_data.clear()

            spans = _get_neuro_spans(limit=10)
            if spans:
                import pandas as pd
                df = pd.DataFrame(spans)
                st.dataframe(df, use_container_width=True, hide_index=True, height=180)
            else:
                st.caption("No spans yet — run an agent query to populate traces.")

            if _PHOENIX_BROWSER_URL:
                st.link_button("🌐 Open Phoenix UI →", url=_PHOENIX_BROWSER_URL, use_container_width=True)
            else:
                st.caption("💡 Phoenix is a container sidecar. Set `PHOENIX_BROWSER_URL` env var to enable this link.")

        # ── Skill Variant switcher ─────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-label">Skill Variant</p>', unsafe_allow_html=True)

            if not DEMO_VARIANTS:
                st.caption("demo_variants.py not found.")
            else:
                uc_agent_names = uc["agent_variants"]
                selected_agent = st.selectbox(
                    "Agent",
                    options=uc_agent_names,
                    key=f"nh_agent_sel_{network_name}",
                    label_visibility="collapsed",
                )
                meta       = DEMO_VARIANTS.get(selected_agent)
                block_name = _AGENT_BLOCK.get(selected_agent, "")

                if meta and block_name:
                    hocon_cache_key  = f"nh_hocon_{network_name}"
                    hocon_source_key = f"nh_hocon_src_{network_name}"

                    if st.session_state.get(hocon_cache_key) is None:
                        with st.spinner("Loading HOCON…"):
                            content, source = _load_hocon(uc)
                            st.session_state[hocon_cache_key] = content
                            st.session_state[hocon_source_key] = source

                    hocon = st.session_state[hocon_cache_key]
                    va_name = meta["version_a_name"]
                    vb_name = meta["version_b_name"]
                    va_text = meta["version_a"]
                    vb_text = meta["version_b"]

                    _, live_instructions, _ = _extract_instructions(hocon, block_name)
                    live_is_a = (live_instructions.strip() == va_text.strip())
                    live_is_b = (live_instructions.strip() == vb_text.strip())
                    live_label = va_name if live_is_a else (vb_name if live_is_b else "Custom")

                    st.caption(
                        f"Source: {st.session_state.get(hocon_source_key, '')} — "
                        f"Live: **{live_label}**"
                    )

                    v_col_a, v_col_b = st.columns(2)
                    with v_col_a:
                        if live_is_a:
                            st.success(f"✅ {va_name}")
                        elif st.button(
                            f"Deploy {va_name}",
                            key=f"nh_dep_a_{network_name}_{selected_agent}",
                            use_container_width=True,
                        ):
                            with st.spinner(f"Deploying {va_name}…"):
                                new_hocon = _replace_instructions(hocon, block_name, va_text)
                                if _save_hocon(new_hocon, uc):
                                    st.session_state[hocon_cache_key] = new_hocon
                                    st.success(f"Deployed {va_name}")
                                    st.balloons()
                                    st.rerun()
                                else:
                                    st.error("Save failed — check WIKI_BUCKET.")
                    with v_col_b:
                        if live_is_b:
                            st.success(f"✅ {vb_name}")
                        elif st.button(
                            f"Deploy {vb_name}",
                            key=f"nh_dep_b_{network_name}_{selected_agent}",
                            use_container_width=True,
                        ):
                            with st.spinner(f"Deploying {vb_name}…"):
                                new_hocon = _replace_instructions(hocon, block_name, vb_text)
                                if _save_hocon(new_hocon, uc):
                                    st.session_state[hocon_cache_key] = new_hocon
                                    st.success(f"Deployed {vb_name}")
                                    st.balloons()
                                    st.rerun()
                                else:
                                    st.error("Save failed — check WIKI_BUCKET.")

                    with st.expander("View diff", expanded=False):
                        st.markdown(_diff_html(va_text, vb_text), unsafe_allow_html=True)

                    if st.button("↺ Reload HOCON", key=f"nh_reload_{network_name}"):
                        st.session_state[hocon_cache_key] = None
                        st.rerun()
                else:
                    st.caption(f"No demo variants configured for {selected_agent}.")

        # ── nsflow link ────────────────────────────────────────────
        if _NSFLOW_BROWSER_URL:
            st.link_button("🔗 Open nsflow UI →", url=_NSFLOW_BROWSER_URL, use_container_width=True)
        else:
            st.caption("💡 nsflow is a container sidecar. Set `NSFLOW_BROWSER_URL` env var to enable this link.")


# ══════════════════════════════════════════════════════════════════
# RENDER TABS
# ══════════════════════════════════════════════════════════════════
with tab_uc1:
    _render_uc_harness("UC1 — Sales to Service")

with tab_pm:
    _render_uc_harness("UC-PM — Problem Management")
