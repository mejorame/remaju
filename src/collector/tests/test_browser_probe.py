import json
from unittest.mock import MagicMock, Mock

import pytest

from browser_probe import inspect_page, listing_response, run_probe
from utils.archive import read_json
from utils.site import LIST_ID, LIST_URL


def listing(count):
    cards = '<div class="card azul"></div>' * count
    return f'<form id="formBuscarRemateExterno"><div id="{LIST_ID}">{cards}</div><input name="captcha"></form>'


def response(status=200, body="", location=""):
    return Mock(status=status, headers={"location": location}, text=Mock(return_value=body))


def browser_factory(page):
    factory = MagicMock()
    browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
    browser.new_context.return_value.new_page.return_value = page
    return factory, browser


def page_with_pagination(html, pagination):
    page = Mock()
    page.url = LIST_URL
    page.goto.return_value = response()
    page.content.side_effect = html
    pending = MagicMock()
    pending.__enter__.return_value.value = pagination
    page.expect_response.return_value = pending
    return page


def test_normal_listing_and_image_captcha_do_not_require_interactive_verification():
    observed = inspect_page(listing(4), LIST_URL, 200, "initial")
    assert observed["listing_available"] is True
    assert observed["verification"] is None
    assert observed["cards"] == 4


@pytest.mark.parametrize("url, method, expected", [
    (LIST_URL, "POST", True),
    (LIST_URL + ";jsessionid=secret?x=1", "POST", True),
    (LIST_URL, "GET", False),
    ("https://example.com/remaju/pages/publico/remateExterno.xhtml", "POST", False),
])
def test_only_listing_posts_are_selected(url, method, expected):
    assert listing_response(Mock(url=url, request=Mock(method=method))) is expected


def test_browser_checks_twelve_rows_without_collecting_or_publishing(tmp_path):
    page = page_with_pagination([listing(4), listing(12)], response())
    factory, browser = browser_factory(page)
    output = tmp_path / "probe.json"
    report = run_probe(output, factory)
    assert report["status"] == "pagination-accessible"
    assert report["publishable"] is False
    assert report["captcha_solver_used"] is False
    assert report["captcha_detected"] is False
    assert report["observations"][-1]["cards"] == 12
    page.goto.assert_called_once()
    page.locator.return_value.select_option.assert_called_once_with("12", timeout=10000)
    browser.close.assert_called_once()
    assert read_json(output) == report


def test_initial_captcha_stops_before_any_click(tmp_path):
    page = page_with_pagination(['<iframe src="https://newassets.hcaptcha.com/captcha"></iframe>'], response())
    page.url = "https://validate.perfdrive.com/?token=private-token"
    factory, _ = browser_factory(page)
    report = run_probe(tmp_path / "probe.json", factory)
    assert report["status"] == "blocked"
    assert report["captcha_detected"] is True
    assert report["verification"]["provider"] == "hcaptcha"
    page.goto.assert_called_once()
    page.locator.assert_not_called()
    page.expect_response.assert_not_called()
    assert "private-token" not in json.dumps(report)


def test_pagination_403_stops_without_another_navigation(tmp_path):
    page = page_with_pagination([listing(4)], response(403, "Acceso denegado"))
    factory, _ = browser_factory(page)
    report = run_probe(tmp_path / "probe.json", factory)
    assert report["status"] == "blocked"
    assert report["verification"]["provider"] == "unknown"
    assert report["captcha_detected"] is False
    page.goto.assert_called_once()
    page.expect_response.assert_called_once()


def test_perfdrive_page_is_inspected_but_captcha_is_not_clicked(tmp_path):
    destination = "https://validate.perfdrive.com/?token=private-token"
    redirect = response(302, "", destination)
    redirect.text.side_effect = AssertionError("Redirect bodies are not available in Chromium")
    page = page_with_pagination([listing(4), '<div class="h-captcha"></div>'], redirect)

    def navigate(url, **kwargs):
        page.url = url
        return response()

    page.goto.side_effect = navigate
    factory, _ = browser_factory(page)
    report = run_probe(tmp_path / "probe.json", factory)
    assert report["status"] == "blocked"
    assert report["captcha_detected"] is True
    assert report["verification"]["provider"] == "hcaptcha"
    assert page.goto.call_count == 2
    page.expect_response.assert_called_once()
    page.locator.return_value.select_option.assert_called_once()
    assert report["captcha_solver_used"] is False
    redirect.text.assert_not_called()
    assert "private-token" not in json.dumps(report)


def test_failed_browser_still_writes_a_non_publishable_sanitized_report(tmp_path):
    page = Mock()
    page.goto.side_effect = ValueError("https://example.com/?token=private-token")
    factory, browser = browser_factory(page)
    report = run_probe(tmp_path / "probe.json", factory)
    assert report["status"] == "failed"
    assert report["publishable"] is False
    assert "private-token" not in json.dumps(report)
    browser.close.assert_called_once()


def test_existing_probe_output_is_preserved(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("existing")
    factory = Mock()
    with pytest.raises(ValueError, match="new file"):
        run_probe(output, factory)
    factory.assert_not_called()
    assert output.read_text() == "existing"
