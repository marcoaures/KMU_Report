"""HTML parsing helpers for extracting UI, contact, and cookie signals."""
from __future__ import annotations

import re
import copy
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from analysis.language_localization import detect_languages_and_hreflang

from config.dictionary_config import (
    EXCLUDE_CSS_SUBSTRINGS,
    MAIN_CSS_KEYWORDS,
    SOCIAL_DOMAINS,
    TAG_MANAGER_PATTERNS,
    COOKIE_PATTERNS,
    COOKIE_INLINE_PATTERNS,
    COOKIE_BANNER_CONTAINER_TOKENS,
    COOKIE_BANNER_FALLBACK_TOKENS,
    COOKIE_INFO_PHRASES,
    COOKIE_STRONG_CONSENT_PHRASES,
    COOKIE_ACCEPT_BUTTON_LABELS,
    COOKIE_REJECT_BUTTON_LABELS,
    COOKIE_SETTINGS_BUTTON_LABELS,
    COOKIE_GENERIC_OK_LABELS,
    EMAIL_REGEX,
    EMAIL_IGNORED_LOCALPARTS,
    SWISS_PHONE_PATTERNS,
    ZIP_CITY_REGEX,
    CONTACT_LINK_TEXTS_L,
    ICON_DECORATIVE_TOKENS,
    SOCIAL_TOKENS,
    PAYMENT_TOKENS,
    INTERACTIVE_ROLES,
    INTERACTIVE_CLASS_TOKENS,
)

from config.config import (
    MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK,
    MAX_CSS_FILES_FOR_RESPONSIVE_CHECK,
)

from http_tools.http_utils import safe_get

# ---------------------------------------------------------------------------
# Helpers for homepage analysis
# ---------------------------------------------------------------------------

VISIBLE_TEXT_MIN_WORD_REGEX = re.compile(r"\w+", re.UNICODE)


def email_is_ignored(addr: str) -> bool:
    local = addr.split("@", 1)[0].lower()
    return any(bad in local for bad in EMAIL_IGNORED_LOCALPARTS)


def estimate_visible_word_count(soup: BeautifulSoup) -> int:
    """
    Rough estimate of visible text on the page (in words).

    Strips obvious non-content elements:
      - script, style, noscript
      - head, title
      - possibly nav/footer for a more "main content" feel
    """
    # Work on a shallow clone to avoid messing with other checks
    soup_clone = copy.copy(soup)

    # Prefer <main> if present, else <body>, else whole soup
    root = soup_clone.find("main") or soup_clone.body or soup_clone

    # Remove noisy elements from root
    for tag_name in ["script", "style", "noscript", "svg"]:
        for el in root.find_all(tag_name):
            el.decompose()

    text = root.get_text(" ", strip=True) or ""
    words = VISIBLE_TEXT_MIN_WORD_REGEX.findall(text)
    return len(words)


def registrable_domain_from_url(url: str) -> str:
    """Return registrable domain (example.ch) from a URL, using tldextract."""
    import tldextract  # local import to avoid circulars

    parsed = urlparse(url)
    ext = tldextract.extract(parsed.netloc)
    if not ext.domain or not ext.suffix:
        return parsed.netloc.lower()
    return f"{ext.domain}.{ext.suffix}".lower()


def score_css_url(css_url: str, page_reg_domain: str) -> int:
    """
    Score CSS URLs so we can pick the most likely layout-related files.

    Higher score = more likely to contain responsive layout rules.
    """
    score = 0
    u = css_url.lower()
    filename = u.rsplit("/", 1)[-1]

    # Prefer same registrable domain
    if registrable_domain_from_url(css_url) == page_reg_domain:
        score += 3

    # Prefer filenames with main-ish keywords
    for kw in MAIN_CSS_KEYWORDS:
        if kw in filename:
            score += 2
            break

    # Slightly prefer shorter filenames (less hashed junk)
    if len(filename) < 40:
        score += 1

    return score


