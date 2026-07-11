# LLMWiki Playwright E2E Test — PM Hard Harness (Facets Scenario)

## Overview

End-to-end UI test using Playwright headless Chromium.  
Tests the full Problem Management agent flow: upload → ingest → ask → harness → report.

**App URL:** `http://llmwiki-alb-1382316210.us-east-1.elb.amazonaws.com`  
**Test script:** `/tmp/pm_e2e_test.py`  
**Report output:** `/tmp/pm_reports/PM-facets-001-handoff-report-20260610.html`

---

## Prerequisites

### Install Playwright (Zscaler/corporate proxy environment)

Zscaler intercepts TLS — `pip install playwright` fails with SSL errors.  
Use the manual install path:

```bash
# 1. Find the Zscaler cert (already in the repo)
CERT="/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code/streamlit/zscaler-ca.pem"

# 2. Download playwright wheel manually
curl --cacert "$CERT" -L "https://files.pythonhosted.org/packages/.../playwright-X.Y.Z-py3-none-linux_x86_64.whl" \
  -o /tmp/playwright.whl

# 3. Install from local file
pip install /tmp/playwright.whl

# 4. Download Chromium headless shell manually (pip run playwright install also fails behind proxy)
mkdir -p ~/.cache/ms-playwright/chromium_headless_shell-NNNN/chrome-linux
curl --cacert "$CERT" -L "<chromium-headless-shell-download-url>" \
  -o ~/.cache/ms-playwright/chromium_headless_shell-NNNN/chrome-linux/headless_shell
chmod +x ~/.cache/ms-playwright/chromium_headless_shell-NNNN/chrome-linux/headless_shell

# 5. Verify
python3 -c "from playwright.sync_api import sync_playwright; print('OK')"
```

> Exact wheel URL and Chromium build number change with each Playwright release.  
> Check `~/.cache/ms-playwright/` after a partial install to find the expected path.

---

## Test Data

**Facets CSV** — 8 realistic problem records for `llmwiki-problem-mgnt-278e7e22`:

```
/tmp/facets-issues.csv
```

Fields: `problem_id, product, component, severity, summary, root_cause, resolution, category, recurrence_type, affected_version`

Key record used in harness:

| Field | Value |
|---|---|
| problem_id | PRB-FAC-001 |
| product | Facets |
| component | Claims Adjudication Engine |
| severity | P1 |
| summary | Claims batch processing fails with NPE on Medicare supplemental claims |
| resolution | Added null guard in processBatch(); patched in Facets 19.2.3 |

---

## Step-by-Step Test Flow

### Step 1 — Upload CSV to PM bucket (Wiki Manager)

- Navigate to `/wiki_manager`
- Selectbox[0] "Agent bucket" → choose **🛠️ Problem Management (UC-PM)**
- Set file input to `/tmp/facets-issues.csv`
- Click **⬆️ Upload & Ingest**
- Confirm success text appears

**Selector notes:**
- Bucket dropdown: `div[data-testid='stSelectbox']` → `li[role='option']` filter by "Problem Management"
- File input: `input[type='file']`
- Upload button: `button` matching `r"Upload.*Ingest"` (case-insensitive)

### Step 2 — Wait for ingest pipeline

- CSV files route through a converter Lambda before ingest
- Wait **90 seconds** after upload confirmation
- `.md`/`.txt` files: ~20-50s; `.csv`: ~60-90s end-to-end

### Step 3 — Ask the Wiki (form, not chat)

- Navigate to `/` (homepage)
- Click **🔍 Ask the Wiki** radio in sidebar
- Fill `[data-testid='stTextArea'] textarea` (NOT `stChatInputTextArea` — this is a form)
- Click **Ask →** button
- Wait for `text=Confidence` to appear (up to 90s)

> **Note:** Ask the Wiki queries the **main wiki bucket** (`llmwiki-278e7e22`).  
> The PM bucket (`llmwiki-problem-mgnt-278e7e22`) is searched by SK-01 inside the PM harness.  
> A Facets question will return "no information" from the main wiki — this is expected.

