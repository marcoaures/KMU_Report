"""Polite HTTP client. One ``DomainClient`` is created per scanned domain.

It bundles everything that keeps the scan gentle and predictable:
connection reuse, a request budget, per-IP throttling shared by all workers,
robots.txt handling, download size caps, stop-on-block and a request log.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from collections import deque
from typing import Dict, Optional, Tuple
from urllib import robotparser
from urllib.parse import urlparse

import requests
import tldextract

from config import config as cfg

request_log = logging.getLogger("kmu.requests")

# Use the public suffix list bundled with tldextract: no download at start-up.
_tld = tldextract.TLDExtract(suffix_list_urls=())
log = logging.getLogger(__name__)


def registrable_domain(host: str) -> str:
    """www.example.co.uk -> example.co.uk (falls back to the host itself)."""
    host = (host or "").split("@")[-1].split(":")[0].strip(".").lower()
    ext = _tld(host)
    if not ext.domain or not ext.suffix:
        return host
    return f"{ext.domain}.{ext.suffix}"


class _IpThrottle:
    """Spaces out requests to the same server IP across all worker threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: Dict[str, float] = {}

    def wait(self, key: str, delay: float) -> None:
        if delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next.get(key, 0.0))
            self._next[key] = start + delay
        if start > now:
            time.sleep(start - now)


