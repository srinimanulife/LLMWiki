# LLMWiki — UX Architecture Improvement

**Problem:** The current UI has 8 navigation destinations across two patterns (sidebar radio + page_link), dead pages (wiki_status, activity_log, expansion_lab are in app.py but unreachable), duplicate concepts split across pages, and no clear customer journey. A first-time customer sees 7 sidebar items and doesn't know where to start.

**Principle:** One destination per job to be done. Group by harness, not by feature.

---

## Current State — What Exists (and What's Wrong)

| Current Page | What It Does | Problem |
|---|---|---|
| `app.py` → Ask a Question | RAG query + domain selector + PM source tabs | OK core feature — buried in radio nav |
| `app.py` → Browse Knowledge | S3 wiki page reader | Rarely used by customers; developer tool |
| `app.py` → Discover Gaps | Gap list + test questions | Useful but orphaned from upload flow |
| `app.py` → _(dead)_ Wiki Status | Bar charts, config dump | Unreachable; moved to governance |
| `app.py` → _(dead)_ Activity Log | DynamoDB log entries | Unreachable; moved to governance |
| `app.py` → _(dead)_ Expansion Lab | Duplicate of Discover Gaps | Unreachable dead code |
| `pages/wiki_manager.py` | Upload + manage + activity | Separate page for "manage" — disjointed from query |
| `pages/harness_demo.py` | UC1 + UC-PM hard harness chat | Good — needs metrics alongside |
| `pages/skill_studio.py` | Neuro SAN chat + nsflow iframe + variant switcher | Good — needs metrics alongside |
| `pages/governance.py` | Cost + cache + rate limits | Platform ops — keep but re-label |
| `pages/knowledge_graph.py` | Force-directed graph | Nice visual — no customer action from it |
| `pages/neuro_san.py` | Duplicate Neuro SAN UI (different tabs) | Redundant with skill_studio.py |
| `pages/traces.py` | Lambda + Neuro SAN OTel traces | Buried under Platform; should be per-harness |

**Root problems:**
1. Lambda RAG and Neuro SAN are the two harnesses but their related features (query, metrics, traces, gaps) are scattered across 5+ pages
2. Upload and Query are on different pages with no visual connection
3. `neuro_san.py` and `skill_studio.py` are effectively the same page — duplicate navigation
4. Three dead pages (`wiki_status`, `activity_log`, `expansion_lab`) inflate the code but are unreachable
5. The sidebar mixes radio-nav and page_link — two different navigation patterns confuse users

---

## Proposed Structure — 4 Pages

```
┌─────────────────────────────────────────────────────────────────┐
│  📚 LLMWiki                                                      │
│  ─────────────────────────────────────────────────────────────  │
│  > 📖  Knowledge Hub       ← Upload + Query + Gaps (combined)   │
│  > ⚡  Lambda Harness       ← UC1 + UC-PM + metrics + traces     │
│  > 🧠  Neuro Harness        ← Neuro SAN chat + metrics + traces  │
│  > ⚙️  Platform             ← Governance + cost + config         │
└─────────────────────────────────────────────────────────────────┘
```

All four items are `st.page_link()` — one consistent navigation pattern. No more radio inside the main area.

---

## Page 1 — Knowledge Hub (`pages/knowledge_hub.py`)