### Step 4 — Navigate to Harness Demo, select PM agent, fill inputs

- Navigate to `/harness_demo`
- Selectbox[0] "Select Agent" → choose **Problem Management (UC-PM)**
- Sidebar has 5 text inputs in order:

| Index | Label | Facets value |
|---|---|---|
| 0 | Batch ID | `PM-FACETS-001` |
| 1 | Component (affected module) | `Claims Adjudication Engine` |
| 2 | Product Platform | `Facets` |
| 3 | Problem ID | `PRB-FAC-001` |
| 4 | Agent ID | (leave default `pm-harness-v1`) |

- Use `.fill(val)` — do NOT use `.triple_click()` (not a valid Playwright method)

### Step 5 — Start Harness and send "Go ahead"

- Click tab: `get_by_role("tab", name=r"Hard Harness")`
- Click button: `locator("[data-testid='stMain'] button").filter(has_text="Start Harness")`
- Wait for chat input to appear: `[data-testid='stChatInputTextArea']`
- Fill and press Enter: `"Go ahead"`

### Step 6 — Wait for phases 1-2 to complete (~15-35s)

Phases 1-2 run **synchronously** in a `st.spinner`. The page blocks until the Lambda returns.  
After return, `st.rerun()` fires and Stage 4 (Phase 3 form) renders.

**Detection logic** — poll until ALL of:
- `[data-testid='stTextArea']` count > 0  
- Widget label text contains `"Your answers"` (only appears in Stage 4)
- Chat messages contain `"Phases 1"` or `"SME input required"`

**Do NOT** match on `"Phase 3"` text alone — the locked plan panel always shows that text.

```python
sme_ta_visible = page.locator("[data-testid='stTextArea'] textarea").count()
label_els = page.locator("[data-testid='stWidgetLabel']").all()
has_sme_label = any("Your answers" in el.inner_text() for el in label_els)
```

### Step 7 — Fill Phase 3 SME textarea and submit

- Fill textarea: `page.locator("[data-testid='stTextArea'] textarea").first`
- Submit: `locator("[data-testid='stMain'] button").filter(has_text=r"Submit answers")`

The exact button label in code is: `"▶ Submit answers & run phases 4–8"`

After submit, phases 4-8 fire **asynchronously** (Lambda `InvocationType="Event"`).  
Streamlit polls via `get_status` every 3s and auto-reruns.

### Step 8 — Poll for all 8 phases complete

**Reliable completion indicator: `[data-testid='stDownloadButton']` count > 0**

This element only renders in Stage 5 (after `phase3_answered=True` and all phases done).  
Do NOT rely on text matching "Phase 8" — that text appears in the locked plan panel before phases run.

```python
dl_count = page.locator("[data-testid='stDownloadButton']").count()
```

Expected time for phases 4-8: ~35-45 seconds.

### Step 9 — Download HTML report

```python
dl_btns = page.locator("[data-testid='stDownloadButton'] button").all()
with page.expect_download(timeout=30000) as dl_info:
    dl_btns[0].click()
download = dl_info.value
download.save_as("/tmp/pm_reports/PM-facets-001-handoff-report-20260610.html")
```

---

## Known UI Issues Found During Testing (All Fixed)

| Issue | Root cause | Fix |
|---|---|---|
| `triple_click` AttributeError | Not a Playwright Python API method | Use `.fill(val)` directly |
| Phase 3 form detected immediately (false positive) | Locked plan panel text contains "Phase 3" always | Match on `stTextArea` + "Your answers" label |
| Phase 8 completion false positive | Locked plan shows all phase names from start | Match on `stDownloadButton` count > 0 |
| PM harness rejects "Facets" product | `VALID_PRODUCTS` in `llmwiki-harness-uc-pm` Lambda hardcoded to `{QNXT, TCS, EAM, EDM}` | Added `Facets`, `FACETS` |
| SK-06 classifier rejects "Facets" | Same `VALID_PRODUCTS` restriction in `llmwiki-skill-problem-classifier` Lambda | Added `Facets`, `FACETS` |
| Classification fields empty in report | Phase 2 (SK-06) returned 400 → stored `{error: ...}` in DynamoDB | Fixed SK-06 + delete stale DynamoDB record |
| Strict mode: "Wiki Manager" matches 2 elements | Both sidebar nav and page_link render the text | Use `get_by_role("link", name=...)` or navigate by URL |

