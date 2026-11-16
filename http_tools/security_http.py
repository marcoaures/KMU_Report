"""Security-related HTTP headers and well-known files."""
from __future__ import annotations

from typing import Dict, Optional

import requests

from config import config as cfg
from http_tools.client import DomainClient

SECURITY_HEADERS = {
    "security_x_frame_options": "x-frame-options",
    "security_x_content_type_options": "x-content-type-options",
    "security_referrer_policy": "referrer-policy",
    "security_csp": "content-security-policy",
    "security_permissions_policy": "permissions-policy",
}


def check_security_headers(resp: Optional[requests.Response]) -> Dict[str, Optional[bool]]:
    """Presence of common security headers; None for all if there is no response."""
    if resp is None:
        return {col: None for col in SECURITY_HEADERS}
    headers = {k.lower() for k in resp.headers.keys()}
    return {col: name in headers for col, name in SECURITY_HEADERS.items()}


def _plain_text_file(client: DomainClient, url: str) -> Optional[str]:
    """Body of a text file, "" if it is missing or really an HTML error page,
    None if the request could not be made at all."""
    resp, reason = client.get(url, max_bytes=cfg.MAX_TEXT_BYTES, return_reason=True)
    if resp is None:
        return None
    if resp.status_code != 200:
        return ""
    body = resp.text or ""
    if "html" in resp.headers.get("Content-Type", "").lower() or "<html" in body[:2000].lower():
        return ""
    return body


def check_security_txt(base_url: str, client: DomainClient) -> Optional[bool]:
    """security.txt at the RFC 9116 location, with the mandatory Contact field."""
    body = _plain_text_file(client, f"{base_url}/.well-known/security.txt")
    if body is None:
        return None
    return "contact:" in body.lower()


def check_llms_txt(base_url: str, client: DomainClient) -> Optional[bool]:
    """llms.txt in the site root."""
    body = _plain_text_file(client, f"{base_url}/llms.txt")
    if body is None:
        return None
    return bool(body.strip())