**Job to be done:** A customer uploads documents, asks questions, and sees knowledge gaps — all in one place without page-hopping.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  📖 Knowledge Hub                                            │
│  Upload documents · Ask questions · Explore what's known    │
├──────────────────────┬──────────────────────────────────────┤
│  LEFT COLUMN (35%)   │  RIGHT COLUMN (65%)                  │
│                      │                                      │
│  ┌────────────────┐  │  ┌──────────────────────────────┐   │
│  │ ⬆ Upload       │  │  │  Knowledge area selector     │   │
│  │                │  │  │  [Sales-to-Service ▼]        │   │
│  │ Drag & drop    │  │  ├──────────────────────────────┤   │
│  │ PDF DOCX PPTX  │  │  │  Example questions (chips)   │   │
│  │ MD CSV XLSX    │  │  ├──────────────────────────────┤   │
│  │                │  │  │  [ Type your question... ]   │   │
│  │ [Upload →]     │  │  │  [ 🔍 Get Answer            ]│   │
│  ├────────────────┤  │  ├──────────────────────────────┤   │
│  │ 📚 Uploaded    │  │  │  Answer (confidence badge)   │   │
│  │ (last 5 docs)  │  │  │  Sources (chips)             │   │
│  ├────────────────┤  │  │  Provenance expander         │   │
│  │ 💡 Open Gaps   │  │  ├──────────────────────────────┤   │
│  │ 3 gaps         │  │  │  💡 Knowledge gaps found     │   │
│  │ [Fill →]       │  │  │  → Upload to fill them       │   │
│  └────────────────┘  │  └──────────────────────────────┘   │
└──────────────────────┴──────────────────────────────────────┘
```

**What moves here (consolidating from current pages):**
- Upload panel from `wiki_manager.py` Tab 1
- Ask a Question from `app.py` (all three radio sections fold into this)
- Gap count widget from Discover Gaps — a compact count badge, not a full sub-page
- Recent upload list (last 5 docs from wiki_manager Tab 2, condensed)

**What is removed:**
- Browse Knowledge sub-page (S3 page reader) — accessed via provenance expander inline, not a top-level nav item. Customers don't browse S3 keys.
- Discover Gaps as a standalone page — gap badges appear inline after each answer, gap count appears in left column. Full gap management moves to Platform > Health.
- The three dead pages in `app.py` are deleted.

**PM domain source tabs:** Kept, but moved into a collapsible "📂 Source documents" expander at the bottom of the right column — not rendered by default (they fire S3 reads on every page load today).

---

## Page 2 — Lambda Harness (`pages/lambda_harness.py`)

**Job to be done:** Run and monitor the Lambda-backed hard harness agent workflows (UC1 Sales-to-Service, UC-PM Problem Management) with metrics and traces immediately visible alongside the chat.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚡ Lambda Harness                                               │
│  Hard harness · 8 system-enforced phases · Gatekeeper validated │
│                                                                  │
│  [UC1 Sales-to-Service]  [UC-PM Problem Management]  ← tabs     │
├──────────────────┬──────────────────────────────────────────────┤
│  CHAT (55%)      │  METRICS + TRACES (45%)                      │
│                  │                                              │
│  Phase tracker   │  ┌──────────────────────────────────────┐   │
│  (locked plan    │  │  📊 This Session                     │   │
│  panel)          │  │  Phases: 8/8  Duration: 42s          │   │
│                  │  │  Confidence: 🟢 High                  │   │
│  Chat messages   │  │  Artifacts: 2 written                │   │
│  stream here     │  ├──────────────────────────────────────┤   │
│                  │  │  ⚡ Lambda Traces (last 10)           │   │
│  [Start Harness] │  │  span | question | confidence        │   │
│                  │  │  ─────┼──────────┼──────────         │   │
│                  │  │  ...DynamoDB spans table...          │   │
│                  │  ├──────────────────────────────────────┤   │
│                  │  │  📈 30-day usage                     │   │
│                  │  │  Queries: 47  Cost: $0.12            │   │
│                  │  │  Cache hit: 68%                      │   │
│                  │  └──────────────────────────────────────┘   │
└──────────────────┴──────────────────────────────────────────────┘
```

**What moves here (consolidating):**
- `harness_demo.py` — the chat panel, phase tracker, plan panel (all existing content)
- Lambda traces tab from `traces.py` — shown inline on the right, auto-refreshes after each run
- Lambda cost/usage metrics from `governance.py` — a compact "this session" + "30-day" summary panel, not the full governance page

**What is removed:**
- The standalone `traces.py` Lambda tab is no longer a separate page — it lives here
- The verbose "How it works" caption blocks at the bottom of traces — moved to a single `?` tooltip icon

---

## Page 3 — Neuro Harness (`pages/neuro_harness.py`)

**Job to be done:** Run and monitor Neuro SAN AAOSA agent workflows with skill inspection, live traces, and before/after comparison in one place.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  🧠 Neuro Harness                                                │
│  AAOSA multi-agent · NLP-driven skills · Phoenix traces         │
│                                                                  │
│  [UC1 Sales-to-Service]  [UC-PM Problem Management]  ← tabs     │
├──────────────────┬──────────────────────────────────────────────┤
│  CHAT (55%)      │  SKILLS + TRACES (45%)                       │
│                  │                                              │
│  Agent messages  │  ┌──────────────────────────────────────┐   │
│  with otrace     │  │  🧠 Active Skills                    │   │
│  chain display   │  │  ContextBootstrap → WikiQuery →      │   │
│                  │  │  ArtifactResolution → GapDetection   │   │
│  [Send]          │  │  → WikiContribute                    │   │
│                  │  ├──────────────────────────────────────┤   │
│  ── Compare ──   │  │  🔍 OTel Traces (from Phoenix)       │   │
│  [Before: Hard   │  │  span | tool | question | answer     │   │
│   Harness]       │  │  ─────┼──────┼──────────┼────────   │   │
│  [After: Neuro]  │  │  ...Phoenix spans table...          │   │
│  Diff view       │  ├──────────────────────────────────────┤   │
│                  │  │  ⚙️ Skill Variant                    │   │
│                  │  │  Switch NLP variant live →           │   │
│                  │  │  [Conservative] [Balanced] [Bold]    │   │
│                  │  └──────────────────────────────────────┘   │
└──────────────────┴──────────────────────────────────────────────┘
```

**What moves here (consolidating):**
- `skill_studio.py` — chat panel, skill spec viewer, variant switcher
- `neuro_san.py` — before/after comparison tab, nsflow iframe (accessible via "Open full Neuro SAN UI" link, not embedded by default)
- Neuro SAN traces tab from `traces.py` — shown inline on right panel, auto-polls Phoenix
- Knowledge Graph (`knowledge_graph.py`) — accessible via a "🕸️ View Knowledge Graph" button that opens it in a modal or new tab; not a separate sidebar item (customers don't navigate to it directly)

**What is removed:**
- `neuro_san.py` as a standalone page — its content fully merges into this page
- `skill_studio.py` as a standalone page — same
- The nsflow full iframe embedded by default (slow, confusing for customers) — replace with a "Open nsflow" link button
- Phoenix full UI iframe from `traces.py` — replace with "Open Phoenix" link button

---

## Page 4 — Platform (`pages/platform.py`)

**Job to be done:** Operations team views cost, cache health, rate limits, and configuration. Not customer-facing — labeled "Platform" not "Admin" or "Governance".

**Layout — three sub-tabs:**

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️ Platform                                                     │
│                                                                  │
│  [📊 Cost & Usage]  [🔒 Governance]  [🔧 Configuration]  ← tabs │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Cost & Usage tab:                                               │
│  - 30-day cost breakdown (Bedrock, Lambda, DynamoDB, S3)         │
│  - Cache hit rate trend                                          │
│  - Per-caller attribution table                                  │
│  - Rate limit status                                             │
│                                                                  │
│  Governance tab:                                                 │
│  - Knowledge gap full list with dismiss / view stub actions      │
│  - Source registry table (all ingested documents)               │
│  - Activity log (recent ingest operations)                       │
│                                                                  │
│  Configuration tab:                                              │
│  - AWS region, bucket names, Lambda function names               │
│  - KB IDs, model in use                                          │
│  - Health check (ping each Lambda)                               │
└─────────────────────────────────────────────────────────────────┘
```

