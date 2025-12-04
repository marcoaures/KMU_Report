from __future__ import annotations

import csv
import datetime
import functools
import logging
import os
import time
import threading
from typing import Dict, List, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import (
    INPUT_CSV,
    OUTPUT_CSV,
    DOMAIN_OFFSET,
    DOMAINS_PER_RUN,
    WORKER_COUNT,
    MAX_CSS_FILES_FOR_RESPONSIVE_CHECK,
    MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK,
    SHOW_PROGRESS,
    SHOW_VERBOSE_PROGRESS,
    CHECKPOINT_INTERVAL,
)

from integrations.api_clients import fetch_pagespeed, detect_cms_and_server
from config.dictionary_config import (
    BLOG_SITEMAP_KEYWORDS,
    BLOG_LINK_TEXT_KEYWORDS,
    BLOG_HREF_KEYWORDS,
    BLOG_FALLBACK_PATHS,
    IMPRINT_SITEMAP_KEYWORDS,
    IMPRINT_LINK_TEXT_KEYWORDS,
    IMPRINT_HREF_KEYWORDS,
    IMPRINT_FALLBACK_PATHS,
    PRIVACY_SITEMAP_KEYWORDS,
    PRIVACY_LINK_TEXT_KEYWORDS,
    PRIVACY_HREF_KEYWORDS,
    PRIVACY_FALLBACK_PATHS,
    TERMS_SITEMAP_KEYWORDS,
    TERMS_LINK_TEXT_KEYWORDS,
    TERMS_HREF_KEYWORDS,
    TERMS_FALLBACK_PATHS,
    EXCLUDE_CSS_SUBSTRINGS,
    MAIN_CSS_KEYWORDS,
)
from http_tools.cdn_utils import detect_cdn_waf
from dns_tools.dns_security import check_dnssec, check_spf, check_dmarc
from analysis.html_analysis import parse_homepage_html
from http_tools.http_utils import (
    USER_AGENT,
    safe_get,
    check_website_reachable,
    check_https_enforced,
    check_hsts,
)
from analysis.sections import detect_careers_section, detect_section
from http_tools.security_http import (
    check_llms_txt,
    check_security_headers,
    check_security_txt,
)
from analysis.sitemap_utils import (
    check_robots,
    count_pages_by_recency,
    fetch_xml,
    find_sitemaps,
    robots_allows_url,
    parse_sitemap_for_urls_and_dates,
)
from http_tools.tls_utils import check_tls

from bs4 import BeautifulSoup

LOG_FILE = "run.log"
PARTIAL_OUTPUT_CSV = f"{OUTPUT_CSV}.partial"
RETRY_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 2

print_lock = threading.Lock()


