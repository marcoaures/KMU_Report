"""KMU Webcheck: scan a list of websites and write one CSV row per domain."""
from __future__ import annotations

import csv
import datetime
import logging
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from analysis.cms_detect import detect_cms
from analysis.html_analysis import parse_homepage_html
from analysis.sections import (FallbackProber, detect_careers_section, detect_section,
                               probe_section)
from analysis.sitemap_utils import check_robots, collect_sitemaps, count_pages_by_recency
from config import config as cfg
from config import dictionary_config as words
from dns_tools.dns_security import check_dmarc, check_dnssec, check_mx, check_spf
from http_tools.cdn_utils import detect_cdn_waf
from http_tools.client import DomainClient, brake, registrable_domain
from http_tools.http_utils import check_https_enforced, check_website_reachable, is_html, parse_hsts
from http_tools.security_http import check_llms_txt, check_security_headers, check_security_txt
from http_tools.tls_utils import check_tls
from integrations.api_clients import detect_cms_whatcms, fetch_pagespeed

# Every column of the output, in order. A value stays empty when the check
# did not run or could not tell - empty never means "no".
FIELDNAMES = [
    # Bookkeeping
    "domain", "input_website", "input_has_path", "scan_timestamp", "tool_version",
    "scan_status", "scan_note", "requests_made",
    # Availability & technical foundation
    "website_reachable", "website_reachability_status", "final_domain",
    "redirects_to_other_domain", "placeholder_page", "https_enforced",
    "hsts_header", "hsts_max_age", "hsts_include_subdomains", "dnssec_status", "cdn_waf",
    # SEO, structure & content
    "robots_txt_present", "sitemap_present", "sitemap_count", "sitemap_page_count",
    "sitemap_truncated", "sitemap_locations", "sitemap_sources",
    "pages_last_12m", "pages_last_6m", "pages_last_3m", "pages_last_1m",
    "sitemap_lastmod_any", "sitemap_lastmod_urls_with_date", "sitemap_lastmod_most_recent",
    "homepage_visible_word_count", "structured_data_jsonld",
    "blog_or_news_present", "blog_or_news_source", "blog_or_news_path",
    "careers_page_present", "careers_page_source", "careers_page_path",
    "social_profiles",
    # Contact
    "public_email", "public_phone", "address_present", "address_source",
    # Language / localization
    "html_lang", "meta_lang", "primary_language", "hreflang_languages",
    "hreflang_default_language", "languages_detected", "localization_status",
    "switcher_languages", "url_languages",
    # Performance & experience
    "pagespeed_desktop_performance_score", "pagespeed_mobile_performance_score",
    "pagespeed_status", "third_parties_without_consent",
    "responsive_design", "responsive_signals",
    # Accessibility (homepage only)
    "accessibility_images_total", "accessibility_images_missing_alt",
    "accessibility_alt_attr_pct", "accessibility_alt_text_pct",
    "accessibility_linked_images_without_alt",
    "accessibility_content_images", "accessibility_content_images_with_alt",
    "accessibility_logo_has_alt", "accessibility_heading_h1_count",
    "accessibility_heading_has_h2", "accessibility_heading_structure_suspect",
    "accessibility_aria_present", "accessibility_aria_count",
    "accessibility_clickable_div_count", "accessibility_clickable_div_suspect",
    # Technology
    "cms_name", "cms_version", "cms_source", "whatcms_status",
    "analytics_tools", "tag_manager_present", "tag_managers",
    # Security
    "security_x_frame_options", "security_x_content_type_options",
    "security_referrer_policy", "security_csp", "security_permissions_policy",
    "mail_mx_present", "spf_present", "spf_record", "dmarc_present", "dmarc_policy",
    "tls_handshake_ok", "tls_protocol", "tls_cert_expiry", "tls_issue_category",
    # Compliance & trust
    "cookie_tools", "cookie_tools_suspected", "cookie_banner_html_present",
    "cookie_banner_has_accept", "cookie_banner_has_reject", "cookie_banner_has_settings",
    "cookie_banner_has_only_ok", "cookie_info_in_footer", "cookie_choice_status",
    "imprint_present", "imprint_source", "imprint_path",
    "privacy_policy_present", "privacy_policy_source", "privacy_policy_path",
    "terms_present", "terms_source", "terms_path",
    "security_txt_present", "llms_txt_present",
]

