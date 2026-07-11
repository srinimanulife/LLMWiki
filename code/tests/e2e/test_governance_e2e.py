"""
Governance Page — E2E Playwright Tests
Migrated from /tmp/governance_e2e_test.py into the canonical test directory.

Run: pytest tests/e2e/test_governance_e2e.py -v
"""

import time
import pytest
from playwright.sync_api import Page, expect, TimeoutError as PWTimeout
from conftest import (nav, wait_spinner_gone, wait_for_title, get_metric, get_main_text,
                       get_sidebar_text, ask_question, BASE_URL, SLOW_STEP)

TEST_QUESTION = "What is our cloud migration strategy for TriZetto Managed Cloud Services?"


# ── Test 1: Page structure ─────────────────────────────────────────

def test_governance_page_loads(page: Page):
    nav(page, "/governance", extra_wait=3)
    assert wait_for_title(page, "Governance"), "Governance page title must be visible"

    has_metrics = page.locator("[data-testid='stMetric']").count() > 0
    has_info    = page.locator("[data-testid='stAlert']").count() > 0
    main_txt    = get_main_text(page)
    assert has_metrics or has_info or len(main_txt) > 20, "Page must render content"


def test_governance_sidebar_link_present(page: Page):
    nav(page, "/governance")
    gov_link = page.locator("a[href*='governance']").first
    assert gov_link.is_visible(), "Governance link must be in sidebar"


# ── Test 2: Ask → usage row tracked ───────────────────────────────

def test_ask_question_creates_usage_row(page: Page):
    nav(page, "/")
    ask_question(page, TEST_QUESTION)

    nav(page, "/governance", extra_wait=2)
    # Refresh metrics
    btn = page.locator("button").filter(has_text="Refresh").first
    if btn.count() > 0:
        btn.click()
        wait_spinner_gone(page, 20_000)
        time.sleep(3)

    req_val = get_metric(page, "Requests")
    req_count = int(req_val.replace(",", "")) if req_val else 0
    assert req_count > 0, f"Requests metric must be > 0 after asking, got {req_count}"

    cost_val = get_metric(page, "Total Cost")
    try:
        cost_num = float(cost_val.replace("$", "").replace(",", "")) if cost_val else 0
        assert cost_num > 0, f"Cost must be > $0, got {cost_val}"
    except ValueError:
        pytest.fail(f"Could not parse cost value: {cost_val}")


def test_recent_requests_table_has_rows(page: Page):
    nav(page, "/governance")
    main = page.locator("[data-testid='stMain']")
    try:
        page_text = main.inner_text(timeout=8_000)
        has_table = any(col in page_text for col in ["Timestamp", "Caller", "Operation"])
    except Exception:
        has_table = False
    assert has_table, "Recent requests table must show column headers"


# ── Test 3: Cache hit rate ─────────────────────────────────────────

def test_cache_hit_rate_appears_after_repeat_question(page: Page):
    # Ask same question a second time
    nav(page, "/")
    ask_question(page, TEST_QUESTION)

    nav(page, "/governance", extra_wait=2)
    btn = page.locator("button").filter(has_text="Refresh").first
    if btn.count() > 0:
        btn.click()
        wait_spinner_gone(page, 20_000)
        time.sleep(3)

    hit_rate = get_metric(page, "Cache Hit Rate")
    assert hit_rate, "Cache Hit Rate metric must be present on governance page"

    try:
        pct = float(hit_rate.replace("%", "").strip())
        assert pct > 0, f"Cache Hit Rate must be > 0% after repeat query, got {hit_rate}"
    except ValueError:
        pytest.fail(f"Could not parse Cache Hit Rate: {hit_rate}")


# ── Test 4: Cache health section ──────────────────────────────────

def test_cache_health_section_renders(page: Page):
    nav(page, "/governance")
    main = page.locator("[data-testid='stMain']")
    page_text = main.inner_text(timeout=10_000)
    assert "Cache Health" in page_text, "Cache Health section must be present"


def test_live_cache_entries_metric(page: Page):
    nav(page, "/governance")
    live = get_metric(page, "Live")
    assert live is not None, "Live cache entries metric must exist"


# ── Test 5: Day-range slider ───────────────────────────────────────

def test_day_range_slider_present(page: Page):
    nav(page, "/governance", extra_wait=3)
    # Wait explicitly for slider to appear (it's in the sidebar user content area)
    try:
        page.locator("[data-testid='stSlider']").first.wait_for(state="visible", timeout=20_000)
    except Exception:
        pass
    slider_count = page.evaluate("() => document.querySelectorAll('[data-testid=\"stSlider\"]').length")
    assert slider_count > 0, "Day-range slider must be present on governance page"


def test_day_range_slider_keyboard_interaction(page: Page):
    nav(page, "/governance")
    thumb = page.locator("[data-testid='stSidebar'] [data-testid='stSlider'] [role='slider']").first
    thumb.focus(timeout=10_000)
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
        time.sleep(0.1)
    time.sleep(2)  # wait for Streamlit re-render — no crash = pass


# ── Test 6: Refresh button ─────────────────────────────────────────

def test_refresh_button_present_and_works(page: Page):
    nav(page, "/governance")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    btn = page.locator("button").filter(has_text="Refresh").first
    assert btn.count() > 0, "Refresh metrics button must be present"

    btn.click()
    wait_spinner_gone(page, 20_000)
    time.sleep(2)
    assert wait_for_title(page, "Governance"), "Page must re-render after refresh"


# ── Test 7: Sidebar navigation ────────────────────────────────────

def test_sidebar_link_navigates_to_governance(page: Page):
    nav(page, "/")
    gov_link = page.locator("a[href*='governance']").first
    assert gov_link.count() > 0, "Governance link must be in sidebar"
    gov_link.click()
    time.sleep(SLOW_STEP + 2)
    assert wait_for_title(page, "Governance"), "Clicking governance link must navigate to governance page"
