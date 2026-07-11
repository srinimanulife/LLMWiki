"""
Wiki Manager — Upload, manage, and monitor knowledge.

Tab 1 — Upload     : drag-and-drop files, pick bucket + prefix, trigger ingest
Tab 2 — Knowledge  : source documents with cascade-delete preview
Tab 3 — Activity   : timeline of recent ingest operations
"""

import json
import os
import re
import time
import boto3
import streamlit as st
from botocore.config import Config
from collections import defaultdict
from datetime import datetime, timezone

# ── AWS clients ───────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
_s3  = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
_lam = boto3.client("lambda", region_name=AWS_REGION)
_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

# ── Bucket / table config ─────────────────────────────────────────────────────
AGENT_BUCKETS = [
    {"label": "Sales-to-Service Wiki",   "env": "WIKI_BUCKET",    "default": "llmwiki-278e7e22",               "icon": "📚"},
    {"label": "Problem Management Wiki", "env": "PM_WIKI_BUCKET", "default": "llmwiki-problem-mgnt-278e7e22",  "icon": "🛠️"},
]
REGISTRY_TABLE   = os.environ.get("REGISTRY_TABLE",  "llmwiki-source-registry")
INDEX_TABLE      = os.environ.get("DYNAMODB_INDEX",  "llmwiki-index")
LOG_TABLE        = os.environ.get("DYNAMODB_LOG",    "llmwiki-log")
INGEST_FN        = "llmwiki-ingest"
CONVERTER_FN     = os.environ.get("CONVERTER_LAMBDA", "llmwiki-converter")

BINARY_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
TEXT_EXTS   = {".md", ".txt", ".csv"}
ALL_EXTS    = sorted(BINARY_EXTS | TEXT_EXTS)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _bucket(a: dict) -> str:
    return os.environ.get(a["env"], a["default"])


def _fmt_size(n: int) -> str:
    if n < 1024:      return f"{n} B"
    if n < 1_048_576: return f"{n/1024:.1f} KB"
    return f"{n/1_048_576:.1f} MB"


def _friendly(key: str) -> str:
    """S3 key → human display name (no extension, title-cased, spaces)."""
    base = key.split("/")[-1]
    stem = re.sub(r"\.[^.]+$", "", base)
    return re.sub(r"[-_]+", " ", stem).title()


def _key_to_slug(key: str) -> str:
    base = key.split("/")[-1]
    return re.sub(r"[^a-z0-9-]", "-", re.sub(r"\.[^.]+$", "", base).lower()).strip("-")


def _presign(bucket: str, key: str, expiry: int = 3600) -> str:
    try:
        return _s3.generate_presigned_url("get_object",
            Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiry)
    except Exception:
        return ""


def _s3_list(bucket: str, prefix: str, max_keys: int = 500) -> list:
    try:
        resp = _s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys)
        return resp.get("Contents", [])
    except Exception:
        return []


def _get_cascade_info(slug: str) -> dict:
    """Return pages_created from source registry for a given slug."""
    try:
        tbl  = _ddb.Table(REGISTRY_TABLE)
        item = tbl.get_item(Key={"source_id": slug}).get("Item", {})
        if item:
            pages = item.get("pages_created", [])
            return {
                "slug":            slug,
                "pages_created":   [p if isinstance(p, str) else p.get("S", "") for p in pages],
                "original_upload": item.get("original_upload_key", ""),
                "raw_assets":      item.get("raw_assets_key", ""),
                "ingested_at":     item.get("ingested_at", ""),
                "found":           bool(item.get("status") == "wiki-page-created"),
            }
    except Exception:
        pass
    return {"slug": slug, "pages_created": [], "original_upload": "", "raw_assets": "", "ingested_at": "", "found": False}


