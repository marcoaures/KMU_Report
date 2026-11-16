"""PageSpeed Insights and WhatCMS clients with shared rate limiting."""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from config import config as cfg
from http_tools.client import registrable_domain

log = logging.getLogger(__name__)


class RateLimiter:
    """At most one call per interval, across all worker threads."""

    def __init__(self, interval_name: str) -> None:
        self._interval_name = interval_name
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        interval = float(getattr(cfg, self._interval_name))
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + interval
        if start > now:
            time.sleep(start - now)


_pagespeed_limiter = RateLimiter("PAGESPEED_MIN_INTERVAL")
_whatcms_limiter = RateLimiter("WHATCMS_MIN_INTERVAL")
# Set once WhatCMS says the key is invalid or the quota is used up: no point
# in asking again during this run.
_whatcms_disabled = threading.Event()
_whatcms_disabled_reason = ""


def _debug(*args) -> None:
    if cfg.DEBUG_API:
        print(*args)


def _backoff(attempt: int, retry_after: Optional[str] = None, max_delay: float = 60.0) -> None:
    """Sleep before the next attempt: Retry-After if given, else jittered exponential."""
    delay = None
    if retry_after:
        try:
            delay = min(float(retry_after), max_delay)
        except ValueError:
            delay = None
    if delay is None:
        delay = random.uniform(1.0, min(max_delay, 2.0 ** attempt))
    time.sleep(delay)


# ---------------------------------------------------------------------------
# PageSpeed Insights
# ---------------------------------------------------------------------------

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
# Lighthouse 13 calls the audit "third-parties-insight"; older versions "third-party-summary".
THIRD_PARTY_AUDITS = ("third-parties-insight", "third-party-summary")


