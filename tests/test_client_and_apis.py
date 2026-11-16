import ssl
import time

import requests

from config import config as cfg
from fake_site import FakeSite
from http_tools import client as client_mod
from http_tools.client import DomainClient
from http_tools.http_utils import check_website_reachable, parse_hsts
from http_tools.tls_utils import classify_tls_error
from integrations import api_clients as api


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload, headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


# --- client ----------------------------------------------------------------
def test_error_status_is_reported_not_swallowed():
    with FakeSite({"/": (500, "oops")}) as site:
        r = check_website_reachable(site.domain, DomainClient(site.domain))
        assert (r["reachable"], r["status"]) == (False, "http_500")


def test_request_budget_is_a_hard_cap(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_REQUESTS_PER_DOMAIN", 5)
    with FakeSite({"/": "hi"}) as site:
        c = DomainClient(site.domain)
        results = [c.get(site.base + "/", return_reason=True)[1] for _ in range(8)]
        assert results[:5] == [None] * 5 and set(results[5:]) == {"budget_exhausted"}
        assert len(site.hits) == 5


def test_429_stops_the_domain():
    with FakeSite({"/a": (429, "slow down")}) as site:
        c = DomainClient(site.domain)
        c.get(site.base + "/a")
        assert c.stop_reason == "blocked_http_429"
        assert c.get(site.base + "/b", return_reason=True) == (None, "blocked_http_429")
        assert len(site.hits) == 1


def test_robots_rules_for_our_token_and_download_cap():
    with FakeSite({"/big": "x" * 50_000}) as site:
        c = DomainClient(site.domain)
        c.set_robots("User-agent: KMU-Webcheck\nDisallow: /private/\n\nUser-agent: *\nDisallow: /\n")
        assert c.allowed(site.base + "/public") and not c.allowed(site.base + "/private/x")
        assert c.allowed("https://cdn.example.net/private/x")  # foreign hosts are not judged
        resp = c.get(site.base + "/big", max_bytes=1000)
        assert len(resp.content) == 1000 and resp.truncated is True


def test_same_ip_is_throttled_across_clients(monkeypatch):
    monkeypatch.setattr(cfg, "REQUEST_DELAY_SECONDS", 0.2)
    monkeypatch.setattr(client_mod, "ip_throttle", client_mod._IpThrottle())
    with FakeSite({"/": "a"}) as one, FakeSite({"/": "b"}) as two:
        start = time.monotonic()
        DomainClient(one.domain).get(one.base + "/")
        DomainClient(two.domain).get(two.base + "/")   # other site, same IP
        DomainClient(one.domain).get(one.base + "/")
        assert time.monotonic() - start >= 0.4


def test_hsts_parsing():
    resp = requests.Response()
    resp.url = "https://a.ch/"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    assert parse_hsts(resp) == {"hsts_header": "max-age=31536000; includeSubDomains",
                                "hsts_max_age": 31536000, "hsts_include_subdomains": True}
    assert parse_hsts(None)["hsts_header"] is None


def test_tls_errors_are_classified_by_code_not_by_wording():
    def err(code):
        e = ssl.SSLCertVerificationError(1, "wording changes between OpenSSL versions")
        e.verify_code = code
        return e
    assert classify_tls_error(err(10)) == "expired"
    assert classify_tls_error(err(18)) == "self_signed"
    assert classify_tls_error(err(20)) == "untrusted_issuer"
    assert classify_tls_error(err(62)) == "hostname_mismatch"
    assert classify_tls_error(TimeoutError()) == "timeout"
    assert classify_tls_error(ConnectionRefusedError()) == "port_closed"


# --- PageSpeed -------------------------------------------------------------
def psi_setup(monkeypatch, responses):
    monkeypatch.setattr(cfg, "SKIPPING_APIS", False)
    monkeypatch.setattr(cfg, "PAGESPEED_API_KEY", "k")
    monkeypatch.setattr(cfg, "PAGESPEED_MIN_INTERVAL", 0)
    monkeypatch.setattr(api, "_backoff", lambda *a, **k: None)
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(api.requests, "get", fake_get)
    return calls


def psi_ok(score, audits=None):
    return FakeResponse(200, {"lighthouseResult": {"categories": {"performance": {"score": score}},
                                                   "audits": audits or {}}})


def test_pagespeed_score_is_rounded(monkeypatch):
    psi_setup(monkeypatch, [psi_ok(0.57), psi_ok(0.29)])
    assert api.fetch_pagespeed("https://a.ch/")["score"] == 57
    assert api.fetch_pagespeed("https://a.ch/")["score"] == 29


def test_pagespeed_retries_on_429_and_timeouts(monkeypatch):
    calls = psi_setup(monkeypatch, [FakeResponse(429), requests.Timeout(), psi_ok(0.9)])
    assert api.fetch_pagespeed("https://a.ch/") == {"score": 90, "status": "ok", "third_parties": None}
    assert len(calls) == 3
    psi_setup(monkeypatch, [FakeResponse(429)] * 3)
    assert api.fetch_pagespeed("https://a.ch/")["status"] == "rate_limited"


def test_pagespeed_third_parties(monkeypatch):
    audits = {"third-parties-insight": {"details": {"items": [
        {"entity": "Google Tag Manager"}, {"entity": {"text": "Facebook"}}, {"entity": "a.ch"}]}}}
    calls = psi_setup(monkeypatch, [FakeResponse(400), psi_ok(0.8, audits)])
    r = api.fetch_pagespeed("https://www.a.ch/", third_parties=True)
    assert r["third_parties"] == ["Facebook", "Google Tag Manager"]
    assert "fields" in calls[0] and "fields" not in calls[1]  # falls back to the full response


# --- WhatCMS ---------------------------------------------------------------
def whatcms_setup(monkeypatch, payloads):
    monkeypatch.setattr(cfg, "SKIPPING_APIS", False)
    monkeypatch.setattr(cfg, "WHATCMS_API_KEY", "k")
    monkeypatch.setattr(cfg, "WHATCMS_MIN_INTERVAL", 0)
    monkeypatch.setattr(api, "_backoff", lambda *a, **k: None)
    api._whatcms_disabled.clear()
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return FakeResponse(200, payloads.pop(0))
    monkeypatch.setattr(api.requests, "get", fake_get)
    return calls


def test_whatcms_success_and_rate_limit(monkeypatch):
    ok = {"result": {"code": 200}, "results": [{"name": "TYPO3", "version": "12", "categories": ["CMS"]}],
          "meta": {"social": [{"network": "twitter", "url": "https://twitter.com/x"},
                              {"network": "", "url": "https://www.wix.com/"}]}}
    calls = whatcms_setup(monkeypatch, [{"result": {"code": 120, "retry_in_seconds": 1}}, ok])
    r = api.detect_cms_whatcms("a.ch")
    assert (r["cms_name"], r["cms_version"], r["whatcms_status"]) == ("TYPO3", "12", "success")
    assert r["whatcms_social_profiles"] == ["X"] and len(calls) == 2


def test_whatcms_quota_exhausted_stops_further_calls(monkeypatch):
    calls = whatcms_setup(monkeypatch, [{"result": {"code": 121}}])
    assert api.detect_cms_whatcms("a.ch")["whatcms_status"] == "quota_exceeded"
    assert api.detect_cms_whatcms("b.ch")["whatcms_status"] == "quota_exceeded"
    assert len(calls) == 1
    api._whatcms_disabled.clear()


def test_whatcms_nothing_found_is_not_an_error(monkeypatch):
    whatcms_setup(monkeypatch, [{"result": {"code": 201}}])
    r = api.detect_cms_whatcms("a.ch")
    assert (r["cms_name"], r["whatcms_status"]) == ("", "success")