def detect_media_queries_in_external_css(urls: List[str], safe_get) -> bool:
    """
    Fetch a small, capped set of external CSS files and check for responsive
    @media (max-width: ...) rules.
    """
    for css_url in urls:
        resp = safe_get(css_url)
        if not resp or resp.status_code != 200:
            continue

        ctype = resp.headers.get("Content-Type", "").lower()
        if "css" not in ctype:
            continue

        # Size guardrail
        if len(resp.content) > MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK:
            continue

        css_text = resp.text or ""
        if "@media" in css_text and "(max-width" in css_text:
            return True

    return False


def label_matches_any(label: str, patterns: List[str]) -> bool:
    """Return True if any pattern appears as a substring in the label (case-insensitive)."""
    if not label:
        return False
    l = label.lower()
    return any(pat in l for pat in patterns)


def tokens_in_any(s: str, tokens: List[str]) -> bool:
    """Return True if any token appears as a substring in s (case-insensitive)."""
    if not s:
        return False
    s_l = s.lower()
    return any(tok in s_l for tok in tokens)


def _parse_dimension(val: str) -> Optional[int]:
    """Extract a numeric pixel value from width/height attributes like '40', '40px'."""
    if not val:
        return None
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else None


def is_small_icon_image(img) -> bool:
    """
    Heuristic: treat image as 'small' if we can see a width/height
    of <= 40px, either via attributes or common filename patterns.
    """
    # 1) width/height attributes on the tag
    w = _parse_dimension(img.get("width", ""))
    h = _parse_dimension(img.get("height", ""))

    if (w is not None and w <= 40) or (h is not None and h <= 40):
        return True

    # 2) fallback: filename like ...-32x32.png
    src = (img.get("src") or "").lower()
    m = re.search(r"(\d{1,2})x(\d{1,2})", src)
    if m:
        a, b = map(int, m.groups())
        if a <= 40 and b <= 40:
            return True

    return False


def classify_image_role(img) -> Dict[str, bool]:
    """
    Classify an <img> roughly as:
      - logo-ish
      - social/payment-ish
      - decorative (small/icon-like and not logo/social/payment)
    """
    src = (img.get("src") or "").lower()
    classes = " ".join(img.get("class") or []).lower()
    id_ = (img.get("id") or "").lower()

    attr_blob = " ".join([src, classes, id_])

    # Logo: class/id/src mentions logo or brand
    is_logo = any(tok in attr_blob for tok in ["logo", "brand"])

    # Social or payment icons
    is_social_or_payment = tokens_in_any(
        attr_blob,
        SOCIAL_TOKENS + PAYMENT_TOKENS,
    )

    # Also look at parent link href for social/payment hints
    parent_link = img.find_parent("a", href=True)
    if parent_link:
        href = (parent_link.get("href") or "").lower()
        if tokens_in_any(href, SOCIAL_TOKENS + PAYMENT_TOKENS):
            is_social_or_payment = True

    # Icon-ish decorative if small or uses typical icon/sprite tokens
    is_small = is_small_icon_image(img)
    looks_like_icon = tokens_in_any(attr_blob, ICON_DECORATIVE_TOKENS)

    # Decorative only if icon-y/small AND not logo AND not social/payment
    is_decorative = (is_small or looks_like_icon) and not (
        is_logo or is_social_or_payment
    )

    return {
        "is_logo": is_logo,
        "is_social_or_payment": is_social_or_payment,
        "is_decorative": is_decorative,
    }


def looks_interactive_divspan(el) -> bool:
    """
    Return True if a <div> or <span> looks like it's meant to be interactive.
    """
    if el.name not in ("div", "span"):
        return False

    # Inline event handlers
    for attr in ("onclick", "onmousedown", "onmouseup", "onkeydown", "onkeyup", "onkeypress"):
        if el.get(attr):
            return True

    # Role-based interaction
    role = (el.get("role") or "").lower()
    if role in INTERACTIVE_ROLES:
        return True

    # Strongly button-like classes
    classes = " ".join(el.get("class") or []).lower()
    if any(tok in classes for tok in INTERACTIVE_CLASS_TOKENS):
        return True

    return False