---

## Lambda Changes Made

### `llmwiki-harness-uc-pm`

```python
# handler.py line 35
VALID_PRODUCTS = {"QNXT", "TCS", "EAM", "EDM", "Facets", "FACETS"}
```

### `llmwiki-skill-problem-classifier` (SK-06)

```python
# handler.py line 29
VALID_PRODUCTS = {"QNXT", "TCS", "EAM", "EDM", "Facets", "FACETS"}
```

### Redeploy commands

```bash
# Package and deploy
cd /tmp/<lambda_src>/
zip -r ../updated.zip *.py
aws lambda update-function-code \
  --function-name <function-name> \
  --zip-file fileb://../updated.zip \
  --profile tzg-sandbox
aws lambda wait function-updated --function-name <function-name> --profile tzg-sandbox
```

### Clear stale DynamoDB run (if classification fields empty)

```bash
aws dynamodb delete-item \
  --table-name llmwiki-pm-runs \
  --key '{"run_id":{"S":"PM-FACETS-001#PRB-FAC-001"},"batch_id":{"S":"PM-FACETS-001"}}' \
  --profile tzg-sandbox
```

---

## Redeploy Streamlit (after UI code changes)

```bash
cd "/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/code"
docker build -f streamlit/Dockerfile -t llmwiki-streamlit:latest .
aws ecr get-login-password --region us-east-1 --profile tzg-sandbox \
  | docker login --username AWS --password-stdin 392568849512.dkr.ecr.us-east-1.amazonaws.com
docker tag llmwiki-streamlit:latest \
  392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-streamlit:latest
docker push 392568849512.dkr.ecr.us-east-1.amazonaws.com/llmwiki-streamlit:latest
aws ecs update-service \
  --cluster llmwiki-cluster --service llmwiki-streamlit \
  --force-new-deployment --profile tzg-sandbox
aws ecs wait services-stable \
  --cluster llmwiki-cluster --services llmwiki-streamlit --profile tzg-sandbox
```

---

## Streamlit Selector Reference

| Element | Selector |
|---|---|
| Main content area | `[data-testid='stMain']` |
| Sidebar | `[data-testid='stSidebar']` |
| Chat input (chat_input) | `[data-testid='stChatInputTextArea']` |
| Form textarea (text_area) | `[data-testid='stTextArea'] textarea` |
| Widget label | `[data-testid='stWidgetLabel']` |
| Download button | `[data-testid='stDownloadButton'] button` |
| Selectbox | `div[data-testid='stSelectbox']` |
| Selectbox options | `li[role='option']` |
| Tabs | `[role='tab']` |
| Sidebar radio labels | `[data-testid='stSidebar'] [data-testid='stRadio'] label` |
| Chat messages | `[data-testid='stChatMessage']` |
| Spinner | `[data-testid='stSpinner']` |

---

## Page Routes

| Page | URL path |
|---|---|
| Ask the Wiki / Browse / Expansion Lab | `/` |
| Wiki Manager (upload) | `/wiki_manager` |
| Agent Harness Demo | `/harness_demo` |

---

## Timing Reference

| Operation | Expected duration |
|---|---|
| `.md` / `.txt` upload → ingest complete | 20-50s |
| `.csv` upload → converter → ingest complete | 60-90s |
| PM harness phases 1-2 (synchronous Lambda) | 15-35s |
| PM harness phases 4-8 (async background Lambda) | 35-50s |
| Ask the Wiki (Bedrock KB query) | 15-40s |
| ECS redeployment stabilize | 90-180s |
