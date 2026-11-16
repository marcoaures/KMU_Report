"""Detection of common site sections (careers, blog, legal pages)."""
from __future__ import annotations

import secrets
from typing import List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from analysis.sitemap_utils import slug_has_keyword
from config import config as cfg
from config.dictionary_config import (
    CAREER_AMBIGUOUS_KEYWORDS,
    CAREER_FALLBACK_PATHS,
    CAREER_KEYWORDS,
    CAREER_SLUG_FILLERS,
    SECTION_TOP_PATHS,
)
from http_tools.client import DomainClient

Result = Tuple[bool, Optional[str], Optional[str]]
LANG_PREFIXES = {"de", "fr", "it", "en", "rm"}
DOCUMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx")


def _slugs(paths: List[str]) -> List[str]:
    return [p.strip("/").lower() for p in paths if p.strip("/")]


def _final_path_has_slug(final_path: str, slugs: List[str]) -> bool:
    segments = [seg for seg in unquote(final_path).lower().split("/") if seg]
    return any(seg == slug for seg in segments for slug in slugs)


def top_paths(section: str, page_lang: Optional[str]) -> List[str]:
    """The few paths worth guessing for a section: page language first,
    then English, then the first choice of the other languages."""
    by_lang = SECTION_TOP_PATHS[section]
    lang = (page_lang or "de").split("-")[0].lower()
    if lang not in by_lang:
        lang = "de"
    ordered = list(by_lang[lang]) + list(by_lang["en"])
    for other in ("de", "fr", "it"):
        ordered.append(by_lang[other][0])
    ordered = list(dict.fromkeys(ordered))
    return ordered[: cfg.MAX_FALLBACK_PATHS_PER_SECTION]


class FallbackProber:
    """Guesses well-known paths, but only on sites where a 404 means something.

    Before the first guess it asks for a path that cannot exist. If the site
    answers that with a page instead of an error, guessing proves nothing and
    is skipped altogether.
    """

    def __init__(self, client: DomainClient, base_url: Optional[str]):
        self.client = client
        self.base_url = base_url
        self._usable: Optional[bool] = None

    def usable(self) -> bool:
        if self._usable is None:
            if not self.base_url:
                self._usable = False
            else:
                url = f"{self.base_url}/kmu-webcheck-{secrets.token_hex(4)}"
                resp = self.client.get(url, max_bytes=2048)
                self._usable = resp is not None and resp.status_code in (404, 410)
        return self._usable

    def find(self, paths: List[str], accepted_slugs: List[str]) -> Optional[str]:
        if not paths or not self.usable():
            return None
        for path in paths:
            resp = self.client.get(self.base_url + path, max_bytes=2048, probe=True)
            if resp is None:
                if self.client.stop_reason:
                    return None
                continue
            if 200 <= resp.status_code < 400:
                final_path = urlparse(resp.url).path or "/"
                if _final_path_has_slug(final_path, accepted_slugs + _slugs([path])):
                    return path
        return None


def detect_section(
    section: str,
    sitemap_urls: List[str],
    soup: Optional[BeautifulSoup],
    homepage_url: Optional[str],
    sitemap_keywords: List[str],
    link_text_keywords: List[str],
    href_keywords: List[str],
    fallback_paths: List[str],
    prober: Optional[FallbackProber] = None,
    page_lang: Optional[str] = None,
) -> Result:
    """Three stages: sitemap URLs, homepage links, a few guessed paths."""
    sitemap_kw = [k.lower() for k in sitemap_keywords]
    text_kw = [k.lower() for k in link_text_keywords]
    href_kw = [k.lower() for k in href_keywords]

    for url in sitemap_urls:
        path = urlparse(url).path or "/"
        if any(slug_has_keyword(path, k) for k in sitemap_kw):
            return True, "sitemap", path

    if soup is not None and homepage_url:
        for a in soup.find_all("a", href=True):
            full_url = urljoin(homepage_url, a.get("href") or "")
            path = urlparse(full_url).path or "/"
            if path.lower().endswith(DOCUMENT_SUFFIXES):
                continue
            text = (a.get_text(" ", strip=True) or "").lower()
            if any(k in text for k in text_kw) and any(slug_has_keyword(path, k) for k in href_kw):
                return True, "homepage_link", path

    if prober is not None:
        hit = prober.find(top_paths(section, page_lang), _slugs(fallback_paths))
        if hit:
            return True, "fallback_url", hit

    return False, None, None


def probe_section(
    section: str, fallback_paths: List[str], prober: FallbackProber,
    page_lang: Optional[str], rank: int,
) -> Result:
    """Try the ``rank``-th guessed path of a section (0 = most likely one)."""
    paths = top_paths(section, page_lang)
    if rank < len(paths):
        hit = prober.find([paths[rank]], _slugs(fallback_paths))
        if hit:
            return True, "fallback_url", hit
    return False, None, None


def career_segment_matches_keyword(seg: str, allow_ambiguous: bool = False) -> bool:
    """Does a URL path segment clearly look like a careers/jobs slug?

    "jobs", "karriere" and "karriere-bei-uns" do; "jobs-to-be-done" does not.
    Everyday words such as "travail" or "lavoro" only count if the caller has
    more evidence (``allow_ambiguous``).
    """
    seg = unquote(seg or "").lower()
    for kw in CAREER_KEYWORDS:
        kw = kw.lower()
        if kw in CAREER_AMBIGUOUS_KEYWORDS and not allow_ambiguous:
            continue
        if seg == kw:
            return True
        if seg.startswith(kw + "-"):
            rest = [t for t in seg[len(kw) + 1:].split("-") if t]
            if rest and all(t in CAREER_SLUG_FILLERS for t in rest):
                return True
    return False


def _career_segments(path: str) -> List[str]:
    segments = [seg for seg in path.lower().split("/") if seg]
    if segments and segments[0] in LANG_PREFIXES:
        segments = segments[1:]
    return segments


def detect_careers_section(
    sitemap_urls: List[str],
    soup: Optional[BeautifulSoup],
    homepage_url: Optional[str],
    prober: Optional[FallbackProber] = None,
    page_lang: Optional[str] = None,
) -> Result:
    """Specialised detector for careers/jobs pages."""
    for url in sitemap_urls:
        path = urlparse(url).path or "/"
        segments = _career_segments(path)
        # deep URLs are articles about jobs, not the jobs page
        if 0 < len(segments) <= 3 and any(career_segment_matches_keyword(s) for s in segments):
            return True, "sitemap", path

    if soup is not None and homepage_url:
        text_kw = [k.lower() for k in CAREER_KEYWORDS]
        for a in soup.find_all("a", href=True):
            text = (a.get_text(" ", strip=True) or "").lower()
            if not any(k in text for k in text_kw):
                continue
            full_url = urljoin(homepage_url, a.get("href") or "")
            segments = _career_segments(urlparse(full_url).path or "/")
            if not segments or len(segments) > 2:
                continue
            if not career_segment_matches_keyword(segments[-1], allow_ambiguous=True):
                continue
            return True, "homepage_link", "/" + "/".join(segments)

    if prober is not None:
        hit = prober.find(top_paths("careers", page_lang), _slugs(CAREER_FALLBACK_PATHS))
        if hit:
            return True, "fallback_url", hit

    return False, None, None
