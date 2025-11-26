"""Checks for security-related HTTP headers and well-known files."""
from __future__ import annotations

from typing import Dict, Optional

import requests

from http_tools.http_utils import safe_get


def check_security_headers(
    resp: Optional[requests.Response],
) -> Dict[str, bool]:
    """Check presence of common security-related HTTP response headers."""
    if not resp:
        return {
            "security_hsts": False,
            "security_x_frame_options": False,
            "security_x_content_type_options": False,
            "security_referrer_policy": False,
            "security_csp": False,
            "security_permissions_policy": False,
        }

    headers = {k.lower(): v for k, v in resp.headers.items()}
    return {
        "security_hsts": "strict-transport-security" in headers,
        "security_x_frame_options": "x-frame-options" in headers,
        "security_x_content_type_options": "x-content-type-options" in headers,
        "security_referrer_policy": "referrer-policy" in headers,
        "security_csp": "content-security-policy" in headers,
        "security_permissions_policy": "permissions-policy" in headers,
    }


def check_security_txt(domain: str, safe_get_fn=safe_get) -> bool:
    """Check for presence of a security.txt file at the IETF-recommended path."""
    url = f"https://{domain}/.well-known/security.txt"
    resp = safe_get_fn(url)
    return bool(resp and resp.status_code == 200)


def check_llms_txt(domain: str, safe_get_fn=safe_get) -> bool:
    """Check for presence of an llms.txt file in common locations."""
    candidates = [
        f"https://{domain}/.well-known/llms.txt",
        f"https://{domain}/llms.txt",
    ]
    for url in candidates:
        resp = safe_get_fn(url)
        if resp and resp.status_code == 200:
            return True
    return False
