import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser

from utils.archive import utc_now, write_json
from utils.debugger import diagnostic_error, diagnostic_url
from utils.site import LIST_FORM, LIST_ID, LIST_URL
from utils.verification import detect_verification


READY = f"""() => !!document.querySelector('form[id="{LIST_FORM}"]')
    || !!document.querySelector('.h-captcha, .g-recaptcha, .cf-turnstile, iframe[src*="hcaptcha"], iframe[src*="recaptcha"]')"""
TWELVE = f"""() => document.querySelectorAll('[id="{LIST_ID}"] .card.azul').length === 12
    || !!document.querySelector('.h-captcha, .g-recaptcha, .cf-turnstile, iframe[src*="hcaptcha"], iframe[src*="recaptcha"]')"""


def inspect_page(html: str, url: str, status: int, phase: str) -> dict[str, Any]:
    tree = HTMLParser(html)
    verification = detect_verification(html, status, url)
    listing = urlsplit(url).hostname == urlsplit(LIST_URL).hostname and tree.css_first(f'form[id="{LIST_FORM}"]') is not None
    count = len(tree.css(f'[id="{LIST_ID}"] .card.azul'))
    return {
        "phase": phase,
        "url": diagnostic_url(url),
        "http_status": status,
        "listing_available": listing and count > 0 and verification is None,
        "cards": count,
        "verification": verification,
    }


def observe(page: Any, response: Any, phase: str, report: dict[str, Any]) -> dict[str, Any]:
    result = inspect_page(page.content(), page.url, response.status if response else 0, phase)
    report["observations"].append(result)
    return result


def finish(report: dict[str, Any], observation: dict[str, Any], status: str) -> None:
    report["status"] = status
    report["verification"] = observation["verification"]
    verification = observation["verification"]
    report["captcha_detected"] = verification is not None and verification["kind"] == "captcha"


def wait_for_page(page: Any, condition: str, report: dict[str, Any]) -> None:
    try:
        page.wait_for_function(condition, timeout=20000)
    except Exception as error:
        report["wait_error"] = type(error).__name__


def listing_response(response: Any) -> bool:
    target = urlsplit(LIST_URL)
    url = urlsplit(response.url)
    return response.request.method == "POST" and url.hostname == target.hostname and url.path.split(";", 1)[0] == target.path


def diagnose(page: Any, report: dict[str, Any]) -> None:
    response = page.goto(LIST_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_load_state("load", timeout=30000)
    initial = observe(page, response, "initial-listing", report)
    if initial["http_status"] in {401, 403, 429} or (initial["verification"] or {}).get("kind") == "captcha":
        finish(report, initial, "blocked")
        return
    if not initial["listing_available"]:
        wait_for_page(page, READY, report)
        initial = observe(page, response, "after-browser-verification", report)
    if not initial["listing_available"]:
        finish(report, initial, "blocked" if initial["verification"] else "unexpected-page")
        return
    page.wait_for_function("() => typeof window.PF === 'function' && !!window.PF('listaRemate')", timeout=15000)
    with page.expect_response(listing_response, timeout=30000) as pending:
        page.locator(f'select[name="{LIST_ID}_rppDD"]').select_option("12", timeout=10000)
    response = pending.value
    body = response.text() if not 300 <= response.status < 400 else ""
    verification = detect_verification(body, response.status, response.headers.get("location", ""))
    report["pagination_response"] = {
        "http_status": response.status,
        "location": diagnostic_url(response.headers.get("location", "")),
        "verification": verification,
    }
    if verification is not None:
        if verification["provider"] == "perfdrive" and response.status in {301, 302, 303, 307, 308}:
            destination = response.headers.get("location", "")
            if urlsplit(destination).scheme == "https" and urlsplit(destination).hostname == "validate.perfdrive.com":
                response = page.goto(destination, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_load_state("load", timeout=30000)
                current = observe(page, response, "verification-page", report)
                if current["http_status"] not in {401, 403, 429} and (current["verification"] or {}).get("kind") != "captcha":
                    wait_for_page(page, READY, report)
                    current = observe(page, response, "after-browser-verification", report)
                if current["verification"] is None and not current["listing_available"]:
                    current["verification"] = verification
                finish(report, current, "verification-cleared" if current["listing_available"] else "blocked")
                return
        current = {"verification": verification}
        finish(report, current, "blocked")
        return
    if response.status != 200:
        finish(report, {"verification": None}, "unexpected-response")
        return
    wait_for_page(page, TWELVE, report)
    current = observe(page, response, "twelve-auction-pagination", report)
    if current["listing_available"] and current["cards"] == 12:
        finish(report, current, "pagination-accessible")
    else:
        finish(report, current, "blocked" if current["verification"] else "unexpected-page")


def run_probe(output: Path, factory: Any = None) -> dict[str, Any]:
    if output.exists():
        raise ValueError("Probe output must be a new file")
    if factory is None:
        from playwright.sync_api import sync_playwright
        factory = sync_playwright
    report: dict[str, Any] = {
        "started_at": utc_now(), "status": "failed", "publishable": False,
        "page_size": 12, "captcha_detected": False, "captcha_solver_used": False,
        "verification": None, "observations": [],
    }
    try:
        with factory() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                diagnose(page, report)
            finally:
                browser.close()
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": diagnostic_error(error)}
    finally:
        report["finished_at"] = utc_now()
        write_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = run_probe(arguments.output)
    print(json.dumps(report, ensure_ascii=False))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        verification = report.get("verification") or {}
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"### Browser verification probe\n\nResult: **{report['status']}**\n\nProvider: **{verification.get('provider', 'not detected')}**\n\nCAPTCHA detected: **{report['captcha_detected']}**\n\nNo CAPTCHA solver was used and no data was published.\n")
    raise SystemExit(0 if report["status"] == "pagination-accessible" else 4)


if __name__ == "__main__":
    main()
