"""Regression tests for the homepage heuristics. Each test pins down a case
that used to be measured wrongly."""
from bs4 import BeautifulSoup

from analysis import html_analysis as h
from analysis.address import detect_address, text_has_address
from analysis.cms_detect import detect_cms
from analysis.language_localization import detect_languages_and_localization


def soup(html):
    return BeautifulSoup(html, "html.parser")


def page(body="", head="", lang="de"):
    return soup(f'<html lang="{lang}"><head>{head}</head><body>{body}</body></html>')


# --- ARIA ------------------------------------------------------------------
def test_aria_is_found():
    assert h.count_aria(soup('<div aria-label="Menu">x</div><nav role="navigation"></nav>')) == 2
    assert h.count_aria(soup('<div class="aria-label">x</div>')) == 0


# --- headings --------------------------------------------------------------
def test_heading_jump_down_is_suspect_but_going_up_is_fine():
    ok = h.analyse_headings(soup("<h1>a</h1><h2>b</h2><h3>c</h3><h4>d</h4><h2>e</h2>"))
    assert ok["accessibility_heading_structure_suspect"] is False
    bad = h.analyse_headings(soup("<h1>a</h1><h2>b</h2><h4>c</h4>"))
    assert bad["accessibility_heading_structure_suspect"] is True
    assert h.analyse_headings(soup("<h3>a</h3>"))["accessibility_heading_structure_suspect"] is True


# --- images ----------------------------------------------------------------
def test_empty_alt_is_not_missing_alt():
    r = h.analyse_images(soup(
        '<img src="a.jpg" alt="Team"><img src="deko.png" alt=""><img src="b.jpg">'
        '<a href="/x"><img src="c.jpg" alt=""></a>'
    ))
    assert r["accessibility_images_total"] == 4
    assert r["accessibility_images_missing_alt"] == 1
    assert r["accessibility_alt_attr_pct"] == 75.0
    assert r["accessibility_linked_images_without_alt"] == 1
    assert r["accessibility_logo_has_alt"] is None  # no logo on the page


def test_logo_alt():
    assert h.analyse_images(soup('<img class="logo" src="l.svg" alt="Muster AG">'))[
        "accessibility_logo_has_alt"] is True
    assert h.analyse_images(soup('<img class="logo" src="l.svg">'))[
        "accessibility_logo_has_alt"] is False


# --- responsive ------------------------------------------------------------
VIEWPORT = '<meta name="viewport" content="width=device-width">'


def test_mobile_first_css_counts_as_responsive():
    for rule in ("@media (min-width: 768px){a{b:c}}", "@media (width >= 600px){a{b:c}}",
                 "@media screen and (max-width:600px){a{b:c}}",
                 "@container card (min-width: 400px){a{b:c}}"):
        r = h.analyse_responsive(page(head=VIEWPORT + f"<style>{rule}</style>"), "https://a.ch/", None)
        assert r["responsive_design"] == "yes", rule


def test_responsive_levels():
    assert h.analyse_responsive(page(head=VIEWPORT), "https://a.ch/", None)["responsive_design"] == "likely"
    assert h.analyse_responsive(page(head="<style>@media print{a{b:c}}</style>"),
                                "https://a.ch/", None)["responsive_design"] == "no"


# --- analytics -------------------------------------------------------------
def test_recaptcha_is_not_google_analytics():
    r = h.analyse_scripts(page('<script>grecaptcha.render("g-recaptcha", {});'
                               'var x = document.getElementById("g-recaptcha-response");</script>'),
                          "https://a.ch/")
    assert r["analytics_tools"] == ""


def test_ga4_gtm_and_others_are_found():
    r = h.analyse_scripts(page(
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-AB12CD34EF"></script>'
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('config','G-AB12CD34EF');</script>"
        "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':1});"
        "j.src='https://www.googletagmanager.com/gtm.js?id='+i})(window,document,'script','dataLayer','GTM-ABC123');</script>"
        '<script src="https://stats.firma.ch/matomo.js"></script>'
        '<script src="https://plausible.io/js/script.js"></script>'
    ), "https://a.ch/")
    assert "Google Analytics 4" in r["analytics_tools"]
    assert "Matomo" in r["analytics_tools"] and "Plausible" in r["analytics_tools"]
    assert r["tag_managers"] == "GTM" and r["tag_manager_present"] is True


# --- social ----------------------------------------------------------------
def test_social_profiles_match_hosts_not_substrings():
    f = h.social_network_for_url
    assert f("https://www.wix.com/") is None
    assert f("https://www.dropbox.com/s/abc") is None
    assert f("https://netflix.com/title/1") is None
    assert f("https://www.facebook.com/sharer/sharer.php?u=https://a.ch") is None
    assert f("https://twitter.com/intent/tweet?text=hi") is None
    assert f("https://www.linkedin.com/shareArticle?url=x") is None
    assert f("https://www.facebook.com/") is None
    assert f("https://www.facebook.com/musterag") == "Facebook"
    assert f("https://x.com/musterag") == "X"
    assert f("https://twitter.com/musterag") == "X"
    assert f("https://ch.linkedin.com/company/muster-ag") == "LinkedIn"


# --- cookie banner ---------------------------------------------------------
def test_cookie_labels_are_whole_words():
    html = page('<div id="cookie-banner">Wir verwenden Cookies.'
                '<a href="https://facebook.com/x">Facebook</a><a href="/book">Book now</a></div>')
    r = h.classify_cookie_ui(html)
    assert r["cookie_banner_html_present"] is True
    assert r["cookie_banner_has_only_ok"] is False