**What moves here:**
- All of `governance.py` → Cost & Usage tab
- Gap management (full list) → Governance tab
- wiki_manager Tab 3 (Activity) → Governance tab
- wiki_manager Tab 2 (Knowledge / source registry) → Governance tab
- Configuration section (currently at bottom of dead Wiki Status page) → Configuration tab

**What is removed:**
- `governance.py` as a standalone page
- `knowledge_graph.py` as a standalone sidebar item (linked from Neuro Harness instead)

---

## Files to Delete

These exist in the codebase but should be removed:

| File | Reason |
|---|---|
| `pages/neuro_san.py` | Content merged into `pages/neuro_harness.py` |
| `pages/skill_studio.py` | Content merged into `pages/neuro_harness.py` |
| `pages/governance.py` | Content merged into `pages/platform.py` |
| `pages/traces.py` | Traces split inline into lambda_harness and neuro_harness |
| `pages/knowledge_graph.py` | Linked from Neuro Harness, not standalone nav |
| `app.py` dead pages | `__legacy_upload__`, `📊 Wiki Status`, `📋 Activity Log`, `🔬 Expansion Lab` — all unreachable; delete the `elif` blocks |

---

## Sidebar — Final State

```python
with st.sidebar:
    st.markdown("# 📚 LLMWiki")
    st.caption("AI-powered knowledge platform")
    st.divider()

    st.page_link("pages/knowledge_hub.py",   label="📖 Knowledge Hub",   icon="📖")
    st.page_link("pages/lambda_harness.py",  label="⚡ Lambda Harness",  icon="⚡")
    st.page_link("pages/neuro_harness.py",   label="🧠 Neuro Harness",   icon="🧠")
    st.page_link("pages/platform.py",        label="⚙️ Platform",        icon="⚙️")

    st.divider()
    st.caption(f"Region: `{AWS_REGION}`")
```

Four items. No radio nav. No section headers with `<p class="nav-section">`. No dividers between individual items.

---

## Customer Journey — Before vs After

**Before (current):**
> Customer opens app → sees 3 radio options + 6 page links → clicks "Ask a Question" → gets answer → wants to upload a document → must find "Upload Documents" in the Manage section → uploads → wants to see what happened → must find "Governance" under Platform → wants to see agent traces → must find "Traces" also under Platform → confused about difference between "AI Skill Studio" and "Neuro SAN" → gives up

**After (proposed):**
> Customer opens app → sees 4 clear destinations → clicks Knowledge Hub → uploads a document AND asks a question on the same page, sees gaps inline → clicks Lambda Harness → runs UC1 or UC-PM, sees phase progress + cost + traces in the same view → clicks Neuro Harness → runs same use case via AAOSA, compares output, sees OTel spans alongside → done

---

## Implementation Order

| Step | Work | Effort |
|---|---|---|
| 1 | Create `pages/knowledge_hub.py` — merge app.py pages + wiki_manager upload tab | 1 day |
| 2 | Refactor `pages/lambda_harness.py` — add traces panel + session metrics inline | 1 day |
| 3 | Create `pages/neuro_harness.py` — merge neuro_san.py + skill_studio.py + Neuro traces | 1 day |
| 4 | Create `pages/platform.py` — merge governance + wiki_manager tabs 2/3 + dead pages | 0.5 days |
| 5 | Update `app.py` sidebar — 4 page_link items, remove radio, remove dead elif blocks | 0.5 days |
| 6 | Delete 6 files listed above | 0.5 days |

Total: ~4.5 days. No new infrastructure. No backend changes. Pure UI consolidation.