WEBSITE_HEADERS = ("website", "url", "domain", "webseite", "web", "homepage")
print_lock = threading.Lock()
log = logging.getLogger("kmu")


# ---------------------------------------------------------------------------
# Scanning one domain
# ---------------------------------------------------------------------------

def _verbose(domain: str, phase: str) -> None:
    if cfg.SHOW_VERBOSE_PROGRESS:
        with print_lock:
            print(f"  {domain}: {phase}")


def new_result(entry: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {name: None for name in FIELDNAMES}
    result.update(
        domain=entry["domain"],
        input_website=entry["website"],
        input_has_path=entry["has_path"],
        scan_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        tool_version=cfg.VERSION,
        tls_issue_category="not_checked",
    )
    return result


def _dns_checks(domain: str, result: Dict[str, Any]) -> None:
    """Passive checks: they ask DNS servers, not the website."""
    result["dnssec_status"] = check_dnssec(domain)
    result["mail_mx_present"] = check_mx(domain)
    result["spf_present"], result["spf_record"] = check_spf(domain)
    result["dmarc_present"], result["dmarc_policy"] = check_dmarc(domain)


def _sitemap_fields(sm: Dict[str, Any], result: Dict[str, Any]) -> None:
    sitemaps = sm["sitemaps"]
    result["sitemap_present"] = bool(sitemaps)
    result["sitemap_count"] = len(sitemaps)
    result["sitemap_page_count"] = len(sm["urls"])
    result["sitemap_truncated"] = sm["truncated"]
    result["sitemap_locations"] = ", ".join(urlparse(u).path or "/" for u in sitemaps)
    result["sitemap_sources"] = "; ".join(
        f"{urlparse(u).path or '/'} ({sm['sources'].get(u, '')})" for u in sitemaps
    )
    counts = count_pages_by_recency(sm["lastmods"])
    for key in ("12m", "6m", "3m", "1m"):
        result[f"pages_last_{key}"] = counts[key]
    dates = [dt for dt in sm["lastmods"].values() if dt is not None]
    result["sitemap_lastmod_any"] = bool(dates)
    result["sitemap_lastmod_urls_with_date"] = len(dates)
    if dates:
        result["sitemap_lastmod_most_recent"] = max(dates).astimezone(
            datetime.timezone.utc).isoformat()


# section -> (output column prefix, dictionary prefix)
SECTIONS = {
    "imprint": ("imprint", "IMPRINT"),
    "privacy": ("privacy_policy", "PRIVACY"),
    "terms": ("terms", "TERMS"),
    "careers": ("careers_page", "CAREER"),
    "blog": ("blog_or_news", "BLOG"),
}


def _section_fields(result, sm_urls, soup, homepage_url, prober, lang) -> None:
    """Sitemap and homepage links first. Only for what is still missing a few
    paths are guessed, one round per section so that every section gets a try
    before the miss limit is reached."""
    found: Dict[str, Tuple] = {}
    for section, (_, prefix) in SECTIONS.items():
        if section == "careers":
            found[section] = detect_careers_section(sm_urls, soup, homepage_url)
        else:
            found[section] = detect_section(
                section, sm_urls, soup, homepage_url,
                getattr(words, f"{prefix}_SITEMAP_KEYWORDS"),
                getattr(words, f"{prefix}_LINK_TEXT_KEYWORDS"),
                getattr(words, f"{prefix}_HREF_KEYWORDS"),
                getattr(words, f"{prefix}_FALLBACK_PATHS"),
            )

    for rank in range(cfg.MAX_FALLBACK_PATHS_PER_SECTION):
        for section, (_, prefix) in SECTIONS.items():
            if not found[section][0]:
                found[section] = probe_section(
                    section, getattr(words, f"{prefix}_FALLBACK_PATHS"), prober, lang, rank
                )

    for section, (column, _) in SECTIONS.items():
        present, source, path = found[section]
        result[f"{column}_present"] = present
        result[f"{column}_source"] = source
        result[f"{column}_path"] = path or ""


def run_checks_for_domain(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Run all checks for one domain. Never raises: problems end up in the row."""
    domain = entry["domain"]
    result = new_result(entry)
    client = DomainClient(domain)
    try:
        _scan(domain, client, result)
    except Exception as exc:  # keep whatever was measured so far
        log.exception("Scan of %s failed", domain)
        result["scan_status"] = "error"
        result["scan_note"] = exc.__class__.__name__
    finally:
        result["requests_made"] = client.requests_made
        client.close()
    return result


def _scan(domain: str, client: DomainClient, result: Dict[str, Any]) -> None:
    _verbose(domain, "DNS")
    _dns_checks(domain, result)

    _verbose(domain, "robots.txt")
    robots_present, robots_txt = check_robots(domain, client)
    result["robots_txt_present"] = robots_present
    client.set_robots(robots_txt)

    if not client.allowed(f"https://{domain}/"):
        # We may not crawl, but a TLS handshake is not crawling.
        result.update(check_tls(domain))
        result.update(scan_status="disallowed_by_robots",
                      website_reachability_status="disallowed_by_robots")
        return

    _verbose(domain, "reachability")
    reach = check_website_reachable(domain, client)
    resp = reach["response"]
    result["website_reachable"] = reach["reachable"]
    result["website_reachability_status"] = reach["status"]
    result["final_domain"] = reach["final_domain"]
    result["redirects_to_other_domain"] = reach["other_domain"]

    # TLS only makes sense if the name resolves and something answered at all.
    if reach["final_domain"] or reach["status"] in ("tls_error", "timeout"):
        result.update(check_tls(domain.split(":")[0]))
    result["cdn_waf"] = detect_cdn_waf(domain, resp, reach["final_domain"])

    if not reach["reachable"]:
        status = reach["status"]
        result["scan_status"] = ("blocked" if status.startswith(("blocked", "overloaded"))
                                 else "http_error" if status.startswith("http_")
                                 else "unreachable")
        return

    base_url = reach["base_url"]
    if reach["other_domain"]:
        # The site lives somewhere else now: its own robots.txt applies there.
        final_host = urlparse(base_url).netloc
        client.add_site(final_host)
        _, robots_txt = check_robots(final_host, client)
        client.set_robots(robots_txt)
        if not client.allowed(base_url + "/"):
            result["scan_status"] = "disallowed_by_robots"
            return

    _verbose(domain, "headers")
    result["https_enforced"] = check_https_enforced(domain, client, base_url)
    result.update(parse_hsts(resp))
    result.update(check_security_headers(resp))

    soup: Optional[BeautifulSoup] = None
    page_lang = None
    if is_html(resp):
        _verbose(domain, "homepage")
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        checks = parse_homepage_html(soup, resp.url, client)
        html_choice = checks.pop("cookie_choice_html_signal")
        result.update({k: v for k, v in checks.items() if k in result})
        page_lang = result["primary_language"]

        signals = []
        if html_choice:
            signals.append("html_ui")
        if result["cookie_tools"]:
            signals.append("cmp_vendor")
        if result["cookie_tools_suspected"]:
            signals.append("gtm_heuristic")
        result["cookie_choice_status"] = ", ".join(signals) or "none"

        cms = detect_cms(soup, html, resp.headers)
        result["cms_name"] = cms["cms_name"]
        result["cms_version"] = cms["cms_version"]
        result["cms_source"] = "local" if cms["cms_name"] else ""

    _verbose(domain, "sitemaps")
    sm = collect_sitemaps(base_url, robots_txt, client)
    _sitemap_fields(sm, result)

    _verbose(domain, "well-known files")
    result["security_txt_present"] = check_security_txt(base_url, client)
    result["llms_txt_present"] = check_llms_txt(base_url, client)

    _verbose(domain, "sections")
    prober = FallbackProber(client, base_url)
    _section_fields(result, sm["urls"], soup, resp.url if soup is not None else None,
                    prober, page_lang)

    # --- External APIs: they do not touch our request budget ---------------
    _verbose(domain, "PageSpeed")
    mobile = fetch_pagespeed(base_url + "/", "mobile", third_parties=cfg.PAGESPEED_THIRD_PARTIES)
    desktop = fetch_pagespeed(base_url + "/", "desktop")
    result["pagespeed_mobile_performance_score"] = mobile["score"]
    result["pagespeed_desktop_performance_score"] = desktop["score"]
    result["pagespeed_status"] = (mobile["status"] if mobile["status"] == desktop["status"]
                                  else f"mobile:{mobile['status']}, desktop:{desktop['status']}")
    if mobile["third_parties"] is not None:
        result["third_parties_without_consent"] = ", ".join(mobile["third_parties"])

    ask_whatcms = cfg.WHATCMS_MODE == "always" or (
        cfg.WHATCMS_MODE == "fallback" and not result["cms_name"]
    )
    tech = detect_cms_whatcms(domain) if ask_whatcms else {"whatcms_status": "skipped"}
    result["whatcms_status"] = tech["whatcms_status"]
    if tech["whatcms_status"] == "success":
        if tech["cms_name"] and (cfg.WHATCMS_MODE == "always" or not result["cms_name"]):
            result.update(cms_name=tech["cms_name"], cms_version=tech["cms_version"],
                          cms_source="whatcms")
        elif result["cms_name"] is None:
            result["cms_name"] = ""
        # what the page links to plus what WhatCMS knows
        merged = set(filter(None, (result["social_profiles"] or "").split(", ")))
        merged.update(tech["whatcms_social_profiles"])
        result["social_profiles"] = ", ".join(sorted(merged))

    if client.stop_reason:
        result.update(scan_status="partial", scan_note=client.stop_reason)
    elif client.requests_made >= cfg.MAX_REQUESTS_PER_DOMAIN:
        result.update(scan_status="partial", scan_note="budget_exhausted")
    else:
        result["scan_status"] = "ok"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def normalize_domain(website: str) -> Tuple[str, bool]:
    """'https://WWW.Example.ch:443/kontakt' -> ('www.example.ch', True).
    Returns ('', False) if there is no usable host."""
    website = (website or "").strip()
    if not website:
        return "", False
    if "://" not in website:
        website = "http://" + website
    try:
        parsed = urlparse(website)
        host = (parsed.hostname or "").strip(".").lower()
        port = parsed.port
    except ValueError:
        return "", False
    if not host or "." not in host and host != "localhost":
        return "", False
    try:
        host = host.encode("idna").decode("ascii")  # müller.ch -> xn--mller-kva.ch
    except UnicodeError:
        return "", False
    if port and port not in (80, 443):
        host = f"{host}:{port}"
    return host, parsed.path not in ("", "/")


def load_domains_from_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Read the input CSV and return one entry per distinct domain.

    Accepts UTF-8 (with or without BOM) and Windows-1252, ";" "," or tab as
    delimiter, and "website", "url", "domain" ... as column name.
    """
    with open(csv_path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")

    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = max(";,\t|", key=first_line.count)
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader, [])]
    column = next((header.index(h) for h in WEBSITE_HEADERS if h in header), None)
    if column is None:
        sys.exit(
            f"{csv_path}: no website column found. Expected one of {', '.join(WEBSITE_HEADERS)} "
            f"but the header is: {', '.join(header) or '(empty)'}"
        )

    entries: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    skipped = 0
    for row in reader:
        website = row[column].strip() if len(row) > column else ""
        domain, has_path = normalize_domain(website)
        if not domain:
            skipped += bool(website)
            continue
        key = domain[4:] if domain.startswith("www.") else domain
        if key in seen:
            continue
        seen.add(key)
        entries.append({"domain": domain, "website": website, "has_path": has_path})
    if skipped:
        log.info("%d input rows had an unusable website value and were skipped", skipped)
    return entries


def load_opt_outs(path: str) -> Set[str]:
    """Domains that asked not to be scanned (registrable domains, lower-case)."""
    if not path or not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        lines = (line.split("#", 1)[0].strip().lower() for line in f)
        return {registrable_domain(normalize_domain(line)[0] or line) for line in lines if line}


def is_platform(domain: str) -> bool:
    host = domain.split(":")[0]
    return registrable_domain(host) in cfg.PLATFORM_DOMAINS or any(
        host == p or host.endswith("." + p) for p in cfg.PLATFORM_DOMAINS
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _cell(value: Any) -> Any:
    return "" if value is None else value


def read_output(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=cfg.OUTPUT_DELIMITER)
        if reader.fieldnames != FIELDNAMES:
            sys.exit(
                f"{path} has different columns than this version writes (older version or "
                "other delimiter?). Move the file away, or set RESUME = False to overwrite it."
            )
        return list(reader)


def write_output(path: str, rows: List[Dict[str, Any]]) -> None:
    """Write all rows at once, atomically."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding=cfg.OUTPUT_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=cfg.OUTPUT_DELIMITER)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in FIELDNAMES})
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(cfg.LOG_FILE, encoding="utf-8")],
    )
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logging.getLogger().addHandler(console)

    requests_logger = logging.getLogger("kmu.requests")
    requests_logger.propagate = False
    if cfg.REQUEST_LOG_FILE:
        handler = logging.FileHandler(cfg.REQUEST_LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s\t%(message)s"))
        requests_logger.addHandler(handler)
        requests_logger.setLevel(logging.INFO)
    else:
        requests_logger.addHandler(logging.NullHandler())


def main() -> None:
    setup_logging()
    entries = load_domains_from_csv(cfg.INPUT_CSV)
    order = {e["domain"]: i for i, e in enumerate(entries)}
    if not entries:
        print(f"No domains found in {cfg.INPUT_CSV}")
        return

    opt_outs = load_opt_outs(cfg.OPT_OUT_FILE)
    todo = entries[cfg.DOMAIN_OFFSET:]
    opted_out = [e for e in todo if registrable_domain(e["domain"].split(":")[0]) in opt_outs]
    todo = [e for e in todo if e not in opted_out]

    # Resume: keep finished rows, scan failed ones again.
    rows: List[Dict[str, Any]] = []
    if cfg.RESUME and os.path.exists(cfg.OUTPUT_CSV):
        existing = read_output(cfg.OUTPUT_CSV)
        rows = [r for r in existing if r.get("scan_status") != "error"]
        done = {r["domain"] for r in rows}
        todo = [e for e in todo if e["domain"] not in done]
    if cfg.DOMAINS_PER_RUN is not None:
        todo = todo[: cfg.DOMAINS_PER_RUN]
    write_output(cfg.OUTPUT_CSV, rows)

    print(f"{len(entries)} domains in {cfg.INPUT_CSV}: {len(rows)} already scanned, "
          f"{len(opted_out)} opted out, {len(todo)} to scan now.")
    if not cfg.CONTACT:
        print("Note: no contact address in the User-Agent (config.CONTACT / KMU_CONTACT).")
    if not todo:
        return

    scan_list = [e for e in todo if not is_platform(e["domain"])]
    if cfg.SHUFFLE_SCAN_ORDER:
        random.Random(cfg.SHUFFLE_SEED).shuffle(scan_list)
    total, completed = len(scan_list), 0
    new_rows: List[Dict[str, Any]] = []

    with open(cfg.OUTPUT_CSV, "a", newline="", encoding="utf-8") as out_file:
        writer = csv.DictWriter(out_file, fieldnames=FIELDNAMES, delimiter=cfg.OUTPUT_DELIMITER)

        def emit(row: Dict[str, Any]) -> None:
            """Every finished row is on disk right away."""
            new_rows.append(row)
            writer.writerow({k: _cell(row.get(k)) for k in FIELDNAMES})
            out_file.flush()

        # Platform links are answered without a single request.
        for entry in todo:
            if is_platform(entry["domain"]):
                row = new_result(entry)
                row.update(scan_status="skipped_platform", requests_made=0)
                emit(row)

        executor = ThreadPoolExecutor(max_workers=cfg.WORKER_COUNT)
        futures = [executor.submit(run_checks_for_domain, e) for e in scan_list]
        handled = set()
        try:
            for future in as_completed(futures):
                handled.add(future)
                row = future.result()
                emit(row)
                completed += 1
                status = row["website_reachability_status"] or ""
                brake.report(status.startswith(("blocked", "overloaded")) or status == "timeout")
                if cfg.SHOW_PROGRESS:
                    with print_lock:
                        print(f"[{completed}/{total}] {row['domain']}: {row['scan_status']} "
                              f"({row['requests_made']} requests)")
        except KeyboardInterrupt:
            print("\nInterrupted: domains in progress are finished, the rest is skipped. "
                  "Run again to continue.")
            executor.shutdown(wait=True, cancel_futures=True)
            for future in futures:
                if future not in handled and future.done() and not future.cancelled():
                    emit(future.result())
        finally:
            executor.shutdown(wait=True)

    # Final pass: same rows, back in input order.
    rows.extend(new_rows)
    rows.sort(key=lambda r: order.get(r["domain"], -1))
    write_output(cfg.OUTPUT_CSV, rows)

    summary: Dict[str, int] = {}
    for row in new_rows:
        summary[row["scan_status"]] = summary.get(row["scan_status"], 0) + 1
    summary_text = ", ".join(f"{k}: {v}" for k, v in sorted(summary.items()))
    log.info("Run finished. New rows: %s. Total rows: %d", summary_text, len(rows))
    print(f"This run: {summary_text or 'nothing new'}")
    print(f"Results written to {cfg.OUTPUT_CSV} ({len(rows)} rows).")


if __name__ == "__main__":
    main()
