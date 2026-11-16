"""Language information from HTML attributes, hreflang, navigation and URLs."""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from config.dictionary_config import LANG_NAME_TO_CODE
from http_tools.client import registrable_domain

LANG_CODES = {"de", "fr", "it", "en", "rm"}


def guess_lang_from_text(text: str) -> Optional[str]:
    """Map a plain language name/code ("Deutsch", "FR") to a language code."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if t in LANG_NAME_TO_CODE:
        return LANG_NAME_TO_CODE[t]
    return t if t in LANG_CODES else None


def guess_lang_from_code_or_flag(code: str) -> Optional[str]:
    """Interpret "de", "de-CH", "flag-de" or "de_flag.png" as a language code.
    Works on tokens, so "en" in "menu" or "rm" in "form" do not match."""
    if not code:
        return None
    c = code.strip().lower()
    if c in LANG_CODES:
        return c
    if re.fullmatch(r"(de|fr|it|en|rm)[-_][a-z]{2}", c):
        return c[:2]
    filename = c.rsplit("/", 1)[-1]
    for tok in re.split(r"[\s._\-]+", filename):
        if tok in LANG_CODES:
            return tok
        m = re.fullmatch(r"(?:lang|flag)(de|fr|it|en|rm)", tok)
        if m:
            return m.group(1)
    return None


def normalize_lang_code(code: str) -> str:
    """'DE_ch' -> 'de-ch'"""
    return (code or "").strip().replace("_", "-").lower()


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc.lower(), pa.path.rstrip("/")) == (pb.netloc.lower(), pb.path.rstrip("/"))


def detect_language_switcher_and_urls(soup: BeautifulSoup, base_url: str) -> Dict[str, set]:
    """Language hints from navigation (names, flags, data attributes) and from
    internal link URLs (/de/, /fr/, ?lang=it)."""
    switcher: List[str] = []
    url_langs: set = set()
    site = registrable_domain(urlparse(base_url).netloc)

    first_segment_re = re.compile(r"^/(de|fr|it|en|rm)(?:[-_][a-z]{2})?(?:/|$)", re.I)
    query_re = re.compile(r"[?&](?:lang|language|locale|hl)=(de|fr|it|en|rm)(?:[-_][a-z]{2})?(?:&|$)", re.I)

    for a in soup.find_all("a", href=True):
        abs_href = urljoin(base_url, a["href"])
        parsed = urlparse(abs_href)

        for candidate in ((a.get_text(strip=True) or ""), (a.get("title") or ""),
                          (a.get("hreflang") or ""), (a.get("lang") or "")):
            code = guess_lang_from_text(candidate) or (
                candidate and re.fullmatch(r"(de|fr|it|en|rm)[-_][a-zA-Z]{2}", candidate.strip())
                and candidate.strip()[:2].lower()
            )
            if code:
                switcher.append(code)

        for img in a.find_all("img"):
            for candidate in (img.get("alt") or "", img.get("title") or "",
                              img.get("src") or "", " ".join(img.get("class") or [])):
                code = guess_lang_from_text(candidate) or guess_lang_from_code_or_flag(candidate)
                if code:
                    switcher.append(code)

        data_lang = a.get("data-lang") or a.get("data-language") or a.get("data-locale") or ""
        if data_lang:
            code = guess_lang_from_code_or_flag(data_lang)
            if code:
                switcher.append(code)

        for cls in (a.get("class") or []):
            if "lang" in cls.lower() or "flag" in cls.lower():
                code = guess_lang_from_code_or_flag(cls)
                if code:
                    switcher.append(code)

        # URL patterns: internal links only, language as the first path segment.
        if registrable_domain(parsed.netloc) != site:
            continue
        m = first_segment_re.match(parsed.path or "/")
        if m:
            url_langs.add(m.group(1).lower())
        m = query_re.search("?" + parsed.query) if parsed.query else None
        if m:
            url_langs.add(m.group(1).lower())

    switcher_langs = set(switcher)
    # A single code proves nothing: "/it/" may be the IT department and one
    # "EN" link is not a switcher. Two different codes are a pattern.
    if len(switcher_langs) < 2:
        switcher_langs = set()
    if len(url_langs) < 2:
        url_langs = set()
    return {"switcher_languages": switcher_langs, "url_languages": url_langs}


def detect_languages_and_localization(soup: BeautifulSoup, base_url: str) -> Dict[str, Optional[str]]:
    """Collect language, hreflang and localization information for the homepage."""
    html_lang = None
    html_tag = soup.find("html")
    if html_tag:
        html_lang = normalize_lang_code(html_tag.get("lang") or html_tag.get("xml:lang") or "")

    meta_lang = None
    for attrs in ({"http-equiv": re.compile(r"^content-language$", re.I)},
                  {"name": re.compile(r"^language$", re.I)}):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            meta_lang = normalize_lang_code(meta["content"].split(",")[0])
            break

    hreflang_map: Dict[str, str] = {}
    x_default_url = None
    for link in soup.find_all("link", href=True):
        rel = link.get("rel") or []
        rel = rel if isinstance(rel, list) else [rel]
        if "alternate" not in [r.lower() for r in rel]:
            continue
        hreflang = normalize_lang_code(link.get("hreflang") or "")
        if not hreflang:
            continue
        abs_url = urljoin(base_url, link["href"])
        if hreflang == "x-default":
            x_default_url = abs_url
        else:
            hreflang_map.setdefault(hreflang, abs_url)
    hreflang_languages = sorted(hreflang_map)

    # x-default: report which language it points at, if we can tell
    hreflang_default = None
    if x_default_url:
        hreflang_default = next(
            (lang for lang, url in hreflang_map.items() if _same_page(url, x_default_url)),
            "x-default",
        )

    nav = detect_language_switcher_and_urls(soup, base_url)
    switcher_langs, url_langs = nav["switcher_languages"], nav["url_languages"]

    roots = {c.split("-")[0] for c in hreflang_languages} | switcher_langs | url_langs
    for code in (html_lang, meta_lang):
        if code:
            roots.add(code.split("-")[0])
    roots.discard("")

    # Primary language: what the page itself declares; failing that, the
    # hreflang entry that points back at this very page.
    primary = html_lang or meta_lang or next(
        (lang for lang, url in hreflang_map.items() if _same_page(url, base_url)), None
    )

    has_hreflang_multi = len({c.split("-")[0] for c in hreflang_languages}) > 1
    if has_hreflang_multi:
        status = "multi_language_best_practice"
    elif len(url_langs) > 1 or len(switcher_langs) > 1:
        status = "multi_language_poor_implementation"
    else:
        status = "single_language"

    return {
        "html_lang": html_lang or None,
        "meta_lang": meta_lang or None,
        "primary_language": primary or None,
        "hreflang_languages": ", ".join(hreflang_languages),
        "hreflang_default_language": hreflang_default,
        "languages_detected": ", ".join(sorted(roots)),
        "localization_status": status,
        "switcher_languages": ", ".join(sorted(switcher_langs)),
        "url_languages": ", ".join(sorted(url_langs)),
    }
