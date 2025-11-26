# api_clients.py
from __future__ import annotations

from typing import Optional, Dict

import random
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from config.dictionary_config import SOCIAL_DOMAINS
from config.config import (
    DEBUG_API,
    PAGESPEED_API_KEY,
    REQUEST_TIMEOUT,
    SKIPPING_APIS,
    WHATCMS_API_KEY,
    WHATCMS_PRIVATE,
)


def _mask_api_key(full_url: str) -> str:
    """Return a URL string with the ``key`` query parameter redacted."""
    try:
        parsed = urlparse(full_url)
        masked_query = urlencode(
            [(k, "***" if k == "key" else v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
        )
        return urlunparse(parsed._replace(query=masked_query))
    except Exception:
        return full_url


def _sleep_with_backoff(attempt: int, base_delay: int = 1, max_delay: int = 30) -> None:
    """
    Sleep for a jittered exponential backoff interval.

    Args:
        attempt: 1-based attempt count.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
    """

    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    jittered_delay = random.uniform(0, delay)
    time.sleep(jittered_delay)


def _log_whatcms_results(techs: list[dict]) -> None:
    """Emit a compact summary of WhatCMS technologies when DEBUG_API is True."""

    if not DEBUG_API:
        return

    print(f"[WhatCMS Parsed] results={len(techs)}")
    for tech in techs[:5]:
        name = tech.get("name")
        version = tech.get("version")
        categories = tech.get("categories") or []
        print(f"  - {name!r} version={version!r} categories={categories}")


def _normalize_social_network(network: str) -> Optional[str]:
    mapping = {
        "twitter": "Twitter",
        "x": "X",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "linkedin": "LinkedIn",
        "youtube": "YouTube",
        "tiktok": "TikTok",
    }

    normalized = mapping.get(network.lower()) if network else None
    return normalized


def _extract_social_from_whatcms(meta: dict) -> list[str]:
    """Map WhatCMS social entries to our normalized labels."""

    social_entries = meta.get("social", []) if isinstance(meta, dict) else []
    if not isinstance(social_entries, list):
        return []

    found: set[str] = set()
    for entry in social_entries:
        if not isinstance(entry, dict):
            continue

        network = entry.get("network") or ""
        url = entry.get("url") or ""

        name = _normalize_social_network(network)

        if not name and url:
            u = url.lower()
            for key, display in SOCIAL_DOMAINS.items():
                if key in u:
                    name = display
                    break

        if name:
            found.add(name)

    return sorted(found)


def whatcms_social(meta: dict) -> list[str]:
    """
    Return normalized social profile names from WhatCMS metadata and log debug details.

    In DEBUG_API mode, this prints both the raw social array returned by WhatCMS and the
    normalized labels derived from it so users can verify the extraction behavior.
    """

    raw_social = meta.get("social", []) if isinstance(meta, dict) else []
    normalized = _extract_social_from_whatcms(meta)

    if DEBUG_API:
        print("[WhatCMS Social] raw entries:", raw_social)
        print("[WhatCMS Social] normalized:", normalized)

    return normalized


def fetch_pagespeed(url: str, strategy: str = "desktop") -> Optional[int]:
    """
    Fetch Lighthouse performance score from Google PageSpeed Insights
    for a given strategy ("desktop" or "mobile").

    Returns:
        0–100 (int) or None on error / if APIs are skipped.
    """
    if SKIPPING_APIS or not PAGESPEED_API_KEY:
        return None

    api_url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {
        "url": url,
        "key": PAGESPEED_API_KEY,
        "strategy": strategy,
        "category": "performance",
        # only request what we actually need
        "fields": "id,lighthouseResult/categories/performance/score",
    }

    for attempt in range(1, 4):
        try:
            resp = requests.get(api_url, params=params, timeout=60)

            if DEBUG_API:
                print("\n[PageSpeed Request]")
                print("Attempt:", attempt)
                print("Strategy:", strategy)
                print("URL:", _mask_api_key(resp.url))
                print("Status:", resp.status_code)

            if resp.status_code != 200:
                if DEBUG_API:
                    try:
                        print("Error JSON:", resp.json())
                    except Exception:
                        print("Error text:", resp.text[:500])
                return None

            data = resp.json()
            lr = data.get("lighthouseResult", {})
            categories = lr.get("categories", {})
            perf_score = categories.get("performance", {}).get("score")
            perf_score = int(perf_score * 100) if perf_score is not None else None

            if DEBUG_API:
                print("[PageSpeed Parsed]", strategy, "performance score:", perf_score)

            return perf_score

        except requests.exceptions.ReadTimeout as e:
            if DEBUG_API:
                print("[PageSpeed ReadTimeout]", strategy, "attempt", attempt, ":", e)

            if attempt < 3:
                _sleep_with_backoff(attempt)
            continue
        except Exception as e:
            if DEBUG_API:
                print("[PageSpeed Error]", strategy, ":", str(e))
            return None

    return None


def detect_cms_and_server(domain: str) -> Dict[str, Optional[str]]:
    """
    Robust WhatCMS detection with:
      - retries (3)
      - explicit error signaling
      - NO new CSV fields
      - encode failures via cms_name="error_*"

    Verbose mode (`DEBUG_API=True`) now mirrors the PageSpeed helper by printing
    each request URL (with key masked), attempt number, HTTP status, API result
    code/message, and a compact summary of detected technologies.
    """
    if SKIPPING_APIS or not WHATCMS_API_KEY:
        return {
            "cms_name": "skipped",
            "cms_version": None,
            "cms_version_up_to_date": None,
            "whatcms_status": "skipped",
            "whatcms_social_profiles": [],
        }

    api_url = "https://whatcms.org/API/Tech"
    params = {
        "key": WHATCMS_API_KEY,
        "url": f"https://{domain}",
    }

    if WHATCMS_PRIVATE:
        params["private"] = "true"

    for attempt in range(1, 4):
        try:
            resp = requests.get(api_url, params=params, timeout=REQUEST_TIMEOUT)

            if DEBUG_API:
                print("\n[WhatCMS Request]")
                print("Attempt:", attempt)
                print("URL:", _mask_api_key(resp.url))
                print("Status:", resp.status_code)

            try:
                data = resp.json()
            except Exception as e:
                if DEBUG_API:
                    print(f"[WhatCMS] Failed to parse JSON: {e}")
                    print("Body:", resp.text[:500])
                return {
                    "cms_name": "api_error_invalid_json",
                    "cms_version": None,
                    "cms_version_up_to_date": None,
                    "whatcms_status": "api_error_invalid_json",
                    "whatcms_social_profiles": [],
                }

            result = data.get("result", {}) if isinstance(data, dict) else {}
            code = result.get("code") if isinstance(result, dict) else None
            msg = result.get("msg") if isinstance(result, dict) else None

            if DEBUG_API:
                print(f"[WhatCMS] API result code={code} msg={msg!r}")

            # API returned an error code
            if code != 200:
                if DEBUG_API:
                    print(f"[WhatCMS] API error code {code}: {msg}")
                return {
                    "cms_name": f"api_error_{code}",
                    "cms_version": None,
                    "cms_version_up_to_date": None,
                    "whatcms_status": f"api_error_{code}",
                    "whatcms_social_profiles": [],
                }

            techs = data.get("results", []) if isinstance(data, dict) else []
            if not isinstance(techs, list):
                techs = []

            _log_whatcms_results(techs)

            cms_name = None
            cms_version = None
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            social_profiles = whatcms_social(meta)

            for tech in techs:
                cats = tech.get("categories") or []
                if "CMS" in cats or "Blog" in cats:
                    cms_name = tech.get("name")
                    cms_version = tech.get("version")
                    break

            # No CMS detected (actual result)
            if cms_name is None:
                if DEBUG_API:
                    print("[WhatCMS Parsed] No CMS detected")
                return {
                    "cms_name": "none",
                    "cms_version": None,
                    "cms_version_up_to_date": None,
                    "whatcms_status": "success",
                    "whatcms_social_profiles": social_profiles,
                }

            # Success
            if DEBUG_API:
                print(f"[WhatCMS Parsed] cms={cms_name!r} version={cms_version!r}")
            return {
                "cms_name": cms_name,
                "cms_version": cms_version,
                "cms_version_up_to_date": None,
                "whatcms_status": "success",
                "whatcms_social_profiles": social_profiles,
            }

        except requests.exceptions.Timeout:
            if DEBUG_API:
                print(f"[WhatCMS] Timeout attempt {attempt} for {domain}")

            if attempt < 3:
                _sleep_with_backoff(attempt)

        except Exception as e:
            if DEBUG_API:
                print(f"[WhatCMS] Error attempt {attempt} for {domain}: {e}")

            if attempt < 3:
                _sleep_with_backoff(attempt)

    # After all retries
    return {
        "cms_name": "error_timeout",
        "cms_version": None,
        "cms_version_up_to_date": None,
        "whatcms_status": "error_timeout",
        "whatcms_social_profiles": [],
    }