def _do_cascade_delete(bucket: str, raw_key: str, info: dict) -> dict:
    """
    Delete the source S3 object + all generated wiki pages + DynamoDB entries.
    Returns {"deleted_s3": list, "deleted_ddb": int, "errors": list}
    """
    deleted_s3, deleted_ddb, errors = [], 0, []

    # Collect all S3 keys to delete
    keys_to_delete = [raw_key]
    if info.get("original_upload") and info["original_upload"] != raw_key:
        keys_to_delete.append(info["original_upload"])
    if info.get("raw_assets") and info["raw_assets"] not in keys_to_delete:
        keys_to_delete.append(info["raw_assets"])

    ddb_pairs = []
    for page_path in info.get("pages_created", []):
        parts = page_path.split("/", 1)
        if len(parts) == 2:
            page_type, page_slug = parts
            keys_to_delete.append(f"wiki/{page_type}/{page_slug}.md")
            ddb_pairs.append((page_type, page_slug))

    # S3 deletes
    for key in keys_to_delete:
        try:
            _s3.delete_object(Bucket=bucket, Key=key)
            deleted_s3.append(key)
        except Exception as e:
            errors.append(f"S3 delete {key}: {e}")

    # DynamoDB index deletes
    idx_tbl = _ddb.Table(INDEX_TABLE)
    for page_type, page_slug in ddb_pairs:
        try:
            idx_tbl.delete_item(Key={"page_type": page_type, "page_slug": page_slug})
            deleted_ddb += 1
        except Exception as e:
            errors.append(f"DDB index {page_type}/{page_slug}: {e}")

    # Registry delete
    try:
        _ddb.Table(REGISTRY_TABLE).delete_item(Key={"source_id": info["slug"]})
    except Exception as e:
        errors.append(f"Registry delete {info['slug']}: {e}")

    return {"deleted_s3": deleted_s3, "deleted_ddb": deleted_ddb, "errors": errors}


def _trigger_ingest(bucket: str, key: str, is_text: bool) -> dict:
    fn = INGEST_FN if is_text else CONVERTER_FN
    payload = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": 0}}}]}
    try:
        resp = _lam.invoke(FunctionName=fn, InvocationType="Event", Payload=json.dumps(payload).encode())
        return {"status": "queued", "fn": fn, "code": resp["StatusCode"]}
    except Exception as e:
        return {"error": str(e)}


def _get_all_registry_items(limit: int = 200) -> list:
    try:
        tbl   = _ddb.Table(REGISTRY_TABLE)
        items = []
        resp  = tbl.scan(Limit=limit)
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp and len(items) < limit:
            resp = tbl.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], Limit=limit - len(items))
            items.extend(resp.get("Items", []))
        return items
    except Exception:
        return []


