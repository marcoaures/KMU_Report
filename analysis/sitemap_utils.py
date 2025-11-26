"""Helpers to discover and parse sitemap-related resources for a domain."""
from __future__ import annotations

import datetime
import gzip
import re
from typing import Callable, Dict, List, Optional, Tuple
from urllib import robotparser
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from http_tools.http_utils import USER_AGENT, safe_get


def now_utc() -> datetime.datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)


def parse_iso_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse ISO-ish date strings into a timezone-aware UTC datetime (best effort)."""
    try:
        # Normalize common 'Z' suffix and parse
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        try:
            # Fallback: only the date part
            dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return None


def check_robots(domain: str, get_fn: Callable = safe_get) -> Tuple[bool, str]:
    """Fetch robots.txt and return (present_flag, content)."""
    robots_url = f"https://{domain}/robots.txt"
    resp = get_fn(robots_url)
    if not resp or resp.status_code != 200:
        return False, ""

    final_path = (urlparse(resp.url).path or "").lower()
    if not final_path.endswith("/robots.txt"):
        return False, ""

    body_l = resp.text.lower()
    if "<html" in body_l:
        return False, ""

    content_type = resp.headers.get("Content-Type", "").lower()
    if content_type and "text/html" in content_type:
        return False, ""

    return True, resp.text


def robots_allows_url(
    robots_txt: str, url: str, user_agent: str = USER_AGENT
) -> bool:
    """Return True if robots.txt allows fetching ``url`` for ``user_agent``."""

    if not robots_txt.strip():
        return True

    parser = robotparser.RobotFileParser()
    parser.parse(robots_txt.splitlines())

    try:
        return parser.can_fetch(user_agent, url)
    except Exception:
        # Be permissive if the robots directives are malformed.
        return True


def fetch_xml(
    url: str,
    get_fn: Callable = safe_get,
    robots_txt: Optional[str] = None,
    log_disallowed: bool = False,
) -> Optional[str]:
    resp = get_fn(url, robots_txt=robots_txt, log_disallowed=log_disallowed)
    if not resp or resp.status_code != 200:
        return None

    raw = resp.content
    text: Optional[str] = None

    # Attempt #1 — if it's a .gz URL, try to decompress if needed
    if url.endswith(".gz"):
        try:
            # case: raw gzipped bytes
            text = gzip.decompress(raw).decode("utf-8", errors="replace")
        except Exception:
            try:
                # case: already decompressed, raw is plain text
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                return None

    # Attempt #2 — non-gz URLs
    if text is None:
        try:
            # trust requests’ automatic Content-Encoding handling
            text = resp.text
        except Exception:
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                return None

    # Very loose sanity check
    if "<" not in text:
        return None

    return text


def get_sitemap_root(xml_text: str) -> Optional[ET.Element]:
    """Return the XML root element if it is a sitemap or sitemap index."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    if root.tag.endswith("urlset") or root.tag.endswith("sitemapindex"):
        return root
    return None


