"""Utilities for extracting language information from HTML content and URLs."""

from __future__ import annotations

from typing import Dict, Optional, List
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from config.dictionary_config import LANG_NAME_TO_CODE

def guess_lang_from_text(text: str) -> Optional[str]:
    """Try to map a plain language name/code to our language codes."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if t in LANG_NAME_TO_CODE:
        return LANG_NAME_TO_CODE[t]
    if t in {"de", "fr", "it", "en", "rm"}:
        return t
    return None


def guess_lang_from_code_or_flag(code: str) -> Optional[str]:
    """
    Interpret strings like "de", "de-CH", "flag-de", "de_flag.png" or flag
    filenames as a language code (de/fr/it/en/rm) where possible.

    This version is much stricter: it works on tokens and filenames instead of
    arbitrary substrings, so it won't match "en" in "menu" or "rm" in "form".
    """
    if not code:
        return None

    c = code.strip().lower()

    # Quick exact match (e.g. "de", "de-ch")
    if c in {"de", "fr", "it", "en", "rm"}:
        return c
    if re.fullmatch(r"(de|fr|it|en|rm)[-_][a-z]{2}", c):
        return c.split("-", 1)[0].split("_", 1)[0]

    # If it's a URL or path, reduce to filename part
    filename = c.rsplit("/", 1)[-1]

    # Split into tokens on common separators
    tokens = re.split(r"[\s._\-]+", filename)

    for tok in tokens:
        if tok in {"de", "fr", "it", "en", "rm"}:
            return tok

        # Patterns like "lang-de", "flag-de", "de-ch", "de_ch"
        m = re.fullmatch(r"(?:lang|flag)?(de|fr|it|en|rm)(?:[._-][a-z]{2})?", tok)
        if m:
            return m.group(1)

    return None


def detect_language_switcher_and_urls(
    soup: BeautifulSoup, base_url: str
) -> Dict[str, set]:
    """
    Look for language indications in navigation and URLs:

      - link text/title that look like language names/codes
      - flags in <img> (alt/title/src/class)
      - language codes in URL path (/de/, /fr/, /it/, /en/, /rm/)
      - language codes in query params (lang=de, hl=en, ...)

    Returns:
        {
            "switcher_languages": set([...]),  # from nav / flags
            "url_languages": set([...]),       # from URL patterns
        }
    """
    switcher_langs_raw: List[str] = []
    url_langs: set[str] = set()

    path_lang_re = re.compile(r"/(de|fr|it|en|rm)(?:[-_][a-z]{2})?(/|$)", re.IGNORECASE)
    query_lang_re = re.compile(
        r"[?&](?:lang|language|locale|hl)=([a-z]{2}(?:[-_][a-z]{2})?)",
        re.IGNORECASE,
    )

    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_href = urljoin(base_url, href)
        text = (a.get_text(strip=True) or "").strip()
        title = (a.get("title") or "").strip()

        # 1) link text/title
        for candidate in (text, title):
            code = guess_lang_from_text(candidate)
            if code:
                switcher_langs_raw.append(code)

        # 2) flags inside link
        for img in a.find_all("img"):
            img_alt = img.get("alt") or ""
            img_title = img.get("title") or ""
            img_src = img.get("src") or ""
            img_classes = " ".join(img.get("class") or [])

            for candidate in (img_alt, img_title, img_src, img_classes):
                code = guess_lang_from_text(candidate)
                if not code:
                    code = guess_lang_from_code_or_flag(candidate)
                if code:
                    switcher_langs_raw.append(code)

        # 3) attributes on <a> itself
        data_lang = (
            a.get("data-lang")
            or a.get("data-language")
            or a.get("data-locale")
            or ""
        )

        # Only use explicit data-* attributes as language hints
        if data_lang:
            code = guess_lang_from_code_or_flag(data_lang)
            if code:
                switcher_langs_raw.append(code)

        # Optionally: if you really want to use classes, only look at ones that
        # explicitly mention "lang" or "flag" to avoid "menu"/"form" etc.
        for cls in (a.get("class") or []):
            cls_l = cls.lower()
            if "lang" in cls_l or "flag" in cls_l:
                code = guess_lang_from_code_or_flag(cls_l)
                if code:
                    switcher_langs_raw.append(code)

        # 4) URL path patterns
        m_path = path_lang_re.search(urlparse(abs_href).path)
        if m_path:
            code = m_path.group(1).lower()
            url_langs.add(code)

        # 5) URL query patterns
        m_query = query_lang_re.search(abs_href)
        if m_query:
            code = m_query.group(1).lower().replace("_", "-")
            url_langs.add(code.split("-")[0])

    switcher_langs = set(switcher_langs_raw)
    # Only treat as a language switcher if at least 2 distinct languages show up
    if len(switcher_langs) < 2:
        switcher_langs = set()

    return {
        "switcher_languages": switcher_langs,
        "url_languages": url_langs,
    }


def normalize_lang_code(code: str) -> str:
    """
    Normalize language tags a bit (BCP 47-ish, but conservative):
    - lowercase everything
    - replace '_' with '-'
    - strip whitespace

    Example: 'DE_ch' -> 'de-ch'
    """
    if not code:
        return ""
    return code.strip().replace("_", "-").lower()


def detect_languages_and_localization(
    soup: BeautifulSoup, base_url: str
) -> Dict[str, Optional[str]]:
    """Collect language, hreflang and localization information for the homepage."""
    # HTML / meta language
    html_lang = None
    html_tag = soup.find("html")
    if html_tag:
        html_lang = normalize_lang_code(
            html_tag.get("lang") or html_tag.get("xml:lang") or ""
        )

    meta_lang = None
    meta_http = soup.find(
        "meta",
        attrs={"http-equiv": lambda v: v and v.lower() == "content-language"},
    )
    if meta_http and meta_http.get("content"):
        meta_lang = normalize_lang_code(meta_http["content"].split(",")[0])

    if not meta_lang:
        meta_name = soup.find(
            "meta",
            attrs={"name": lambda v: v and v.lower() == "language"},
        )
        if meta_name and meta_name.get("content"):
            meta_lang = normalize_lang_code(meta_name["content"].split(",")[0])

    # hreflang
    hreflang_map: Dict[str, set[str]] = {}
    hreflang_default_lang = None

    for link in soup.find_all("link", rel=lambda v: v and "alternate" in v.lower()):
        href = link.get("href")
        if not href:
            continue
        hreflang_raw = (link.get("hreflang") or "").strip()
        if not hreflang_raw:
            continue

        hreflang = normalize_lang_code(hreflang_raw)
        abs_url = urljoin(base_url, href)

        if hreflang == "x-default":
            hreflang_default_lang = "x-default"
        else:
            hreflang_map.setdefault(hreflang, set()).add(abs_url)

    hreflang_languages = sorted(hreflang_map.keys())

    # Navigation / URL-based detection (incl. flags)
    nav_signals = detect_language_switcher_and_urls(soup, base_url)
    switcher_langs = nav_signals["switcher_languages"]
    url_langs = nav_signals["url_languages"]

    def lang_root(code: str) -> str:
        return code.split("-")[0] if code else ""

    detected_lang_roots: set[str] = set()
    for lang in hreflang_languages:
        detected_lang_roots.add(lang_root(lang))
    for lang in switcher_langs:
        detected_lang_roots.add(lang_root(lang))
    for lang in url_langs:
        detected_lang_roots.add(lang_root(lang))
    if html_lang:
        detected_lang_roots.add(lang_root(html_lang))
    if meta_lang:
        detected_lang_roots.add(lang_root(meta_lang))

    detected_lang_roots.discard("")
    languages_detected = sorted(detected_lang_roots)

    # Primary language heuristic
    primary_language = None
    if hreflang_languages:
        primary_language = hreflang_languages[0]
    elif html_lang:
        primary_language = html_lang
    elif meta_lang:
        primary_language = meta_lang

    # Localization status
    has_hreflang_multi = len(hreflang_languages) > 1

    # Only treat as multi-language if hreflang, URL patterns or switcher
    # clearly indicate multiple languages – not just one stray signal.
    multi_via_urls_or_switcher = (
        len(url_langs) > 1 or len(switcher_langs) > 1
    )

    has_multi_lang_signals = has_hreflang_multi or multi_via_urls_or_switcher

    if not has_multi_lang_signals:
        localization_status = "single_language"
    else:
        if has_hreflang_multi:
            localization_status = "multi_language_best_practice"
        else:
            localization_status = "multi_language_poor_implementation"

    return {
        "html_lang": html_lang or None,
        "meta_lang": meta_lang or None,
        "primary_language": primary_language,
        "hreflang_languages": ", ".join(hreflang_languages)
        if hreflang_languages
        else "",
        "hreflang_default_language": hreflang_default_lang,
        "languages_detected": ", ".join(languages_detected)
        if languages_detected
        else "",
        "localization_status": localization_status,
        "switcher_languages": ", ".join(sorted(switcher_langs))
        if switcher_langs
        else "",
        "url_languages": ", ".join(sorted(url_langs)) if url_langs else "",
    }


# Backwards-compatible alias

def detect_languages_and_hreflang(
    soup: BeautifulSoup, base_url: str
) -> Dict[str, Optional[str]]:
    return detect_languages_and_localization(soup, base_url)