def test_cookie_banner_with_choices():
    html = page('<div class="cookie-consent"><p>Diese Website verwendet Cookies.</p>'
                '<button>Alle akzeptieren</button><button>Ablehnen</button>'
                '<button>Einstellungen</button></div>')
    r = h.classify_cookie_ui(html)
    assert (r["cookie_banner_has_accept"], r["cookie_banner_has_reject"],
            r["cookie_banner_has_settings"]) == (True, True, True)
    assert r["cookie_choice_html_signal"] is True


def test_cookie_banner_ok_only_and_body_class_is_ignored():
    html = soup('<html><body class="cookies-not-set"><nav><a href="#">Facebook</a></nav>'
                '<div id="cookie-notice">Diese Seite nutzt Cookies. <button>OK</button></div>'
                "</body></html>")
    r = h.classify_cookie_ui(html)
    assert r["cookie_banner_has_only_ok"] is True
    assert r["cookie_banner_has_accept"] is False


def test_no_cookie_banner():
    assert h.classify_cookie_ui(page("<p>Hallo</p>"))["cookie_banner_html_present"] is False


# --- contact / address -----------------------------------------------------
def test_years_are_not_addresses():
    for text in ("© 2025 Muster AG", "Seit 1998 Ihr Partner", "Copyright 2024 Alle Rechte vorbehalten"):
        assert text_has_address(text) is None, text
        assert text_has_address(text, {}) is None, text  # also without a PLZ list


def test_real_addresses():
    assert text_has_address("Bahnhofstrasse 1, 8000 Zürich") == "plz_match"
    assert text_has_address("Musterweg 3 · 9470 Buchs") == "plz_match"
    assert text_has_address("Rue Centrale 5, 2502 Bienne") == "plz_match"
    assert text_has_address("Bahnhofstrasse 1, 8000 Zürich", {}) == "plz_heuristic"
    assert text_has_address("8000 Muster", ) is None


def test_address_from_structured_data():
    s = page('<script type="application/ld+json">{"@type":"LocalBusiness","address":'
             '{"@type":"PostalAddress","postalCode":"8000","addressLocality":"Zürich"}}</script>')
    assert detect_address(s) == (True, "jsonld")
    assert detect_address(page("<address>Muster AG<br>Hauptstr. 1<br>3011 Bern</address>")) == (True, "address_tag")


def test_contact_details():
    r = h.detect_contact_info_on_page(page(
        '<a href="mailto:info@muster.ch">Mail</a> Tel. 044 123 45 67 <a href="mailto:noreply@x.ch">n</a>'))
    assert r["public_email"] == "clickable" and r["public_phone"] == "text"
    r = h.detect_contact_info_on_page(page(
        '<a href="/cdn-cgi/l/email-protection#abc">[email protected]</a> IBAN CH93 0076 2011 6238 5295 7'))
    assert r["public_email"] == "obfuscated" and r["public_phone"] == "none"


# --- language --------------------------------------------------------------
def test_primary_language_is_what_the_page_declares():
    s = soup('<html lang="fr"><head><link rel="alternate" hreflang="fr" href="/">'
             '<link rel="alternate" hreflang="de" href="/de/"></head><body></body></html>')
    r = detect_languages_and_localization(s, "https://a.ch/")
    assert r["primary_language"] == "fr"
    assert r["localization_status"] == "multi_language_best_practice"


def test_single_it_link_is_not_italian():
    s = page('<a href="/it/">IT-Services</a><a href="https://facebook.com/fr/x">fb</a>')
    r = detect_languages_and_localization(s, "https://a.ch/")
    assert r["url_languages"] == "" and r["languages_detected"] == "de"
    assert r["localization_status"] == "single_language"


def test_two_language_prefixes_are_a_pattern():
    s = page('<a href="/de/">Deutsch</a><a href="/fr/">Français</a>')
    r = detect_languages_and_localization(s, "https://a.ch/")
    assert r["url_languages"] == "de, fr" and r["switcher_languages"] == "de, fr"
    assert r["localization_status"] == "multi_language_poor_implementation"


# --- CMS -------------------------------------------------------------------
def test_cms_detection():
    s = page(head='<meta name="generator" content="Elementor 3.20.1">'
                  '<meta name="generator" content="WordPress 6.4.2">')
    assert detect_cms(s, str(s)) == {"cms_name": "WordPress", "cms_version": "6.4.2",
                                     "cms_evidence": "generator"}
    html = '<html><link href="/typo3temp/assets/x.css"></html>'
    assert detect_cms(soup(html), html)["cms_name"] == "TYPO3"
    assert detect_cms(page(), "", {"X-Wix-Request-Id": "1"})["cms_name"] == "Wix"
    assert detect_cms(page("<p>hi</p>"), "<p>hi</p>")["cms_name"] == ""


# --- placeholder -----------------------------------------------------------
def test_placeholder_pages():
    assert h.detect_placeholder(page("<h1>Hier entsteht eine neue Website</h1>"), 6) == "under_construction"
    assert h.detect_placeholder(page("<p>This domain is for sale</p>"), 5) == "for_sale"
    assert h.detect_placeholder(page("<p>coming soon</p>"), 900) == ""


# --- clickable divs --------------------------------------------------------
def test_clickable_divs():
    assert h.looks_interactive_divspan(soup('<div onclick="x()">a</div>').div)
    assert h.looks_interactive_divspan(soup('<div class="btn btn-primary">a</div>').div)
    assert not h.looks_interactive_divspan(soup('<div class="btn-group"><button>a</button></div>').div)
    assert not h.looks_interactive_divspan(soup('<div class="button-wrapper"><a href="/">a</a></div>').div)
