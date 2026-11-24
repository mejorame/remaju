import json
from unittest.mock import Mock

import pytest
import requests

from utils.debugger import Trace
from utils.verification import VerificationRequired, detect_verification


@pytest.mark.parametrize("html, provider", [
    ('<div class="h-captcha"></div>', "hcaptcha"),
    ('<iframe src="https://newassets.hcaptcha.com/captcha"></iframe>', "hcaptcha"),
    ('<div class="g-recaptcha"></div>', "recaptcha"),
    ('<div class="cf-turnstile"></div>', "turnstile"),
])
def test_interactive_providers_are_distinguished(html, provider):
    assert detect_verification(html) == {"kind": "captcha", "provider": provider, "signal": "captcha-markup"}


def test_perfdrive_redirect_is_verification_not_proof_of_captcha():
    result = detect_verification("", 302, "https://validate.perfdrive.com/?token=secret")
    assert result == {"kind": "bot-verification", "provider": "perfdrive", "signal": "verification-host"}


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_denied_does_not_guess_captcha_provider(status):
    assert detect_verification("Acceso denegado", status) == {"kind": "access-denied", "provider": "unknown", "signal": f"http-{status}"}


def test_protected_listing_with_image_captcha_is_not_a_challenge():
    html = '<script>ssConf("cu", "validate.perfdrive.com")</script><form id="formBuscarRemateExterno"><input name="captcha"></form>'
    assert detect_verification(html) is None


def test_perfdrive_interstitial_is_recognized_without_redirect():
    assert detect_verification('<html><center>rdwr</center></html>')["provider"] == "perfdrive"


def test_unknown_redirect_is_not_misclassified_as_verification():
    assert detect_verification("", 302, "/remaju/error/error500.xhtml") is None
    assert detect_verification("", 302, "https://validate.perfdrive.com.example.com/") is None


@pytest.mark.parametrize("status, body, location", [
    (403, "Acceso denegado", ""),
    (302, "private-challenge-token", "https://validate.perfdrive.com/?token=private-challenge-token"),
    (200, '<div class="h-captcha">private-challenge-token</div>', ""),
])
def test_trace_stops_without_retry_and_does_not_publish_challenge_material(tmp_path, status, body, location):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    response.headers["Location"] = location
    session = Mock()
    session.request.return_value = response
    trace = Trace(tmp_path / "trace")
    with pytest.raises(VerificationRequired):
        trace.request(session, "POST", "https://example.com/list", "list-page")
    session.request.assert_called_once()
    assert trace.last_response["challenge_detected"] is True
    captured = json.loads((trace.directory / "000001-list-page.txt").read_text())
    assert captured["verification"] == trace.last_response["verification"]
    assert "private-challenge-token" not in (trace.directory / "events.jsonl").read_text()
