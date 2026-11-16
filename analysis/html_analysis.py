"""Homepage analysis: responsiveness, accessibility, tracking, cookies, contact."""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from analysis.address import detect_address
from analysis.language_localization import detect_languages_and_localization
from config import config as cfg
from config.dictionary_config import (
    ANALYTICS_PATTERNS,
    CONTACT_LINK_TEXTS_L,
    COOKIE_ACCEPT_BUTTON_LABELS,
    COOKIE_BANNER_CONTAINER_TOKENS,
    COOKIE_BANNER_FALLBACK_TOKENS,
    COOKIE_GENERIC_OK_LABELS,
    COOKIE_INFO_PHRASES,
    COOKIE_INLINE_PATTERNS,
    COOKIE_PATTERNS,
    COOKIE_REJECT_BUTTON_LABELS,
    COOKIE_SETTINGS_BUTTON_LABELS,
    COOKIE_STRONG_CONSENT_PHRASES,
    EMAIL_IGNORED_LOCALPARTS,
    EMAIL_REGEX,
    EXCLUDE_CSS_SUBSTRINGS,
    ICON_DECORATIVE_TOKENS,
    INTERACTIVE_ROLES,
    MAIN_CSS_KEYWORDS,
    PAYMENT_TOKENS,
    PLACEHOLDER_PHRASES,
    SOCIAL_DOMAINS,
    SOCIAL_SHARE_PATH_TOKENS,
    SOCIAL_TOKENS,
    SWISS_PHONE_PATTERNS,
    TAG_MANAGER_PATTERNS,
)
from http_tools.client import DomainClient, registrable_domain

WORD_RE = re.compile(r"\w+", re.UNICODE)

# Any width-dependent rule counts: max-width, min-width (mobile first),
# range syntax "(width <= 600px)" and container queries.
WIDTH_QUERY_RE = re.compile(
    r"@(?:media|container)[^{};]{0,300}?\b(?:width|inline-size)\b", re.I
)

GA4_ID_RE = re.compile(r"(?<![\w-])G-[A-Z0-9]{8,12}(?![\w-])")
UA_ID_RE = re.compile(r"(?<![\w-])UA-\d{4,10}-\d{1,4}(?![\w-])")
GTM_ID_RE = re.compile(r"(?<![\w-])GTM-[A-Z0-9]{4,10}(?![\w-])")
CONSENT_KEYWORDS = ("ad_storage", "analytics_storage", "personalization_storage",
                    "functionality_storage", "security_storage", "cookie_consent",
                    "'consent'", '"consent"')


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def email_is_ignored(addr: str) -> bool:
    local = addr.split("@", 1)[0].lower()
    return any(bad in local for bad in EMAIL_IGNORED_LOCALPARTS)


def estimate_visible_word_count(soup: BeautifulSoup) -> int:
    """Rough number of visible words in <main> (or <body>)."""
    clone = copy.copy(soup)  # bs4 copies the whole tree, the original stays intact
    root = clone.find("main") or clone.body or clone
    for el in root.find_all(["script", "style", "noscript", "svg", "template"]):
        el.decompose()
    return len(WORD_RE.findall(root.get_text(" ", strip=True) or ""))


def _attr_tokens(*values) -> List[str]:
    """Split id/class/role values into lower-case word tokens."""
    tokens: List[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            value = " ".join(str(v) for v in value)
        tokens.extend(t for t in re.split(r"[^a-z0-9äöüéèàç]+", str(value or "").lower()) if t)
    return tokens


def _phrase_regex(phrases: List[str]) -> re.Pattern:
    """One regex matching any phrase as whole words ("ok" but not "facebook")."""
    parts = sorted({re.escape(p.strip().lower()) for p in phrases if p.strip()}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])")


_ACCEPT_RE = _phrase_regex(COOKIE_ACCEPT_BUTTON_LABELS)
_REJECT_RE = _phrase_regex(COOKIE_REJECT_BUTTON_LABELS)
_SETTINGS_RE = _phrase_regex(COOKIE_SETTINGS_BUTTON_LABELS)
_OK_RE = _phrase_regex(COOKIE_GENERIC_OK_LABELS)


# ---------------------------------------------------------------------------
# Responsive design
# ---------------------------------------------------------------------------