def has_keyboard_focus(el) -> bool:
    """
    Return True if element is keyboard-focusable via tabindex >= 0.
    """
    tabindex = el.get("tabindex")
    if tabindex is None:
        return False
    try:
        return int(tabindex) >= 0
    except ValueError:
        return False


def classify_cookie_ui(soup: BeautifulSoup) -> Dict[str, object]:
    """
    Inspect the homepage HTML for cookie / consent UI.

    Returns descriptive flags instead of opaque A–E categories:

        {
            "cookie_banner_present": bool,
            "cookie_banner_has_accept": bool,
            "cookie_banner_has_reject": bool,
            "cookie_banner_has_settings": bool,
            "cookie_banner_has_only_ok": bool,
            "cookie_info_in_footer": bool,
            "cookie_choice_html_signal": bool,
        }
    """

    def find_candidate_containers(
        tokens: List[str],
        allow_generic_cookie_text: bool,
    ) -> List[tuple[object, str]]:
        """
        Find candidate cookie banner containers by looking for elements whose
        id/class/role/data-* attributes contain any of the given tokens,
        and whose text looks cookie-related.
        """
        candidates: List[tuple[object, str]] = []
        token_l = [t.lower() for t in tokens]

        for tag in soup.find_all(True):
            # attributes we care about
            attrs_chunks: List[str] = []

            tag_id = tag.get("id") or ""
            if tag_id:
                attrs_chunks.append(tag_id)

            classes = tag.get("class") or []
            if classes:
                attrs_chunks.extend(classes)

            role = tag.get("role") or ""
            if role:
                attrs_chunks.append(role)

            # data-* attributes
            for k, v in tag.attrs.items():
                if k.startswith("data-"):
                    attrs_chunks.append(str(v))

            attrs_str = " ".join(attrs_chunks).lower()
            if not any(tok in attrs_str for tok in token_l):
                continue

            text_l = (tag.get_text(" ", strip=True) or "").lower()
            has_cookie_word = "cookie" in text_l or "cookies" in text_l
            has_phrase = any(phrase in text_l for phrase in COOKIE_INFO_PHRASES)

            if allow_generic_cookie_text:
                if not (has_cookie_word or has_phrase):
                    continue
            else:
                # stricter: still require explicit cookie-related wording
                if not has_cookie_word and not has_phrase:
                    continue

            candidates.append((tag, text_l))

        return candidates

    # Stage 1: strong cookie-specific containers; relaxed text check
    candidates = find_candidate_containers(
        COOKIE_BANNER_CONTAINER_TOKENS,
        allow_generic_cookie_text=True,
    )

    # Stage 2: generic modal/overlay containers; strict text check
    if not candidates:
        candidates = find_candidate_containers(
            COOKIE_BANNER_FALLBACK_TOKENS,
            allow_generic_cookie_text=False,
        )

    cookie_banner_present = bool(candidates)
    cookie_banner_has_accept = False
    cookie_banner_has_reject = False
    cookie_banner_has_settings = False
    cookie_banner_has_only_ok = False
    cookie_info_in_footer = False
    cookie_choice_html_signal = False

    if candidates:
        cont, cont_text = candidates[0]  # first candidate is usually good enough

        labels: List[str] = []
        for btn in cont.find_all(["button", "a", "input"]):
            label = (btn.get_text(strip=True) or "") + " " + (btn.get("value") or "")
            label = label.strip()
            if label:
                labels.append(label.lower())

        has_accept = any(label_matches_any(l, COOKIE_ACCEPT_BUTTON_LABELS) for l in labels)
        has_reject = any(label_matches_any(l, COOKIE_REJECT_BUTTON_LABELS) for l in labels)
        has_settings = any(label_matches_any(l, COOKIE_SETTINGS_BUTTON_LABELS) for l in labels)
        has_ok = any(label_matches_any(l, COOKIE_GENERIC_OK_LABELS) for l in labels)

        has_strong_consent_text = any(
            phrase in cont_text for phrase in COOKIE_STRONG_CONSENT_PHRASES
        )

        cookie_banner_has_accept = has_accept
        cookie_banner_has_reject = has_reject
        cookie_banner_has_settings = has_settings
        cookie_banner_has_only_ok = has_ok and not (has_accept or has_reject or has_settings)

        # Our HTML-only notion of "likely gives user some choice"
        cookie_choice_html_signal = bool(
            has_reject or has_settings or has_strong_consent_text
        )

    # No banner-like container with cookie text → check for footer note
    footer = soup.find("footer")
    footer_text = ""
    if footer:
        footer_text = (footer.get_text(" ", strip=True) or "").lower()

    if any(phrase in footer_text for phrase in COOKIE_INFO_PHRASES) or \
       "cookie" in footer_text or "cookies" in footer_text:
        cookie_info_in_footer = True

    return {
        "cookie_banner_present": cookie_banner_present,
        "cookie_banner_has_accept": cookie_banner_has_accept,
        "cookie_banner_has_reject": cookie_banner_has_reject,
        "cookie_banner_has_settings": cookie_banner_has_settings,
        "cookie_banner_has_only_ok": cookie_banner_has_only_ok,
        "cookie_info_in_footer": cookie_info_in_footer,
        "cookie_choice_html_signal": cookie_choice_html_signal,
    }


