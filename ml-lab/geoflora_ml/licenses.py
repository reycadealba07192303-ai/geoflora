"""Normalisation and eligibility checks for image licenses.

GBIF media records carry a license URL (or code). Only images whose license is
explicitly listed in configs/default.yaml -> download.allowed_licenses are kept.
"""

from __future__ import annotations

import re

LICENSE_LABELS = {
    "CC0-1.0": "CC0 1.0 (public domain dedication)",
    "PDM-1.0": "Public Domain Mark 1.0",
    "CC-BY-4.0": "CC BY 4.0",
    "CC-BY-NC-4.0": "CC BY-NC 4.0 (non-commercial)",
    "CC-BY-SA-4.0": "CC BY-SA 4.0",
    "CC-BY-NC-SA-4.0": "CC BY-NC-SA 4.0 (non-commercial)",
    "CC-BY-ND-4.0": "CC BY-ND 4.0 (no derivatives)",
    "CC-BY-NC-ND-4.0": "CC BY-NC-ND 4.0 (non-commercial, no derivatives)",
}


def normalize_license(raw: str | None) -> str | None:
    """Map a license URL/code to a canonical code such as 'CC-BY-NC-4.0'. Returns None if unrecognised."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in {"nan", "none", "null"} or "all rights reserved" in s:
        return None
    if "publicdomain/zero" in s or s.startswith("cc0") or s == "cc-zero":
        return "CC0-1.0"
    if "publicdomain/mark" in s or s.startswith("pdm"):
        return "PDM-1.0"

    m = re.search(r"licenses/([a-z\-]+)/(\d\.\d)", s)
    if m:
        parts, version = m.group(1), m.group(2)
    else:
        m = re.match(r"cc[_\- ]?(by(?:[_\- ](?:nc|sa|nd))*)[_\- ]?(\d)[_\.](\d)$", s)
        if not m:
            return None
        parts, version = re.sub(r"[_ ]", "-", m.group(1)), f"{m.group(2)}.{m.group(3)}"
    return "CC-" + "-".join(p.upper() for p in parts.split("-") if p) + f"-{version}"


def is_license_allowed(code: str | None, allowed: list[str]) -> bool:
    return code is not None and code in set(allowed)


def build_attribution(creator: str | None, rights_holder: str | None, license_code: str | None,
                      source: str, reference_url: str | None) -> str:
    who = (creator or rights_holder or "Unknown creator").strip()
    lic = LICENSE_LABELS.get(license_code or "", license_code or "unknown license")
    text = f"{who}, {lic}, via {source}" if source else f"{who}, {lic}"
    if license_code not in {"CC0-1.0", "PDM-1.0"}:
        text = "© " + text
    if reference_url:
        text += f" ({reference_url})"
    return text
