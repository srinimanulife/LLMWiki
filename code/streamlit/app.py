"""
LLMWiki Streamlit UI — entry point.
All content pages live in pages/. This file renders the home screen.
"""

import os
import json
import boto3
import streamlit as st
from botocore.config import Config
from datetime import datetime

AWS_REGION       = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
WIKI_BUCKET      = os.environ.get("WIKI_BUCKET",    "")
PM_WIKI_BUCKET   = os.environ.get("PM_WIKI_BUCKET", "llmwiki-problem-mgnt-278e7e22")
QUERY_LAMBDA     = os.environ.get("QUERY_LAMBDA",   "llmwiki-query")
DYNAMODB_INDEX   = os.environ.get("DYNAMODB_INDEX", "llmwiki-index")
DYNAMODB_LOG     = os.environ.get("DYNAMODB_LOG",   "llmwiki-log")
REGISTRY_TABLE   = os.environ.get("REGISTRY_TABLE", "llmwiki-source-registry")

s3           = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
dynamodb     = boto3.resource("dynamodb", region_name=AWS_REGION)

st.set_page_config(
    page_title="LLMWiki",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.answer-card { background:#f0f9f4; border-left:4px solid #16a34a;
               border-radius:8px; padding:16px 20px; margin:10px 0; }
.src-chip { display:inline-block; background:#e0f2fe; color:#075985;
            border:1px solid #bae6fd; border-radius:10px;
            padding:2px 10px; font-size:.8em; margin:2px 3px 2px 0; }
.gap-banner { background:#fefce8; border:1px solid #fde68a; border-radius:8px;
              padding:12px 16px; font-size:.9em; margin:8px 0; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 📚 LLMWiki")
    st.caption("AI-powered knowledge platform")
    st.divider()

    st.page_link("pages/knowledge_hub.py",  label="📖 Knowledge Hub",  icon="📖")
    st.page_link("pages/lambda_harness.py", label="⚡ Lambda Harness", icon="⚡")
    st.page_link("pages/neuro_harness.py",  label="🧠 Neuro Harness",  icon="🧠")
    st.page_link("pages/platform.py",       label="⚙️ Platform",       icon="⚙️")

    st.divider()
    st.caption(f"Region: `{AWS_REGION}`")


# ── Home screen ───────────────────────────────────────────────────
st.markdown("## 📚 LLMWiki")
st.caption("AI-powered knowledge platform · Select a page from the sidebar to get started")

c1, c2 = st.columns(2, gap="large")

with c1:
    with st.container(border=True):
        st.markdown("### 📖 Knowledge Hub")
        st.caption("Upload documents, ask questions, explore what the AI knows")
        st.page_link("pages/knowledge_hub.py", label="Open Knowledge Hub →", icon="📖")

    with st.container(border=True):
        st.markdown("### ⚡ Lambda Harness")
        st.caption("UC1 Sales-to-Service · UC-PM Problem Management · 8 enforced phases")
        st.page_link("pages/lambda_harness.py", label="Open Lambda Harness →", icon="⚡")

with c2:
    with st.container(border=True):
        st.markdown("### 🧠 Neuro Harness")
        st.caption("Neuro SAN AAOSA multi-agent chat with live OTel traces")
        st.page_link("pages/neuro_harness.py", label="Open Neuro Harness →", icon="🧠")

    with st.container(border=True):
        st.markdown("### ⚙️ Platform")
        st.caption("Cost & usage · Governance · Configuration · Health checks")
        st.page_link("pages/platform.py", label="Open Platform →", icon="⚙️")