# ---------------------------------------------------------------------------
# Kontaktmöglichkeiten – page-level contact info
# ---------------------------------------------------------------------------

def detect_contact_info_on_page(
    soup: BeautifulSoup,
    base_url: str,
) -> Dict[str, bool]:
    """
    Detect basic contact info on a single page:
      - public_email: none / text / clickable
      - public_phone: none / text / clickable
      - address_present (ZIP + city-like pattern)
    """
    text = (soup.get_text(" ", strip=True) or "")

    email_clickable = False
    phone_clickable = False

    # Clickable mailto: / tel:
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        href_l = href.lower()

        if href_l.startswith("mailto:"):
            addr = href.split(":", 1)[1]
            addr = addr.split("?", 1)[0].strip()
            if addr and not email_is_ignored(addr):
                email_clickable = True

        if href_l.startswith("tel:"):
            # We don't try to parse the format here – just "clickable phone"
            phone_clickable = True

    # Email present: either clickable, or raw in text
    email_present = email_clickable
    if not email_present:
        for m in EMAIL_REGEX.finditer(text):
            addr = m.group(0)
            if not email_is_ignored(addr):
                email_present = True
                break

    # Phone present: either clickable, or Swiss-pattern match in text
    phone_present = phone_clickable
    if not phone_present:
        for pat in SWISS_PHONE_PATTERNS:
            if pat.search(text):
                phone_present = True
                break

    # Very light-weight postal address: ZIP + city-ish word
    address_present = bool(ZIP_CITY_REGEX.search(text))

    public_email = "none"
    if email_present:
        public_email = "clickable" if email_clickable else "text"

    public_phone = "none"
    if phone_present:
        public_phone = "clickable" if phone_clickable else "text"

    return {
        "public_email": public_email,
        "public_phone": public_phone,
        "address_present": address_present,
    }


def find_contact_like_url(
    soup: BeautifulSoup,
    base_url: str,
) -> Optional[str]:
    """
    Find a link to a likely contact page (Kontakt/Contact/Contatto/etc.)
    on the same hostname as base_url.
    """
    base_parsed = urlparse(base_url)
    base_host = base_parsed.netloc.lower()

    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        if not any(lbl in text for lbl in CONTACT_LINK_TEXTS_L):
            continue

        href = a.get("href") or ""
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc.lower() != base_host:
            continue

        return full_url

    return None


# ---------------------------------------------------------------------------
# Top-level: parse homepage HTML
# ---------------------------------------------------------------------------

