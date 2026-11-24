from urllib.parse import urlsplit


CAPTCHA_MARKERS = {
    "hcaptcha": ("h-captcha", "hcaptcha.com", "hcaptcha"),
    "recaptcha": ("g-recaptcha", "google.com/recaptcha", "recaptcha.net"),
    "turnstile": ("cf-turnstile", "challenges.cloudflare.com/turnstile"),
}


class VerificationRequired(ValueError):
    def __init__(self, verification: dict[str, str]):
        self.verification = verification
        super().__init__(f"Source verification required: {verification['provider']} ({verification['kind']})")


def detect_verification(body: str, status: int = 200, location: str = "") -> dict[str, str] | None:
    lowered = body.lower()
    for provider, markers in CAPTCHA_MARKERS.items():
        if any(marker in lowered for marker in markers):
            return {"kind": "captcha", "provider": provider, "signal": "captcha-markup"}
    if urlsplit(location).hostname == "validate.perfdrive.com":
        return {"kind": "bot-verification", "provider": "perfdrive", "signal": "verification-host"}
    protected = "formbuscarremateexterno" in lowered or "formdetalleremate" in lowered or "formseguimiento" in lowered
    if not protected:
        if "perfdrive.com" in lowered or "<center>rdwr</center>" in lowered:
            return {"kind": "bot-verification", "provider": "perfdrive", "signal": "verification-markup"}
        if "radware" in lowered:
            return {"kind": "bot-verification", "provider": "radware", "signal": "verification-markup"}
        if "/cdn-cgi/challenge-platform/" in lowered:
            return {"kind": "bot-verification", "provider": "cloudflare", "signal": "verification-markup"}
    if status in {401, 403, 429}:
        return {"kind": "access-denied", "provider": "unknown", "signal": f"http-{status}"}
    return None