class GlobalBrake:
    """Pauses every worker when too many recent domains were blocked/timed out."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: deque = deque()
        self._paused_until = 0.0

    def report(self, bad: bool) -> None:
        with self._lock:
            self._window.append(bool(bad))
            while len(self._window) > cfg.BRAKE_WINDOW:
                self._window.popleft()
            if len(self._window) < cfg.BRAKE_WINDOW:
                return
            share = sum(self._window) / len(self._window)
            if share >= cfg.BRAKE_THRESHOLD:
                self._paused_until = time.monotonic() + cfg.BRAKE_PAUSE_SECONDS
                self._window.clear()
                log.warning(
                    "Emergency brake: %.0f%% of the last %d domains were blocked or "
                    "timed out. Pausing all requests for %d s.",
                    share * 100, cfg.BRAKE_WINDOW, cfg.BRAKE_PAUSE_SECONDS,
                )

    def wait(self) -> None:
        while True:
            remaining = self._paused_until - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(5.0, remaining))


ip_throttle = _IpThrottle()
brake = GlobalBrake()


class DomainClient:
    """HTTP access to one site, with a budget and a memory of how it went."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.sites = {registrable_domain(domain)}
        self.session = requests.Session()
        self.session.headers.update(cfg.HEADERS)

        self.requests_made = 0
        self.probe_misses = 0
        self.forbidden = 0
        self.unavailable = 0
        self.consecutive_errors = 0
        # Set once the scan of this domain must stop (block, dead host).
        self.stop_reason: Optional[str] = None

        self._robots: Optional[robotparser.RobotFileParser] = None
        self._crawl_delay = 0.0
        self._ips: Dict[str, str] = {}

    # -- robots ------------------------------------------------------------
    def set_robots(self, robots_txt: str) -> None:
        """Parse robots.txt once; later requests are checked against it."""
        self._robots = None
        self._crawl_delay = 0.0
        if not (robots_txt or "").strip():
            return
        parser = robotparser.RobotFileParser()
        parser.parse(robots_txt.splitlines())
        self._robots = parser
        try:
            delay = parser.crawl_delay(cfg.USER_AGENT_TOKEN)
            if delay:
                self._crawl_delay = min(float(delay), cfg.MAX_CRAWL_DELAY_SECONDS)
        except Exception:
            pass

    def add_site(self, host: str) -> None:
        """Treat another registrable domain as part of this site (after a redirect)."""
        self.sites.add(registrable_domain(host))

    def is_own_host(self, url: str) -> bool:
        return registrable_domain(urlparse(url).netloc) in self.sites

    def allowed(self, url: str) -> bool:
        """robots.txt verdict; URLs on foreign hosts (CDNs) are not judged by it."""
        if self._robots is None or not self.is_own_host(url):
            return True
        try:
            return self._robots.can_fetch(cfg.USER_AGENT_TOKEN, url)
        except Exception:
            return True

    # -- requests ----------------------------------------------------------
    def _ip_key(self, host: str) -> str:
        if host not in self._ips:
            try:
                self._ips[host] = socket.gethostbyname(host.split(":")[0])
            except OSError:
                self._ips[host] = host
        return self._ips[host]

    def get(
        self,
        url: str,
        allow_redirects: bool = True,
        max_bytes: Optional[int] = None,
        probe: bool = False,
        is_homepage: bool = False,
        return_reason: bool = False,
    ):
        """GET ``url``. Returns the response or None.

        ``probe`` marks guessed URLs: their 404s count towards the per-domain
        miss limit. With ``return_reason`` a (response, reason) tuple is returned,
        where reason says why there is no response.
        """
        resp, reason = self._get(url, allow_redirects, max_bytes, probe, is_homepage)
        return (resp, reason) if return_reason else resp

    def _refuse(self, url: str, reason: str) -> Tuple[None, str]:
        request_log.info("%s\t%s\t%s\t-", self.domain, url, reason)
        return None, reason

    def _get(self, url, allow_redirects, max_bytes, probe, is_homepage):
        own = self.is_own_host(url)
        if own and self.stop_reason:
            return self._refuse(url, self.stop_reason)
        if not self.allowed(url):
            return self._refuse(url, "disallowed_by_robots")
        if self.requests_made >= cfg.MAX_REQUESTS_PER_DOMAIN:
            return self._refuse(url, "budget_exhausted")
        if probe and self.probe_misses >= cfg.MAX_PROBE_MISSES_PER_DOMAIN:
            return self._refuse(url, "probe_limit")

        host = urlparse(url).netloc
        delay = cfg.REQUEST_DELAY_SECONDS
        if own:
            delay = max(delay, self._crawl_delay)
        brake.wait()
        ip_throttle.wait(self._ip_key(host), delay)

        self.requests_made += 1
        cap = max_bytes or cfg.MAX_HTML_BYTES
        try:
            resp = self.session.get(
                url, timeout=cfg.REQUEST_TIMEOUT, allow_redirects=allow_redirects, stream=True
            )
            chunks, size, truncated = [], 0, False
            for chunk in resp.iter_content(65536):
                chunks.append(chunk)
                size += len(chunk)
                if size >= cap:
                    truncated = size > cap or resp.raw.read(1) != b""
                    break
            resp._content = b"".join(chunks)[:cap]
            resp._content_consumed = True
            resp.truncated = truncated
            resp.close()
        except requests.Timeout:
            return self._failed(url, "timeout", own)
        except requests.exceptions.SSLError:
            return self._failed(url, "tls_error", own)
        except requests.ConnectionError:
            return self._failed(url, "connection_error", own)
        except requests.RequestException as exc:
            return self._failed(url, exc.__class__.__name__.lower(), own)
        except Exception as exc:  # broken encodings, decompression errors, ...
            return self._failed(url, exc.__class__.__name__.lower(), own)

        status = resp.status_code
        request_log.info("%s\t%s\t%s\t%s", self.domain, url, status, len(resp.content))
        if own or self.is_own_host(resp.url):
            self.consecutive_errors = 0
            if status == 429:
                self.stop_reason = "blocked_http_429"
            elif status == 403:
                self.forbidden += 1
                if is_homepage or self.forbidden >= cfg.MAX_FORBIDDEN_PER_DOMAIN:
                    self.stop_reason = "blocked_http_403"
            elif status == 503:
                self.unavailable += 1
                if self.unavailable >= 2:
                    self.stop_reason = "overloaded_http_503"
            if probe and status in (404, 410):
                self.probe_misses += 1
        return resp, None

    def _failed(self, url: str, reason: str, own: bool) -> Tuple[None, str]:
        request_log.info("%s\t%s\t%s\t-", self.domain, url, reason)
        if own:
            self.consecutive_errors += 1
            if self.consecutive_errors >= cfg.MAX_CONSECUTIVE_ERRORS:
                self.stop_reason = "unreachable"
        return None, reason

    def close(self) -> None:
        self.session.close()
