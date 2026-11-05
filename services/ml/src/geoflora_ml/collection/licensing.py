from urllib.parse import unquote, urlparse


_ALLOWED_CODES = {"cc0", "cc-by", "cc-by-sa"}
# Non-commercial licences are accepted only when a caller opts in (non-invasive look-alike photos for this
# non-commercial research workspace; see docs/ai-review-and-auto-promotion.md). Invasive training data never uses them.
_NONCOMMERCIAL_CODES = {"cc-by-nc", "cc-by-nc-sa"}
_ALLOWED_PATHS = {
    "/publicdomain/zero/1.0/",
    "/licenses/by/2.0/",
    "/licenses/by/2.5/",
    "/licenses/by/3.0/",
    "/licenses/by/4.0/",
    "/licenses/by-sa/2.0/",
    "/licenses/by-sa/2.5/",
    "/licenses/by-sa/3.0/",
    "/licenses/by-sa/4.0/",
}


_NONCOMMERCIAL_PATHS = {f"/licenses/{kind}/{version}/" for kind in ("by-nc", "by-nc-sa") for version in ("2.0", "2.5", "3.0", "4.0")}


def normalize_license(value: str | None, allow_noncommercial: bool = False) -> str | None:
    if not value:
        return None
    license_value = unquote(value.strip()).lower()
    if license_value in _ALLOWED_CODES or (allow_noncommercial and license_value in _NONCOMMERCIAL_CODES):
        return license_value

    parsed = urlparse(license_value)
    path = parsed.path.rstrip("/") + "/"
    if parsed.hostname in {"creativecommons.org", "www.creativecommons.org"}:
        if path == "/publicdomain/zero/1.0/":
            return "cc0"
        if path.startswith("/licenses/by/") and path in _ALLOWED_PATHS:
            return "cc-by"
        if path.startswith("/licenses/by-sa/") and path in _ALLOWED_PATHS:
            return "cc-by-sa"
        if allow_noncommercial and path in _NONCOMMERCIAL_PATHS:
            return "cc-by-nc-sa" if path.startswith("/licenses/by-nc-sa/") else "cc-by-nc"
    return None


def training_license_eligible(value: str | None, attribution: str | None = None) -> bool:
    """Strict training allowlist while non-commercial permission is unresolved."""
    normalized = normalize_license(value)
    if normalized is not None:
        return normalized == "cc0" or bool((attribution or "").strip())
    return value == "owner_own_photo" and bool((attribution or "").strip())
