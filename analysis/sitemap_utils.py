"""robots.txt and sitemap discovery/parsing, with hard limits."""
from __future__ import annotations

import datetime
import re
import zlib
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from config import config as cfg
from http_tools.client import DomainClient

# Guessed sitemap locations, most common first. Only tried if robots.txt names none.
SITEMAP_PROBE_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
]


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def parse_iso_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse ISO-ish date strings into a timezone-aware datetime (best effort)."""
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def check_robots(domain: str, client: DomainClient) -> Tuple[Optional[bool], str]:
    """Fetch robots.txt. Returns (present, content); present is None if the
    server could not be asked at all."""
    resp = None
    for scheme in ("https", "http"):
        resp, reason = client.get(
            f"{scheme}://{domain}/robots.txt", max_bytes=cfg.MAX_TEXT_BYTES, return_reason=True
        )
        if resp is not None or reason not in ("connection_error", "tls_error", "timeout"):
            break
    if resp is None:
        return None, ""
    if resp.status_code != 200:
        return False, ""
    body = resp.text or ""
    if "html" in resp.headers.get("Content-Type", "").lower() or "<html" in body[:2000].lower():
        return False, ""
    return True, body


def sitemaps_from_robots(robots_txt: str) -> List[str]:
    urls = []
    for line in (robots_txt or "").splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url.lower().startswith(("http://", "https://")):
                urls.append(url)
    return list(dict.fromkeys(urls))


def fetch_sitemap_root(url: str, client: DomainClient, probe: bool = False) -> Optional[ET.Element]:
    """Download one sitemap file and return its XML root (urlset/sitemapindex)."""
    resp = client.get(url, max_bytes=cfg.MAX_SITEMAP_BYTES, probe=probe)
    if resp is None or resp.status_code != 200:
        return None
    raw = resp.content
    if raw[:2] == b"\x1f\x8b":  # gzip file served as-is
        try:
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, cfg.MAX_SITEMAP_BYTES)
        except zlib.error:
            return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    tag = root.tag.rsplit("}", 1)[-1].lower()
    return root if tag in ("urlset", "sitemapindex") else None


def _children(root: ET.Element, name: str):
    for el in root:
        if el.tag.rsplit("}", 1)[-1].lower() == name:
            yield el


def _child_text(el: ET.Element, name: str) -> str:
    for child in _children(el, name):
        return (child.text or "").strip()
    return ""


def collect_sitemaps(base_url: str, robots_txt: str, client: DomainClient) -> Dict[str, Any]:
    """Find and read the site's sitemaps.

    Returns a dict with:
        sitemaps   top-level sitemap URLs that really are sitemaps
        sources    url -> "robots.txt" | "guessed"
        urls       page URLs (deduplicated)
        lastmods   page URL -> datetime | None
        truncated  True if a limit (files, depth, URLs) cut the crawl short
    """
    out: Dict[str, Any] = {"sitemaps": [], "sources": {}, "urls": [], "lastmods": {},
                           "truncated": False}
    queue: deque = deque()
    declared = sitemaps_from_robots(robots_txt)
    if declared:
        for url in declared:
            queue.append((url, 0, "robots.txt", False))
    else:
        for path in SITEMAP_PROBE_PATHS:
            queue.append((urljoin(base_url + "/", path.lstrip("/")), 0, "guessed", True))

    seen = set()
    files = 0
    lastmods: Dict[str, Optional[datetime.datetime]] = {}
    while queue:
        url, depth, source, is_probe = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if files >= cfg.MAX_SITEMAP_FILES:
            out["truncated"] = True
            break
        root = fetch_sitemap_root(url, client, probe=is_probe)
        if root is None:
            # ran out of budget or guesses: stop quietly
            if client.stop_reason or client.requests_made >= cfg.MAX_REQUESTS_PER_DOMAIN:
                out["truncated"] = bool(out["sitemaps"])
                break
            continue
        files += 1
        if depth == 0:
            out["sitemaps"].append(url)
            out["sources"][url] = source
            if is_probe:
                # one guessed sitemap is enough
                queue = deque(item for item in queue if not item[3])

        if root.tag.rsplit("}", 1)[-1].lower() == "sitemapindex":
            for sm in _children(root, "sitemap"):
                loc = _child_text(sm, "loc")
                if not loc:
                    continue
                if depth + 1 >= cfg.MAX_SITEMAP_DEPTH:
                    out["truncated"] = True
                    continue
                queue.append((loc, depth + 1, source, False))
            continue

        for url_el in _children(root, "url"):
            loc = _child_text(url_el, "loc")
            if not loc:
                continue
            if len(lastmods) >= cfg.MAX_SITEMAP_URLS:
                out["truncated"] = True
                break
            lm = _child_text(url_el, "lastmod")
            dt = parse_iso_date(lm) if lm else None
            if loc not in lastmods or dt is not None:
                lastmods[loc] = dt

    out["urls"] = list(lastmods.keys())
    out["lastmods"] = lastmods
    return out


def count_pages_by_recency(lastmods: Dict[str, Optional[datetime.datetime]]) -> Dict[str, int]:
    """Number of URLs changed in the last 12/6/3/1 months."""
    now = now_utc()
    periods = {
        "12m": now - datetime.timedelta(days=365),
        "6m": now - datetime.timedelta(days=182),
        "3m": now - datetime.timedelta(days=91),
        "1m": now - datetime.timedelta(days=30),
    }
    counts = {k: 0 for k in periods}
    for dt in lastmods.values():
        if not dt:
            continue
        for key, threshold in periods.items():
            if dt >= threshold:
                counts[key] += 1
    return counts


def slug_has_keyword(slug: str, keyword: str) -> bool:
    """True if `keyword` appears in `slug` as a separate alphanumeric token."""
    if not slug or not keyword:
        return False
    tokens = [t for t in re.split(r"[^a-z0-9]+", slug.lower()) if t]
    return keyword.lower() in tokens