def find_sitemaps(
    domain: str,
    robots_txt: str,
    get_fn: Callable = safe_get,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Discover sitemap URLs in two steps:

      1) Look for 'Sitemap:' entries in robots.txt.
      2) If none found, probe a set of common sitemap (and sitemap index) URLs.

    Returns:
        (sitemaps, sitemap_sources) where:
            sitemaps: list of sitemap URLs
            sitemap_sources: mapping sitemap_url -> 'robots.txt' /
                             'heuristic_index' / 'heuristic_other'
    """
    sitemaps: List[str] = []
    sitemap_sources: Dict[str, str] = {}

    # 1) Look in robots.txt for explicit Sitemap: directives
    for line in robots_txt.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url:
                sitemaps.append(url)
                sitemap_sources[url] = "robots.txt"

    if sitemaps:
        # dedupe preserving order
        sitemaps = list(dict.fromkeys(sitemaps))
        # ensure sources exist for all after dedupe
        sitemap_sources = {url: sitemap_sources.get(url, "robots.txt") for url in sitemaps}
        return sitemaps, sitemap_sources

    # 2) Fallback: probe common locations, preferring index-like ones
    index_like_paths = [
        "/sitemap_index.xml",
        "/sitemap.xml",
        "/sitemap/sitemap-index.xml",
        "/sitemap/index.xml",
        "/wp-sitemap.xml",
        "/wp-sitemap-index.xml",
        "/sitemaps/sitemap-index.xml",
        "/sitemaps/sitemap.xml",
        "/sitemap_index.xml.gz",
        "/sitemap.xml.gz",
    ]

    other_paths = [
        "/sitemap1.xml",
        "/news-sitemap.xml",
        "/sitemap-news.xml",
        "/video-sitemap.xml",
        "/image-sitemap.xml",
        "/mobile-sitemap.xml",
        "/sitemap-products.xml",
        "/sitemap-posts.xml",
        "/sitemap-pages.xml",
        "/sitemap-categories.xml",
        "/sitemap-tags.xml",
        "/post-sitemap.xml",
        "/page-sitemap.xml",
        "/category-sitemap.xml",
        "/author-sitemap.xml",
        "/feeds/sitemap.xml",
        "/xml/sitemap.xml",
        "/data/sitemap.xml",
    ]

    def is_valid_sitemap(url: str) -> bool:
        if robots_txt and not robots_allows_url(robots_txt, url):
            return False

        xml = fetch_xml(url, get_fn=get_fn, robots_txt=robots_txt, log_disallowed=True)
        if not xml or not xml.strip():
            return False

        return get_sitemap_root(xml) is not None

    for path in index_like_paths:
        url = f"https://{domain}{path}"
        if is_valid_sitemap(url):
            return [url], {url: "heuristic_index"}

    for path in other_paths:
        url = f"https://{domain}{path}"
        if is_valid_sitemap(url):
            return [url], {url: "heuristic_other"}

    return [], {}


def parse_sitemap_for_urls_and_dates(
    xml_text: str,
    get_fn: Callable = safe_get,
    robots_txt: Optional[str] = None,
    log_disallowed: bool = False,
) -> Tuple[List[str], Dict[str, Optional[datetime.datetime]]]:
    """
    Parse a sitemap or sitemap index XML string.

    Returns:
        urls: list of URL strings
        lastmods: mapping URL -> lastmod datetime (UTC, if parseable) or None

    Handles:
        - sitemap indexes (<sitemapindex>)
        - regular sitemaps (<urlset>)
    """
    urls: List[str] = []
    lastmods: Dict[str, Optional[datetime.datetime]] = {}

    root = get_sitemap_root(xml_text)
    if root is None:
        return urls, lastmods

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Sitemap index
    if root.tag.endswith("sitemapindex"):
        for sm in root.findall(f"{ns}sitemap"):
            loc_el = sm.find(f"{ns}loc")
            if loc_el is None or not loc_el.text:
                continue
            sm_url = loc_el.text.strip()
            sm_xml = fetch_xml(
                sm_url,
                get_fn=get_fn,
                robots_txt=robots_txt,
                log_disallowed=log_disallowed,
            )
            if sm_xml:
                u, lm = parse_sitemap_for_urls_and_dates(
                    sm_xml,
                    get_fn=get_fn,
                    robots_txt=robots_txt,
                    log_disallowed=log_disallowed,
                )
                urls.extend(u)
                lastmods.update(lm)
        return urls, lastmods

    # Regular sitemap
    for url_el in root.findall(f"{ns}url"):
        loc_el = url_el.find(f"{ns}loc")
        if loc_el is None or not loc_el.text:
            continue
        loc = loc_el.text.strip()
        urls.append(loc)

        lastmod_el = url_el.find(f"{ns}lastmod")
        if lastmod_el is not None and lastmod_el.text:
            dt = parse_iso_date(lastmod_el.text.strip())
            lastmods[loc] = dt
        else:
            lastmods[loc] = None

    return urls, lastmods


def count_pages_by_recency(
    lastmods: Dict[str, Optional[datetime.datetime]]
) -> Dict[str, int]:
    """
    Count pages by last modification recency.

    Buckets:
        12m, 6m, 3m, 1m  (number of URLs changed in the last X months)
    """
    now = now_utc()
    periods = {
        "12m": now - datetime.timedelta(days=365),
        "6m": now - datetime.timedelta(days=182),
        "3m": now - datetime.timedelta(days=91),
        "1m": now - datetime.timedelta(days=30),
    }
    counts = {k: 0 for k in periods}
    for _, dt in lastmods.items():
        if not dt:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        for key, threshold in periods.items():
            if dt >= threshold:
                counts[key] += 1
    return counts


def slug_has_keyword(slug: str, keyword: str) -> bool:
    """
    Return True if `keyword` appears in `slug` as a separate token,
    delimited by non-alphanumeric characters.
    """
    if not slug or not keyword:
        return False

    slug_l = slug.lower()
    kw_l = keyword.lower()

    # Split on any non [a-z0-9] → tokens are pure alphanumerics
    tokens = [t for t in re.split(r"[^a-z0-9]+", slug_l) if t]

    return kw_l in tokens
