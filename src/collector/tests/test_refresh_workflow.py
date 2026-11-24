from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_refresh_collects_twelve_auction_pages():
    workflow = (ROOT / ".github/workflows/refresh.yml").read_text()
    assert "--page-size 12 " in workflow
    assert "--page-size 4 " not in workflow
    assert "(12 auctions each)" in workflow


def test_blocked_refresh_calls_separate_browser_diagnostic():
    workflow = (ROOT / ".github/workflows/refresh.yml").read_text()
    assert "source_blocked: ${{ steps.collect.outputs.source_blocked }}" in workflow
    assert 'SOURCE_BLOCKED' in workflow
    browser = workflow.split("  inspect-verification:", 1)[1]
    assert "needs.refresh.outputs.source_blocked == 'true'" in browser
    assert "always()" in browser
    assert "uses: ./.github/workflows/browser-probe.yml" in browser
    assert "secrets: inherit" not in browser


def test_browser_diagnostic_has_no_production_credentials_or_publication():
    workflow = (ROOT / ".github/workflows/browser-probe.yml").read_text()
    assert "secrets." not in workflow
    assert "environment:" not in workflow
    assert "GEMINI" not in workflow
    assert "storage.py" not in workflow
    assert "main.py process" not in workflow
    assert "persist-credentials: false" in workflow
    assert "playwright install --with-deps chromium" in workflow
    assert "uv sync --locked --group browser" in workflow
    assert "path: var/browser-probe.json" in workflow
