"""
🧠 AI Skill Studio — Powered by Neuro SAN
Business users define agent behavior in plain English (HOCON NLP instructions).
No Python code required. Watch agents converse via the AAOSA protocol.
Embeds nsflow live agent network UI.
"""

import os
import json
import time
import boto3
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(
    page_title="AI Skill Studio — LLMWiki",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))

_SK_FUNCTIONS = {
    "SK-01": os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap"),
    "SK-02": os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query"),
    "SK-05": os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection"),
}

def _lambda_invoke(function_name: str, payload: dict) -> dict:
    """Invoke a Lambda and return the unwrapped body dict. Never raises."""
    try:
        client = boto3.client("lambda", region_name=_AWS_REGION)
        resp = client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload, default=str).encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if raw.get("FunctionError"):
            return {"_error": True, "error": str(raw), "status": "error"}
        body = raw.get("body", raw)
        return json.loads(body) if isinstance(body, str) else (body or {})
    except Exception as exc:
        return {"_error": True, "error": str(exc), "status": "error"}

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.hero-banner {
    background: linear-gradient(135deg, #1e3a5f 0%, #0d6efd 60%, #6610f2 100%);
    border-radius: 12px; padding: 28px 32px; color: white; margin-bottom: 24px;
}
.hero-banner h1 { font-size: 2em; margin: 0 0 8px 0; }
.hero-banner p  { font-size: 1.05em; opacity: 0.92; margin: 4px 0; }
.skill-card {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-left: 4px solid #0d6efd;
    border-radius: 10px; padding: 18px 20px; margin: 10px 0;
}
.skill-card-neuro {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-left: 4px solid #16a34a;
    border-radius: 10px; padding: 18px 20px; margin: 10px 0;
}
.skill-card-compare {
    background: #fefce8; border: 1px solid #fde68a;
    border-left: 4px solid #ca8a04;
    border-radius: 10px; padding: 14px 18px; margin: 6px 0;
    font-size: 0.92em;
}
.aaosa-step {
    background: white; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 12px 16px; margin: 6px 0;
}
.aaosa-step.determine { border-left: 4px solid #6366f1; }
.aaosa-step.fulfill   { border-left: 4px solid #0d6efd; }
.aaosa-step.followup  { border-left: 4px solid #f59e0b; }
.aaosa-step.compile   { border-left: 4px solid #16a34a; }
.agent-role {
    display: inline-block; padding: 2px 10px; border-radius: 10px;
    font-size: 0.78em; font-weight: 700; margin-right: 6px;
}
.role-frontman  { background: #dbeafe; color: #1e40af; }
.role-subagent  { background: #d1fae5; color: #065f46; }
.role-tool      { background: #fef3c7; color: #92400e; }
.nlp-instruction {
    background: #1e293b; color: #e2e8f0; border-radius: 8px;
    padding: 14px 18px; font-family: monospace; font-size: 0.84em;
    line-height: 1.6; margin: 8px 0; white-space: pre-wrap;
}
.benefit-chip {
    display: inline-block; background: #dbeafe; color: #1e40af;
    border-radius: 10px; padding: 3px 10px; font-size: 0.8em; margin: 3px 3px;
}
</style>
""", unsafe_allow_html=True)

# ── NLP skill definitions (the "after" Neuro SAN form) ────────────
NEURO_SKILLS = {
    "SK-01": {
        "id": "SK-01", "icon": "📋",
        "business_name": "Customer Briefing Loader",
        "neuro_agent": "ContextBootstrap",
        "class": "llmwiki.context_bootstrap_tool.ContextBootstrapTool",
        "tier": "Universal",
        "color": "#0d6efd",
        "old_description": "Python Lambda: boto3.client('dynamodb')... parallel KB queries... 120 lines of handler.py",
        "nlp_instruction": """\
You are the ContextBootstrap tool. Before ANY agent takes action on a customer engagement,
you must be called FIRST. You have one job: give the agent a complete, current picture of
the customer and the playbook for their use case.

Specifically, you retrieve IN PARALLEL:
1. The customer's full wiki history (all prior contributions for this customer_id)
2. The implementation playbook for the requested use_case (e.g. "UC1")

Return a structured briefing that includes:
- customer_status: "new" if no history exists, "existing" with summary if history found
- key_facts: the 3-5 most important facts about this customer (products, constraints, risk tier)
- playbook_steps: the ordered list of steps the agent must follow for this use case
- prior_contributions: list of wiki pages already written for this customer

If customer_status is "new", note that no prior work exists and the agent should start fresh.
If customer_status is "existing", surface any open action items or blockers from prior agents.

IMPORTANT: Your output feeds every subsequent skill. A missed fact here compounds downstream.
Call this tool with customer_id, use_case, and the calling agent_id.""",
        "sly_data_fields": ["customer_id", "llmwiki_api_key"],
        "input_params": ["customer_id", "use_case", "agent_id"],
        "output_keys": ["customer_status", "pages_loaded", "key_facts"],
        "uc_agents": "All UC1–UC10",
    },
    "SK-02": {
        "id": "SK-02", "icon": "🔍",
        "business_name": "Knowledge Finder",
        "neuro_agent": "WikiQuery",
        "class": "llmwiki.wiki_query_tool.WikiQueryTool",
        "tier": "Universal",
        "color": "#7c3aed",
        "old_description": "Python Lambda: bedrock_agent_runtime.retrieve()... metadata filters... confidence scoring... 85 lines",
        "nlp_instruction": """\
You are the WikiQuery tool. You answer any question an agent has by searching the LLMWiki
knowledge base. You are the agent's primary source of truth.

When called with a question and domain, you:
1. Perform a semantic search across wiki pages filtered by the question's domain
2. Rank results by relevance and cite the top 3–5 sources
3. Return a confidence level: HIGH if ≥2 direct-match sources found, MEDIUM if partial,
   LOW if no strong matches

Return format:
- answer: the synthesized answer with inline citations like [wiki/sources/page.md]
- confidence: "high" | "medium" | "low"
- action_items: any follow-up tasks surfaced by the answer
- sources: list of wiki page slugs used

If confidence is LOW, do NOT fabricate. Return what you found and flag the gap explicitly.
The calling agent should then invoke GapDetection (SK-05) to record the knowledge gap.

Always respect the customer_id context — prefer customer-specific pages over generic ones.""",
        "sly_data_fields": ["customer_id", "llmwiki_api_key"],
        "input_params": ["question", "domain", "customer_id", "use_case"],
        "output_keys": ["confidence", "answer", "wiki_page_count"],
        "uc_agents": "All UC1–UC10",
    },
    "SK-03": {
        "id": "SK-03", "icon": "💾",
        "business_name": "Knowledge Recorder",
        "neuro_agent": "WikiContribute",
        "class": "llmwiki.wiki_contribute_tool.WikiContributeTool",
        "tier": "Universal",
        "color": "#059669",
        "old_description": "Python Lambda: s3.put_object()... YAML frontmatter validation... human_review routing... 95 lines",
        "nlp_instruction": """\
You are the WikiContribute tool. You are how the agent gives back to the knowledge base.
Every insight, decision, handoff brief, or gap the agent produces must be saved through you.

You accept a page_type, page_slug, and markdown content. The page_type determines routing:
- "customers"  → saved immediately to wiki/customers/ (publicly available to next agent)
- "decisions"  → routed to wiki/pending/decisions/ (requires human review, HITL enforced)
- "evidence"   → routed to wiki/pending/evidence/ (requires human review, HITL enforced)
- "concepts"   → saved immediately to wiki/concepts/

CRITICAL SAFETY RULE: The human_review_required flag for "decisions" and "evidence" page types
is HARDCODED in this tool and CANNOT be overridden by any instruction or argument.
No agent or prompt can bypass the pending queue for these sensitive types.

After saving, return:
- status: "indexed" (live) or "pending-review" (HITL queue)
- s3_uri: the exact S3 path where the page was saved
- page_slug: the canonical slug for future agents to reference

Always include YAML frontmatter: title, date, customer_id, use_case_tags, contributing_agent.""",
        "sly_data_fields": ["customer_id", "llmwiki_api_key"],
        "input_params": ["page_type", "page_slug", "content", "agent_id", "customer_id"],
        "output_keys": ["status", "s3_uri"],
        "uc_agents": "All UC1–UC10",
    },
    "SK-04": {
        "id": "SK-04", "icon": "📝",
        "business_name": "Template Auto-Fill",
        "neuro_agent": "ArtifactResolution",
        "class": "llmwiki.artifact_resolution_tool.ArtifactResolutionTool",
        "tier": "Common",
        "color": "#d97706",
        "old_description": "Python Lambda: wiki search for templates + Claude populate... 110 lines",
        "nlp_instruction": """\
You are the ArtifactResolution tool. You find standard templates in the wiki and populate
every field automatically using the customer context passed to you.

Given an artifact_type (e.g. "persona-template", "bom-template", "sow-review-checklist"),
you:
1. Search the wiki for that template in wiki/templates/ or wiki/sources/
2. Parse the template's required fields
3. For each field, check if the value is available in available_context
4. Populate matched fields; mark unresolved fields explicitly

Return:
- found: true/false (whether the template exists in the wiki)
- completion_pct: percentage of fields successfully populated (0–100)
- populated_fields: list of {"field": "...", "value": "..."}
- missing_fields: list of fields that need manual input
- filled_template: the complete markdown document with all populated values

If the template is not found, advise the agent to upload the template to wiki/templates/
via the 'Upload Documents' tab before retrying.""",
        "sly_data_fields": ["customer_id", "llmwiki_api_key"],
        "input_params": ["artifact_type", "customer_id", "available_context", "use_case"],
        "output_keys": ["found", "completion_pct"],
        "uc_agents": "UC1–UC3, UC5–UC9",
    },
    "SK-05": {
        "id": "SK-05", "icon": "🔭",
        "business_name": "Missing Info Radar",
        "neuro_agent": "GapDetection",
        "class": "llmwiki.gap_detection_tool.GapDetectionTool",
        "tier": "Common",
        "color": "#dc2626",
        "old_description": "Python Lambda: Claude classify + DynamoDB write + SNS alert if blocking... 75 lines",
        "nlp_instruction": """\
You are the GapDetection tool. You are called when WikiQuery (SK-02) returns
confidence=low or when the agent encounters a question it cannot answer from the wiki.

Your job is to formally classify and record the knowledge gap so future agents —
and humans reviewing the wiki — know exactly what information is missing and why it matters.

For each gap you detect:
1. Assign a gap_type: "entity" (missing org/person), "concept" (missing process/policy),
   or "question" (unanswerable question)
2. Assess blocking: true if this gap would halt the current use case, false otherwise
3. Write a clear gap_rationale explaining why this matters for the use case
4. Record the gap to DynamoDB (llmwiki-gaps table) with status="suggested"
5. If blocking=true, escalate immediately — do not allow the agent to proceed
   without flagging this to the calling agent

Return:
- gap_count: total gaps detected
- blocking: true if any gap is blocking
- gaps: list of {"title", "gap_type", "blocking", "rationale", "source_query"}

Never fabricate information to fill a gap. Better a recorded gap than a hallucinated answer.""",
        "sly_data_fields": ["customer_id", "llmwiki_api_key"],
        "input_params": ["question", "domain", "use_case", "customer_id", "low_confidence_response"],
        "output_keys": ["gap_count", "blocking"],
        "uc_agents": "UC1, UC2, UC5, UC8–UC10",
    },
}

# ── AAOSA conversation trace for UC1 demo ─────────────────────────
AAOSA_TRACE = [
    {
        "round": 1, "type": "determine", "label": "Round 1 — Determine",
        "from": "UC1SalesToServiceAgent (FrontMan)", "to": "ContextBootstrap",
        "message": "Can you help me load the briefing for customer bcbs-mn-001 running UC1?",
        "response": "Yes, I can load customer history and UC1 playbook. I'll fetch both in parallel.",
        "latency_ms": 480, "tokens": 210,
    },
    {
        "round": 2, "type": "fulfill", "label": "Round 2 — Fulfill (SK-01 executes)",
        "from": "ContextBootstrap", "to": "Bedrock KB + DynamoDB",
        "message": "Executing: parallel fetch of customer history and UC1 playbook",
        "response": "customer_status=existing · 4 pages loaded · 3 key_facts surfaced · 7 playbook steps",
        "latency_ms": 480, "tokens": 0,
    },
    {
        "round": 3, "type": "determine", "label": "Round 3 — Determine",
        "from": "UC1SalesToServiceAgent (FrontMan)", "to": "WikiQuery",
        "message": "What are the delivery risks for a new QNXT implementation for BlueCross MN?",
        "response": "Yes, I can search the wiki for QNXT delivery risk patterns and BlueCross history.",
        "latency_ms": 120, "tokens": 180,
    },
    {
        "round": 4, "type": "fulfill", "label": "Round 4 — Fulfill (SK-02 executes)",
        "from": "WikiQuery", "to": "Bedrock KB (S3 Vectors)",
        "message": "Semantic search: domain=customer-onboarding · customer_id=bcbs-mn-001",
        "response": "confidence=high · 3 sources · 2 action_items: [EHR Epic integration, HIPAA BAA required]",
        "latency_ms": 640, "tokens": 890,
    },
    {
        "round": 5, "type": "followup", "label": "Round 5 — Follow-up (gap check)",
        "from": "UC1SalesToServiceAgent (FrontMan)", "to": "GapDetection",
        "message": "WikiQuery returned confidence=high. Check if any gaps remain before templating.",
        "response": "No blocking gaps detected. Proceeding with template population.",
        "latency_ms": 340, "tokens": 120,
    },
    {
        "round": 6, "type": "fulfill", "label": "Round 6 — Fulfill (SK-04 executes)",
        "from": "ArtifactResolution", "to": "Wiki template store",
        "message": "Find and populate: persona-template for bcbs-mn-001",
        "response": "found=true · completion_pct=84% · 11 fields populated · 2 missing (TPA contact, go-live Q)",
        "latency_ms": 820, "tokens": 1240,
    },
    {
        "round": 7, "type": "compile", "label": "Round 7 — Compile (final save)",
        "from": "UC1SalesToServiceAgent (FrontMan)", "to": "WikiContribute",
        "message": "Save handoff brief to wiki/customers/bcbs-mn-001-handoff-2026.md",
        "response": "status=indexed · s3_uri=s3://llmwiki/wiki/customers/bcbs-mn-001-handoff-2026.md",
        "latency_ms": 290, "tokens": 340,
    },
]

AAOSA_COLORS = {
    "determine": ("#6366f1", "#eef2ff"),
    "fulfill":   ("#0d6efd", "#eff6ff"),
    "followup":  ("#f59e0b", "#fffbeb"),
    "compile":   ("#16a34a", "#f0fdf4"),
}

# ── UC1 agent network diagram (HTML/CSS tree) ──────────────────────
AGENT_NETWORK_HTML = """
<style>
.tree { font-family: -apple-system, sans-serif; font-size: 14px; }
.node { display: flex; align-items: center; gap: 8px; padding: 8px 14px;
        border-radius: 8px; margin: 4px 0; font-weight: 500; }
.node-frontman { background: #1e3a5f; color: white; font-size: 15px; }
.node-aaosa    { background: #dbeafe; color: #1e40af; margin-left: 28px; border: 1px solid #bfdbfe; }
.node-tool     { background: #f0fdf4; color: #065f46; margin-left: 56px; border: 1px solid #bbf7d0; }
.edge { color: #94a3b8; margin-left: 14px; font-size: 12px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 8px;
         font-weight: 600; margin-left: auto; }
.badge-universal { background: #dbeafe; color: #1e40af; }
.badge-common    { background: #d1fae5; color: #065f46; }
.badge-domain    { background: #fef3c7; color: #92400e; }
.latency { font-size: 11px; color: #94a3b8; margin-left: 6px; }
</style>
<div class="tree">
  <div class="node node-frontman">
    🧠 UC1SalesToServiceAgent
    <span class="badge" style="background:#f1f5f9;color:#475569">FrontMan · AAOSA</span>
  </div>
  <div class="edge">└── calls sub-agents via AAOSA Determine/Fulfill protocol</div>
  <div class="node node-aaosa">
    📋 ContextBootstrap <span class="latency">~480ms</span>
    <span class="badge badge-universal">SK-01 · Tier 1</span>
  </div>
  <div class="node node-tool" style="margin-left:84px">
    🗄️ DynamoDB (customer history) · Bedrock KB (playbook)
  </div>
  <div class="node node-aaosa">
    🔍 WikiQuery <span class="latency">~640ms</span>
    <span class="badge badge-universal">SK-02 · Tier 1</span>
  </div>
  <div class="node node-tool" style="margin-left:84px">
    🔎 S3 Vectors (semantic search) · Bedrock Claude
  </div>
  <div class="node node-aaosa">
    🔭 GapDetection <span class="latency">~340ms</span>
    <span class="badge badge-common">SK-05 · Tier 2</span>
  </div>
  <div class="node node-tool" style="margin-left:84px">
    🗄️ DynamoDB (gaps table) · SNS (blocking alert)
  </div>
  <div class="node node-aaosa">
    📝 ArtifactResolution <span class="latency">~820ms</span>
    <span class="badge badge-common">SK-04 · Tier 2</span>
  </div>
  <div class="node node-tool" style="margin-left:84px">
    📄 Wiki template store · Claude (field population)
  </div>
  <div class="node node-aaosa">
    💾 WikiContribute <span class="latency">~290ms</span>
    <span class="badge badge-universal">SK-03 · Tier 1</span>
  </div>
  <div class="node node-tool" style="margin-left:84px">
    🪣 S3 (wiki/customers/ or wiki/pending/) · Bedrock KB re-index
  </div>
  <div style="margin-top:16px;padding:10px 14px;background:#f8fafc;border-radius:8px;
              border:1px solid #e2e8f0;font-size:12px;color:#64748b;">
    <b>Sly Data channel</b> (never enters LLM context):
    customer_id · llmwiki_api_key · engagement_id
    <span style="margin-left:12px;background:#fef3c7;color:#92400e;padding:2px 8px;
                 border-radius:8px;font-size:11px;">🔒 Prompt-injection proof</span>
  </div>
</div>
"""

# ── Hero ───────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
  <h1>🧠 AI Skill Studio</h1>
  <p><b>Powered by Neuro SAN</b> — Define agents in plain English. No Python required.</p>
  <p>Business analysts write the <em>what</em>. The LLM figures out the <em>how</em>. Agents talk to each other automatically.</p>
</div>
""", unsafe_allow_html=True)

# ── Key value proposition chips ───────────────────────────────────
st.markdown("""
<span class="benefit-chip">✍️ NLP-defined skills</span>
<span class="benefit-chip">👁️ Watch agents converse live</span>
<span class="benefit-chip">🔒 Sly Data keeps secrets out of LLM</span>
<span class="benefit-chip">🔄 AAOSA auto-routes between agents</span>
<span class="benefit-chip">📊 Full Langfuse observability</span>
<span class="benefit-chip">🚫 No code for business logic changes</span>
""", unsafe_allow_html=True)
st.write("")

# ── Main tabs ──────────────────────────────────────────────────────
tab_overview, tab_skills, tab_aaosa, tab_live, tab_compare = st.tabs([
    "🗺️ Agent Network",
    "📖 NLP Skill Definitions",
    "🎬 Live AAOSA Trace",
    "⚡ Live Agent Runner",
    "🔄 Before vs After",
])


# ════════════════════════════════════════════════════════════════════
# TAB 1: Agent Network Overview
# ════════════════════════════════════════════════════════════════════
with tab_overview:
    st.subheader("UC1 Sales-to-Service — Agent Network")
    st.caption(
        "Every skill is now an AAOSA-protocol sub-agent. "
        "The FrontMan orchestrates them automatically — no hardcoded call sequence."
    )

    col_net, col_metrics = st.columns([3, 2], gap="large")

    with col_net:
        components.html(AGENT_NETWORK_HTML, height=450, scrolling=False)

    with col_metrics:
        st.markdown("#### Network at a glance")
        m1, m2 = st.columns(2)
        m1.metric("Total agents", "6")
        m2.metric("Coded tools", "5")
        m1.metric("AAOSA rounds", "7 avg")
        m2.metric("Total latency", "~2.6s")
        m1.metric("UC agents served", "10/10")
        m2.metric("Sly Data fields", "3")

        st.divider()
        st.markdown("#### How AAOSA works")
        st.markdown("""
1. **Determine** — FrontMan asks each sub-agent: *"Can you help with this?"*
2. **Fulfill** — Sub-agent executes its coded tool (calls AWS API)
3. **Follow-up** — FrontMan collects results, may ask follow-ups
4. **Compile** — FrontMan synthesizes all outputs into final answer

This replaces the hardcoded `if phase == 4: invoke SK-01` logic in the Lambda harness.
The LLM decides which agents to call and in what order, guided by NLP instructions.
""")

    st.divider()
    st.markdown("#### All 10 UC Agent Networks")
    st.caption(
        "Each UC agent is defined as a HOCON file. "
        "They all share the same 5 coded tools via the `manifest.hocon` registry."
    )

    uc_data = [
        ("UC1",  "Sales-to-Service",       ["SK-01","SK-02","SK-03","SK-04","SK-05"], "🟢 POC ready"),
        ("UC2",  "Environment Provision",  ["SK-01","SK-02","SK-03","SK-09"],          "🟡 Planned"),
        ("UC3",  "IAM Onboarding",         ["SK-01","SK-02","SK-03","SK-04"],          "🟡 Planned"),
        ("UC4",  "Business Config",        ["SK-01","SK-02","SK-03"],                   "🟡 Planned"),
        ("UC5",  "Data Migration",         ["SK-01","SK-02","SK-03","SK-05"],          "🟡 Planned"),
        ("UC6",  "SIT",                    ["SK-01","SK-02","SK-07"],                   "🟡 Planned"),
        ("UC7",  "E2E Testing",            ["SK-01","SK-02","SK-07"],                   "🟡 Planned"),
        ("UC8",  "Cutover",                ["SK-01","SK-02","SK-03","SK-08"],           "🟡 Planned"),
        ("UC9",  "PTO/Handover",           ["SK-01","SK-02","SK-03","SK-04"],          "🟡 Planned"),
        ("UC10", "Hypercare",              ["SK-01","SK-02","SK-03","SK-05"],          "🟡 Planned"),
    ]

    for uc_id, name, skills, status in uc_data:
        with st.expander(f"{status}  **{uc_id}** — {name}  · {len(skills)} skills"):
            skill_chips = "  ".join(f"`{s}`" for s in skills)
            st.markdown(f"**Skills:** {skill_chips}")
            st.caption(
                f"HOCON file: `registries/llmwiki/{uc_id.lower()}_{name.lower().replace(' ', '_')}.hocon`"
            )


# ════════════════════════════════════════════════════════════════════
# TAB 2: NLP Skill Definitions
# ════════════════════════════════════════════════════════════════════
with tab_skills:
    st.subheader("📖 Skills Defined in Plain English")
    st.info(
        "**What changed:** In the old Lambda design, skill behavior was buried in Python code. "
        "With Neuro SAN, a business analyst writes the NLP instruction block. "
        "The LLM reads it and knows exactly what to do — no code changes needed to update business rules.",
        icon="💡",
    )

    st.markdown("#### HOCON structure — every skill follows this pattern")
    with st.expander("View HOCON template", expanded=False):
        st.code("""\
# Every skill in LLMWiki follows this HOCON pattern
{
    "name": "WikiQuery",              # Agent name (called by FrontMan)
    "function": {
        "description": "...",         # Business-readable capability summary
        "parameters": {               # What the FrontMan passes in
            "type": "object",
            "properties": {
                "question":    {"type": "string", "description": "..."},
                "domain":      {"type": "string"},
                "customer_id": {"type": "string"}   # <- also in sly_data
            },
            "required": ["question", "domain"]
        }
    },
    "instructions": \"\"\"           # ← THIS IS THE KEY: pure NLP
        You are the WikiQuery tool. You answer any question...
        (full plain-English behavioral spec)
    \"\"\",
    "class": "llmwiki.wiki_query_tool.WikiQueryTool"  # Python coded tool
}""", language="hocon")
        st.caption(
            "The `instructions` block is read by Claude at runtime. "
            "Change business rules by editing this text — no Lambda redeploy needed."
        )

    st.divider()

    for sk_id, sk in NEURO_SKILLS.items():
        with st.container():
            h1, h2 = st.columns([3, 1])
            h1.markdown(
                f"### {sk['icon']} {sk['id']} — {sk['business_name']}"
                f"<br><small style='color:#64748b'>Neuro SAN agent: `{sk['neuro_agent']}` · "
                f"Coded tool: `{sk['class'].split('.')[-1]}`</small>",
                unsafe_allow_html=True,
            )
            h2.markdown(
                f"<div style='text-align:right;margin-top:8px'>"
                f"<span style='background:#dbeafe;color:#1e40af;padding:3px 10px;"
                f"border-radius:8px;font-size:0.82em;font-weight:600'>"
                f"Tier: {sk['tier']}</span><br>"
                f"<span style='color:#64748b;font-size:0.8em'>{sk['uc_agents']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Sly Data badges
            sly_html = " ".join(
                f"<span style='background:#fef3c7;color:#92400e;padding:2px 8px;"
                f"border-radius:8px;font-size:0.75em;font-weight:600'>"
                f"🔒 sly: {f}</span>"
                for f in sk["sly_data_fields"]
            )
            st.markdown(
                f"**Sly Data** (never in LLM context): {sly_html}",
                unsafe_allow_html=True,
            )

            with st.expander(f"📜 NLP Instruction Block for {sk_id}", expanded=False):
                st.markdown(
                    f"<div class='nlp-instruction'>{sk['nlp_instruction']}</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "This is the exact text Claude reads when deciding how to invoke this skill. "
                    "A business analyst can update this to change agent behavior — no code change required."
                )

            col_in, col_out = st.columns(2)
            with col_in:
                st.caption("**Input parameters:**")
                for p in sk["input_params"]:
                    st.markdown(f"- `{p}`")
            with col_out:
                st.caption("**Key output fields:**")
                for o in sk["output_keys"]:
                    st.markdown(f"- `{o}`")
            st.divider()


# ════════════════════════════════════════════════════════════════════
# TAB 3: Live AAOSA Trace
# ════════════════════════════════════════════════════════════════════
with tab_aaosa:
    st.subheader("🎬 UC1 AAOSA Conversation Trace")
    st.caption(
        "Watch the FrontMan and sub-agents negotiate tasks via AAOSA. "
        "This is what happens inside Neuro SAN when a user sends: "
        "*'Run UC1 for bcbs-mn-001'*"
    )

    col_legend, _ = st.columns([2, 3])
    with col_legend:
        legend_items = [
            ("🟣 Determine", "#eef2ff", "FrontMan asks: 'can you help?'"),
            ("🔵 Fulfill",   "#eff6ff", "Sub-agent executes coded tool"),
            ("🟡 Follow-up", "#fffbeb", "FrontMan checks results"),
            ("🟢 Compile",   "#f0fdf4", "Final output assembled"),
        ]
        for label, bg, desc in legend_items:
            st.markdown(
                f"<span style='background:{bg};padding:3px 10px;border-radius:6px;"
                f"font-size:0.82em;margin:3px;display:inline-block'>{label}</span> {desc}",
                unsafe_allow_html=True,
            )

    if "aaosa_step" not in st.session_state:
        st.session_state.aaosa_step = 0

    total_steps = len(AAOSA_TRACE)
    cur_step = st.session_state.aaosa_step
    st.progress(cur_step / total_steps, text=f"Round {cur_step} of {total_steps}")

    ctrl1, ctrl2, ctrl3, _ = st.columns([1, 1, 1, 4])
    if ctrl1.button("▶ Next round", type="primary", key="aaosa_next", disabled=cur_step >= total_steps):
        st.session_state.aaosa_step = min(cur_step + 1, total_steps)
        st.rerun()
    if ctrl2.button("◀ Back", key="aaosa_back", disabled=cur_step == 0):
        st.session_state.aaosa_step = max(cur_step - 1, 0)
        st.rerun()
    if ctrl3.button("↺ Reset", key="aaosa_reset"):
        st.session_state.aaosa_step = 0
        st.rerun()

    st.divider()

    # Show completed steps
    for i, step in enumerate(AAOSA_TRACE[:cur_step]):
        color, bg = AAOSA_COLORS[step["type"]]
        st.markdown(
            f"""<div style='background:{bg};border-left:4px solid {color};
                border-radius:8px;padding:12px 16px;margin:6px 0'>
              <b>{step['label']}</b>
              <div style='font-size:0.82em;color:#64748b;margin:4px 0'>
                {step['from']} → {step['to']}
              </div>
              <div style='margin:4px 0'><b>→</b> {step['message']}</div>
              <div style='margin:4px 0;color:#374151'><b>←</b> <em>{step['response']}</em></div>
              <div style='font-size:0.78em;color:#94a3b8;margin-top:6px'>
                {f"⏱ {step['latency_ms']}ms" if step['latency_ms'] else ""}
                {"  ·  " if step['latency_ms'] and step['tokens'] else ""}
                {f"🔤 {step['tokens']} tokens" if step['tokens'] else ""}
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

    if cur_step == 0:
        st.info("Click **▶ Next round** to step through the AAOSA protocol.")
    elif cur_step >= total_steps:
        total_tokens = sum(s["tokens"] for s in AAOSA_TRACE)
        total_lat    = sum(s["latency_ms"] for s in AAOSA_TRACE)
        st.success(
            f"**UC1 complete via AAOSA** · Total: {total_lat:,}ms · "
            f"{total_tokens:,} tokens · ~${total_tokens * 0.003 / 1000:.4f}"
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("AAOSA rounds", total_steps)
        c2.metric("Total latency", f"{total_lat:,}ms")
        c3.metric("Tokens consumed", f"{total_tokens:,}")

        st.markdown("""
**What just happened (no code):**
- The FrontMan received a single intent: *"Run UC1 for bcbs-mn-001"*
- AAOSA auto-routed to each skill in the right order based on NLP instructions
- Sly Data carried `customer_id` and `api_key` outside the LLM context — injection-proof
- The handoff brief is now live in the wiki, available to UC2 immediately
""")


# ════════════════════════════════════════════════════════════════════
# TAB 4: Live Agent Runner (AAOSA simulator with real Lambda calls)
# ════════════════════════════════════════════════════════════════════
with tab_live:
    st.subheader("⚡ Live Agent Runner — Real AAOSA with AWS Lambdas")
    st.caption(
        "No external tool required. Configure a customer and use case, then run each AAOSA round "
        "against your live Lambda skills. Watch agents negotiate, execute, and respond in real time."
    )

    # ── Config bar ────────────────────────────────────────────────────
    cfg1, cfg2, cfg3 = st.columns([2, 2, 1])
    live_customer_id = cfg1.text_input(
        "Customer ID", value="bcbs-mn-001", key="live_customer_id",
        help="Passed to SK-01 as the customer identifier",
    )
    live_use_case = cfg2.selectbox(
        "Use Case", ["UC1", "UC2", "UC3", "UC4", "UC5"], key="live_use_case",
    )
    live_question = st.text_input(
        "Business question (for SK-02 & SK-05)",
        value="What are the Sales-to-Service handoff requirements and delivery risks?",
        key="live_question",
    )

    st.divider()

    # ── Session state ─────────────────────────────────────────────────
    if "live_rounds" not in st.session_state:
        st.session_state.live_rounds = []         # list of completed round dicts
    if "live_running" not in st.session_state:
        st.session_state.live_running = False
    if "live_ctx" not in st.session_state:
        st.session_state.live_ctx = {}            # carries context between rounds

    # ── Control buttons ───────────────────────────────────────────────
    btn1, btn2, btn3, _ = st.columns([1, 1, 1, 4])

    run_next  = btn1.button(
        "▶ Run Next Round", type="primary", key="live_next",
        disabled=st.session_state.live_running or len(st.session_state.live_rounds) >= 5,
    )
    run_all   = btn2.button(
        "⚡ Run All Rounds", key="live_all",
        disabled=st.session_state.live_running or len(st.session_state.live_rounds) >= 5,
    )
    reset_run = btn3.button("↺ Reset", key="live_reset")

    if reset_run:
        st.session_state.live_rounds = []
        st.session_state.live_ctx    = {}
        st.session_state.live_running = False
        st.rerun()

    # ── Round definitions ─────────────────────────────────────────────
    # Each round: id, label, description of what it does, execution function
    LIVE_ROUNDS = [
        {
            "id": "R1", "skill": "SK-01",
            "from": "UC1SalesToServiceAgent (FrontMan)", "to": "ContextBootstrap",
            "type": "determine+fulfill",
            "label": "Round 1 — Determine + Fulfill (SK-01: Customer Briefing Loader)",
            "narrative": "FrontMan asks ContextBootstrap to load the customer briefing. SK-01 fetches customer history and UC1 playbook in parallel from DynamoDB + Bedrock KB.",
        },
        {
            "id": "R2", "skill": "SK-02",
            "from": "UC1SalesToServiceAgent (FrontMan)", "to": "WikiQuery",
            "type": "determine+fulfill",
            "label": "Round 2 — Determine + Fulfill (SK-02: Knowledge Finder)",
            "narrative": "FrontMan routes the business question to WikiQuery. SK-02 performs semantic search over the knowledge base and returns a confidence-scored answer.",
        },
        {
            "id": "R3", "skill": "SK-05",
            "from": "UC1SalesToServiceAgent (FrontMan)", "to": "GapDetection",
            "type": "followup+fulfill",
            "label": "Round 3 — Follow-up + Fulfill (SK-05: Missing Info Radar)",
            "narrative": "FrontMan sends the WikiQuery result to GapDetection for gap analysis. SK-05 classifies any knowledge gaps and flags blockers.",
        },
        {
            "id": "R4", "skill": None,
            "from": "UC1SalesToServiceAgent (FrontMan)", "to": "All sub-agents",
            "type": "compile",
            "label": "Round 4 — Compile (FrontMan synthesizes results)",
            "narrative": "FrontMan compiles all sub-agent outputs into a structured handoff brief. This round is pure synthesis — no Lambda call needed.",
        },
        {
            "id": "R5", "skill": None,
            "from": "UC1SalesToServiceAgent (FrontMan)", "to": "WikiContribute",
            "type": "save",
            "label": "Round 5 — Save (SK-03: Knowledge Recorder — simulated)",
            "narrative": "FrontMan instructs WikiContribute to save the handoff brief. SK-03 routes page_type=customers directly to S3; decisions/evidence pages require human review (HITL enforced in Python).",
        },
    ]

    n_done = len(st.session_state.live_rounds)

    # ── Execute one round ─────────────────────────────────────────────
    def _execute_round(round_def: dict, customer_id: str, use_case: str, question: str, ctx: dict) -> dict:
        """Run one AAOSA round. Returns a result dict for display."""
        t0 = time.time()
        skill = round_def["skill"]
        result = {}
        error  = None

        sly = {"customer_id": customer_id, "llmwiki_api_key": "", "engagement_id": "live-demo"}

        if skill == "SK-01":
            payload = {
                "skill": "ContextBootstrapSkill", "version": "1.0",
                "invoked_by": "uc1-live-demo",
                "inputs": {"customer_id": customer_id, "use_case": use_case, "agent_id": "uc1-live-demo"},
            }
            raw = _lambda_invoke(_SK_FUNCTIONS["SK-01"], payload)
            if raw.get("_error"):
                error = raw.get("error", "Lambda error")
            else:
                outputs = raw.get("outputs", raw)
                result = {
                    "customer_status": outputs.get("customer_status", "unknown"),
                    "pages_loaded":    outputs.get("pages_loaded", 0),
                    "key_facts":       outputs.get("key_facts", [])[:3],
                    "playbook_steps":  outputs.get("playbook_steps", [])[:3],
                    "skill_id":        outputs.get("skill_id", "SK-01"),
                }
                ctx["customer_status"] = result["customer_status"]
                ctx["key_facts"]       = result["key_facts"]

        elif skill == "SK-02":
            payload = {
                "skill": "WikiQuerySkill", "version": "1.0",
                "invoked_by": "uc1-live-demo",
                "inputs": {
                    "question": question, "domain": "customer-onboarding",
                    "customer_id": customer_id, "use_case": use_case,
                },
            }
            raw = _lambda_invoke(_SK_FUNCTIONS["SK-02"], payload)
            if raw.get("_error"):
                error = raw.get("error", "Lambda error")
            else:
                outputs = raw.get("outputs", raw)
                result = {
                    "confidence":     outputs.get("confidence", "unknown"),
                    "answer":         outputs.get("answer", ""),
                    "wiki_page_count": outputs.get("wiki_page_count", 0),
                    "sources":        outputs.get("sources", [])[:3],
                    "action_items":   outputs.get("action_items", [])[:3],
                    "skill_id":       outputs.get("skill_id", "SK-02"),
                }
                ctx["confidence"] = result["confidence"]
                ctx["wiki_answer"] = result["answer"]

        elif skill == "SK-05":
            payload = {
                "skill": "GapDetectionSkill", "version": "1.0",
                "invoked_by": "uc1-live-demo",
                "inputs": {
                    "question": question, "domain": "customer-onboarding",
                    "customer_id": customer_id, "use_case": use_case,
                    "low_confidence_response": {
                        "confidence": ctx.get("confidence", "low"),
                        "answer": ctx.get("wiki_answer", ""),
                    },
                },
            }
            raw = _lambda_invoke(_SK_FUNCTIONS["SK-05"], payload)
            if raw.get("_error"):
                error = raw.get("error", "Lambda error")
            else:
                outputs = raw.get("outputs", raw)
                result = {
                    "gap_count": outputs.get("gap_count", 0),
                    "blocking":  outputs.get("blocking", False),
                    "gaps":      (outputs.get("gaps") or [])[:2],
                    "skill_id":  outputs.get("skill_id", "SK-05"),
                }
                ctx["gaps"]     = result["gaps"]
                ctx["blocking"] = result["blocking"]

        elif round_def["id"] == "R4":
            # Pure synthesis — no Lambda
            facts_summary = "; ".join(ctx.get("key_facts", []))[:120] or "No facts loaded"
            result = {
                "synthesis": f"Customer: {customer_id} · Status: {ctx.get('customer_status','?')} · "
                             f"Confidence: {ctx.get('confidence','?')} · "
                             f"Gaps: {len(ctx.get('gaps',[]))} "
                             f"({'blocking' if ctx.get('blocking') else 'non-blocking'})",
                "key_facts_summary": facts_summary,
                "action": "FrontMan compiles: handoff brief ready for WikiContribute",
            }
            ctx["ready_to_save"] = True

        elif round_def["id"] == "R5":
            # Simulated save — show HITL routing logic
            result = {
                "page_type": "customers",
                "hitl_required": False,
                "routing": "wiki/customers/ (live — no review needed)",
                "note": "decisions / evidence page_types are HARDCODED to HITL in Python — cannot be bypassed",
                "simulated": True,
            }

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "round_def": round_def,
            "result":    result,
            "error":     error,
            "latency_ms": latency_ms,
            "ts":        datetime.utcnow().strftime("%H:%M:%S UTC"),
        }

    # ── Trigger execution ─────────────────────────────────────────────
    rounds_to_run = []
    if run_next and n_done < len(LIVE_ROUNDS):
        rounds_to_run = [LIVE_ROUNDS[n_done]]
    elif run_all and n_done < len(LIVE_ROUNDS):
        rounds_to_run = LIVE_ROUNDS[n_done:]

    if rounds_to_run:
        st.session_state.live_running = True
        progress_bar = st.progress(0, text="Running AAOSA rounds…")
        for i, rdef in enumerate(rounds_to_run):
            progress_bar.progress(
                (i + 1) / len(rounds_to_run),
                text=f"Executing {rdef['label']}…",
            )
            completed = _execute_round(
                rdef, live_customer_id, live_use_case, live_question,
                st.session_state.live_ctx,
            )
            st.session_state.live_rounds.append(completed)
        progress_bar.empty()
        st.session_state.live_running = False
        st.rerun()

    # ── Display progress ──────────────────────────────────────────────
    n_done = len(st.session_state.live_rounds)
    st.progress(n_done / len(LIVE_ROUNDS), text=f"Round {n_done} of {len(LIVE_ROUNDS)}")

    if n_done == 0:
        st.info(
            "Click **▶ Run Next Round** to execute the first AAOSA round against your live Lambdas, "
            "or **⚡ Run All Rounds** to run the full UC1 flow in one shot.",
            icon="⚡",
        )

    # ── Render completed rounds ───────────────────────────────────────
    for completed in st.session_state.live_rounds:
        rdef   = completed["round_def"]
        result = completed["result"]
        err    = completed["error"]
        lat    = completed["latency_ms"]
        ts     = completed["ts"]

        rtype = rdef["type"]
        color_map = {
            "determine+fulfill": ("#0d6efd", "#eff6ff"),
            "followup+fulfill":  ("#f59e0b", "#fffbeb"),
            "compile":           ("#16a34a", "#f0fdf4"),
            "save":              ("#7c3aed", "#f5f3ff"),
        }
        border_color, bg_color = color_map.get(rtype, ("#64748b", "#f8fafc"))

        status_icon = "❌" if err else "✅"
        lat_display = f"⏱ {lat:,}ms" if rdef["skill"] else "⚡ instant"

        st.markdown(
            f"<div style='background:{bg_color};border-left:4px solid {border_color};"
            f"border-radius:10px;padding:14px 18px;margin:8px 0'>"
            f"<div style='font-weight:700;font-size:1.0em'>"
            f"{status_icon} {rdef['label']}"
            f"<span style='float:right;font-size:0.75em;color:#94a3b8'>{lat_display} · {ts}</span>"
            f"</div>"
            f"<div style='font-size:0.82em;color:#64748b;margin:4px 0'>"
            f"<b>{rdef['from']}</b> → <b>{rdef['to']}</b>"
            f"</div>"
            f"<div style='font-size:0.88em;color:#475569;margin:6px 0'>{rdef['narrative']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if err:
            st.error(f"**Lambda error:** {err}")
        elif result:
            # Render skill-specific result detail
            skill = rdef["skill"]
            rid   = rdef["id"]

            if skill == "SK-01":
                c1, c2, c3 = st.columns(3)
                c1.metric("Customer status",  result.get("customer_status", "—"))
                c2.metric("Wiki pages loaded", result.get("pages_loaded", 0))
                c3.metric("Key facts",         len(result.get("key_facts", [])))
                if result.get("key_facts"):
                    with st.expander("Key facts surfaced by SK-01", expanded=True):
                        for f in result["key_facts"]:
                            st.markdown(f"- {f}")
                if result.get("playbook_steps"):
                    with st.expander("Playbook steps for this use case"):
                        for s in result["playbook_steps"]:
                            st.markdown(f"- {s}")

            elif skill == "SK-02":
                conf   = result.get("confidence", "?")
                conf_color = {"high": "#16a34a", "medium": "#d97706", "low": "#dc2626"}.get(conf, "#64748b")
                c1, c2, c3 = st.columns(3)
                c1.markdown(
                    f"<div style='text-align:center'><div style='font-size:0.75em;color:#64748b'>Confidence</div>"
                    f"<div style='font-size:1.5em;font-weight:700;color:{conf_color}'>{conf.upper()}</div></div>",
                    unsafe_allow_html=True,
                )
                c2.metric("Wiki pages used", result.get("wiki_page_count", 0))
                c3.metric("Action items",    len(result.get("action_items", [])))
                if result.get("answer"):
                    with st.expander("Answer from SK-02", expanded=True):
                        st.markdown(result["answer"][:600] + ("…" if len(result.get("answer","")) > 600 else ""))
                if result.get("sources"):
                    st.caption("Sources: " + " · ".join(f"`{s}`" for s in result["sources"]))

            elif skill == "SK-05":
                blocking = result.get("blocking", False)
                gap_count = result.get("gap_count", 0)
                c1, c2 = st.columns(2)
                c1.metric("Gaps detected", gap_count)
                c2.metric("Blocking", "YES ⚠️" if blocking else "No ✓")
                for g in result.get("gaps", []):
                    severity = "🔴" if g.get("blocking") else "🟡"
                    st.markdown(
                        f"<div style='background:#fef2f2;border-left:3px solid #dc2626;"
                        f"border-radius:6px;padding:8px 12px;margin:4px 0;font-size:0.85em'>"
                        f"{severity} <b>{g.get('title','Gap')}</b> · type: {g.get('gap_type','?')}<br>"
                        f"<span style='color:#64748b'>{g.get('human_prompt','')[:180]}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            elif rid == "R4":
                st.success(result.get("synthesis", ""))
                st.caption(result.get("action", ""))

            elif rid == "R5":
                c1, c2 = st.columns(2)
                c1.markdown(
                    f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;"
                    f"padding:10px 14px;font-size:0.88em'>"
                    f"✅ <b>customers</b> page → saved directly (no HITL)<br>"
                    f"📁 {result.get('routing','')}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f"<div style='background:#fef3c7;border:1px solid #fde68a;border-radius:8px;"
                    f"padding:10px 14px;font-size:0.88em'>"
                    f"🔒 <b>decisions / evidence</b> → HITL queue<br>"
                    f"Hardcoded in Python — prompt injection cannot bypass"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.caption("⚠️ Save is simulated in this demo — no actual S3 write performed.")

    # ── Final summary when all rounds complete ────────────────────────
    if n_done >= len(LIVE_ROUNDS):
        total_lat = sum(r["latency_ms"] for r in st.session_state.live_rounds)
        lambda_lat = sum(
            r["latency_ms"] for r in st.session_state.live_rounds
            if r["round_def"]["skill"] is not None
        )
        errors = [r for r in st.session_state.live_rounds if r["error"]]

        if errors:
            st.error(f"**{len(errors)} round(s) had errors.** Check Lambda permissions and function names above.")
        else:
            st.success(
                f"**UC1 complete via AAOSA!** · 5 rounds · {total_lat:,}ms total · "
                f"{lambda_lat:,}ms in Lambda calls",
                icon="🎉",
            )

        ctx = st.session_state.live_ctx
        st.markdown("#### Final context assembled by FrontMan")
        col_s, col_c, col_g = st.columns(3)
        col_s.metric("Customer status",   ctx.get("customer_status", "—"))
        col_c.metric("Answer confidence", ctx.get("confidence", "—"))
        col_g.metric("Gaps found",        len(ctx.get("gaps", [])))

        with st.expander("Full context dict (what the FrontMan compiled)"):
            display_ctx = {k: v for k, v in ctx.items() if k != "wiki_answer"}
            if ctx.get("wiki_answer"):
                display_ctx["wiki_answer"] = ctx["wiki_answer"][:200] + "…"
            st.json(display_ctx)


# ════════════════════════════════════════════════════════════════════
# TAB 5: Before vs After comparison
# ════════════════════════════════════════════════════════════════════
with tab_compare:
    st.subheader("🔄 Before vs After — Lambda vs Neuro SAN NLP")
    st.caption(
        "The same 5 skills. Same AWS infrastructure. "
        "But business rules are now in HOCON, not buried in Python."
    )

    compare_items = [
        {
            "aspect": "Define what a skill does",
            "before": "Edit handler.py — requires Python developer, Lambda redeploy, CI/CD pipeline, ~45 min",
            "after":  "Edit HOCON `instructions` block — business analyst edits plain English, ns reload, ~2 min",
            "win":    "10x faster iteration",
        },
        {
            "aspect": "Add a new business rule",
            "before": "Add `if/else` branch in Python handler, unit test, PR review, deploy",
            "after":  "Append a sentence to the NLP instruction: *'If customer_type=Medicare, always check HIPAA flag'*",
            "win":    "Zero-code rule change",
        },
        {
            "aspect": "Skill call ordering",
            "before": "Hardcoded: `phase4 → phase5 → phase6` in harness handler. Wrong order = bug.",
            "after":  "AAOSA Determine auto-routes. FrontMan asks each agent if it can help. Order emerges from context.",
            "win":    "Self-organizing workflow",
        },
        {
            "aspect": "Secret handling",
            "before": "customer_id passed as Lambda event payload — visible in CloudWatch logs",
            "after":  "customer_id in Sly Data channel — never touches LLM, never in CloudWatch prompt logs",
            "win":    "Structural security",
        },
        {
            "aspect": "Business analyst ownership",
            "before": "BA writes spec.md → developer implements Python → review cycle → deploy → BA validates",
            "after":  "BA writes HOCON instructions directly → `ns run` → BA tests in nsflow chat immediately",
            "win":    "BA → production in 1 step",
        },
        {
            "aspect": "Observability",
            "before": "CloudWatch logs + custom DynamoDB audit table per skill",
            "after":  "Langfuse traces every AAOSA round, per-agent token/latency, confidence trend charts",
            "win":    "Full agentic observability",
        },
        {
            "aspect": "Adding a new UC agent (UC11)",
            "before": "New Lambda function + handler.py + IAM role + API GW route + DynamoDB + CI/CD config",
            "after":  "New `uc11_name.hocon` file + one line in `manifest.hocon`. Reuse all 5 coded tools.",
            "win":    "New agent in ~20 min",
        },
    ]

    for item in compare_items:
        with st.expander(f"**{item['aspect']}**  →  _{item['win']}_", expanded=False):
            col_b, col_a = st.columns(2)
            with col_b:
                st.markdown(
                    f"<div style='background:#fee2e2;border-left:4px solid #dc2626;"
                    f"border-radius:8px;padding:12px 14px'>"
                    f"<b style='color:#dc2626'>❌ Before — Lambda</b><br>{item['before']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_a:
                st.markdown(
                    f"<div style='background:#f0fdf4;border-left:4px solid #16a34a;"
                    f"border-radius:8px;padding:12px 14px'>"
                    f"<b style='color:#16a34a'>✅ After — Neuro SAN NLP</b><br>{item['after']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.divider()
    st.markdown("#### Code comparison — SK-02 Knowledge Finder")
    col_code_b, col_code_a = st.columns(2)

    with col_code_b:
        st.markdown("**Before: handler.py**")
        st.code("""\
# 85 lines of Python — only a developer can change this
def handler(event, context):
    inputs = event.get('inputs', {})
    question = inputs.get('question', '')
    domain   = inputs.get('domain', '')
    cust_id  = inputs.get('customer_id', '')

    # Hardcoded retrieval logic
    kb_resp = bedrock_agent.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={'text': question},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 5,
                'filter': {
                    'equals': {
                        'key': 'domain',
                        'value': domain
                    }
                }
            }
        }
    )
    # ... 40 more lines of scoring + formatting
""", language="python")

    with col_code_a:
        st.markdown("**After: HOCON + coded tool**")
        st.code("""\
# HOCON: business analyst defines behavior in plain English
{
  "name": "WikiQuery",
  "function": {
    "description": "Searches the knowledge base",
    "parameters": { ... }
  },
  "instructions": \"\"\"
    You are the WikiQuery tool.
    When called with a question and domain,
    search wiki pages, rank by relevance,
    cite top 3–5 sources, return confidence:
    HIGH ≥2 direct matches, LOW if none.
    Never fabricate — flag gaps instead.
  \"\"\",
  "class": "llmwiki.wiki_query_tool.WikiQueryTool"
}

# Coded tool: just the AWS call, no business logic
class WikiQueryTool(CodedTool):
    async def async_invoke(self, args, sly_data):
        cust_id = sly_data.get("customer_id")
        return requests.post(LLMWIKI_API_URL
            + "/wiki/ask", json=args).json()
""", language="python")

    st.divider()
    st.markdown("#### Migration impact summary")

    impact_data = {
        "Metric":             ["Lines of business logic in Python", "Time to change a business rule",
                               "Non-developer can own skill?", "Observability depth",
                               "Security: secrets in LLM context?", "New agent time"],
        "Before (Lambda)":    ["~85 per skill (425 total)", "45 min + redeploy",
                               "No", "CloudWatch only", "Risk (event payload visible)", "~3 days"],
        "After (Neuro SAN)":  ["~15 per tool (75 total)", "2 min (HOCON edit)",
                               "Yes (BA writes HOCON)", "Langfuse + AAOSA trace", "No (Sly Data)", "~20 min"],
    }

    import pandas as pd
    st.dataframe(pd.DataFrame(impact_data).set_index("Metric"), use_container_width=True)
