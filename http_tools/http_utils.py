"""Reachability, HTTPS enforcement and HSTS helpers."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from http_tools.client import DomainClient, registrable_domain


def is_html(resp: Optional[requests.Response]) -> bool:
    """True if the response carries an HTML document."""
    if resp is None:
        return False
    ctype = resp.headers.get("Content-Type", "").lower()
    return "html" in ctype


def check_website_reachable(domain: str, client: DomainClient) -> Dict[str, Any]:
    """Try HTTPS first, then HTTP.

    Returns a dict with:
        reachable   True only for a final status below 400
        status      "ok", "http_<code>", "blocked_http_403/429" or an error label
        response    the homepage response (only if reachable)
        base_url    scheme://host of the final URL (only if reachable)
        final_domain / other_domain   where redirects ended up
    """
    out: Dict[str, Any] = {
        "reachable": False, "status": "unreachable", "response": None,
        "base_url": None, "final_domain": None, "other_domain": None,
    }
    for url in (f"https://{domain}/", f"http://{domain}/"):
        resp, error = client.get(url, is_homepage=True, return_reason=True)
        if resp is not None:
            code = resp.status_code
            final = urlparse(resp.url)
            out["final_domain"] = final.netloc.lower()
            out["other_domain"] = registrable_domain(final.netloc) != registrable_domain(domain)
            if code < 400:
                out.update(reachable=True, status="ok", response=resp,
                           base_url=f"{final.scheme}://{final.netloc}")
            elif code in (403, 429):
                out["status"] = f"blocked_http_{code}"
            else:
                out["status"] = f"http_{code}"
            return out
        if error:
            out["status"] = error
        if error in ("disallowed_by_robots", "budget_exhausted") or client.stop_reason:
            break
    return out


def check_https_enforced(
    domain: str, client: DomainClient, base_url: Optional[str]
) -> Optional[bool]:
    """Is http://<domain>/ redirected to HTTPS?

    True/False as measured, None if plain HTTP does not answer at all.
    """
    if base_url and base_url.startswith("http://"):
        return False  # the site itself is served over plain HTTP
    # Only headers matter here, so download next to nothing.
    resp = client.get(f"http://{domain}/", max_bytes=2048)
    if resp is None:
        return None
    return resp.url.lower().startswith("https://")


def parse_hsts(resp: Optional[requests.Response]) -> Dict[str, Any]:
    """Split the Strict-Transport-Security header into its parts."""
    out: Dict[str, Any] = {"hsts_header": None, "hsts_max_age": None,
                           "hsts_include_subdomains": None}
    if resp is None or not resp.url.lower().startswith("https://"):
        return out
    value = resp.headers.get("Strict-Transport-Security", "")
    out["hsts_header"] = value
    if value:
        m = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.I)
        out["hsts_max_age"] = int(m.group(1)) if m else None
        out["hsts_include_subdomains"] = "includesubdomains" in value.lower()
    return out
