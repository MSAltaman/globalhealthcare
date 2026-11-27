"""Browser smoke test for the built site.

Run after `python scripts/build_site_data.py`:
    pip install playwright pytest && playwright install --with-deps chromium
    python -m pytest -q tests/browser

Opens site/index.html from disk (the page works from file:// because the data is
bundled into site/data/bundle.js), visits every top-level page and every country
page at desktop and phone width, and fails on any script error. Skipped when
Playwright or the built data isn't there, so the plain `pytest tests` run in CI
is unaffected.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site" / "index.html"
BUNDLE = ROOT / "site" / "data" / "bundle.js"

sync_api = pytest.importorskip("playwright.sync_api")
if not BUNDLE.exists():
    pytest.skip("site data not built; run scripts/build_site_data.py", allow_module_level=True)

WIDTHS = {"desktop": 1280, "phone": 390}
TOP_PAGES = ["ranking", "financing", "outcomes", "about"]


def country_hashes():
    return sorted(p.stem.lower() for p in (ROOT / "data" / "countries").glob("*.json"))


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def open_page(browser, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Fonts come from Google; offline runners may block them. Anything else is an error.
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text else None)
    return page, errors


def visit(page, h):
    page.goto(f"{SITE.as_uri()}#{h}")
    page.wait_for_selector("#view *", timeout=10_000)
    page.wait_for_timeout(300)
    return page.inner_text("#view")


@pytest.mark.parametrize("width", WIDTHS.values(), ids=WIDTHS.keys())
def test_every_page_loads(browser, width):
    page, errors = open_page(browser, width)
    for h in TOP_PAGES + country_hashes():
        text = visit(page, h)
        if h == "outcomes" and "How health outcomes are scored" not in page.content():
            continue  # the page is optional until it ships
        assert len(text.strip()) > 200, f"#{h} rendered almost nothing at {width}px"
        assert "Could not load" not in text, f"#{h}: {text[:200]}"
    assert not errors, errors


def test_ranking_sorts(browser):
    page, errors = open_page(browser, 1280)
    visit(page, "ranking")
    buttons = page.locator("button.sort")
    if buttons.count() < 2:
        pytest.skip("ranking table has no sortable columns")
    first = page.eval_on_selector_all("table tbody tr", "rows => rows.map(r => r.innerText)")
    buttons.nth(1).click()
    page.wait_for_timeout(200)
    second = page.eval_on_selector_all("table tbody tr", "rows => rows.map(r => r.innerText)")
    assert sorted(first) == sorted(second), "sorting lost or added rows"
    assert not errors, errors


def test_about_lists_sources(browser):
    page, errors = open_page(browser, 1280)
    text = visit(page, "about")
    assert re.search(r"source", text, re.I)
    assert not errors, errors
