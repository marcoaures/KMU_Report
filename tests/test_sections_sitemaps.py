from bs4 import BeautifulSoup

from analysis.sections import (FallbackProber, career_segment_matches_keyword,
                               detect_careers_section, detect_section, top_paths)
from analysis.sitemap_utils import check_robots, collect_sitemaps
from config import config as cfg
from config.dictionary_config import (IMPRINT_FALLBACK_PATHS, IMPRINT_HREF_KEYWORDS,
                                      IMPRINT_LINK_TEXT_KEYWORDS, IMPRINT_SITEMAP_KEYWORDS)
from fake_site import FakeSite
from http_tools.client import DomainClient

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def imprint(sitemap_urls=(), soup=None, homepage=None, prober=None, lang="de"):
    return detect_section("imprint", list(sitemap_urls), soup, homepage, IMPRINT_SITEMAP_KEYWORDS,
                          IMPRINT_LINK_TEXT_KEYWORDS, IMPRINT_HREF_KEYWORDS,
                          IMPRINT_FALLBACK_PATHS, prober, lang)


def test_career_slugs():
    ok = ["jobs", "karriere", "karriere-bei-uns", "jobs-und-karriere", "offene-stellen", "careers"]
    bad = ["jobs-to-be-done", "travail-du-bois", "lavoro-artigianale", "travail", "lavoro"]
    assert all(career_segment_matches_keyword(s) for s in ok)
    assert not any(career_segment_matches_keyword(s) for s in bad)
    assert career_segment_matches_keyword("lavoro", allow_ambiguous=True)


def test_careers_from_sitemap_ignores_deep_articles():
    assert detect_careers_section(["https://a.ch/unternehmen/karriere"], None, None)[0] is True
    assert detect_careers_section(["https://a.ch/blog/2020/05/jobs-to-be-done"], None, None)[0] is False
    assert detect_careers_section(["https://a.ch/blog/2020/05/artikel/jobs"], None, None)[0] is False


def test_section_from_homepage_link():
    soup = BeautifulSoup('<a href="/ueber-uns/impressum">Impressum</a>', "html.parser")
    assert imprint(soup=soup, homepage="https://a.ch/") == (True, "homepage_link", "/ueber-uns/impressum")


def test_top_paths_follow_page_language():
    assert top_paths("imprint", "fr-CH")[0] == "/mentions-legales"
    assert top_paths("imprint", "de")[0] == "/impressum"
    assert len(top_paths("blog", None)) <= cfg.MAX_FALLBACK_PATHS_PER_SECTION


def test_fallback_probe_finds_page():
    with FakeSite({"/": "home", "/impressum": "<h1>Impressum</h1>"}) as site:
        client = DomainClient(site.domain)
        prober = FallbackProber(client, site.base)
        assert imprint(prober=prober) == (True, "fallback_url", "/impressum")


def test_fallback_probe_skipped_on_soft_404_sites():
    # this site answers every path with a page: guessing would "find" everything
    with FakeSite({"/": "home"}, default_status=200) as site:
        client = DomainClient(site.domain)
        prober = FallbackProber(client, site.base)
        assert imprint(prober=prober)[0] is False
        assert client.requests_made == 1  # only the test request, no guesses


def test_probing_stops_after_too_many_misses():
    with FakeSite({"/": "home"}) as site:
        client = DomainClient(site.domain)
        prober = FallbackProber(client, site.base)
        for section in ("imprint", "privacy", "terms", "careers", "blog"):
            prober.find(top_paths(section, "de") + ["/x1", "/x2"], [])
        assert client.probe_misses == cfg.MAX_PROBE_MISSES_PER_DOMAIN
        assert client.requests_made == 1 + cfg.MAX_PROBE_MISSES_PER_DOMAIN


def test_robots_html_error_page_is_not_a_robots_txt():
    with FakeSite({"/robots.txt": (200, "<html>nope</html>", {"Content-Type": "text/html"})}) as site:
        assert check_robots(site.domain, DomainClient(site.domain)) == (False, "")
    with FakeSite({"/robots.txt": "User-agent: *\nDisallow:\n"}) as site:
        assert check_robots(site.domain, DomainClient(site.domain))[0] is True


def test_sitemap_index_and_lastmod():
    def pages(base):
        return {
            "/sitemap.xml": f"<sitemapindex {NS}><sitemap><loc>{base}/a.xml</loc></sitemap>"
                            f"<sitemap><loc>{base}/b.xml</loc></sitemap></sitemapindex>",
            "/a.xml": f"<urlset {NS}><url><loc>{base}/x</loc><lastmod>2026-10-01</lastmod></url>"
                      f"<url><loc>{base}/y</loc></url></urlset>",
            "/b.xml": f"<urlset {NS}><url><loc>{base}/x</loc></url><url><loc>{base}/z</loc></url></urlset>",
        }
    with FakeSite({}) as site:
        site.pages.update(pages(site.base))
        r = collect_sitemaps(site.base, "", DomainClient(site.domain))
        assert r["sitemaps"] == [f"{site.base}/sitemap.xml"]
        assert r["sources"][f"{site.base}/sitemap.xml"] == "guessed"
        assert len(r["urls"]) == 3  # /x is listed twice but counted once
        assert r["lastmods"][f"{site.base}/x"] is not None
        assert r["truncated"] is False


def test_self_referencing_sitemap_terminates():
    with FakeSite({}) as site:
        site.pages["/sitemap.xml"] = (f"<sitemapindex {NS}><sitemap><loc>{site.base}/sitemap.xml</loc>"
                                      "</sitemap></sitemapindex>")
        client = DomainClient(site.domain)
        r = collect_sitemaps(site.base, f"Sitemap: {site.base}/sitemap.xml\n", client)
        assert r["sitemaps"] == [f"{site.base}/sitemap.xml"] and r["urls"] == []
        assert client.requests_made == 1


def test_sitemap_file_limit_sets_truncated():
    with FakeSite({}) as site:
        subs = "".join(f"<sitemap><loc>{site.base}/s{i}.xml</loc></sitemap>" for i in range(30))
        site.pages["/sitemap.xml"] = f"<sitemapindex {NS}>{subs}</sitemapindex>"
        for i in range(30):
            site.pages[f"/s{i}.xml"] = f"<urlset {NS}><url><loc>{site.base}/p{i}</loc></url></urlset>"
        r = collect_sitemaps(site.base, "", DomainClient(site.domain))
        assert r["truncated"] is True
        assert len(r["urls"]) == cfg.MAX_SITEMAP_FILES - 1


def test_declared_but_missing_sitemap_is_not_counted():
    with FakeSite({}) as site:
        r = collect_sitemaps(site.base, f"Sitemap: {site.base}/nope.xml\n", DomainClient(site.domain))
        assert r["sitemaps"] == []