def _recent_log(limit: int = 30) -> list:
    try:
        tbl  = _ddb.Table(LOG_TABLE)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp  = tbl.query(
            KeyConditionExpression="log_date = :d",
            FilterExpression="#op = :ingest",
            ExpressionAttributeNames={"#op": "operation"},
            ExpressionAttributeValues={":d": today, ":ingest": "ingest"},
            Limit=200, ScanIndexForward=False,
        )
        return resp.get("Items", [])[:limit]
    except Exception as e:
        return [{"_error": str(e)}]


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Wiki Manager", page_icon="🗂️", layout="wide")

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Page header */
.wm-hero { background:linear-gradient(135deg,#1a3a5c,#0f5c4a); color:#fff;
           padding:20px 28px; border-radius:12px; margin-bottom:22px; }
.wm-hero h1 { margin:0 0 4px 0; font-size:1.5em; font-weight:700; }
.wm-hero p  { margin:0; opacity:.85; font-size:.95em; }

/* Source document cards */
.source-card { background:#f8fbff; border:1px solid #d0e4f5; border-left:4px solid #1a6bbd;
               border-radius:8px; padding:14px 18px; margin-bottom:10px; }
.source-card h4 { margin:0 0 4px 0; color:#1a2f4a; font-size:1.0em; }
.source-card .meta { color:#6b7280; font-size:.82em; }

/* Wiki page chips */
.page-chip { display:inline-block; background:#e8f4ed; color:#1a5c35;
             border:1px solid #b5ddc5; border-radius:12px;
             padding:3px 10px; font-size:.78em; margin:2px 3px 2px 0; }
.page-chip-concept { background:#fef3e2; color:#92400e; border-color:#fde68a; }
.page-chip-entity  { background:#ede9fe; color:#4c1d95; border-color:#c4b5fd; }
.page-chip-question{ background:#fff1f2; color:#9f1239; border-color:#fecdd3; }

/* Delete preview box */
.del-preview { background:#fff5f5; border:1px solid #fca5a5; border-radius:8px;
               padding:14px 18px; margin:10px 0; }
.del-preview h4 { color:#dc2626; margin:0 0 8px 0; }
.del-item { font-size:.87em; padding:2px 0; color:#374151; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="wm-hero">
  <h1>🗂️ Wiki Manager</h1>
  <p>Upload documents · Manage your knowledge base · Track what the AI has learned</p>
</div>
""", unsafe_allow_html=True)

# ── Bucket selector (compact, in top bar) ─────────────────────────────────────
agent_labels = [f"{a['icon']} {a['label']}" for a in AGENT_BUCKETS]
sel_idx = st.selectbox("Knowledge base", range(len(AGENT_BUCKETS)),
                        format_func=lambda i: agent_labels[i],
                        key="wm_bucket_sel", label_visibility="collapsed")
agent  = AGENT_BUCKETS[sel_idx]
bucket = _bucket(agent)

tab_upload, tab_kb, tab_activity = st.tabs(["⬆️ Upload", "📚 Knowledge Base", "📋 Activity"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — UPLOAD
# ══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    col_form, col_help = st.columns([3, 2], gap="large")

    with col_form:
        st.markdown("#### Add documents to the knowledge base")
        st.caption("Supported: PDF, Word, PowerPoint, Excel, Markdown, CSV")

        cust_prefix = st.text_input(
            "Customer or topic (optional)",
            placeholder="e.g.  bcbs-mn-001  or  claims-processing",
            help="Groups documents by customer or topic in the knowledge base.",
            key="wm_prefix",
        )
        src_type = st.selectbox(
            "Document category",
            ["Auto-detect", "Articles & Research", "Meeting Notes", "Technical Papers",
             "Data Files", "Runbooks & SOPs"],
            key="wm_srctype",
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
            "Drop files here or click to browse",
            type=[e.lstrip(".") for e in ALL_EXTS],
            accept_multiple_files=True,
            key="wm_uploader",
        )

        trigger_ingest = st.checkbox(
            "Process immediately after upload",
            value=True,
            help="Triggers the AI to read the document and create wiki pages.",
        )

        upload_btn = st.button(
            "⬆️ Upload to Knowledge Base",
            type="primary",
            disabled=not uploaded_files,
            use_container_width=True,
        )

    with col_help:
        st.markdown("#### How it works")
        st.markdown("""
**1. Upload** → file lands in the knowledge base
**2. AI reads** → Claude extracts key ideas, entities, concepts
**3. Wiki pages** → structured pages appear in your knowledge base
**4. Searchable** → you can now ask questions about this document

**PDF & Office files** are automatically converted to text before processing.
**Markdown / CSV** are processed directly.

> 💡 Add a **customer prefix** (e.g. `bcbs-mn-001`) to keep documents organized by customer.
""")

        if uploaded_files:
            st.success(f"**{len(uploaded_files)} file{'s' if len(uploaded_files) > 1 else ''} ready to upload**")
            for uf in uploaded_files:
                ext = os.path.splitext(uf.name)[1].lower()
                kind = "📄 Text" if ext in TEXT_EXTS else "🗂 File"
                st.caption(f"{kind} · {uf.name} · {_fmt_size(uf.size)}")

    # ── Handle upload ─────────────────────────────────────────────────────────
    if upload_btn and uploaded_files:
        st.divider()
        for uf in uploaded_files:
            ext    = os.path.splitext(uf.name)[1].lower()
            is_text = ext in TEXT_EXTS

            # Determine folder
            folder = src_map.get(src_type)
            if folder is None:
                folder = ("articles" if ext == ".pdf"
                          else "notes" if ext in (".docx", ".doc", ".txt", ".csv")
                          else "data"  if ext in (".xlsx", ".xls")
                          else "articles")

            parts = ["raw"]
            if cust_prefix.strip():
                parts.append(cust_prefix.strip().replace(" ", "-"))
            parts.append(folder)
            dest_key = "/".join(parts) + f"/{uf.name}"

            with st.spinner(f"Uploading {uf.name}…"):
                try:
                    _s3.put_object(Bucket=bucket, Key=dest_key, Body=uf.read(),
                                   ContentType="text/plain" if is_text else "application/octet-stream")
                    st.success(f"✅ **{uf.name}** uploaded successfully")

                    if trigger_ingest:
                        ir = _trigger_ingest(bucket, dest_key, is_text)
                        if ir.get("error"):
                            st.warning(f"  Processing trigger failed: {ir['error']}")
                        else:
                            wait = "~30 seconds" if is_text else "~2 minutes"
                            st.info(f"  Processing started — wiki pages will appear in **{wait}**. "
                                    "Check the **Activity** tab to confirm.")
                except Exception as e:
                    st.error(f"✗ Failed to upload {uf.name}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════════════════
with tab_kb:

    # Session state for delete confirmation
    if "wm_confirm_slug" not in st.session_state:
        st.session_state.wm_confirm_slug = None
    if "wm_kb_refresh" not in st.session_state:
        st.session_state.wm_kb_refresh = 0

    col_hdr, col_ref = st.columns([6, 1])
    col_hdr.markdown("#### Source Documents")
    col_hdr.caption(
        "Documents you've uploaded and the wiki pages the AI generated from each one. "
        "Deleting a document also removes all AI-generated pages derived from it."
    )
    if col_ref.button("↺ Refresh", key="kb_refresh"):
        st.session_state.wm_kb_refresh += 1
        st.session_state.wm_confirm_slug = None
        st.rerun()

    # ── Load registry ─────────────────────────────────────────────────────────
    registry_items = _get_all_registry_items()

    if not registry_items:
        st.info("No documents processed yet. Upload a document in the **Upload** tab to get started.")
    else:
        # Sort by ingested_at descending
        registry_items.sort(key=lambda x: x.get("ingested_at", ""), reverse=True)

        PAGE_TYPE_LABELS = {
            "sources":   ("📑", "Summary"),
            "entities":  ("🏢", "Entity"),
            "concepts":  ("💡", "Concept"),
            "questions": ("❓", "Gap"),
            "runbooks":  ("📋", "Runbook"),
            "customers": ("👤", "Customer"),
            "decisions": ("⚖️", "Decision"),
            "sops":      ("📌", "SOP"),
            "evidence":  ("🔒", "Evidence"),
            "artifacts": ("📦", "Artifact"),
        }

        def _chip_class(page_type: str) -> str:
            return {
                "concepts":  "page-chip-concept",
                "entities":  "page-chip-entity",
                "questions": "page-chip-question",
            }.get(page_type, "page-chip")

        for item in registry_items:
            source_id  = item.get("source_id", "")
            source_key = item.get("source_key", item.get("original_upload_key", source_id))
            orig_key   = item.get("original_upload_key", source_key)
            pages      = item.get("pages_created", [])
            ingested   = item.get("ingested_at", "")[:10]
            n_pages    = len(pages)
            status     = item.get("status", "unknown")

            display_name = _friendly(orig_key or source_key)
            file_ext     = (orig_key or source_key).split(".")[-1].upper() if "." in (orig_key or source_key) else "DOC"

            is_deleting = (st.session_state.wm_confirm_slug == source_id)

            # ── Delete confirmation block ──────────────────────────────────────
            if is_deleting:
                st.markdown(f"""
<div class="del-preview">
<h4>⚠️ Delete "{display_name}"?</h4>
<p style="margin:0 0 10px 0;font-size:.9em;color:#374151;">
  This will permanently remove the source document and all AI-generated wiki pages derived from it:
</p>
""", unsafe_allow_html=True)

                items_to_delete = []
                if source_key:
                    items_to_delete.append(("📄", "Source file", source_key))
                if orig_key and orig_key != source_key:
                    items_to_delete.append(("📎", "Original upload", orig_key))

                for page_path in pages:
                    parts = page_path.split("/", 1)
                    if len(parts) == 2:
                        pt, ps = parts
                        icon, label = PAGE_TYPE_LABELS.get(pt, ("📄", pt.title()))
                        items_to_delete.append((icon, f"{label} page", f"wiki/{pt}/{ps}.md"))

                for icon, label, key in items_to_delete:
                    st.markdown(
                        f'<div class="del-item">{icon} <b>{label}</b> — <code style="font-size:.8em">{key}</code></div>',
                        unsafe_allow_html=True
                    )

                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("")

                dc1, dc2, dc3 = st.columns([2, 1.5, 1.5])
                dc1.markdown(f"**{len(items_to_delete)} items will be deleted** and removed from the AI knowledge base.")

                if dc2.button(f"🗑 Delete all {len(items_to_delete)} items", type="primary",
                               key=f"del_confirm_{source_id}"):
                    cascade_info = {
                        "slug": source_id,
                        "pages_created": pages,
                        "original_upload": orig_key,
                        "raw_assets": item.get("raw_assets_key", ""),
                    }
                    with st.spinner("Deleting…"):
                        result = _do_cascade_delete(bucket, source_key, cascade_info)
                    if result["errors"]:
                        st.warning(f"Deleted with warnings: {'; '.join(result['errors'][:2])}")
                    else:
                        st.success(
                            f"✅ Deleted **{display_name}** — "
                            f"{len(result['deleted_s3'])} files and {result['deleted_ddb']} wiki index entries removed."
                        )
                    st.session_state.wm_confirm_slug = None
                    time.sleep(0.5)
                    st.rerun()

                if dc3.button("Cancel", key=f"del_cancel_{source_id}"):
                    st.session_state.wm_confirm_slug = None
                    st.rerun()

                continue  # Don't render normal card while confirming

            # ── Normal source card ─────────────────────────────────────────────
            with st.container():
                c_info, c_actions = st.columns([6, 1])

                with c_info:
                    status_dot = "🟢" if status == "wiki-page-created" else "🟡"
                    st.markdown(
                        f"**{display_name}**  "
                        f"<span style='background:#e5e7eb;color:#374151;border-radius:4px;"
                        f"padding:1px 7px;font-size:.78em;'>{file_ext}</span>  "
                        f"{status_dot}",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Ingested {ingested} · {n_pages} wiki page{'s' if n_pages != 1 else ''} generated")

                    if pages:
                        chip_html = ""
                        for page_path in pages:
                            parts = page_path.split("/", 1)
                            if len(parts) == 2:
                                pt, ps = parts
                                icon, label = PAGE_TYPE_LABELS.get(pt, ("📄", pt.title()))
                                nice = _friendly(ps)
                                chip_html += (
                                    f'<span class="page-chip {_chip_class(pt)}">'
                                    f'{icon} {nice}</span>'
                                )
                        if chip_html:
                            st.markdown(chip_html, unsafe_allow_html=True)

                with c_actions:
                    url = _presign(bucket, source_key)
                    if url:
                        st.markdown(
                            f'<a href="{url}" target="_blank" style="display:block;text-align:center;'
                            f'padding:4px 8px;border-radius:4px;background:#f3f4f6;color:#374151;'
                            f'font-size:.8em;text-decoration:none;margin-bottom:6px;">⬇ Download</a>',
                            unsafe_allow_html=True,
                        )
                    if st.button("🗑 Delete", key=f"del_start_{source_id}",
                                  help="Remove document and all generated wiki pages"):
                        st.session_state.wm_confirm_slug = source_id
                        st.rerun()

                st.divider()

    # ── Raw uploads not yet ingested ──────────────────────────────────────────
    raw_items = _s3_list(bucket, "raw/", max_keys=100)
    if raw_items:
        ingested_slugs = {item.get("source_id", "") for item in registry_items}
        pending = [
            it for it in raw_items
            if not it["Key"].endswith("/")
            and _key_to_slug(it["Key"]) not in ingested_slugs
        ]
        if pending:
            with st.expander(f"📂 {len(pending)} file(s) awaiting processing"):
                st.caption("These files are in the knowledge base but have not been processed by the AI yet.")
                for it in sorted(pending, key=lambda x: x.get("LastModified", ""), reverse=True)[:20]:
                    k   = it["Key"]
                    ts  = it.get("LastModified")
                    ts_s = ts.strftime("%Y-%m-%d") if ts else "?"
                    ext  = os.path.splitext(k)[1].lower()
                    is_text = ext in TEXT_EXTS
                    pc1, pc2 = st.columns([5, 1])
                    pc1.markdown(f"**{_friendly(k)}** `{ext}` — {ts_s}")
                    if pc2.button("▶ Process", key=f"pend_ingest_{k}"):
                        ir = _trigger_ingest(bucket, k, is_text)
                        if ir.get("error"):
                            st.error(ir["error"])
                        else:
                            st.success(f"Processing started for `{k}`")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ACTIVITY
# ══════════════════════════════════════════════════════════════════════════════
with tab_activity:
    col_hdr2, col_ref2 = st.columns([6, 1])
    col_hdr2.markdown("#### Recent AI Processing Activity")
    col_hdr2.caption("Documents the AI has processed today and what wiki pages were created.")
    if col_ref2.button("↺ Refresh", key="act_refresh"):
        st.rerun()

    log = _recent_log(limit=30)

    if not log:
        st.info("No processing activity today. Upload a document to get started.")
    elif "_error" in log[0]:
        st.warning(f"Could not read activity log: {log[0]['_error']}")
    else:
        for entry in log:
            ts_raw  = entry.get("timestamp_id", "")
            ts      = ts_raw.split("#")[0][:16].replace("T", " ") if ts_raw else "—"
            src     = entry.get("source_slug", entry.get("source_key", "unknown"))
            pages   = entry.get("pages_created", [])
            n_pages = len(pages)
            ok      = n_pages > 0

            lc1, lc2 = st.columns([6, 1])
            with lc1:
                st.markdown(
                    f"{'✅' if ok else '⚠️'} **{_friendly(src)}** — "
                    f"{'Generated ' + str(n_pages) + ' wiki page' + ('s' if n_pages != 1 else '') if ok else 'No pages generated'}  "
                    f"<span style='color:#6b7280;font-size:.83em;'>  {ts} UTC</span>",
                    unsafe_allow_html=True,
                )
                if pages:
                    page_names = "  ·  ".join(_friendly(p.split("/")[-1]) for p in pages[:4])
                    extra = f"  + {len(pages)-4} more" if len(pages) > 4 else ""
                    st.caption(f"{page_names}{extra}")
            lc2.caption(ts.split(" ")[1] if " " in ts else "")

            st.divider()

    # ── Manual trigger ────────────────────────────────────────────────────────
    with st.expander("🔧 Manually trigger processing on an existing file"):
        st.caption("Use this if a file was uploaded via CLI or if processing failed.")
        mc1, mc2 = st.columns(2)
        man_key  = mc1.text_input("S3 key", placeholder="raw/articles/my-doc.md", key="wm_man_key")
        man_mode = mc2.radio("Processing mode", ["Text → Wiki", "Binary → Convert → Wiki"],
                              horizontal=True, key="wm_man_mode")
        if st.button("▶ Start Processing", disabled=not man_key.strip(), key="wm_man_go"):
            with st.spinner("Starting…"):
                ir = _trigger_ingest(bucket, man_key.strip(), "Binary" not in man_mode)
            if ir.get("error"):
                st.error(ir["error"])
            else:
                st.success(f"Processing started via `{ir['fn']}`. Check Activity tab in ~60s.")