def score_css_url(css_url: str, page_reg_domain: str) -> int:
    """Higher score = more likely to hold the layout rules."""
    score = 0
    filename = urlparse(css_url).path.lower().rsplit("/", 1)[-1]
    if registrable_domain(urlparse(css_url).netloc) == page_reg_domain:
        score += 3
    if any(kw in filename for kw in MAIN_CSS_KEYWORDS):
        score += 2
    if len(filename) < 40:
        score += 1
    return score


def analyse_responsive(soup: BeautifulSoup, base_url: str, client: Optional[DomainClient]) -> Dict[str, Any]:
    """yes     viewport tag and width-dependent CSS rules
    likely  viewport tag, but no such rules seen (fluid layouts need none,
            or the CSS could not be read)
    no      no viewport tag: phones render the page at desktop width
    """
    signals: List[str] = []
    viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}) is not None
    if viewport:
        signals.append("viewport")

    inline = any(WIDTH_QUERY_RE.search(tag.get_text() or "") for tag in soup.find_all("style"))
    if inline:
        signals.append("inline_media")

    css_links: List[str] = []
    for link in soup.find_all("link", href=True):
        rel = link.get("rel") or []
        rel = rel if isinstance(rel, list) else [rel]
        if any("stylesheet" in str(r).lower() for r in rel):
            url = urljoin(base_url, link["href"])
            name = urlparse(url).path.lower().rsplit("/", 1)[-1]
            # "fa-" (Font Awesome) is only meaningful at the start of a file name
            if name.startswith("fa-") or any(
                sub in url.lower() for sub in EXCLUDE_CSS_SUBSTRINGS if sub != "fa-"
            ):
                continue
            css_links.append(url)
    css_links = list(dict.fromkeys(css_links))
    page_domain = registrable_domain(urlparse(base_url).netloc)
    css_links.sort(key=lambda u: score_css_url(u, page_domain), reverse=True)

    external, checked = False, 0
    if client is not None and not inline:
        for css_url in css_links[: cfg.MAX_CSS_FILES_FOR_RESPONSIVE_CHECK]:
            resp = client.get(css_url, max_bytes=cfg.MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK)
            if resp is None or resp.status_code != 200:
                continue
            if "css" not in resp.headers.get("Content-Type", "").lower():
                continue
            checked += 1
            if WIDTH_QUERY_RE.search(resp.text or ""):
                external = True
                break
    if external:
        signals.append("external_media")
    elif css_links and not inline and checked == 0:
        signals.append("css_unchecked")

    if not viewport:
        verdict = "no"
    elif inline or external:
        verdict = "yes"
    else:
        verdict = "likely"
    return {"responsive_design": verdict, "responsive_signals": ", ".join(signals)}


# ---------------------------------------------------------------------------
# Images / accessibility
# ---------------------------------------------------------------------------

def _parse_dimension(val) -> Optional[int]:
    m = re.search(r"(\d+)", str(val or ""))
    return int(m.group(1)) if m else None


def is_small_icon_image(img) -> bool:
    w, h = _parse_dimension(img.get("width")), _parse_dimension(img.get("height"))
    if (w is not None and w <= 40) or (h is not None and h <= 40):
        return True
    m = re.search(r"(?<!\d)(\d{1,2})x(\d{1,2})(?!\d)", (img.get("src") or "").lower())
    return bool(m and int(m.group(1)) <= 40 and int(m.group(2)) <= 40)


def classify_image_role(img) -> Dict[str, bool]:
    """Roughly: logo, social/payment icon, or decorative (small/icon-like)."""
    blob = " ".join([(img.get("src") or ""), " ".join(img.get("class") or []),
                     (img.get("id") or "")]).lower()
    is_logo = "logo" in blob or "brand" in _attr_tokens(blob)
    special = any(tok in blob for tok in SOCIAL_TOKENS + PAYMENT_TOKENS)
    parent_link = img.find_parent("a", href=True)
    if parent_link and any(tok in (parent_link.get("href") or "").lower()
                           for tok in SOCIAL_TOKENS + PAYMENT_TOKENS):
        special = True
    icon_like = is_small_icon_image(img) or any(tok in blob for tok in ICON_DECORATIVE_TOKENS)
    return {"is_logo": is_logo, "is_social_or_payment": special,
            "is_decorative": icon_like and not (is_logo or special)}


