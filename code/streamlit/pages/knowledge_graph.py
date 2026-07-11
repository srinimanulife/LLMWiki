"""
OKF Knowledge Graph — switches between S2S and PM harness views.

S2S:  Force-directed graph of wiki/sources, wiki/concepts, wiki/entities etc.
       Edges = [[wikilinks]] between pages.

PM:   Cross-product dependency graph of kb/ knowledge files + PRB records.
       Edges = cross-system impact mentions (Facets→EAM, QNXT→FRM, etc.)
       plus PRB records linked to their primary + secondary products.
"""

import os, re, json
import boto3
import streamlit as st
import streamlit.components.v1 as components
from collections import defaultdict
from botocore.config import Config

AWS_REGION     = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
S2S_BUCKET     = os.environ.get("WIKI_BUCKET",    "llmwiki-278e7e22")
PM_BUCKET      = os.environ.get("PM_WIKI_BUCKET", "llmwiki-problem-mgnt-278e7e22")

_s3 = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))

st.set_page_config(page_title="Knowledge Graph", page_icon="🕸️", layout="wide")

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.kg-hero { background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
           color:#e0e0e0; padding:18px 28px; border-radius:12px; margin-bottom:14px; }
.kg-hero h1 { margin:0 0 3px 0; font-size:1.4em; font-weight:700; color:#fff; }
.kg-hero p  { margin:0; opacity:.8; font-size:.88em; }
.stat-box   { background:#f8faff; border:1px solid #d0e0f0; border-radius:8px;
              padding:10px 14px; text-align:center; }
.stat-box .num { font-size:1.7em; font-weight:700; color:#1a6bbd; }
.stat-box .lbl { font-size:.78em; color:#6b7280; }
.node-card  { background:#f0f7ff; border:1px solid #bbd6f5; border-left:4px solid #1a6bbd;
              border-radius:8px; padding:13px 16px; margin:8px 0; }
.okf-fm     { background:#1e1e2e; color:#cdd6f4; border-radius:6px;
              padding:10px 14px; font-family:monospace; font-size:.78em; margin:8px 0; }
.link-chip  { display:inline-block; background:#e8f0fe; color:#1967d2;
              border:1px solid #c5d8ff; border-radius:10px;
              padding:2px 8px; font-size:.76em; margin:2px 2px 2px 0; }
.link-chip-in { background:#f0fdf4; color:#166534; border-color:#bbf7d0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="kg-hero">
  <h1>🕸️ OKF Knowledge Graph</h1>
  <p>Every knowledge page is a node · Every link/reference is an edge · Select a harness to see its graph</p>
</div>
""", unsafe_allow_html=True)

# ── Harness selector — honour ?harness=pm query param ─────────────────────────
_RADIO_OPTIONS = ["📚 Sales-to-Service (S2S)", "🛠️ Problem Management (UC-PM)"]
_qp = st.query_params.get("harness", "").lower()
if _qp == "pm":
    st.session_state["kg_harness"] = _RADIO_OPTIONS[1]
elif _qp == "s2s":
    st.session_state["kg_harness"] = _RADIO_OPTIONS[0]

_rc1, _rc2 = st.columns([6, 1])
with _rc1:
    harness_choice = st.radio(
        "Knowledge domain",
        _RADIO_OPTIONS,
        horizontal=True,
        key="kg_harness",
    )
with _rc2:
    if st.button("↺ Refresh", help="Re-scan S3 now (cache clears automatically every 2 min)"):
        st.session_state["kg_clear_cache"] = True
        st.rerun()
is_pm = "PM" in harness_choice

# ═══════════════════════════════════════════════════════════════════════════════
# S2S GRAPH — OKF wikilink graph from wiki/sources, concepts, entities …
# ═══════════════════════════════════════════════════════════════════════════════
TYPE_COLORS_S2S = {
    "sources":   "#3b82f6", "concepts":  "#f59e0b", "entities":  "#8b5cf6",
    "questions": "#ef4444", "customers": "#10b981", "runbooks":  "#06b6d4",
    "decisions": "#f97316", "sops":      "#84cc16", "evidence":  "#ec4899",
    "artifacts": "#6366f1",
}
TYPE_ICONS_S2S = {
    "sources":"📑","concepts":"💡","entities":"🏢","questions":"❓",
    "customers":"👤","runbooks":"📋","decisions":"⚖️","sops":"📌",
    "evidence":"🔒","artifacts":"📦",
}
TYPE_LABELS_S2S = {
    "sources":"Source Summaries","concepts":"Concepts","entities":"Entities",
    "questions":"Knowledge Gaps","customers":"Customers","runbooks":"Runbooks",
    "decisions":"Decisions","sops":"SOPs","evidence":"Evidence","artifacts":"Artifacts",
}

@st.cache_data(ttl=120, show_spinner=False)
def load_s2s_graph():
    nodes, edges, fm_map, content_map = {}, [], {}, {}
    by_type = defaultdict(list)
    try:
        resp = _s3.list_objects_v2(Bucket=S2S_BUCKET, Prefix="wiki/", MaxKeys=500)
    except Exception as e:
        return {}, [], {}, {}, defaultdict(list), str(e)
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".md"):
            continue
        parts = key.replace("wiki/", "").replace(".md", "").split("/")
        if len(parts) != 2:
            continue
        page_type, slug = parts
        try:
            body = _s3.get_object(Bucket=S2S_BUCKET, Key=key)["Body"].read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        fm, title = {}, slug.replace("-", " ").title()
        if body.startswith("---"):
            end = body.find("---", 3)
            if end > 0:
                for line in body[3:end].split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip().strip('"\'')
                        if k.strip() == "title":
                            title = v.strip().strip('"\'')
        okf_score = sum([bool(fm.get("type")), bool(fm.get("title")), bool(fm.get("resource", fm.get("source_file","")))])
        nodes[slug] = {"id":slug,"label":title[:40],"title":title,"type":page_type,
                       "color":TYPE_COLORS_S2S.get(page_type,"#94a3b8"),
                       "okf_score":okf_score,"fm":fm}
        fm_map[slug], content_map[slug] = fm, body
        by_type[page_type].append(slug)
        for link in re.findall(r"\[\[([^\]]+)\]\]", body):
            target = link.split("|")[0].strip()
            if target != slug:
                edges.append({"from":slug,"to":target})
    return nodes, edges, fm_map, content_map, by_type, None

# ═══════════════════════════════════════════════════════════════════════════════
# PM GRAPH — cross-product dependency graph from kb/ + specs/ + PRB JSON
# ═══════════════════════════════════════════════════════════════════════════════
PM_PRODUCT_COLORS = {
    "Facets":     "#3b82f6",
    "QNXT":       "#10b981",
    "EDM":        "#f59e0b",
    "EAM":        "#f97316",
    "TCS":        "#8b5cf6",
    "NetworX":    "#ef4444",
    "FRM":        "#ec4899",
}
PM_NODE_TYPES = {
    "product":  {"color":"#1a6bbd","icon":"🏭","label":"Product KB"},
    "skill":    {"color":"#7c3aed","icon":"🔧","label":"Skill Spec"},
    "problem":  {"color":"#dc2626","icon":"🔴","label":"Problem Record"},
    "spec":     {"color":"#059669","icon":"📘","label":"PM Spec"},
}
# Cross-system impact map: product → products it impacts
PM_CROSS_SYSTEM = {
    "Facets":  ["EDM","EAM","FRM","TCS"],
    "QNXT":    ["EDM","EAM","FRM","TCS"],
    "EAM":     ["Facets","QNXT","EDM"],
    "EDM":     ["FRM"],
    "TCS":     ["Facets","QNXT"],
    "NetworX": ["FRM","Facets","QNXT"],
    "FRM":     ["EDM"],
}
# KB files in PM bucket
PM_KB_FILES = {
    "Facets":    "kb/facets.md",
    "QNXT":      "kb/qnxt.md",
    "EDM-EAM-TCS":"kb/edm-eam-tcs.md",
    "NetworX-FRM":"kb/networx-frm.md",
}
PM_SPEC_FILES = {
    "SK-06 Problem Classifier":    "specs/pm-skill-spec-sk06.md",
    "PM Use Case Brief":           "specs/pm-uc-brief.md",
    "PM Workflow Spec":            "specs/pm-workflow-spec.md",
}

@st.cache_data(ttl=120, show_spinner=False)
def load_pm_graph():
    nodes, edges = {}, []
    by_type = defaultdict(list)
    content_map = {}

    # ── Product KB nodes ──────────────────────────────────────────
    for prod, key in PM_KB_FILES.items():
        try:
            body = _s3.get_object(Bucket=PM_BUCKET, Key=key)["Body"].read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        # Count PRB references in this file
        prb_refs = re.findall(r"PRB-[A-Z0-9-]+", body)
        categories = list(set(re.findall(r"###\s+(PRB-[^\n]+)", body)))[:5]
        nodes[prod] = {
            "id": prod, "label": prod, "title": prod,
            "type": "product",
            "color": PM_PRODUCT_COLORS.get(prod.split("-")[0], "#1a6bbd"),
            "prb_count": len(prb_refs),
            "categories": categories,
            "body": body[:3000],
        }
        by_type["product"].append(prod)
        content_map[prod] = body

    # ── Skill spec nodes ──────────────────────────────────────────
    for name, key in PM_SPEC_FILES.items():
        try:
            body = _s3.get_object(Bucket=PM_BUCKET, Key=key)["Body"].read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        slug = name.lower().replace(" ", "-")
        nodes[slug] = {
            "id": slug, "label": name[:35], "title": name,
            "type": "skill" if "SK-" in name else "spec",
            "color": "#7c3aed" if "SK-" in name else "#059669",
            "body": body[:2000],
        }
        by_type["skill" if "SK-" in name else "spec"].append(slug)
        content_map[slug] = body

    # ── Problem record nodes from wiki/pm/drafts/ ─────────────────
    try:
        resp = _s3.list_objects_v2(Bucket=PM_BUCKET, Prefix="wiki/pm/drafts/", MaxKeys=100)
    except Exception:
        resp = {}
    prb_rca = {}
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith("rca-draft.json"):
            continue
        parts = key.split("/")
        prb_id = parts[3] if len(parts) >= 4 else "PRB-?"
        try:
            body = _s3.get_object(Bucket=PM_BUCKET, Key=key)["Body"].read().decode("utf-8", errors="ignore")
            data = json.loads(body)
        except Exception:
            data = {}
        prb_rca[prb_id] = data
        risk  = data.get("risk_tier", "medium")
        prod  = data.get("product", "Facets")
        cat   = data.get("category", "Unknown")
        slug  = prb_id.lower()
        nodes[slug] = {
            "id": slug, "label": prb_id, "title": f"{prb_id} — {data.get('title','')[:50]}",
            "type": "problem",
            "color": "#dc2626" if risk in ("high","P1") else "#f97316" if risk in ("medium","P2") else "#6b7280",
            "risk": risk, "product": prod, "category": cat,
            "body": json.dumps(data, indent=2)[:2000],
        }
        by_type["problem"].append(slug)
        content_map[slug] = json.dumps(data, indent=2)

    # ── Edges: cross-system impacts (product → product) ──────────
    for src, targets in PM_CROSS_SYSTEM.items():
        src_node = src  # e.g. "Facets"
        # find the best matching node key
        src_key = next((k for k in nodes if src.lower() in k.lower()), None)
        for tgt in targets:
            tgt_key = next((k for k in nodes if tgt.lower() in k.lower()), None)
            if src_key and tgt_key and src_key != tgt_key:
                edges.append({"from": src_key, "to": tgt_key, "type": "cross-system"})

    # ── Edges: PRB → primary product + cross-product mentions ────
    for prb_id, data in prb_rca.items():
        slug = prb_id.lower()
        primary_prod = data.get("product", "")
        prod_key = next((k for k in nodes if primary_prod.lower() in k.lower()
                         and nodes[k]["type"] == "product"), None)
        if prod_key:
            edges.append({"from": slug, "to": prod_key, "type": "primary"})
        # cross-system from contributing_factors
        for factor in data.get("contributing_factors", []):
            for prod in PM_PRODUCT_COLORS:
                if prod.lower() in factor.lower() and prod.lower() != primary_prod.lower():
                    tgt_key = next((k for k in nodes if prod.lower() in k.lower()
                                    and nodes[k]["type"] == "product"), None)
                    if tgt_key:
                        edges.append({"from": slug, "to": tgt_key, "type": "cross-impact"})

    # ── Edges: specs → products they cover ───────────────────────
    for slug in by_type["spec"] + by_type["skill"]:
        body = content_map.get(slug, "")
        for prod in PM_PRODUCT_COLORS:
            if prod.lower() in body.lower():
                prod_key = next((k for k in nodes if prod.lower() in k.lower()
                                 and nodes[k]["type"] == "product"), None)
                if prod_key:
                    edges.append({"from": slug, "to": prod_key, "type": "covers"})

    return nodes, edges, content_map, by_type, None


# ── Deferred cache clear (button was clicked on previous run) ─────────────────
if st.session_state.pop("kg_clear_cache", False):
    load_s2s_graph.clear()
    load_pm_graph.clear()

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER — common vis.js builder used by both branches
# ═══════════════════════════════════════════════════════════════════════════════
def build_vis_html(vis_nodes, vis_edges, legend_html="", height=520):
    vis_data = json.dumps({"nodes": vis_nodes, "edges": vis_edges})
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;background:#0f0f1a;font-family:sans-serif;}}
#graph{{width:100%;height:{height}px;}}
#info{{position:absolute;top:8px;right:8px;background:rgba(255,255,255,.95);
       border-radius:8px;padding:10px 14px;max-width:240px;font-size:12px;
       box-shadow:0 2px 12px rgba(0,0,0,.3);display:none;}}
#info h4{{margin:0 0 5px 0;font-size:13px;}}
#info .meta{{color:#6b7280;font-size:11px;}}
.legend{{position:absolute;bottom:8px;left:8px;background:rgba(255,255,255,.9);
         border-radius:8px;padding:7px 12px;font-size:11px;line-height:1.8;}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:middle;}}
</style></head><body>
<div style="position:relative;">
<div id="graph"></div>
<div id="info">
  <h4 id="i-title">—</h4>
  <div class="meta" id="i-meta"></div>
</div>
<div class="legend">{legend_html}</div>
</div>
<script src="https://unpkg.com/vis-network@9.1.9/dist/vis-network.min.js"></script>
<script>
const D={vis_data};
const net=new vis.Network(document.getElementById("graph"),{{
  nodes:new vis.DataSet(D.nodes),
  edges:new vis.DataSet(D.edges),
}},{{
  physics:{{barnesHut:{{gravitationalConstant:-9000,springLength:130,damping:.13}},
            stabilization:{{iterations:250,fit:true}}}},
  interaction:{{hover:true,zoomView:true}},
  nodes:{{shape:"dot",borderWidth:2}},
  edges:{{smooth:{{type:"dynamic"}},arrows:{{to:{{enabled:true,scaleFactor:.5}}}}}},
}});
net.on("click",p=>{{
  if(p.nodes.length>0){{
    const n=D.nodes.find(x=>x.id===p.nodes[0]);
    document.getElementById("i-title").textContent=n.label;
    document.getElementById("i-meta").textContent=n.title.replace(/<br>/g,"\\n");
    document.getElementById("info").style.display="block";
    window.parent.postMessage({{type:"node_click",slug:n.id}},"*");
  }}else document.getElementById("info").style.display="none";
}});
net.on("stabilizationIterationsDone",()=>net.fit());
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════════════════════

if not is_pm:
    # ── S2S graph ──────────────────────────────────────────────────
    with st.spinner("Building S2S knowledge graph…"):
        nodes, edges, fm_map, content_map, by_type, err = load_s2s_graph()
    if err:
        st.error(f"Could not load S2S wiki: {err}")
        st.stop()
    if not nodes:
        st.info("No S2S wiki pages found. Ingest documents first.")
        st.stop()

    # Stats
    inbound = defaultdict(int)
    for e in edges:
        inbound[e["to"]] += 1
    okf_ok = sum(1 for n in nodes.values() if n["okf_score"] == 3)
    okf_part = sum(1 for n in nodes.values() if n["okf_score"] in (1,2))

    sc = st.columns(5)
    for col, (num, lbl, clr) in zip(sc, [
        (len(nodes), "Wiki Pages", "#1a6bbd"),
        (len(edges), "Knowledge Links", "#1a6bbd"),
        (len(by_type), "Domain Types", "#1a6bbd"),
        (okf_ok,   "OKF Conformant ✓", "#16a34a"),
        (okf_part, "Partial OKF", "#d97706"),
    ]):
        col.markdown(
            f'<div class="stat-box"><div class="num" style="color:{clr}">{num}</div>'
            f'<div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)
    st.markdown("")

    # Filters
    fc1, fc2, fc3 = st.columns([3,3,1])
    all_types = sorted(by_type.keys())
    sel_types = fc1.multiselect("Filter by type", all_types, default=all_types,
        format_func=lambda t: f"{TYPE_ICONS_S2S.get(t,'')} {TYPE_LABELS_S2S.get(t,t.title())}")
    search_q  = fc2.text_input("Search pages", placeholder="e.g. cloud, QNXT, RCA…")
    max_n     = fc3.number_input("Max", 20, 500, 200, 20)

    filtered = {s for t in sel_types for s in by_type.get(t,[])}
    if search_q.strip():
        q = search_q.strip().lower()
        filtered = {s for s in filtered if q in s or q in nodes[s]["title"].lower()}
    filtered = set(list(filtered)[:max_n])
    f_edges   = [e for e in edges if e["from"] in filtered and e["to"] in filtered]

    vis_nodes = []
    for s in filtered:
        n = nodes[s]
        ib = sum(1 for e in f_edges if e["to"] == s)
        vis_nodes.append({
            "id": s, "label": n["label"],
            "title": f"{n['title']}<br>Type: {n['type']}<br>Links in: {ib}",
            "color": {"background": n["color"], "border":"#fff",
                      "highlight":{"background":n["color"],"border":"#000"}},
            "size": 12 + min(ib*3, 28),
            "font": {"color":"#eee","size":10},
        })
    vis_edges = [{"from":e["from"],"to":e["to"],
                  "color":{"color":"#94a3b8","opacity":.5}} for e in f_edges]

    legend_html = "".join(
        f'<span class="dot" style="background:{TYPE_COLORS_S2S.get(t,"#ccc")}"></span>'
        f'{TYPE_ICONS_S2S.get(t,"")} {t}&nbsp;&nbsp;'
        for t in sel_types if t in TYPE_COLORS_S2S
    )

    # Two-column layout
    gc, dc = st.columns([3,2], gap="large")
    with gc:
        st.markdown(f"**{len(filtered)} nodes · {len(f_edges)} edges**")
        components.html(build_vis_html(vis_nodes, vis_edges, legend_html), height=540)

    with dc:
        st.markdown("#### 📖 Page Detail")
        sorted_slugs = sorted(filtered, key=lambda s: nodes[s]["title"])
        sel_s = st.selectbox("Select a page",sorted_slugs,
            format_func=lambda s: f"{TYPE_ICONS_S2S.get(nodes[s]['type'],'')} {nodes[s]['title']}",
            key="kg_s2s_sel")
        if sel_s:
            n = nodes[sel_s]; fm = fm_map.get(sel_s,{}); content = content_map.get(sel_s,"")
            okf_s = n["okf_score"]
            badge = ("✅ OKF conformant" if okf_s==3 else f"⚠️ Partial ({okf_s}/3)" if okf_s>0 else "❌ No frontmatter")
            st.markdown(
                f"**{TYPE_ICONS_S2S.get(n['type'],'')} {n['title']}**  "
                f"<span style='background:{TYPE_COLORS_S2S.get(n['type'],'#ccc')}20;"
                f"color:{TYPE_COLORS_S2S.get(n['type'],'#555')};border-radius:4px;"
                f"padding:1px 8px;font-size:.78em;'>{n['type']}</span>  "
                f"<span style='font-size:.78em;color:#6b7280;'>{badge}</span>",
                unsafe_allow_html=True)
            if fm:
                fm_lines = "\n".join(f"{k}: {v}" for k,v in fm.items()
                    if k in ("type","title","description","resource","okf_version","date","tags","status"))
                st.markdown(
                    f'<div class="okf-fm">---<br>{"<br>".join(fm_lines.split(chr(10)))}<br>---</div>',
                    unsafe_allow_html=True)
            out_l = [e["to"] for e in f_edges if e["from"]==sel_s]
            in_l  = [e["from"] for e in f_edges if e["to"]==sel_s]
            if out_l or in_l:
                st.markdown("**Connected pages:**")
                html = "".join(
                    f'<span class="link-chip">→ {TYPE_ICONS_S2S.get(nodes.get(t,{}).get("type",""),"")} {nodes.get(t,{}).get("title",t)[:26]}</span>'
                    for t in sorted(set(out_l))
                )
                html += "".join(
                    f'<span class="link-chip link-chip-in">← {TYPE_ICONS_S2S.get(nodes.get(t,{}).get("type",""),"")} {nodes.get(t,{}).get("title",t)[:26]}</span>'
                    for t in sorted(set(in_l))
                )
                st.markdown(html, unsafe_allow_html=True)
                st.caption(f"→ {len(out_l)} outbound  ·  ← {len(in_l)} inbound")
            with st.expander("📄 Read page content"):
                body = content
                if body.startswith("---"):
                    end = body.find("---", 3)
                    if end > 0: body = body[end+3:].strip()
                st.markdown(body[:3000] + ("\n\n_(truncated)_" if len(body)>3000 else ""))

    # OKF Index + Conformance (S2S only)
    st.divider()
    st.markdown("## 🗂️ OKF Index — Domain Overview")
    idx_cols = st.columns(min(len(by_type), 5))
    for ci, page_type in enumerate(sorted(by_type.keys())):
        slugs = sorted(by_type[page_type], key=lambda s: nodes[s]["title"])
        with idx_cols[ci % len(idx_cols)]:
            with st.expander(f"{TYPE_ICONS_S2S.get(page_type,'📄')} **{TYPE_LABELS_S2S.get(page_type,page_type.title())}** ({len(slugs)})", expanded=False):
                for s in slugs:
                    ib = inbound.get(s,0); ob = sum(1 for e in edges if e["from"]==s)
                    st.markdown(
                        f"**{nodes[s]['title']}**  "
                        f"<span style='color:#6b7280;font-size:.8em;'>↔ {ib+ob}</span>",
                        unsafe_allow_html=True)

    st.divider()
    st.markdown("## 🔍 OKF Conformance Audit")
    full_ok = [(s,n) for s,n in nodes.items() if n["okf_score"]==3]
    partial  = [(s,n) for s,n in nodes.items() if n["okf_score"] in (1,2)]
    none_ok  = [(s,n) for s,n in nodes.items() if n["okf_score"]==0]
    cc1,cc2,cc3 = st.columns(3)
    with cc1:
        with st.expander(f"✅ Fully conformant ({len(full_ok)})", expanded=False):
            for s,n in sorted(full_ok,key=lambda x:x[1]["title"])[:20]:
                st.caption(f"{TYPE_ICONS_S2S.get(n['type'],'')} {n['title']}")
    with cc2:
        with st.expander(f"⚠️ Partial ({len(partial)})", expanded=True):
            for s,n in sorted(partial,key=lambda x:x[1]["title"])[:20]:
                fm = fm_map.get(s,{})
                missing = [f for f in ["type","title","resource"] if not fm.get(f)]
                st.caption(f"{TYPE_ICONS_S2S.get(n['type'],'')} {n['title']} — missing: {', '.join(missing)}")
    with cc3:
        with st.expander(f"❌ No frontmatter ({len(none_ok)})", expanded=len(none_ok)>0):
            for s,n in sorted(none_ok,key=lambda x:x[1]["title"])[:20]:
                st.caption(f"{TYPE_ICONS_S2S.get(n['type'],'')} {n['title']}")

    # Harness context panel
    st.divider()
    st.markdown("## 🤖 OKF Context for S2S Harness Phases")
    st.caption("Which pages each skill phase draws from, ranked by authority (most inbound links first).")
    SKILL_Q = {
        "SK-01 Context Bootstrap": ["customers","sources"],
        "SK-02 Wiki Query":        ["concepts","entities","sources"],
        "SK-04 Artifact Resolution":["artifacts","sops","decisions"],
        "SK-05 Gap Detection":     ["questions"],
    }
    hc = st.columns(len(SKILL_Q))
    for col,(sk,types) in zip(hc,SKILL_Q.items()):
        with col:
            pages = [s for t in types for s in by_type.get(t,[])]
            pages.sort(key=lambda s:-inbound.get(s,0))
            st.markdown(f"**{sk}**")
            st.caption(" · ".join(types))
            for s in pages[:5]:
                n2 = nodes.get(s,{})
                ib = inbound.get(s,0)
                st.markdown(f"<span style='font-size:.8em;'>{'⭐ ' if ib>=5 else '· '}{TYPE_ICONS_S2S.get(n2.get('type',''),'')} {n2.get('title',s)[:28]}</span>", unsafe_allow_html=True)
            if len(pages)>5: st.caption(f"+ {len(pages)-5} more")

else:
    # ── PM graph ───────────────────────────────────────────────────
    with st.spinner("Building Problem Management knowledge graph…"):
        pm_nodes, pm_edges, pm_content, pm_by_type, err = load_pm_graph()
    if err:
        st.error(f"Could not load PM wiki: {err}")
        st.stop()
    if not pm_nodes:
        st.info("No PM knowledge files found.")
        st.stop()

    # Stats
    pm_inbound = defaultdict(int)
    for e in pm_edges:
        pm_inbound[e["to"]] += 1

    sc = st.columns(4)
    for col,(num,lbl,clr) in zip(sc,[
        (len(pm_nodes), "Knowledge Nodes", "#1a6bbd"),
        (len(pm_edges), "Cross-System Links", "#dc2626"),
        (len(pm_by_type.get("problem",[])), "Problem Records (RCAs)", "#f97316"),
        (len(pm_by_type.get("product",[])), "Product Domains", "#059669"),
    ]):
        col.markdown(
            f'<div class="stat-box"><div class="num" style="color:{clr}">{num}</div>'
            f'<div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)
    st.markdown("")

    # Filters
    pf1, pf2 = st.columns([3, 1])
    all_pm_types = sorted(pm_by_type.keys())
    sel_pm_types = pf1.multiselect(
        "Filter by node type", all_pm_types, default=all_pm_types,
        format_func=lambda t: f"{PM_NODE_TYPES.get(t,{}).get('icon','📄')} {PM_NODE_TYPES.get(t,{}).get('label',t.title())}")
    show_prb_only = pf2.checkbox("PRBs only", value=False)

    pm_filtered = {s for t in sel_pm_types for s in pm_by_type.get(t,[])}
    if show_prb_only:
        pm_filtered = {s for s in pm_filtered if pm_nodes[s]["type"] == "problem"}
    pm_f_edges = [e for e in pm_edges if e["from"] in pm_filtered and e["to"] in pm_filtered]

    # Build vis nodes
    pm_vis_nodes = []
    for s in pm_filtered:
        n = pm_nodes[s]
        ib = pm_inbound.get(s, 0)
        ntype = n["type"]
        # Products = large hexagons, PRBs = small dots, specs = triangles
        shape = "diamond" if ntype == "product" else "dot" if ntype == "problem" else "square"
        size  = (35 if ntype=="product" else 10 + min(ib*2,20) if ntype=="problem" else 20)
        pm_vis_nodes.append({
            "id": s,
            "label": n["label"],
            "title": n["title"].replace("'","")[:80],
            "color": {"background": n["color"], "border":"#fff",
                      "highlight":{"background":n["color"],"border":"#000"}},
            "shape": shape,
            "size": size,
            "font": {"color":"#eee","size": 13 if ntype=="product" else 9},
        })

    edge_colors = {"cross-system":"#ef4444","primary":"#3b82f6","cross-impact":"#f97316","covers":"#6b7280"}
    pm_vis_edges = []
    for e in pm_f_edges:
        ec = edge_colors.get(e.get("type",""), "#94a3b8")
        pm_vis_edges.append({
            "from": e["from"], "to": e["to"],
            "color": {"color": ec, "opacity": 0.65},
            "width": 2 if e.get("type")=="cross-system" else 1,
        })

    legend_html = (
        '<span class="dot" style="background:#1a6bbd;width:14px;height:14px;border-radius:3px;"></span> Product KB &nbsp;'
        '<span class="dot" style="background:#7c3aed;width:14px;height:14px;border-radius:2px;transform:rotate(45deg);display:inline-block;"></span> Skill/Spec &nbsp;'
        '<span class="dot" style="background:#dc2626;"></span> Problem Record &nbsp;&nbsp;'
        '<span style="color:#ef4444;">— cross-system</span> &nbsp;'
        '<span style="color:#3b82f6;">— primary</span> &nbsp;'
        '<span style="color:#f97316;">— cross-impact</span>'
    )

    gc, dc = st.columns([3, 2], gap="large")
    with gc:
        st.markdown(
            f"**{len(pm_filtered)} nodes · {len(pm_f_edges)} edges**  "
            f"<span style='font-size:.82em;color:#6b7280;'>◆ = Product · ● = Problem Record · ■ = Spec/Skill</span>",
            unsafe_allow_html=True)
        components.html(build_vis_html(pm_vis_nodes, pm_vis_edges, legend_html, height=540), height=560)

    with dc:
        st.markdown("#### 📖 Node Detail")
        sorted_pm = sorted(pm_filtered, key=lambda s: (pm_nodes[s]["type"], pm_nodes[s]["label"]))
        sel_pm = st.selectbox(
            "Select a node", sorted_pm,
            format_func=lambda s: f"{PM_NODE_TYPES.get(pm_nodes[s]['type'],{}).get('icon','📄')} {pm_nodes[s]['label']}",
            key="kg_pm_sel")

        if sel_pm:
            n = pm_nodes[sel_pm]
            ntype = n["type"]
            type_meta = PM_NODE_TYPES.get(ntype, {})

            st.markdown(
                f"**{type_meta.get('icon','📄')} {n['title']}**  "
                f"<span style='background:{n['color']}20;color:{n['color']};"
                f"border-radius:4px;padding:1px 8px;font-size:.78em;'>{type_meta.get('label',ntype)}</span>",
                unsafe_allow_html=True)

            # Type-specific detail
            if ntype == "problem":
                c1,c2,c3 = st.columns(3)
                c1.metric("Risk", n.get("risk","—").upper())
                c2.metric("Product", n.get("product","—"))
                c3.metric("Category", n.get("category","—"))

            elif ntype == "product":
                st.caption(f"Problem records in KB: {n.get('prb_count',0)}")
                cross_out = [e["to"] for e in pm_f_edges if e["from"]==sel_pm and e.get("type")=="cross-system"]
                cross_in  = [e["from"] for e in pm_f_edges if e["to"]==sel_pm and e.get("type")=="cross-system"]
                if cross_out:
                    st.markdown(f"**Downstream systems it can break:** {', '.join(pm_nodes.get(t,{}).get('label',t) for t in cross_out)}")
                if cross_in:
                    st.markdown(f"**Upstream systems that can break it:** {', '.join(pm_nodes.get(t,{}).get('label',t) for t in cross_in)}")

            # Connected nodes
            out_l = [e["to"]   for e in pm_f_edges if e["from"]==sel_pm]
            in_l  = [e["from"] for e in pm_f_edges if e["to"]==sel_pm]
            if out_l or in_l:
                st.markdown("**Linked nodes:**")
                html = "".join(
                    f'<span class="link-chip">→ {PM_NODE_TYPES.get(pm_nodes.get(t,{}).get("type",""),{}).get("icon","📄")} {pm_nodes.get(t,{}).get("label",t)[:26]}</span>'
                    for t in sorted(set(out_l))
                )
                html += "".join(
                    f'<span class="link-chip link-chip-in">← {PM_NODE_TYPES.get(pm_nodes.get(t,{}).get("type",""),{}).get("icon","📄")} {pm_nodes.get(t,{}).get("label",t)[:26]}</span>'
                    for t in sorted(set(in_l))
                )
                st.markdown(html, unsafe_allow_html=True)

            with st.expander("📄 View raw content"):
                body = pm_content.get(sel_pm,"")
                if body.startswith("{"):
                    try:
                        st.json(json.loads(body))
                    except Exception:
                        st.code(body[:2000])
                else:
                    st.markdown(body[:3000] + ("\n\n_(truncated)_" if len(body)>3000 else ""))

    # PM: Problem records table
    st.divider()
    st.markdown("## 🔴 Problem Records (RCA Drafts)")
    st.caption("All problem records from the PM harness — click to expand and see root cause, risk tier, and cross-system factors.")

    prb_nodes = [(s, pm_nodes[s]) for s in sorted(pm_by_type.get("problem",[]),
                  key=lambda s: pm_nodes[s].get("risk","z"))]
    for slug, n in prb_nodes:
        risk_color = {"high":"#fef2f2","P1":"#fef2f2"}.get(n.get("risk",""),"#fff7ed")
        risk_icon  = {"high":"🔴","P1":"🔴","medium":"🟠","P2":"🟠"}.get(n.get("risk",""),"🟡")
        with st.expander(f"{risk_icon} **{n['label']}** — {n.get('category','?')} · {n.get('product','?')} · Risk: {n.get('risk','?').upper()}"):
            body = pm_content.get(slug,"")
            if body.startswith("{"):
                try:
                    data = json.loads(body)
                    st.markdown(f"**Root cause:** {data.get('root_cause','—')[:300]}")
                    cfs = data.get("contributing_factors",[])
                    if cfs:
                        st.markdown("**Contributing factors:**")
                        for cf in cfs[:3]:
                            st.markdown(f"- {str(cf)[:150]}")
                    ps = data.get("pattern_section","")
                    if ps:
                        st.markdown(f"**Cross-system pattern:** {str(ps)[:300]}")
                except Exception:
                    st.code(body[:500])
            # Linked products
            linked = [pm_nodes[e["to"]]["label"] for e in pm_f_edges
                      if e["from"]==slug and e["to"] in pm_nodes]
            if linked:
                st.caption(f"Cross-system links: {', '.join(linked)}")

    # PM: Harness context panel
    st.divider()
    st.markdown("## 🤖 OKF Context for PM Harness Phases")
    st.caption("Which knowledge nodes each PM harness phase draws from.")
    PM_PHASE_MAP = {
        "Phase 4 — Load Prior Knowledge (SK-01)": ["product", "spec"],
        "Phase 5 — RCA & Cross-System Patterns (SK-02)": ["product","problem"],
        "Phase 6 — Gap Detection (SK-05)": ["problem"],
        "Phase 7 — Fill KEDB Templates (SK-04)": ["spec"],
    }
    pc = st.columns(len(PM_PHASE_MAP))
    for col,(phase,types) in zip(pc,PM_PHASE_MAP.items()):
        with col:
            pages = [s for t in types for s in pm_by_type.get(t,[])]
            pages.sort(key=lambda s: -pm_inbound.get(s,0))
            st.markdown(f"**{phase}**")
            for s in pages[:5]:
                n2 = pm_nodes.get(s,{})
                ib = pm_inbound.get(s,0)
                icon = PM_NODE_TYPES.get(n2.get("type",""),{}).get("icon","📄")
                st.markdown(f"<span style='font-size:.8em;'>{'⭐ ' if ib>=3 else '· '}{icon} {n2.get('label',s)[:28]}</span>",
                            unsafe_allow_html=True)
            if len(pages)>5: st.caption(f"+ {len(pages)-5} more")