def setup_logging() -> None:
    """Configure structured logging to both file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def log_verbose(domain: str, phase: str) -> None:
    """Print phase information for a domain when verbose progress is enabled."""
    if not SHOW_VERBOSE_PROGRESS:
        return

    with print_lock:
        print(f"[INFO] {domain}: {phase}")


def update_progress(completed: int, total: int) -> None:
    """Render a simple progress counter when progress display is enabled."""
    if not SHOW_PROGRESS:
        return

    with print_lock:
        print(f"\rProgress: {completed}/{total}", end="", flush=True)

# ---------------------------------------------------------------------------
# Top-level per-domain orchestration
# ---------------------------------------------------------------------------

def run_checks_for_domain(domain: str) -> Dict[str, object]:
    """Run all checks for a single domain and return a flat result dict."""
    result: Dict[str, object] = {
        "domain": domain,
        # Availability & Technical Foundation
        "website_reachable": False,
        "website_reachability_status": "unreachable",
        "https_enforced": None,
        "hsts_header": "",
        "dnssec_status": None,
        "cdn_waf": None,
        # SEO, Structure & Content
        "robots_txt_present": False,
        "sitemap_present": False,
        "sitemap_url_count": 0,
        "sitemap_page_count": 0,
        "sitemap_locations": "",
        "sitemap_sources": "",
        "homepage_visible_word_count": None,
        # Contact info
        "public_email": "none",
        "public_phone": "none",
        "address_present": False,
        # sitemap lastmod / recency
        "pages_last_12m": 0,
        "pages_last_6m": 0,
        "pages_last_3m": 0,
        "pages_last_1m": 0,
        "sitemap_lastmod_any": False,          # do any URLs have lastmod?
        "sitemap_lastmod_urls_with_date": 0,   # how many URLs have lastmod
        "sitemap_lastmod_most_recent": None,   # ISO string of most recent lastmod
        "structured_data_jsonld": False,
        "blog_or_news_present": False,
        "blog_or_news_source": None,
        "blog_or_news_path": "",
        "social_profiles": "",
        "careers_page_present": False,
        "careers_page_source": None,
        "careers_page_path": "",
        # Language / localization
        "html_lang": None,
        "meta_lang": None,
        "primary_language": None,
        "hreflang_languages": "",
        "hreflang_default_language": None,
        "languages_detected": "",
        "localization_status": "",
        "switcher_languages": "",
        "url_languages": "",
        # Performance & Experience
        "pagespeed_desktopperformance_score": None,
        "pagespeed_mobileperformance_score": None,
        "responsive_design": None,
        "responsive_signals": "",
        # Accessibility
        "accessibility_alt_text_pct": None,
        "accessibility_content_images": None,
        "accessibility_content_images_with_alt": None,
        "accessibility_logo_has_alt": None,
        "accessibility_heading_h1_count": None,
        "accessibility_heading_has_h2": None,
        "accessibility_heading_structure_suspect": None,
        "accessibility_aria_present": None,
        "accessibility_clickable_div_count": None,
        "accessibility_clickable_div_suspect": None,
        # Technology Stack
        "cms_name": None,
        "cms_version": None,
        "cms_version_up_to_date": None,
        "analytics_tools": "",
        "tag_manager_present": False,
        "tag_managers": "",
        # Security Posture
        "security_hsts": False,
        "security_x_frame_options": False,
        "security_x_content_type_options": False,
        "security_referrer_policy": False,
        "security_csp": False,
        "security_permissions_policy": False,
        "spf_present": False,
        "spf_record": "",
        "dmarc_policy": None,
        # TLS details
        "tls_handshake_ok": None,
        "tls_protocol": None,
        "tls_cert_expiry": None,
        "tls_issue_category": "no_tls_or_other_error",
        # Compliance & Trust
        "cookie_tools": "",                  # detected CMP vendors from script URLs / inline JS
        "cookie_tools_suspected": "",        # e.g. "GTM-based CMP" if only heuristically inferred
        "cookie_banner_html_present": False, # any banner-like container detected in HTML
        "cookie_banner_has_accept": False,
        "cookie_banner_has_reject": False,
        "cookie_banner_has_settings": False,
        "cookie_banner_has_only_ok": False,
        "cookie_info_in_footer": False,
        "cookie_choice_status": "none",  # html_ui / cmp_vendor / gtm_heuristic combinations
        "imprint_present": False,
        "imprint_source": None,
        "imprint_path": "",
        "privacy_policy_present": False,
        "privacy_policy_source": None,
        "privacy_policy_path": "",
        "terms_present": False,
        "terms_source": None,
        "terms_path": "",
        # Well-known files
        "security_txt_present": False,
        "llms_txt_present": False,
    }

    log_verbose(domain, "Starting checks")

    # --- robots.txt ---
    log_verbose(domain, "Analyzing robots.txt policies")
    robots_present, robots_txt = check_robots(domain)
    result["robots_txt_present"] = robots_present

    robots_allow_root = robots_allows_url(robots_txt, f"https://{domain}/")

    if not robots_allow_root:
        result["website_reachability_status"] = "disallowed_by_robots"
        result["website_reachable"] = False
        return result

    robots_safe_get = functools.partial(
        safe_get, robots_txt=robots_txt, user_agent=USER_AGENT, log_disallowed=True
    )

    # --- Availability & technical foundation ---
    log_verbose(domain, "Checking availability and reachability")
    reachable, base_url, base_resp, reachability_status = check_website_reachable(
        domain, get_fn=robots_safe_get
    )
    result["website_reachable"] = reachable
    result["website_reachability_status"] = reachability_status

    result["https_enforced"] = check_https_enforced(domain, get_fn=robots_safe_get)

    if base_resp and base_resp.url.lower().startswith("https://"):
        result["hsts_header"] = check_hsts(base_resp)

    result["dnssec_status"] = check_dnssec(domain)
    result["cdn_waf"] = detect_cdn_waf(domain, base_resp)

    # --- robots.txt & sitemaps ---
    log_verbose(domain, "Analyzing sitemaps")
    sitemaps, sitemap_sources = find_sitemaps(
        domain, robots_txt, get_fn=robots_safe_get
    )
    if sitemaps:
        result["sitemap_present"] = True
    else:
        sitemap_sources = {}

    all_urls: List[str] = []
    all_lastmods: Dict[str, Optional[datetime.datetime]] = {}
    for sm_url in sitemaps:
        xml_text = fetch_xml(
            sm_url, get_fn=robots_safe_get, robots_txt=robots_txt, log_disallowed=True
        )
        if not xml_text:
            continue
        urls, lastmods = parse_sitemap_for_urls_and_dates(
            xml_text,
            get_fn=robots_safe_get,
            robots_txt=robots_txt,
            log_disallowed=True,
        )
        all_urls.extend(urls)
        all_lastmods.update(lastmods)

    result["sitemap_url_count"] = len(sitemaps)
    result["sitemap_page_count"] = len(all_urls)

    # Store sitemap locations and how they were discovered (paths only, no domain)
    if sitemaps:
        paths = [urlparse(u).path or "/" for u in sitemaps]
        result["sitemap_locations"] = ", ".join(paths)

        result["sitemap_sources"] = "; ".join(
            f"{urlparse(u).path or '/'} ({sitemap_sources.get(u, '')})"
            for u in sitemaps
        )
    else:
        result["sitemap_locations"] = ""
        result["sitemap_sources"] = ""

    if all_lastmods:
        counts = count_pages_by_recency(all_lastmods)
        result["pages_last_12m"] = counts["12m"]
        result["pages_last_6m"] = counts["6m"]
        result["pages_last_3m"] = counts["3m"]
        result["pages_last_1m"] = counts["1m"]

        # lastmod availability & most recent date
        dates = [dt for dt in all_lastmods.values() if dt is not None]
        if dates:
            # Normalize to UTC and compute stats
            normalized = [
                dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.timezone.utc)
                for dt in dates
            ]
            most_recent = max(normalized)
            result["sitemap_lastmod_any"] = True
            result["sitemap_lastmod_urls_with_date"] = len(normalized)

            # normalize all outputs to UTC for consistency
            most_recent_utc = most_recent.astimezone(datetime.timezone.utc)
            result["sitemap_lastmod_most_recent"] = most_recent_utc.isoformat()
        else:
            # We have sitemaps, but no lastmod on any URL
            result["sitemap_lastmod_any"] = False
            result["sitemap_lastmod_urls_with_date"] = 0
            result["sitemap_lastmod_most_recent"] = None
    else:
        # No sitemap URLs at all
        result["sitemap_lastmod_any"] = False
        result["sitemap_lastmod_urls_with_date"] = 0
        result["sitemap_lastmod_most_recent"] = None

    # --- Blog / careers / legal section detection (sitemap + homepage + fallback) ---
    log_verbose(domain, "Detecting sitemap-based and on-page sections")
    homepage_html: Optional[str] = None
    homepage_url: Optional[str] = None
    soup_for_sections: Optional[BeautifulSoup] = None

    if base_resp and "text/html" in base_resp.headers.get("Content-Type", ""):
        homepage_html = base_resp.text
        homepage_url = base_resp.url
        try:
            soup_for_sections = BeautifulSoup(homepage_html, "html.parser")
        except Exception:
            soup_for_sections = None

    # Blog / news
    blog_present, blog_source, blog_path = detect_section(
        sitemap_urls=all_urls,
        soup=soup_for_sections,
        homepage_url=homepage_url,
        domain=domain,
        sitemap_keywords=BLOG_SITEMAP_KEYWORDS,
        link_text_keywords=BLOG_LINK_TEXT_KEYWORDS,
        href_keywords=BLOG_HREF_KEYWORDS,
        fallback_paths=BLOG_FALLBACK_PATHS,
        safe_get_fn=robots_safe_get,
    )
    result["blog_or_news_present"] = blog_present
    result["blog_or_news_source"] = blog_source
    result["blog_or_news_path"] = blog_path or ""

    # Careers / jobs (specialized logic)
    careers_present, careers_source, careers_path = detect_careers_section(
        sitemap_urls=all_urls,
        soup=soup_for_sections,
        homepage_url=homepage_url,
        domain=domain,
        safe_get_fn=robots_safe_get,
    )
    result["careers_page_present"] = careers_present
    result["careers_page_source"] = careers_source
    result["careers_page_path"] = careers_path or ""

    # Imprint / Impressum
    imprint_present, imprint_source, imprint_path = detect_section(
        sitemap_urls=all_urls,
        soup=soup_for_sections,
        homepage_url=homepage_url,
        domain=domain,
        sitemap_keywords=IMPRINT_SITEMAP_KEYWORDS,
        link_text_keywords=IMPRINT_LINK_TEXT_KEYWORDS,
        href_keywords=IMPRINT_HREF_KEYWORDS,
        fallback_paths=IMPRINT_FALLBACK_PATHS,
        safe_get_fn=robots_safe_get,
    )
    result["imprint_present"] = imprint_present
    result["imprint_source"] = imprint_source
    result["imprint_path"] = imprint_path or ""

    # Privacy policy / Datenschutz
    privacy_present, privacy_source, privacy_path = detect_section(
        sitemap_urls=all_urls,
        soup=soup_for_sections,
        homepage_url=homepage_url,
        domain=domain,
        sitemap_keywords=PRIVACY_SITEMAP_KEYWORDS,
        link_text_keywords=PRIVACY_LINK_TEXT_KEYWORDS,
        href_keywords=PRIVACY_HREF_KEYWORDS,
        fallback_paths=PRIVACY_FALLBACK_PATHS,
        safe_get_fn=robots_safe_get,
    )
    result["privacy_policy_present"] = privacy_present
    result["privacy_policy_source"] = privacy_source
    result["privacy_policy_path"] = privacy_path or ""

    # Terms & conditions / AGB
    terms_present, terms_source, terms_path = detect_section(
        sitemap_urls=all_urls,
        soup=soup_for_sections,
        homepage_url=homepage_url,
        domain=domain,
        sitemap_keywords=TERMS_SITEMAP_KEYWORDS,
        link_text_keywords=TERMS_LINK_TEXT_KEYWORDS,
        href_keywords=TERMS_HREF_KEYWORDS,
        fallback_paths=TERMS_FALLBACK_PATHS,
        safe_get_fn=robots_safe_get,
    )
    result["terms_present"] = terms_present
    result["terms_source"] = terms_source
    result["terms_path"] = terms_path or ""

    # --- HTML-based checks on homepage ---
    if base_resp and "text/html" in base_resp.headers.get("Content-Type", ""):
        log_verbose(domain, "Running HTML-based homepage checks")
        html_checks = parse_homepage_html(
            base_resp.text, base_resp.url, robots_safe_get
        )
        result.update(
            {
                # Responsive design
                "responsive_design": html_checks["responsive_design"],
                "responsive_signals": html_checks["responsive_signals"],
                # Language / localization
                "html_lang": html_checks["html_lang"],
                "meta_lang": html_checks["meta_lang"],
                "primary_language": html_checks["primary_language"],
                "hreflang_languages": html_checks["hreflang_languages"],
                "hreflang_default_language": html_checks["hreflang_default_language"],
                "languages_detected": html_checks["languages_detected"],
                "localization_status": html_checks["localization_status"],
                "switcher_languages": html_checks["switcher_languages"],
                "url_languages": html_checks["url_languages"],
                # Structured data & content
                "structured_data_jsonld": html_checks["structured_data_jsonld"],
                "social_profiles": html_checks["social_profiles"],
                # Accessibility
                "accessibility_alt_text_pct": html_checks["accessibility_alt_text_pct"],
                "accessibility_content_images": html_checks["accessibility_content_images"],
                "accessibility_content_images_with_alt": html_checks["accessibility_content_images_with_alt"],
                "accessibility_logo_has_alt": html_checks["accessibility_logo_has_alt"],
                "accessibility_heading_h1_count": html_checks["accessibility_heading_h1_count"],
                "accessibility_heading_has_h2": html_checks["accessibility_heading_has_h2"],
                "accessibility_heading_structure_suspect": html_checks["accessibility_heading_structure_suspect"],
                "accessibility_aria_present": html_checks["accessibility_aria_present"],
                "accessibility_clickable_div_count": html_checks["accessibility_clickable_div_count"],
                "accessibility_clickable_div_suspect": html_checks["accessibility_clickable_div_suspect"],
                # Tooling
                "analytics_tools": html_checks["analytics_tools"],
                "cookie_tools": html_checks["cookie_tools"],
                "cookie_tools_suspected": html_checks["cookie_tools_suspected"],
                "cookie_banner_html_present": html_checks["cookie_banner_html_present"],
                "cookie_banner_has_accept": html_checks["cookie_banner_has_accept"],
                "cookie_banner_has_reject": html_checks["cookie_banner_has_reject"],
                "cookie_banner_has_settings": html_checks["cookie_banner_has_settings"],
                "cookie_banner_has_only_ok": html_checks["cookie_banner_has_only_ok"],
                "cookie_info_in_footer": html_checks["cookie_info_in_footer"],
                "tag_manager_present": html_checks["tag_manager_present"],
                "tag_managers": html_checks["tag_managers"],
                # Contact info
                "public_email": html_checks["public_email"],
                "public_phone": html_checks["public_phone"],
                "address_present": html_checks["address_present"],
                # Content
                "homepage_visible_word_count": html_checks["homepage_visible_word_count"],
            }
        )

        cookie_choice_signals = []
        html_choice_signal = bool(html_checks["cookie_choice_html_signal"])
        vendor_signal = bool((result.get("cookie_tools") or "").strip())
        gtm_signal = bool((result.get("cookie_tools_suspected") or "").strip())

        if html_choice_signal:
            cookie_choice_signals.append("html_ui")
        if vendor_signal:
            cookie_choice_signals.append("cmp_vendor")
        if gtm_signal:
            cookie_choice_signals.append("gtm_heuristic")

        result["cookie_choice_status"] = ", ".join(cookie_choice_signals) if cookie_choice_signals else "none"

    # --- Performance / Lighthouse (PageSpeed) ---
    if base_url and result["website_reachable"]:
        log_verbose(domain, "Collecting PageSpeed metrics")
        desktop_score = fetch_pagespeed(base_url, strategy="desktop")
        mobile_score = fetch_pagespeed(base_url, strategy="mobile")

        result["pagespeed_desktopperformance_score"] = desktop_score
        result["pagespeed_mobileperformance_score"] = mobile_score

    # --- Tech stack (CMS / server) ---
    log_verbose(domain, "Detecting CMS and server stack")
    tech = detect_cms_and_server(domain)
    result["cms_name"] = tech["cms_name"]
    result["cms_version"] = tech["cms_version"]
    result["cms_version_up_to_date"] = tech["cms_version_up_to_date"]

    # Prefer WhatCMS social media discovery when the API succeeds;
    # fall back to the on-page parser only when the API call fails.
    if tech.get("whatcms_status") == "success":
        social_profiles = tech.get("whatcms_social_profiles") or []
        result["social_profiles"] = ", ".join(social_profiles)

    # --- Security headers ---
    log_verbose(domain, "Evaluating security headers")
    sec_headers = check_security_headers(base_resp)
    result.update(sec_headers)

    # --- SPF / DMARC ---
    log_verbose(domain, "Checking SPF and DMARC records")
    spf_present, spf_record = check_spf(domain)
    result["spf_present"] = spf_present
    result["spf_record"] = spf_record

    result["dmarc_policy"] = check_dmarc(domain)
    
    # --- TLS check (port 443) ---
    # Only bother if the site is reachable at all – otherwise it will just timeout again.
    if reachable:
        log_verbose(domain, "Performing TLS checks")
        tls = check_tls(domain)
        result["tls_handshake_ok"] = tls["tls_handshake_ok"]
        result["tls_protocol"] = tls["tls_protocol"]
        result["tls_cert_expiry"] = tls["tls_cert_expiry"]
        result["tls_issue_category"] = tls["tls_issue_category"]

    # --- Well-known files ---
    log_verbose(domain, "Inspecting well-known files")
    result["security_txt_present"] = check_security_txt(domain, safe_get_fn=robots_safe_get)
    result["llms_txt_present"] = check_llms_txt(domain, safe_get_fn=robots_safe_get)

    log_verbose(domain, "Finished checks")

    return result


def run_checks_with_retry(domain: str) -> Dict[str, object]:
    """Wrap run_checks_for_domain with simple retry logic for transient failures."""
    attempt = 1
    while True:
        try:
            return run_checks_for_domain(domain)
        except Exception:
            if attempt >= RETRY_ATTEMPTS:
                raise

            logging.warning(
                "Retrying domain %s after failure (attempt %s/%s)",
                domain,
                attempt,
                RETRY_ATTEMPTS,
                exc_info=True,
            )
            time.sleep(RETRY_DELAY_SECONDS)
            attempt += 1

# ---------------------------------------------------------------------------
# CSV domain loading
# ---------------------------------------------------------------------------

def load_domains_from_csv(csv_path: str) -> List[str]:
    """
    Read domains from the given CSV file.

    Expects a header 'website' and uses ';' as delimiter, e.g.:

        name;address;industry;website

    Normalizes entries to a domain name (netloc) and deduplicates.
    """
    domains: List[str] = []
    seen: set[str] = set()

    # encoding is latin-1 to tolerate typical Swiss SME exports from Excel
    with open(csv_path, newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            website = (row.get("website") or "").strip()
            if not website:
                continue

            # Ensure we have a scheme so urlparse works properly
            if not website.startswith(("http://", "https://")):
                website = "http://" + website

            parsed = urlparse(website)
            domain = parsed.netloc.strip()

            if not domain or domain in seen:
                continue

            seen.add(domain)
            domains.append(domain)

    return domains


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    domains = load_domains_from_csv(INPUT_CSV)
    if DOMAIN_OFFSET > 0:
        domains = domains[DOMAIN_OFFSET:]

    if DOMAINS_PER_RUN is not None:
        domains = domains[:DOMAINS_PER_RUN]

    if DOMAIN_OFFSET > 0 or DOMAINS_PER_RUN is not None:
        logging.info(
            "Domain window applied (offset=%s, limit=%s). Remaining: %s",
            DOMAIN_OFFSET,
            DOMAINS_PER_RUN if DOMAINS_PER_RUN is not None else "none",
            len(domains),
        )

    if not domains:
        print(f"No domains found in {INPUT_CSV}")
        return

    total_domains = len(domains)
    if SHOW_PROGRESS:
        update_progress(0, total_domains)

    fieldnames = [
        "domain",
        # Availability & Technical Foundation
        "website_reachable",
        "website_reachability_status",
        "https_enforced",
        "hsts_header",
        "dnssec_status",
        "cdn_waf",
        # SEO, Structure & Content
        "robots_txt_present",
        "sitemap_present",
        "sitemap_url_count",
        "sitemap_page_count",
        "sitemap_locations",
        "sitemap_sources",
        "sitemap_lastmod_any",
        "sitemap_lastmod_urls_with_date",
        "sitemap_lastmod_most_recent",
        "pages_last_12m",
        "pages_last_6m",
        "pages_last_3m",
        "pages_last_1m",
        "structured_data_jsonld",
        "blog_or_news_present",
        "blog_or_news_source",
        "blog_or_news_path",
        "social_profiles",
        "careers_page_present",
        "careers_page_source",
        "careers_page_path",
        "homepage_visible_word_count",
        # Contact info
        "public_email",
        "public_phone",
        "address_present",
        # Language / Localization
        "html_lang",
        "meta_lang",
        "primary_language",
        "hreflang_languages",
        "hreflang_default_language",
        "languages_detected",
        "localization_status",
        "switcher_languages",
        "url_languages",
        # Performance & Experience
        "pagespeed_desktopperformance_score",
        "pagespeed_mobileperformance_score",
        "responsive_design",
        "responsive_signals",
        # Accessibility
        "accessibility_alt_text_pct",
        "accessibility_content_images",
        "accessibility_content_images_with_alt",
        "accessibility_logo_has_alt",
        "accessibility_heading_h1_count",
        "accessibility_heading_has_h2",
        "accessibility_heading_structure_suspect",
        "accessibility_aria_present",
        "accessibility_clickable_div_count",
        "accessibility_clickable_div_suspect",
        # Technology Stack
        "cms_name",
        "cms_version",
        "cms_version_up_to_date",
        "analytics_tools",
        "tag_manager_present",
        "tag_managers",
        # Security Posture
        "security_hsts",
        "security_x_frame_options",
        "security_x_content_type_options",
        "security_referrer_policy",
        "security_csp",
        "security_permissions_policy",
        "spf_present",
        "spf_record",
        "dmarc_policy",
        "tls_handshake_ok",
        "tls_protocol",
        "tls_cert_expiry",
        "tls_issue_category",
        # Compliance & Trust
        "cookie_tools",
        "cookie_tools_suspected",
        "cookie_banner_html_present",
        "cookie_banner_has_accept",
        "cookie_banner_has_reject",
        "cookie_banner_has_settings",
        "cookie_banner_has_only_ok",
        "cookie_info_in_footer",
        "cookie_choice_status",
        "imprint_present",
        "imprint_source",
        "imprint_path",
        "privacy_policy_present",
        "privacy_policy_source",
        "privacy_policy_path",
        "terms_present",
        "terms_source",
        "terms_path",
        # Well-known files
        "security_txt_present",
        "llms_txt_present",
    ]

    # Collect results keyed by domain so we can preserve the input order later
    results = {}
    failed_domains = set()
    completed = 0
    next_checkpoint_index = 0

    # Prepare partial output for periodic checkpointing
    os.makedirs(os.path.dirname(PARTIAL_OUTPUT_CSV) or ".", exist_ok=True)
    with open(PARTIAL_OUTPUT_CSV, "w", newline="", encoding="utf-8") as partial_file:
        writer = csv.DictWriter(partial_file, fieldnames=fieldnames)
        writer.writeheader()

        def flush_ready_rows() -> None:
            nonlocal next_checkpoint_index
            while next_checkpoint_index < total_domains:
                domain = domains[next_checkpoint_index]
                if domain in results:
                    writer.writerow(results.pop(domain))
                    next_checkpoint_index += 1
                elif domain in failed_domains:
                    next_checkpoint_index += 1
                else:
                    break
            partial_file.flush()

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
            future_to_domain = {
                executor.submit(run_checks_with_retry, domain): domain
                for domain in domains
            }

            for future in as_completed(future_to_domain):
                domain = future_to_domain[future]

                try:
                    result = future.result()
                except Exception as e:
                    logging.exception("Domain %s failed irrecoverably", domain)
                    with print_lock:
                        print(f"[ERROR] {domain}: {e}")

                    failed_domains.add(domain)
                    completed += 1
                    update_progress(completed, total_domains)
                    flush_ready_rows()
                    continue

                results[domain] = result
                with print_lock:
                    print(f"[DONE] {domain}")

                completed += 1
                update_progress(completed, total_domains)

                if completed % CHECKPOINT_INTERVAL == 0:
                    flush_ready_rows()

            # Final flush of any remaining ready rows
            flush_ready_rows()

    if SHOW_PROGRESS:
        print()

    # Crash-safe finalization: rename partial file to final output
    try:
        os.replace(PARTIAL_OUTPUT_CSV, OUTPUT_CSV)
    except Exception:
        logging.exception("Failed to finalize output file rename")
        raise

    if failed_domains:
        logging.info("Run completed with %d failed domains", len(failed_domains))
        print("Failed domains:", ", ".join(sorted(failed_domains)))

    print(f"Results written to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
