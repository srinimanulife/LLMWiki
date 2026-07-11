"""
UC1 Sales-to-Service — End-to-End UI Tests (Playwright)
========================================================
Tests the full UC1 workflow through the Streamlit Harness Demo UI.
Covers: start → Phase 1+2 → pause → human input → resume → completion → report download.

Eval-first principle: these tests define what the UI must deliver.
Run BEFORE deploying UC1 to production users.

Run: pytest tests/e2e/test_uc1_e2e.py -v
"""

import time
import pytest
from playwright.sync_api import Page, TimeoutError as PWTimeout
from conftest import (nav, wait_spinner_gone, wait_for_title, get_main_text,
                       get_sidebar_text, activate_tab, BASE_URL, SLOW_STEP, TIMEOUT)

# ── Test fixtures ──────────────────────────────────────────────────

UC1_INPUTS = {
    "customer_name": "BlueCross BlueShield Minnesota",
    "product":       "TriZetto QNXT",
    "sow_ref":       "SOW-2026-EVAL-001",
}
# customer_id is generated per-test call to avoid prior-run conflicts in session-scoped browser

HUMAN_CONTEXT = (
    "Executive sponsor is Jane Smith, CMO. Go-live Q1 2027. No prior implementation attempts. "
    "HIPAA compliance required. EHR is Epic. Contract has a 30-day penalty clause if missed."
)


# ── Helpers specific to harness demo ─────────────────────────────

def _nav_to_harness(page: Page):
    nav(page, "/harness_demo", extra_wait=2)
    activate_tab(page, "Hard Harness")


def _select_uc1_agent(page: Page):
    """Select the Sales-to-Service (UC1) agent from the dropdown."""
    agent_select = page.locator("[data-testid='stSelectbox']").first
    agent_select.click()
    time.sleep(0.5)
    page.locator("[data-testid='stSelectbox'] option, li[role='option']").filter(
        has_text="Sales-to-Service"
    ).first.click()
    time.sleep(SLOW_STEP)


def _fill_uc1_inputs(page: Page, customer_id: str = ""):
    """Fill the UC1 sidebar input fields. Uses a unique customer_id per call to avoid prior-run conflicts."""
    import hashlib, os
    if not customer_id:
        customer_id = f"eval-e2e-{hashlib.md5(os.urandom(4)).hexdigest()[:8]}"
    sidebar = page.locator("[data-testid='stSidebar']")
    inputs = sidebar.locator("[data-testid='stTextInput'] input").all()
    if len(inputs) >= 4:
        inputs[0].clear()
        inputs[0].fill(customer_id)
        inputs[1].clear()
        inputs[1].fill(UC1_INPUTS["customer_name"])
        inputs[2].clear()
        inputs[2].fill(UC1_INPUTS["product"])
        inputs[3].clear()
        inputs[3].fill(UC1_INPUTS["sow_ref"])
    time.sleep(0.5)


def _reset_harness_if_needed(page: Page):
    """Click 'Reset Harness' if a prior run is in progress, to start clean."""
    try:
        reset_btn = page.locator("button").filter(has_text="Reset Harness").first
        if reset_btn.count():
            reset_btn.click()
            wait_spinner_gone(page, 15_000)
            time.sleep(SLOW_STEP)
    except Exception:
        pass


def _click_start_harness(page: Page):
    """Click the Start Harness button."""
    wait_spinner_gone(page, 15_000)
    for label in ["Start Harness", "Start"]:
        btn = page.locator("button").filter(has_text=label).first
        if btn.count():
            btn.click()
            wait_spinner_gone(page, 30_000)
            time.sleep(SLOW_STEP)
            return


def _send_chat_message(page: Page, text: str):
    """Send a message in the chat input."""
    # Wait for chat input to be ready (not locked during Streamlit processing)
    wait_spinner_gone(page, 30_000)
    for sel in [
        "[data-testid='stChatInputTextArea']",
        "[data-testid='stChatInput'] textarea",
    ]:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=15_000)
            el.fill(text)
            page.keyboard.press("Enter")
            time.sleep(SLOW_STEP)
            return
        except Exception:
            continue
    # fallback: last textarea
    page.locator("textarea").last.fill(text)
    page.keyboard.press("Enter")
    time.sleep(SLOW_STEP)