def _collect_entities(node: Any, found: List[str]) -> None:
    """Pull every "entity" name out of an audit's details, whatever their nesting."""
    if isinstance(node, dict):
        entity = node.get("entity")
        if isinstance(entity, dict):
            entity = entity.get("text")
        if isinstance(entity, str) and entity.strip():
            found.append(entity.strip())
        for value in node.values():
            _collect_entities(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_entities(value, found)


def extract_third_parties(data: dict, page_url: str) -> Optional[List[str]]:
    """Names of third parties Lighthouse saw while loading the page, or None
    if the response does not contain the audit."""
    audits = (data.get("lighthouseResult") or {}).get("audits") or {}
    audit = next((audits[a] for a in THIRD_PARTY_AUDITS if a in audits), None)
    if audit is None:
        return None
    found: List[str] = []
    _collect_entities(audit.get("details"), found)
    own = registrable_domain(urlparse(page_url).netloc)
    return sorted({name for name in found if registrable_domain(name) != own and name.lower() != own})


def fetch_pagespeed(url: str, strategy: str = "mobile", third_parties: bool = False) -> Dict[str, Any]:
    """Lighthouse performance score (0-100) for ``strategy``.

    Returns {"score", "status", "third_parties"}. status is "ok", "skipped",
    "no_score", "rate_limited", "timeout", "http_<code>" or "error".
    """
    out: Dict[str, Any] = {"score": None, "status": "skipped", "third_parties": None}
    if cfg.SKIPPING_APIS or not cfg.PAGESPEED_API_KEY:
        return out

    fields = ["lighthouseResult/categories/performance/score"]
    if third_parties:
        fields += [f"lighthouseResult/audits/{a}/details" for a in THIRD_PARTY_AUDITS]
    params = {"url": url, "key": cfg.PAGESPEED_API_KEY, "strategy": strategy,
              "category": "performance", "fields": ",".join(fields)}

    for attempt in range(1, cfg.API_MAX_ATTEMPTS + 1):
        last = attempt == cfg.API_MAX_ATTEMPTS
        _pagespeed_limiter.wait()
        try:
            resp = requests.get(PSI_URL, params=params, timeout=cfg.PAGESPEED_TIMEOUT)
        except requests.Timeout:
            out["status"] = "timeout"
            if not last:
                _backoff(attempt)
            continue
        except requests.RequestException:
            out["status"] = "error"
            if not last:
                _backoff(attempt)
            continue

        _debug("[PageSpeed]", strategy, url, "->", resp.status_code)
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                out["status"] = "error"
                return out
            score = ((data.get("lighthouseResult") or {}).get("categories") or {}) \
                .get("performance", {}).get("score")
            out["score"] = round(score * 100) if score is not None else None
            out["status"] = "ok" if score is not None else "no_score"
            if third_parties:
                out["third_parties"] = extract_third_parties(data, url)
            return out
        if resp.status_code == 400 and "fields" in params and third_parties:
            # the field filter was not accepted: ask again for the full response
            params.pop("fields")
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            out["status"] = "rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}"
            if not last:
                _backoff(attempt, resp.headers.get("Retry-After"))
            continue
        out["status"] = f"http_{resp.status_code}"
        return out
    return out


# ---------------------------------------------------------------------------
# WhatCMS
# ---------------------------------------------------------------------------

WHATCMS_URL = "https://whatcms.org/API/Tech"
_SOCIAL_NAMES = {"twitter": "X", "x": "X", "instagram": "Instagram", "facebook": "Facebook",
                 "linkedin": "LinkedIn", "youtube": "YouTube", "tiktok": "TikTok"}


def _whatcms_social(meta: Any) -> List[str]:
    from analysis.html_analysis import social_network_for_url

    entries = meta.get("social", []) if isinstance(meta, dict) else []
    found = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name = _SOCIAL_NAMES.get((entry.get("network") or "").lower()) \
            or social_network_for_url(entry.get("url") or "")
        if name:
            found.add(name)
    return sorted(found)


def detect_cms_whatcms(domain: str) -> Dict[str, Any]:
    """Ask WhatCMS which CMS a site runs.

    Returns {"cms_name", "cms_version", "whatcms_status", "whatcms_social_profiles"}.
    whatcms_status: "success", "skipped", "rate_limited", "quota_exceeded",
    "invalid_key", "timeout", "invalid_json", "api_error_<code>" or "error".
    cms_name is "" when WhatCMS answered but found no CMS, None when it did not answer.
    """
    global _whatcms_disabled_reason
    out: Dict[str, Any] = {"cms_name": None, "cms_version": None,
                           "whatcms_status": "skipped", "whatcms_social_profiles": []}
    if cfg.SKIPPING_APIS or not cfg.WHATCMS_API_KEY or cfg.WHATCMS_MODE == "off":
        return out
    if _whatcms_disabled.is_set():
        out["whatcms_status"] = _whatcms_disabled_reason
        return out

    params = {"key": cfg.WHATCMS_API_KEY, "url": f"https://{domain}"}
    if cfg.WHATCMS_PRIVATE:
        params["private"] = "true"

    for attempt in range(1, cfg.API_MAX_ATTEMPTS + 1):
        last = attempt == cfg.API_MAX_ATTEMPTS
        _whatcms_limiter.wait()
        try:
            resp = requests.get(WHATCMS_URL, params=params, timeout=30)
        except requests.Timeout:
            out["whatcms_status"] = "timeout"
            if not last:
                _backoff(attempt)
            continue
        except requests.RequestException:
            out["whatcms_status"] = "error"
            if not last:
                _backoff(attempt)
            continue

        try:
            data = resp.json()
        except ValueError:
            out["whatcms_status"] = "invalid_json"
            return out
        result = data.get("result", {}) if isinstance(data, dict) else {}
        code = result.get("code") if isinstance(result, dict) else None
        _debug("[WhatCMS]", domain, "-> code", code, result.get("msg") if isinstance(result, dict) else "")

        if code == 120:  # too many requests: wait as told, then try again
            out["whatcms_status"] = "rate_limited"
            if not last:
                _backoff(attempt, str(result.get("retry_in_seconds") or ""), max_delay=120)
            continue
        if code in (100, 101, 102, 121, 123):  # key problems or quota used up
            reason = "quota_exceeded" if code == 121 else "invalid_key"
            _whatcms_disabled_reason = reason
            _whatcms_disabled.set()
            log.warning("WhatCMS disabled for the rest of this run: %s (code %s)", reason, code)
            out["whatcms_status"] = reason
            return out
        if code == 201:  # answered, nothing found
            out.update(cms_name="", whatcms_status="success")
            return out
        if code != 200:
            out["whatcms_status"] = f"api_error_{code}"
            return out

        techs = data.get("results", [])
        out["whatcms_status"] = "success"
        out["cms_name"] = ""
        out["whatcms_social_profiles"] = _whatcms_social(data.get("meta", {}))
        for tech in techs if isinstance(techs, list) else []:
            cats = tech.get("categories") or []
            if "CMS" in cats or "Blog" in cats:
                out["cms_name"] = tech.get("name") or ""
                out["cms_version"] = tech.get("version") or None
                break
        return out
    return out