def parse_homepage_html(html: str, base_url: str, safe_get) -> Dict[str, object]:
    """
    Run homepage-level checks: language, schema, social, legal, accessibility, analytics.

    `safe_get` is an HTTP GET helper injected from the caller (to avoid circular imports).
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Responsive design signals: viewport + inline + capped external CSS ---

    # 1) Viewport tag
    viewport_el = soup.find("meta", attrs={"name": "viewport"})
    viewport_present = viewport_el is not None

    # 2) Inline media queries in <style> tags
    inline_media_query_present = False
    for style_tag in soup.find_all("style"):
        css_text = style_tag.get_text() or ""
        if "@media" in css_text and "(max-width" in css_text:
            inline_media_query_present = True
            break

    css_links: List[str] = []

    def rel_is_stylesheet(v):
        if not v:
            return False
        # v can be a list/tuple or a string
        if isinstance(v, (list, tuple)):
            return any(isinstance(x, str) and "stylesheet" in x.lower() for x in v)
        if isinstance(v, str):
            return "stylesheet" in v.lower()
        return False

    for link in soup.find_all("link", rel=rel_is_stylesheet):
        href = link.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        css_links.append(full_url)

    filtered_css: List[str] = []
    for url in css_links:
        u = url.lower()
        if any(sub in u for sub in EXCLUDE_CSS_SUBSTRINGS):
            continue
        filtered_css.append(url)

    # Sort by heuristic score
    page_reg_domain = registrable_domain_from_url(base_url)
    filtered_css.sort(
        key=lambda u: score_css_url(u, page_reg_domain),
        reverse=True,
    )

    # Take top N
    selected_css = filtered_css[:MAX_CSS_FILES_FOR_RESPONSIVE_CHECK]

    external_media_query_present = detect_media_queries_in_external_css(selected_css, safe_get)

    # Combine signals into a simple flag + debug string
    responsive_design = viewport_present and (
        inline_media_query_present or external_media_query_present
    )

    responsive_signals: List[str] = []
    if viewport_present:
        responsive_signals.append("viewport")
    if inline_media_query_present:
        responsive_signals.append("inline_media")
    if external_media_query_present:
        responsive_signals.append("external_media")

    # Language / hreflang / localization detection
    lang_info = detect_languages_and_hreflang(soup, base_url)

    # Structured data: JSON-LD
    has_jsonld = bool(
        soup.find("script", attrs={"type": "application/ld+json"})
    )

    # Social profile links
    found_social: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        for key, name in SOCIAL_DOMAINS.items():
            if key in full_url.lower():
                found_social.add(name)

    # Accessibility: alt texts, heading structure, ARIA presence
    imgs = soup.find_all("img")
    img_count = len(imgs)

    imgs_with_alt = 0
    content_images = 0
    content_images_with_alt = 0
    logo_has_alt = False

    for img in imgs:
        alt = img.get("alt")
        has_alt_text = bool(alt and alt.strip())
        if has_alt_text:
            imgs_with_alt += 1

        roles = classify_image_role(img)
        is_content = not roles["is_decorative"]

        if is_content:
            content_images += 1
            if has_alt_text:
                content_images_with_alt += 1

        if roles["is_logo"] and has_alt_text:
            logo_has_alt = True

    alt_pct = (imgs_with_alt / img_count * 100.0) if img_count else None

    # Heading structure
    headings: List[int] = []
    # Collect headings in DOM order
    for h in soup.find_all(re.compile(r"^h[1-6]$", re.I)):
        try:
            level = int(h.name[1])
            headings.append(level)
        except (ValueError, IndexError):
            continue

    h1_count = headings.count(1)
    has_h2 = 2 in headings

    # Structure suspect:
    # - first heading is h3 or deeper, OR
    # - any jump between consecutive headings is > 1 (up or down)
    heading_structure_suspect = False
    if headings:
        first = headings[0]
        if first >= 3:
            heading_structure_suspect = True
        else:
            for prev, curr in zip(headings, headings[1:]):
                if abs(curr - prev) > 1:
                    heading_structure_suspect = True
                    break

    # ARIA presence
    aria_present = bool(
        soup.find(
            attrs=lambda attrs: attrs
            and any(k.startswith("aria-") for k in attrs)
        )
    )

    # Clickable div/span without proper keyboard access
    clickable_div_suspect_count = 0
    for el in soup.find_all(["div", "span"]):
        if not looks_interactive_divspan(el):
            continue
        if not has_keyboard_focus(el):
            clickable_div_suspect_count += 1

    # Analytics and cookie tools (script/link URLs + inline CMP hints)
    gtm_present = False
    gtm_consent_signals_present = False
    analytics_found: set[str] = set()
    cookie_found: set[str] = set()
    tag_managers_found: set[str] = set()

    for tag in soup.find_all(["script", "link"]):
        src = ""

        if tag.name == "script":
            src = tag.get("src") or ""
        else:  # link
            src = tag.get("href") or ""

        # External script / stylesheet detection
        if src:
            full_src = urljoin(base_url, src).lower()

            # CMP / cookie tools by URL
            for pat, name in COOKIE_PATTERNS.items():
                if pat in full_src:
                    cookie_found.add(name)

            # Tag manager detection
            for pat, name in TAG_MANAGER_PATTERNS.items():
                if pat in full_src:
                    tag_managers_found.add(name)

            # GTM detection by script URL (no IDs stored)
            if "googletagmanager.com/gtm.js" in full_src:
                gtm_present = True
                tag_managers_found.add("GTM")

        if tag.name == "script" and not src:
            js = (tag.get_text() or "")
            js_l = js.lower()
            if not js_l:
                continue

            # Inline CMP fingerprints
            for pat, name in COOKIE_INLINE_PATTERNS.items():
                if pat in js_l:
                    cookie_found.add(name)

            # GTM container ID present (anonymous)
            if re.search(r"\bgtm-[a-z0-9]+\b", js_l):
                gtm_present = True
                tag_managers_found.add("GTM")

            # Heuristic: dataLayer / gtag consent config → GTM-based CMP very likely
            if ("dataLayer" in js or "datalayer" in js_l or "gtag(" in js_l):
                consent_keywords = [
                    "consent",
                    "ad_storage",
                    "analytics_storage",
                    "personalization_storage",
                    "functionality_storage",
                    "security_storage",
                    "cookie_consent",
                ]
                if any(kw in js_l for kw in consent_keywords):
                    gtm_consent_signals_present = True

            # --- GA4 / Universal Analytics direct detection (no IDs stored) ---

            # GA4 measurement IDs: G-XXXXXXX...
            if re.search(r"\bG-[A-Z0-9]{6,16}\b", js, flags=re.I):
                analytics_found.add("Google Analytics 4")

            # gtag('config', 'G-...') style calls
            if "gtag(" in js_l and "config" in js_l and "g-" in js_l:
                analytics_found.add("Google Analytics 4")

            # Legacy UA-based gtag configs
            if "gtag(" in js_l and "config" in js_l and "ua-" in js_l:
                analytics_found.add("Google Analytics")

            # --- Meta / Facebook Pixel ---

            if "fbq(" in js_l or "fbevents.js" in js_l:
                analytics_found.add("Meta Pixel")

            # --- LinkedIn Insight Tag ---

            if "snap.licdn.com/li.lms-analytics/insight.min.js" in js_l:
                analytics_found.add("LinkedIn Insight Tag")

    cookie_tools_str = ", ".join(sorted(cookie_found)) if cookie_found else ""
    has_cmp = bool(cookie_found)

    # Heuristic: GTM-based CMP suspected if:
    #   - we saw GTM
    #   - we saw consent-related dataLayer/gtag config
    #   - BUT no explicit CMP vendor detected
    cookie_tools_suspected = ""
    if gtm_present and gtm_consent_signals_present and not has_cmp:
        cookie_tools_suspected = "GTM-based CMP"

    # Classify UI pattern (banner/buttons/footer) → descriptive flags
    cookie_ui = classify_cookie_ui(soup)

    # --- Contact info: email, phone, postal address ---

    contact_flags = detect_contact_info_on_page(soup, base_url)

    status_rank = {"none": 0, "text": 1, "clickable": 2}

    # If nothing found, try a contact/Kontakt page on same host (one extra fetch)
    if not (
        contact_flags["public_email"] != "none"
        or contact_flags["public_phone"] != "none"
        or contact_flags["address_present"]
    ):
        contact_url = find_contact_like_url(soup, base_url)
        if contact_url:
            resp_contact = safe_get(contact_url)
            if resp_contact and "text/html" in resp_contact.headers.get("Content-Type", ""):
                try:
                    contact_soup = BeautifulSoup(resp_contact.text, "html.parser")
                    contact_flags_contact = detect_contact_info_on_page(contact_soup, contact_url)
                    # Merge by selecting the stronger signal
                    for key in ("public_email", "public_phone"):
                        incoming = contact_flags_contact.get(key, "none")
                        if status_rank.get(incoming, 0) > status_rank.get(contact_flags.get(key, "none"), 0):
                            contact_flags[key] = incoming

                    if contact_flags_contact.get("address_present"):
                        contact_flags["address_present"] = True
                except Exception:
                    pass

    # word counter
    visible_word_count = estimate_visible_word_count(soup)

    return {
        # responsive design
        "responsive_design": responsive_design,
        "responsive_signals": ", ".join(responsive_signals) if responsive_signals else "",
        # language-related
        "html_lang": lang_info["html_lang"],
        "meta_lang": lang_info["meta_lang"],
        "primary_language": lang_info["primary_language"],
        "hreflang_languages": lang_info["hreflang_languages"],
        "hreflang_default_language": lang_info["hreflang_default_language"],
        "languages_detected": lang_info["languages_detected"],
        "localization_status": lang_info["localization_status"],
        "switcher_languages": lang_info["switcher_languages"],
        "url_languages": lang_info["url_languages"],
        # structured data & content
        "structured_data_jsonld": has_jsonld,
        "social_profiles": ", ".join(sorted(found_social)) if found_social else "",
        # accessibility
        "accessibility_alt_text_pct": alt_pct,
        "accessibility_content_images": content_images,
        "accessibility_content_images_with_alt": content_images_with_alt,
        "accessibility_logo_has_alt": logo_has_alt,
        "accessibility_heading_h1_count": h1_count,
        "accessibility_heading_has_h2": has_h2,
        "accessibility_heading_structure_suspect": heading_structure_suspect,
        "accessibility_aria_present": aria_present,
        "accessibility_clickable_div_count": clickable_div_suspect_count,
        "accessibility_clickable_div_suspect": clickable_div_suspect_count > 0,
        # tooling
        "analytics_tools": ", ".join(sorted(analytics_found)) if analytics_found else "",
        "cookie_tools": cookie_tools_str,
        "cookie_tools_suspected": cookie_tools_suspected,
        "cookie_banner_html_present": cookie_ui["cookie_banner_present"],
        "cookie_banner_has_accept": cookie_ui["cookie_banner_has_accept"],
        "cookie_banner_has_reject": cookie_ui["cookie_banner_has_reject"],
        "cookie_banner_has_settings": cookie_ui["cookie_banner_has_settings"],
        "cookie_banner_has_only_ok": cookie_ui["cookie_banner_has_only_ok"],
        "cookie_info_in_footer": cookie_ui["cookie_info_in_footer"],
        "cookie_choice_html_signal": cookie_ui["cookie_choice_html_signal"],
        "tag_manager_present": bool(tag_managers_found),
        "tag_managers": ", ".join(sorted(tag_managers_found)) if tag_managers_found else "",
        # contact
        "public_email": contact_flags["public_email"],
        "public_phone": contact_flags["public_phone"],
        "address_present": contact_flags["address_present"],
        # content depth
        "homepage_visible_word_count": visible_word_count,
    }