def analyse_images(soup: BeautifulSoup) -> Dict[str, Any]:
    """Alt-text statistics.

    A missing alt attribute is always a defect. An empty alt="" is correct for
    decorative images, but wrong on an image that is the only content of a link.
    """
    imgs = soup.find_all("img")
    total = len(imgs)
    missing = with_text = linked_empty = 0
    content = content_with_alt = 0
    logo_seen, logo_has_alt = False, False

    for img in imgs:
        alt = img.get("alt")
        has_text = bool(alt and alt.strip())
        if alt is None:
            missing += 1
        if has_text:
            with_text += 1

        if not has_text and img.get("aria-hidden") != "true":
            link = img.find_parent("a")
            if link is not None and not link.get_text(strip=True) \
                    and not (link.get("aria-label") or link.get("title")):
                linked_empty += 1

        roles = classify_image_role(img)
        if not roles["is_decorative"]:
            content += 1
            content_with_alt += has_text
        if roles["is_logo"]:
            logo_seen = True
            logo_has_alt = logo_has_alt or has_text

    return {
        "accessibility_images_total": total,
        "accessibility_images_missing_alt": missing,
        "accessibility_alt_attr_pct": round((total - missing) / total * 100, 1) if total else None,
        "accessibility_alt_text_pct": round(with_text / total * 100, 1) if total else None,
        "accessibility_linked_images_without_alt": linked_empty,
        "accessibility_content_images": content,
        "accessibility_content_images_with_alt": content_with_alt,
        "accessibility_logo_has_alt": logo_has_alt if logo_seen else None,
    }


def analyse_headings(soup: BeautifulSoup) -> Dict[str, Any]:
    levels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$", re.I))]
    # Suspect: the page starts at h3 or deeper, or a level is skipped on the
    # way down (h2 -> h4). Going back up (h4 -> h2) is perfectly fine.
    suspect = bool(levels) and (
        levels[0] >= 3 or any(cur - prev > 1 for prev, cur in zip(levels, levels[1:]))
    )
    return {
        "accessibility_heading_h1_count": levels.count(1),
        "accessibility_heading_has_h2": 2 in levels,
        "accessibility_heading_structure_suspect": suspect,
    }


def count_aria(soup: BeautifulSoup) -> int:
    """Elements carrying an aria-* attribute or an explicit role."""
    return sum(
        1 for tag in soup.find_all(True)
        if any(k == "role" or k.startswith("aria-") for k in tag.attrs)
    )


def looks_interactive_divspan(el) -> bool:
    """A <div>/<span> that is meant to be clicked."""
    if any(el.get(a) for a in ("onclick", "onmousedown", "onmouseup", "onkeydown",
                               "onkeyup", "onkeypress")):
        return True
    if (el.get("role") or "").lower() in INTERACTIVE_ROLES:
        return True
    classes = [c.lower() for c in (el.get("class") or [])]
    for c in classes:
        # "btn", "btn-primary", "button", "cta-button" - but not the wrappers
        # around buttons ("btn-group", "button-wrapper").
        if re.search(r"(group|wrap|container|row|bar|list|holder|area)", c):
            continue
        if c in ("btn", "button", "cta") or c.startswith(("btn-", "button-", "cta-")) \
                or c.endswith(("-btn", "-button", "-cta")):
            # a wrapper that merely contains a real control is fine
            return el.find(["a", "button", "input"]) is None
    return False


def has_keyboard_focus(el) -> bool:
    try:
        return int(el.get("tabindex")) >= 0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Social profiles
# ---------------------------------------------------------------------------

