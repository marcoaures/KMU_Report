"""End-to-end: scan local fake sites through main.main() and read the CSV back."""
import csv

import main
from config import config as cfg
from fake_site import FakeSite

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'

HOME = """<!doctype html><html lang="de"><head><title>Muster AG</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="WordPress 6.4.2">
<link rel="stylesheet" href="/style.css">
<script type="application/ld+json">{"@type":"LocalBusiness","name":"Muster AG"}</script>
</head><body>
<nav role="navigation"><a href="/impressum">Impressum</a> <a href="/datenschutz">Datenschutz</a>
<a href="/karriere">Jobs</a> <a href="/kontakt">Kontakt</a>
<a href="https://www.facebook.com/musterag">Facebook</a>
<a href="https://www.wix.com/">Erstellt mit Wix</a></nav>
<h1>Willkommen</h1><h2>Angebot</h2><img src="/team.jpg" alt="Unser Team"><img src="/deko.png" alt="">
<div id="cookie-banner"><p>Wir verwenden Cookies.</p><button>Akzeptieren</button><button>Ablehnen</button></div>
<footer>© 2025 Muster AG</footer></body></html>"""

KONTAKT = """<html lang="de"><body><h1>Kontakt</h1>
<a href="mailto:info@muster.example">Mail</a> <a href="tel:+41441234567">044 123 45 67</a>
<address>Muster AG, Bahnhofstrasse 1, 8000 Zürich</address></body></html>"""


def site_pages(base):
    return {
        "/": (200, HOME, {"X-Frame-Options": "DENY"}),
        "/style.css": "@media (min-width: 768px){body{margin:0}}",
        "/kontakt": KONTAKT,
        "/robots.txt": f"User-agent: *\nDisallow: /intern/\nSitemap: {base}/sitemap.xml\n",
        "/sitemap.xml": f"<urlset {NS}><url><loc>{base}/</loc><lastmod>2026-11-01</lastmod></url>"
                        f"<url><loc>{base}/impressum</loc></url><url><loc>{base}/agb</loc></url></urlset>",
        "/.well-known/security.txt": "Contact: mailto:security@muster.example\n",
    }


def configure(tmp_path, lines):
    inp = tmp_path / "input.csv"
    inp.write_text("name;address;industry;website\n" + "\n".join(lines) + "\n", encoding="utf-8")
    cfg.INPUT_CSV = str(inp)
    cfg.OUTPUT_CSV = str(tmp_path / "out" / "output.csv")
    cfg.LOG_FILE = str(tmp_path / "run.log")
    cfg.OPT_OUT_FILE = str(tmp_path / "opt_out.txt")
    cfg.RESUME = True
    cfg.DOMAINS_PER_RUN = None
    cfg.DOMAIN_OFFSET = 0
    cfg.SHOW_PROGRESS = False


def read_rows():
    with open(cfg.OUTPUT_CSV, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=cfg.OUTPUT_DELIMITER))


