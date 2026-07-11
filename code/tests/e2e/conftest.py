"""
Shared Playwright fixtures for all E2E tests.

Note on stMain vs stMainBlockContainer:
  stMain is a <section> whose .evaluate() can hang on some Streamlit builds.
  Use get_page_text() / get_main_text() which use stMainBlockContainer + JS innerText.
"""

import time
import pytest
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

BASE_URL  = "http://llmwiki-alb-1382316210.us-east-1.elb.amazonaws.com"
TIMEOUT   = 120_000   # ms — Bedrock calls can be slow
SLOW_STEP = 2.0       # seconds between steps for Streamlit re-render

# Reliable main content selector (stMain.evaluate() hangs; stMainBlockContainer works)
_MAIN_SEL = "[data-testid='stMainBlockContainer']"
_APP_SEL  = "[data-testid='stAppViewContainer']"


@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        yield ctx
        browser.close()


@pytest.fixture
def page(browser_context: BrowserContext):
    pg = browser_context.new_page()
    pg.set_default_timeout(TIMEOUT)
    yield pg
    pg.close()


# ── Shared helpers ─────────────────────────────────────────────────

def nav(page: Page, path: str, extra_wait: float = 0):
    page.goto(f"{BASE_URL}{path}", wait_until="load", timeout=TIMEOUT)
    _wait_app_ready(page)
    time.sleep(SLOW_STEP + extra_wait)


def activate_tab(page: Page, tab_text: str):
    """Click a Streamlit tab button and wait for it to render."""
    try:
        tab = page.locator("button").filter(has_text=tab_text).first
        if tab.count():
            tab.click()
            wait_spinner_gone(page, 30_000)
            time.sleep(SLOW_STEP)
    except Exception:
        pass


def _wait_app_ready(page: Page, timeout_ms: int = 60_000):
    """Wait until Streamlit finishes its initial render."""
    try:
        page.locator("[data-testid='stStatusWidgetRunningIcon']").wait_for(
            state="hidden", timeout=timeout_ms
        )
    except PWTimeout:
        pass
    try:
        page.locator(_MAIN_SEL).wait_for(state="visible", timeout=15_000)
    except PWTimeout:
        pass


def wait_spinner_gone(page: Page, timeout_ms: int = 90_000):
    """Wait for Streamlit running spinner to disappear."""
    for sel in ["[data-testid='stStatusWidgetRunningIcon']",
                "[data-testid='stSpinner']"]:
        try:
            page.locator(sel).wait_for(state="hidden", timeout=timeout_ms)
            return
        except PWTimeout:
            continue


def _js_text(page: Page, css_sel: str) -> str:
    """Get innerText of a DOM element using page.evaluate (avoids Playwright locator hang)."""
    try:
        # Use double-quotes in the JS string so single-quote attribute values are safe
        js = f'document.querySelector("{css_sel}")?.innerText || ""'
        return page.evaluate(f"() => {js}") or ""
    except Exception:
        return ""


def get_main_text(page: Page) -> str:
    """Get text from the main content area using JS (avoids stMain locator hang)."""
    for sel in [
        "[data-testid=stMainBlockContainer]",
        "[data-testid=stAppViewContainer]",
        "body",
    ]:
        txt = _js_text(page, sel)
        if txt.strip():
            return txt
    return ""


def get_sidebar_text(page: Page) -> str:
    """Get sidebar text via JS."""
    return _js_text(page, "[data-testid=stSidebar]")


def wait_for_title(page: Page, text: str, timeout_ms: int = 20_000) -> bool:
    """Check for title text — h1 locator first, JS fallback."""
    try:
        page.locator(f"h1:has-text('{text}')").wait_for(state="visible", timeout=timeout_ms // 2)
        return True
    except PWTimeout:
        pass
    content = get_main_text(page)
    return text.lower() in content.lower()


def get_metric(page: Page, label: str) -> str:
    """Return the stMetricValue text for the metric whose label contains `label`."""
    try:
        result = page.evaluate(f"""() => {{
            for (const m of document.querySelectorAll('[data-testid="stMetric"]')) {{
                const lbl = m.querySelector('[data-testid="stMetricLabel"]')?.innerText || '';
                if (lbl.toLowerCase().includes('{label.lower()}')) {{
                    return m.querySelector('[data-testid="stMetricValue"]')?.innerText || '';
                }}
            }}
            return '';
        }}""")
        return result or ""
    except Exception:
        return ""


def click_sidebar_radio(page: Page, label: str):
    sidebar = page.locator("[data-testid='stSidebar']")
    sidebar.locator("[data-testid='stRadio'] label").filter(has_text=label).first.click()
    time.sleep(SLOW_STEP)


def ask_question(page: Page, question: str):
    """Submit a question on the Ask a Question page and wait for the answer."""
    click_sidebar_radio(page, "Ask a Question")
    page.locator("[data-testid='stTextArea'] textarea").first.fill(question)
    page.locator(_MAIN_SEL + " button").filter(has_text="Get Answer").first.click()
    deadline = TIMEOUT
    while deadline > 0:
        txt = get_main_text(page)
        if "confidence" in txt.lower():
            break
        time.sleep(2)
        deadline -= 2000
    wait_spinner_gone(page)
    time.sleep(SLOW_STEP)
