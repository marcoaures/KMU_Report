"""Heuristics for identifying CDN or WAF providers from headers and DNS."""
from __future__ import annotations

from typing import Optional

import dns.exception
import requests

from dns_tools.dns_security import resolver

# CNAME fragments -> provider
_CNAME_PATTERNS = {
    "cloudflare": "Cloudflare",
    "akamai": "Akamai",
    "edgekey": "Akamai",
    "edgesuite": "Akamai",
    "fastly": "Fastly",
    "incapdns": "Imperva",
    "cloudfront": "CloudFront",
    "azureedge": "Azure Front Door",
    "azurefd": "Azure Front Door",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "wpengine": "WPEngine",
    "stackpath": "StackPath",
    "sucuri": "Sucuri",
}


def _from_headers(resp: requests.Response) -> Optional[str]:
    h = {k.lower(): v for k, v in resp.headers.items()}
    server = h.get("server", "").lower()
    via = h.get("via", "").lower()
    x_cache = h.get("x-cache", "").lower()

    if "cloudflare" in server or "cf-ray" in h or "cf-cache-status" in h:
        return "Cloudflare"
    if "akamai" in server or any(k.startswith(("akamai-", "x-akamai-")) for k in h):
        return "Akamai"
    if "fastly" in via or "fastly" in x_cache or "fastly" in h.get("x-served-by", "").lower():
        return "Fastly"
    if "x-amz-cf-id" in h or "cloudfront" in via or "cloudfront" in x_cache:
        return "CloudFront"
    if "x-azure-ref" in h:
        return "Azure Front Door"
    if "x-vercel-id" in h or server == "vercel":
        return "Vercel"
    if "netlify" in server or "x-nf-request-id" in h:
        return "Netlify"
    if "x-sucuri-id" in h or "sucuri" in server:
        return "Sucuri"
    if "x-iinfo" in h or "incap_ses" in h.get("set-cookie", "").lower():
        return "Imperva"
    if "awselb" in server or "elastic load balancer" in server:
        return "AWS ELB/ALB"
    if "x-fly-region" in h or "fly.io" in server or "fly.io" in via:
        return "Fly.io"
    return None


def detect_cdn_waf(
    domain: str, resp: Optional[requests.Response], final_host: Optional[str] = None
) -> Optional[str]:
    """Provider label, "" if nothing was recognised, None if there was nothing
    to look at (no response and no DNS answer)."""
    if resp is not None:
        found = _from_headers(resp)
        if found:
            return found

    # CNAME fingerprints. The apex rarely has a CNAME, so also look at www
    # and at the host the redirects ended on.
    hosts = [domain]
    if not domain.startswith("www."):
        hosts.append("www." + domain)
    if final_host and final_host not in hosts:
        hosts.append(final_host)

    answered = False
    for host in hosts:
        try:
            answers = resolver.resolve(host, "CNAME")
        except dns.exception.DNSException:
            continue
        answered = True
        for r in answers:
            target = str(r.target).lower()
            for key, label in _CNAME_PATTERNS.items():
                if key in target:
                    return label
    if resp is None and not answered:
        return None
    return ""