def test_full_scan_resume_and_special_rows(tmp_path):
    with FakeSite({}) as site, FakeSite({"/": (403, "go away")}) as blocked:
        site.pages.update(site_pages(site.base))
        configure(tmp_path, [
            f"Muster AG;Zürich;Töpferei;http://{site.domain}/",
            f"Dublette;Zürich;x;{site.domain}",
            "Nur Facebook;Bern;x;https://www.facebook.com/nurfacebook",
            f"Gesperrt;Bern;x;{blocked.domain}",
            "Tot;Bern;x;127.0.0.1:9",
            "Leer;Bern;x;",
        ])
        main.main()
        rows = read_rows()
        assert [r["scan_status"] for r in rows] == ["ok", "skipped_platform", "blocked", "unreachable"]

        r = rows[0]
        assert r["domain"] == site.domain and r["input_website"] == f"http://{site.domain}/"
        assert r["website_reachable"] == "True" and r["https_enforced"] == "False"
        assert r["robots_txt_present"] == "True"
        assert (r["sitemap_present"], r["sitemap_count"], r["sitemap_page_count"]) == ("True", "1", "3")
        assert r["sitemap_sources"] == "/sitemap.xml (robots.txt)"
        assert r["sitemap_lastmod_urls_with_date"] == "1"
        assert r["responsive_design"] == "yes" and "external_media" in r["responsive_signals"]
        assert (r["cms_name"], r["cms_version"], r["cms_source"]) == ("WordPress", "6.4.2", "local")
        assert r["social_profiles"] == "Facebook"
        assert (r["imprint_present"], r["imprint_source"]) == ("True", "sitemap")
        assert (r["privacy_policy_present"], r["privacy_policy_source"]) == ("True", "homepage_link")
        assert (r["terms_present"], r["terms_source"]) == ("True", "sitemap")
        assert (r["careers_page_present"], r["careers_page_path"]) == ("True", "/karriere")
        assert r["blog_or_news_present"] == "False"
        assert (r["public_email"], r["public_phone"]) == ("clickable", "clickable")
        assert (r["address_present"], r["address_source"]) == ("True", "address_tag")
        assert (r["cookie_banner_has_accept"], r["cookie_banner_has_reject"]) == ("True", "True")
        assert r["cookie_choice_status"] == "html_ui"
        assert r["accessibility_images_missing_alt"] == "0" and r["accessibility_aria_present"] == "True"
        assert r["security_x_frame_options"] == "True" and r["security_csp"] == "False"
        assert r["security_txt_present"] == "True" and r["llms_txt_present"] == "False"
        assert r["pagespeed_status"] == "skipped" and r["pagespeed_mobile_performance_score"] == ""
        assert r["primary_language"] == "de" and r["structured_data_jsonld"] == "True"
        assert int(r["requests_made"]) <= cfg.MAX_REQUESTS_PER_DOMAIN
        # robots.txt is honoured and nothing below /intern/ was requested
        assert not any(hit.startswith("/intern") for hit in site.hits)

        # not measured stays empty instead of "False"
        blocked_row, dead_row = rows[2], rows[3]
        assert blocked_row["website_reachability_status"] == "blocked_http_403"
        assert blocked_row["imprint_present"] == "" and blocked_row["security_csp"] == ""
        assert blocked.hits.count("/") == 1  # no second try after the 403
        assert dead_row["website_reachable"] == "False" and dead_row["sitemap_present"] == ""
        assert rows[1]["requests_made"] == "0"

        # second run: nothing is scanned twice
        hits_before = len(site.hits)
        main.main()
        assert len(site.hits) == hits_before
        assert len(read_rows()) == 4


def test_error_rows_are_rescanned_and_opt_outs_skipped(tmp_path, monkeypatch):
    with FakeSite({"/": "<html><body>hi</body></html>"}) as a:
        configure(tmp_path, [f"A;x;x;{a.domain}", "B;x;x;https://www.optout.ch/"])
        (tmp_path / "opt_out.txt").write_text("# asked on 1.1.\noptout.ch\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("kaputt")
        monkeypatch.setattr(main, "collect_sitemaps", boom)
        main.main()
        rows = read_rows()
        assert len(rows) == 1                             # the opted-out domain has no row
        assert rows[0]["scan_status"] == "error" and rows[0]["scan_note"] == "RuntimeError"
        assert rows[0]["website_reachable"] == "True"     # what was measured is kept

        monkeypatch.undo()
        cfg.REQUEST_DELAY_SECONDS = 0
        main.main()
        rows = read_rows()
        assert len(rows) == 1 and rows[0]["scan_status"] == "ok"


def test_input_variants(tmp_path):
    f = tmp_path / "in.csv"
    f.write_bytes("Name,Website\nMüller,https://www.Beispiel.ch/kontakt\nB,beispiel.ch\nC,müller.ch\n"
                  .encode("cp1252"))
    entries = main.load_domains_from_csv(str(f))
    assert [e["domain"] for e in entries] == ["www.beispiel.ch", "xn--mller-kva.ch"]
    assert entries[0]["has_path"] is True

    f.write_bytes("﻿website;name\nbeispiel.ch;A\n".encode("utf-8"))
    assert main.load_domains_from_csv(str(f))[0]["domain"] == "beispiel.ch"


def test_missing_website_column_is_a_clear_error(tmp_path):
    f = tmp_path / "in.csv"
    f.write_text("name;adresse\nA;B\n", encoding="utf-8")
    try:
        main.load_domains_from_csv(str(f))
    except SystemExit as exc:
        assert "no website column" in str(exc) and "adresse" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_platform_detection():
    assert main.is_platform("www.facebook.com") and main.is_platform("firma.wixsite.com")
    assert not main.is_platform("firma.ch") and not main.is_platform("notfacebook.com.firma.ch")
