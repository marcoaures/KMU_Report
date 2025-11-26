"""HTTP helpers with safe defaults for reachability checks and downloads."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import requests

from config.config import HEADERS, REQUEST_TIMEOUT, USER_AGENT



def safe_get(
    url: str,
    allow_redirects: bool = True,
    return_reason: bool = False,
    robots_txt: Optional[str] = None,
    user_agent: str = USER_AGENT,
    log_disallowed: bool = False,
):
    """HTTP GET with common headers, timeout and error handling.

    If ``return_reason`` is True, return a tuple of (response, error_reason) where
    ``error_reason`` is a short string describing why the request failed.
    """
    if robots_txt is not None:
        from analysis.sitemap_utils import robots_allows_url

        if not robots_allows_url(robots_txt, url, user_agent=user_agent):
            if log_disallowed:
                print(f"[safe_get] disallowed_by_robots: {url}")
            return (None, "disallowed_by_robots") if return_reason else None

    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=allow_redirects,
        )
        if return_reason:
            return resp, None
        return resp
    except requests.Timeout:
        return (None, "timeout") if return_reason else None
    except requests.ConnectionError:
        return (None, "connection_error") if return_reason else None
    except requests.RequestException as exc:
        return (None, exc.__class__.__name__.lower()) if return_reason else None


def check_website_reachable(
    domain: str,
    get_fn: Callable = safe_get,
) -> Tuple[bool, Optional[str], Optional[requests.Response], str]:
    """
    Try to reach the website via HTTPS first, then HTTP.

    Returns:
        reachable (bool),
        base_url (str | None),
        base_response (requests.Response | None),
        reachability_status (str)
    """
    https_url = f"https://{domain}/"
    http_url = f"http://{domain}/"

    last_error = "unreachable"

    for url in (https_url, http_url):
        resp, error = get_fn(url, return_reason=True)
        if resp:
            status = resp.status_code
            if status < 400:
                return True, url, resp, "ok"
            return False, url, None, f"http_{status}"
        if error:
            last_error = error

    return False, None, None, last_error


def check_https_enforced(domain: str, get_fn: Callable = safe_get) -> Optional[bool]:
    """
    Check if http://<domain> is redirected to https://...

    Returns:
        True  -> HTTP redirected to HTTPS
        False -> HTTP reachable but not redirected to HTTPS
        None  -> HTTP not reachable / cannot determine
    """
    http_url = f"http://{domain}/"
    resp = get_fn(http_url, allow_redirects=True)
    if not resp:
        return None
    final_url = resp.url.lower()
    return final_url.startswith("https://")


def check_hsts(resp_https: Optional[requests.Response]) -> str:
    """Return the Strict-Transport-Security header value if present, else empty string."""
    if not resp_https:
        return ""
    return resp_https.headers.get("Strict-Transport-Security", "")
