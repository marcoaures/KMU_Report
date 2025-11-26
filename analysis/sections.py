"""Shared helpers for detecting common site sections (careers, blog, legal)."""

from __future__ import annotations

from typing import Optional, Tuple

from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from http_tools.http_utils import safe_get
from analysis.sitemap_utils import slug_has_keyword
from config.dictionary_config import CAREER_KEYWORDS, CAREER_FALLBACK_PATHS


def _normalized_fallback_slugs(fallback_paths: list[str]) -> list[str]:
    """Lowercase fallback path slugs (last path segment) for matching redirects."""
    slugs: list[str] = []
    for rel_path in fallback_paths:
        slug = rel_path.strip("/").lower()
        if slug:
            slugs.append(slug)
    return slugs


def _final_path_has_fallback_slug(final_path: str, fallback_slugs: list[str]) -> bool:
    segments = [seg for seg in unquote(final_path).lower().split("/") if seg]
    return bool(segments) and any(seg == slug for seg in segments for slug in fallback_slugs)


def detect_section(
    sitemap_urls: list[str],
    soup: Optional[BeautifulSoup],
    homepage_url: Optional[str],
    domain: str,
    sitemap_keywords: list[str],
    link_text_keywords: list[str],
    href_keywords: list[str],
    fallback_paths: list[str],
    safe_get_fn=safe_get,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Generic three-stage detector for sections like blog, jobs, legal pages."""
    sitemap_keywords_l = [k.lower() for k in sitemap_keywords]
    link_text_keywords_l = [k.lower() for k in link_text_keywords]
    href_keywords_l = [k.lower() for k in href_keywords]
    fallback_slugs = _normalized_fallback_slugs(fallback_paths)

    # --- Stage 1: sitemap URLs ---
    for url in sitemap_urls:
        try:
            path = urlparse(url).path or "/"
            path_l = path.lower()
        except Exception:
            continue

        if any(slug_has_keyword(path_l, k) for k in sitemap_keywords_l):
            return True, "sitemap", path

    # --- Stage 2: homepage links ---
    if soup is not None and homepage_url:
        try:
            for a in soup.find_all("a", href=True):
                href = a.get("href") or ""
                full_url = urljoin(homepage_url, href)
                path = urlparse(full_url).path or "/"
                path_l = path.lower()

                text = (a.get_text(strip=True) or "").strip().lower()

                text_has_keyword = any(k in text for k in link_text_keywords_l)
                href_has_keyword = any(
                    slug_has_keyword(path_l, k) for k in href_keywords_l
                )

                if path_l.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):
                    href_has_keyword = False

                if text_has_keyword and href_has_keyword:
                    return True, "homepage_link", path
        except Exception:
            pass

    # --- Stage 3: fallback well-known paths ---
    base = f"https://{domain}"
    for rel_path in fallback_paths:
        if not rel_path.startswith("/"):
            rel_path = "/" + rel_path
        url = base + rel_path
        resp = safe_get_fn(url)
        if resp and 200 <= resp.status_code < 400:
            final_path = urlparse(resp.url).path or "/"
            if _final_path_has_fallback_slug(final_path, fallback_slugs):
                return True, "fallback_url", rel_path

    return False, None, None


def career_segment_matches_keyword(seg: str) -> bool:
    """
    Return True if a URL path segment clearly looks like a careers/jobs slug.
    """
    seg = (seg or "").lower()
    for kw in CAREER_KEYWORDS:
        if seg == kw:
            return True
        if seg.startswith(kw + "-"):
            return True
    return False


def detect_careers_section(
    sitemap_urls: list[str],
    soup: Optional[BeautifulSoup],
    homepage_url: Optional[str],
    domain: str,
    safe_get_fn=safe_get,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Specialized detector for careers/jobs pages.
    """
    sitemap_keywords_l = [k.lower() for k in CAREER_KEYWORDS]
    fallback_slugs = _normalized_fallback_slugs(CAREER_FALLBACK_PATHS)

    # --- Stage 1: sitemap URLs ---
    for url in sitemap_urls:
        try:
            path = urlparse(url).path or "/"
            path_l = path.lower()
        except Exception:
            continue

        segments = [seg for seg in path_l.split("/") if seg]
        for seg in segments:
            if career_segment_matches_keyword(seg):
                return True, "sitemap", path

    # --- Stage 2: homepage links ---
    if soup is not None and homepage_url:
        try:
            for a in soup.find_all("a", href=True):
                href = a.get("href") or ""
                full_url = urljoin(homepage_url, href)
                path = urlparse(full_url).path or "/"
                path_l = path.lower()

                text = (a.get_text(strip=True) or "").strip().lower()

                text_has_keyword = any(k in text for k in sitemap_keywords_l)
                if not text_has_keyword:
                    continue

                segments = [seg for seg in path_l.split("/") if seg]
                if segments and segments[0] in {"de", "fr", "it", "en", "rm"}:
                    segments = segments[1:]

                if not segments:
                    continue

                if len(segments) > 2:
                    continue

                last_seg = segments[-1]
                if not career_segment_matches_keyword(last_seg):
                    continue

                career_seg_count = sum(
                    1 for s in segments if career_segment_matches_keyword(s)
                )
                if career_seg_count != 1:
                    continue

                normalized_path = "/" + "/".join(segments)
                return True, "homepage_link", normalized_path

        except Exception:
            pass

    # --- Stage 3: fallback well-known paths ---
    base = f"https://{domain}"
    for rel_path in CAREER_FALLBACK_PATHS:
        if not rel_path.startswith("/"):
            rel_path = "/" + rel_path
        url = base + rel_path
        resp = safe_get_fn(url)
        if resp and 200 <= resp.status_code < 400:
            final_path = urlparse(resp.url).path or "/"
            if _final_path_has_fallback_slug(final_path, fallback_slugs):
                return True, "fallback_url", rel_path

    return False, None, None