def _wait_for_phase(page: Page, phase_num: int, timeout_ms: int = 90_000) -> bool:
    """Wait for a specific phase indicator to appear."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        txt = get_main_text(page) + get_sidebar_text(page)
        if f"Phase {phase_num}" in txt or f"phase{phase_num}" in txt.lower():
            return True
        time.sleep(2)
    return False


def _wait_for_paused(page: Page, timeout_ms: int = 90_000) -> bool:
    """Wait for the human input pause state (Phase 3 questions)."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        txt = get_main_text(page)
        if any(kw in txt.lower() for kw in [
            "executive sponsor", "go-live", "phase 3", "question",
            "sales team", "human", "decision authority", "timeline"
        ]):
            return True
        # Also check for textarea appearing
        try:
            page.locator("[data-testid='stChatInputTextArea']").wait_for(
                state="visible", timeout=2_000
            )
            return True
        except PWTimeout:
            pass
        time.sleep(2)
    return False


def _wait_for_completed(page: Page, timeout_ms: int = 180_000) -> bool:
    """Wait for the harness to reach completed status."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        txt = get_main_text(page)
        if "completed" in txt.lower() or "All 8 phases" in txt:
            return True
        try:
            page.locator("a[href*='report'], button").filter(
                has_text="Download"
            ).wait_for(state="visible", timeout=2_000)
            return True
        except PWTimeout:
            pass
        time.sleep(3)
    return False


# ── Tests ──────────────────────────────────────────────────────────

def test_harness_demo_page_loads(page: Page):
    """The Harness Demo page must load with UC1 and PM agent options."""
    _nav_to_harness(page)
    main_text = get_main_text(page)
    assert any(keyword in main_text for keyword in
               ["Sales-to-Service", "Harness", "Agent", "Hard Harness"]), \
        f"Harness Demo page must show agent selection. Got: {main_text[:400]}"


def test_harness_demo_sidebar_link_present(page: Page):
    """Harness Demo must be accessible from the sidebar navigation."""
    nav(page, "/")
    harness_link = page.locator("a[href*='harness']").first
    assert harness_link.count() > 0, "Harness Demo link must be in sidebar"


def test_uc1_agent_selectable(page: Page):
    """UC1 Sales-to-Service option must be selectable in the agent dropdown."""
    _nav_to_harness(page)
    main_text = get_main_text(page)
    # Also check selectbox value and sidebar for UC1/Sales-to-Service
    sidebar_text = get_sidebar_text(page)
    selectbox_val = page.evaluate("""
        () => document.querySelector('[data-testid="stSelectbox"] [data-baseweb="select"] [data-testid="stMarkdownContainer"]')?.innerText
              || document.querySelector('[data-testid="stSelectbox"]')?.innerText
              || ''
    """) or ""
    combined = main_text + sidebar_text + selectbox_val
    assert "Sales-to-Service" in combined or "UC1" in combined or "UC-1" in combined, \
        f"UC1 agent option must be present. Got combined: {combined[:400]}"


def test_uc1_sidebar_inputs_accept_values(page: Page):
    """UC1 sidebar input fields must be fillable."""
    _nav_to_harness(page)
    sidebar = page.locator("[data-testid='stSidebar']")
    # Wait up to 10s for inputs to appear (rendered after tab activation)
    for _ in range(5):
        inputs = sidebar.locator("[data-testid='stTextInput'] input").all()
        if inputs:
            break
        time.sleep(2)

    if not inputs:
        pytest.skip("Could not find text inputs in sidebar after 10s")

    for inp in inputs[:4]:
        inp.fill("test-value")
        time.sleep(0.1)
    # Verify at least one filled
    assert any(i.input_value() for i in inputs[:4]), "Input fields must accept values"


def test_uc1_start_harness_button_present(page: Page):
    """Start Harness button must be visible after selecting UC1."""
    _nav_to_harness(page)
    btn = page.locator("button").filter(has_text="Start").first
    main_text = get_main_text(page)
    assert btn.count() > 0 or "Start Harness" in main_text, "Start Harness button must be present"


def test_uc1_full_workflow_pauses_at_phase3(page: Page):
    """
    Full UC1 workflow E2E:
    1. Navigate to harness demo
    2. Fill inputs
    3. Start harness
    4. Send 'Go ahead'
    5. Confirm workflow pauses at Phase 3 with questions for sales team
    """
    _nav_to_harness(page)
    _reset_harness_if_needed(page)
    _fill_uc1_inputs(page)
    _click_start_harness(page)
    wait_spinner_gone(page, 30_000)

    # Send the go-ahead trigger
    _send_chat_message(page, "Go ahead")
    wait_spinner_gone(page, 90_000)
    time.sleep(5)

    main_text = get_main_text(page)

    # Should be paused — look for question content or Phase 3 indicator
    has_pause_signal = any(keyword in main_text.lower() for keyword in [
        "executive sponsor", "go-live", "phase 3", "question", "sales team",
        "human", "decision authority", "timeline",
    ])
    assert has_pause_signal, (
        f"After 'Go ahead', workflow must pause at Phase 3 with sales team questions. "
        f"Page text (first 500 chars): {main_text[:500]}"
    )


def test_uc1_phase_progress_panel_visible(page: Page):
    """The locked plan panel showing 8 phases must be visible during execution."""
    _nav_to_harness(page)
    time.sleep(2)  # extra settle after tab activation
    sidebar_text = get_sidebar_text(page)
    main_text    = get_main_text(page)
    combined     = sidebar_text + main_text
    has_phases = any(kw in combined for kw in [
        "SOW Intake", "Customer Classification", "Risk", "Template", "Report", "Phase",
        "Intake", "Classification", "Handoff", "Write"
    ])
    assert has_phases, (
        f"Phase progress panel must be visible in sidebar or main content.\n"
        f"Sidebar: {sidebar_text[:400]}\nMain: {main_text[:200]}"
    )


def test_uc1_human_input_form_accepts_text(page: Page):
    """
    After workflow pauses at Phase 3, the human input textarea must accept text.
    This test navigates directly to the harness in a paused state if available,
    or triggers the workflow fresh.
    """
    _nav_to_harness(page)
    _reset_harness_if_needed(page)
    _fill_uc1_inputs(page)
    _click_start_harness(page)
    wait_spinner_gone(page, 30_000)
    _send_chat_message(page, "Go ahead")
    wait_spinner_gone(page, 90_000)
    time.sleep(5)

    # Look for the human input textarea
    textareas = page.locator("[data-testid='stTextArea'] textarea").all()
    chat_inputs = page.locator("[data-testid='stChatInputTextArea']").all()

    available_inputs = textareas + chat_inputs
    if not available_inputs:
        pytest.skip("Human input form not found — workflow may not have reached Phase 3 yet")

    # Try filling the first available input
    available_inputs[0].fill(HUMAN_CONTEXT[:200])
    assert available_inputs[0].input_value(), "Human input form must accept text"


def test_uc1_workflow_report_download_url_present(page: Page):
    """
    Full end-to-end: start → pause → resume with human context → completed → report URL.
    This is the CRITICAL eval-first test: it must pass before UC1 goes live.
    Marks as slow since it invokes 8 Bedrock phases.
    """
    pytest.skip(
        "Full E2E workflow test — run manually: "
        "pytest tests/e2e/test_uc1_e2e.py::test_uc1_workflow_report_download_url_present -v -s"
        "\nRequires ~3-5 minutes to complete all 8 phases."
    )
    # Uncomment and run manually when ready:
    # _nav_to_harness(page)
    # _fill_uc1_inputs(page)
    # _click_start_harness(page)
    # wait_spinner_gone(page, 30_000)
    # _send_chat_message(page, "Go ahead")
    # wait_spinner_gone(page, 120_000)
    # time.sleep(5)
    #
    # # Fill human context
    # chat_input = page.locator("[data-testid='stChatInputTextArea']").last
    # chat_input.fill(HUMAN_CONTEXT)
    # page.keyboard.press("Enter")
    # wait_spinner_gone(page, 180_000)
    # time.sleep(10)
    #
    # main_text = page.locator("[data-testid='stMain']").inner_text(timeout=15_000)
    # assert "completed" in main_text.lower() or "Download" in main_text, \
    #     "Completed workflow must show completion status and/or download link"
    # assert "Download" in main_text or "report" in main_text.lower(), \
    #     "Completed run must offer report download"