def social_network_for_url(url: str) -> Optional[str]:
    """Network name if ``url`` is a profile link (not a share button or policy page)."""
    parsed = urlparse(url if "//" in url else "//" + url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    for domain, name in SOCIAL_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            path = parsed.path.lower()
            if len(path.strip("/")) < 2:
                return None  # bare network home page
            if any(path == tok.rstrip("/") or path.startswith(tok if tok.endswith("/") else tok + "/")
                   or path.startswith(tok + ".") for tok in SOCIAL_SHARE_PATH_TOKENS):
                return None
            return name
    return None


def find_social_profiles(soup: BeautifulSoup, base_url: str) -> List[str]:
    found = set()
    for a in soup.find_all("a", href=True):
        name = social_network_for_url(urljoin(base_url, a["href"]))
        if name:
            found.add(name)
    return sorted(found)


# ---------------------------------------------------------------------------
# Tracking, tag managers, consent tools
# ---------------------------------------------------------------------------

def analyse_scripts(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    analytics, cookie_tools, tag_managers = set(), set(), set()
    gtm_present = consent_mode = False

    def match_analytics(text_l: str) -> None:
        for pat, name in ANALYTICS_PATTERNS.items():
            if pat in text_l:
                analytics.add(name)

    for tag in soup.find_all(["script", "link", "iframe", "img"]):
        src = tag.get("src") or tag.get("href") or tag.get("data-src") or ""
        if src:
            full = urljoin(base_url, src)
            full_l = full.lower()
            if tag.name in ("script", "link"):
                for pat, name in COOKIE_PATTERNS.items():
                    if pat in full_l:
                        cookie_tools.add(name)
            for pat, name in TAG_MANAGER_PATTERNS.items():
                if pat.lower() in full_l:
                    tag_managers.add(name)
            if "googletagmanager.com/gtm.js" in full_l or "googletagmanager.com/ns.html" in full_l:
                gtm_present = True
                tag_managers.add("GTM")
            if "googletagmanager.com/gtag/js" in full_l:
                if GA4_ID_RE.search(full):
                    analytics.add("Google Analytics 4")
                elif UA_ID_RE.search(full):
                    analytics.add("Google Analytics")
                elif "id=aw-" in full_l:
                    analytics.add("Google Ads")
            if tag.name != "link":
                match_analytics(full_l)

        if tag.name == "script" and not tag.get("src"):
            js = tag.get_text() or ""
            if not js.strip() or "ld+json" in (tag.get("type") or "").lower():
                continue
            js_l = js.lower()
            for pat, name in COOKIE_INLINE_PATTERNS.items():
                if pat in js_l:
                    cookie_tools.add(name)
            if GTM_ID_RE.search(js) and ("googletagmanager" in js_l or "gtm.start" in js_l):
                gtm_present = True
                tag_managers.add("GTM")
            uses_gtag = "gtag(" in js_l or "datalayer" in js_l
            if uses_gtag and any(kw in js_l for kw in CONSENT_KEYWORDS):
                consent_mode = True
            # IDs only count next to the code that uses them; "g-recaptcha"
            # and CSS class names must not look like Google Analytics.
            if uses_gtag or "googletagmanager" in js_l or "google-analytics" in js_l:
                if GA4_ID_RE.search(js):
                    analytics.add("Google Analytics 4")
                if UA_ID_RE.search(js):
                    analytics.add("Google Analytics")
            match_analytics(js_l)

    suspected = "GTM-based CMP" if (gtm_present and consent_mode and not cookie_tools) else ""
    return {
        "analytics_tools": ", ".join(sorted(analytics)),
        "cookie_tools": ", ".join(sorted(cookie_tools)),
        "cookie_tools_suspected": suspected,
        "tag_manager_present": bool(tag_managers),
        "tag_managers": ", ".join(sorted(tag_managers)),
    }


# ---------------------------------------------------------------------------
# Cookie banner in the static HTML
# ---------------------------------------------------------------------------

def _is_button_like(el) -> bool:
    if el.name == "button":
        return True
    if el.name == "input":
        return (el.get("type") or "").lower() in ("button", "submit")
    if (el.get("role") or "").lower() == "button":
        return True
    if el.name == "a":
        href = (el.get("href") or "").strip().lower()
        classes = " ".join(el.get("class") or []).lower()
        return (not href or href.startswith(("#", "javascript:"))
                or "btn" in classes or "button" in classes)
    return False


def _button_label(el) -> str:
    label = el.get_text(" ", strip=True) or el.get("value") or el.get("aria-label") \
        or el.get("title") or ""
    label = re.sub(r"\s+", " ", label).strip(" \t\n.!:»›>✓✔×").lower()
    return label if len(label) <= 40 else ""


def classify_cookie_ui(soup: BeautifulSoup) -> Dict[str, Any]:
    """Look for a cookie/consent banner and the choices it offers.

    Only the HTML as delivered is seen. Banners that a script builds in the
    browser are invisible here (the CMP vendor detection covers many of those).
    """

    def candidates(tokens: List[str]) -> List[tuple]:
        long_tokens = [t.lower() for t in tokens if len(t) >= 6]
        short_tokens = {t.lower() for t in tokens if len(t) < 6}
        found = []
        for tag in soup.find_all(True):
            if tag.name in ("html", "body", "head", "script", "style", "link", "meta",
                            "noscript", "a", "button", "input", "footer", "main"):
                continue
            values = [tag.get("id") or "", tag.get("class") or [], tag.get("role") or ""]
            values += [str(v) for k, v in tag.attrs.items() if k.startswith("data-")]
            toks = _attr_tokens(*values)
            if not toks:
                continue
            joined = " ".join(toks)
            if not (any(t in joined for t in long_tokens) or short_tokens.intersection(toks)):
                continue
            text_l = (tag.get_text(" ", strip=True) or "").lower()
            if len(text_l) > 2500:
                continue  # a whole page section, not a banner
            if "cookie" not in text_l and not any(p in text_l for p in COOKIE_INFO_PHRASES):
                continue
            buttons = [el for el in tag.find_all(["button", "a", "input", "span", "div"])
                       if _is_button_like(el)]
            found.append((len(buttons), -len(text_l), tag, text_l, buttons))
        return found

    found = candidates(COOKIE_BANNER_CONTAINER_TOKENS) or candidates(COOKIE_BANNER_FALLBACK_TOKENS)

    out = {
        "cookie_banner_html_present": bool(found),
        "cookie_banner_has_accept": False,
        "cookie_banner_has_reject": False,
        "cookie_banner_has_settings": False,
        "cookie_banner_has_only_ok": False,
        "cookie_info_in_footer": False,
        "cookie_choice_html_signal": False,
    }
    if found:
        # the candidate with the most buttons is the banner; ties go to the
        # more compact one
        _, _, _, text_l, buttons = max(found, key=lambda c: (c[0], c[1]))
        labels = [l for l in (_button_label(b) for b in buttons) if l]
        has_reject = any(_REJECT_RE.search(l) for l in labels)
        has_settings = any(_SETTINGS_RE.search(l) for l in labels)
        # "alle ablehnen" must not count as accept because of a shared word
        has_accept = any(_ACCEPT_RE.search(l) and not _REJECT_RE.search(l) for l in labels)
        has_ok = any(_OK_RE.search(l) for l in labels)
        out.update(
            cookie_banner_has_accept=has_accept,
            cookie_banner_has_reject=has_reject,
            cookie_banner_has_settings=has_settings,
            cookie_banner_has_only_ok=has_ok and not (has_accept or has_reject or has_settings),
            cookie_choice_html_signal=bool(
                has_reject or has_settings
                or any(p in text_l for p in COOKIE_STRONG_CONSENT_PHRASES)
            ),
        )

    footer = soup.find("footer")
    if footer:
        footer_text = (footer.get_text(" ", strip=True) or "").lower()
        out["cookie_info_in_footer"] = "cookie" in footer_text or any(
            p in footer_text for p in COOKIE_INFO_PHRASES
        )
    return out


# ---------------------------------------------------------------------------
# Contact information
# ---------------------------------------------------------------------------

CONTACT_RANK = {"none": 0, "text": 1, "obfuscated": 2, "clickable": 3}


def detect_contact_info_on_page(soup: BeautifulSoup) -> Dict[str, Any]:
    """public_email / public_phone: none, text, obfuscated (e-mail hidden from
    bots, e.g. by Cloudflare) or clickable; plus the address check."""
    text = soup.get_text(" ", strip=True) or ""
    email = phone = "none"

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        href_l = href.lower()
        if href_l.startswith("mailto:"):
            addr = href.split(":", 1)[1].split("?", 1)[0].strip()
            if addr and not email_is_ignored(addr):
                email = "clickable"
        elif "/cdn-cgi/l/email-protection" in href_l and email == "none":
            email = "obfuscated"
        elif href_l.startswith("tel:") and len(re.sub(r"\D", "", href)) >= 7:
            phone = "clickable"

    if email == "none":
        if soup.find(class_="__cf_email__"):
            email = "obfuscated"
        elif any(not email_is_ignored(m.group(0)) for m in EMAIL_REGEX.finditer(text)):
            email = "text"
    if phone == "none" and any(p.search(text) for p in SWISS_PHONE_PATTERNS):
        phone = "text"

    address_present, address_source = detect_address(soup, text)
    return {"public_email": email, "public_phone": phone,
            "address_present": address_present, "address_source": address_source}


def find_contact_like_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """A link to a contact page on the same host."""
    base_host = urlparse(base_url).netloc.lower()
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        if not text or len(text) > 40 or not any(lbl in text for lbl in CONTACT_LINK_TEXTS_L):
            continue
        full_url = urljoin(base_url, a.get("href") or "")
        parsed = urlparse(full_url)
        if parsed.scheme in ("http", "https") and parsed.netloc.lower() == base_host \
                and parsed.path.rstrip("/") != urlparse(base_url).path.rstrip("/"):
            return full_url.split("#")[0]
    return None


def analyse_contact(soup: BeautifulSoup, base_url: str, client: Optional[DomainClient]) -> Dict[str, Any]:
    """Contact details on the homepage; if something is missing, one look at
    the contact page."""
    flags = detect_contact_info_on_page(soup)
    complete = (flags["public_email"] != "none" and flags["public_phone"] != "none"
                and flags["address_present"])
    if complete or client is None:
        return flags
    contact_url = find_contact_like_url(soup, base_url)
    if not contact_url:
        return flags
    resp = client.get(contact_url)
    if resp is None or resp.status_code != 200 \
            or "html" not in resp.headers.get("Content-Type", "").lower():
        return flags
    try:
        other = detect_contact_info_on_page(BeautifulSoup(resp.text, "html.parser"))
    except Exception:
        return flags
    for key in ("public_email", "public_phone"):
        if CONTACT_RANK[other[key]] > CONTACT_RANK[flags[key]]:
            flags[key] = other[key]
    if other["address_present"] and not flags["address_present"]:
        flags["address_present"] = True
        flags["address_source"] = other["address_source"]
    return flags


# ---------------------------------------------------------------------------
# Placeholder pages
# ---------------------------------------------------------------------------

def detect_placeholder(soup: BeautifulSoup, word_count: int) -> str:
    """"for_sale", "under_construction", "default_page" or "" - only for pages
    with hardly any content, so a blog post about domains is not flagged."""
    if word_count > 150:
        return ""
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = (title + " " + soup.get_text(" ", strip=True)).lower()
    for label, phrases in PLACEHOLDER_PHRASES.items():
        if any(p in text for p in phrases):
            return label
    return ""


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def parse_homepage_html(
    soup: BeautifulSoup, base_url: str, client: Optional[DomainClient] = None
) -> Dict[str, Any]:
    """Run all homepage checks on an already parsed page.

    ``client`` is used for at most three extra requests (two stylesheets and
    the contact page); pass None to stay offline.
    """
    out: Dict[str, Any] = {}
    out.update(analyse_responsive(soup, base_url, client))
    out.update(detect_languages_and_localization(soup, base_url))

    out["structured_data_jsonld"] = bool(
        soup.find("script", attrs={"type": re.compile(r"ld\+json", re.I)})
    )
    out["social_profiles"] = ", ".join(find_social_profiles(soup, base_url))

    out.update(analyse_images(soup))
    out.update(analyse_headings(soup))
    aria = count_aria(soup)
    out["accessibility_aria_count"] = aria
    out["accessibility_aria_present"] = aria > 0
    clickable = sum(
        1 for el in soup.find_all(["div", "span"])
        if looks_interactive_divspan(el) and not has_keyboard_focus(el)
    )
    out["accessibility_clickable_div_count"] = clickable
    out["accessibility_clickable_div_suspect"] = clickable > 0

    out.update(analyse_scripts(soup, base_url))
    out.update(classify_cookie_ui(soup))
    out.update(analyse_contact(soup, base_url, client))

    words = estimate_visible_word_count(soup)
    out["homepage_visible_word_count"] = words
    out["placeholder_page"] = detect_placeholder(soup, words)
    return out
