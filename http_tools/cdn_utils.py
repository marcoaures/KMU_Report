"""Heuristics for identifying CDN or WAF providers from headers and DNS."""
from __future__ import annotations

from typing import Optional

import dns.exception
import dns.resolver
import requests


def detect_cdn_waf(domain: str, resp: Optional[requests.Response]) -> str:
    """
    Heuristic CDN/WAF detection based on:
      1) HTTP response headers (no extra requests)
      2) DNS CNAME records as a fallback

    Returns a provider label (e.g. "Cloudflare") or "None".
    """
    # Step 1: try to identify the provider using only the existing response.
    if resp is not None:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        server = headers.get("server", "").lower()

        # Cloudflare
        if (
            "cloudflare" in server
            or any(h.startswith("cf-") for h in headers.keys())
            or "cf-cache-status" in headers
            or "cf-ray" in headers
        ):
            return "Cloudflare"

        # Akamai
        if (
            "akamai" in server
            or any(k.startswith("akamai-") or k.startswith("x-akamai-") for k in headers.keys())
        ):
            return "Akamai"

        # Fastly
        x_served_by = headers.get("x-served-by", "").lower()
        via = headers.get("via", "").lower()
        x_cache = headers.get("x-cache", "").lower()
        if (
            "fastly" in x_served_by
            or "fastly" in via
            or "fastly" in x_cache
        ):
            return "Fastly"

        # Netlify
        if "netlify" in server or "x-nf-request-id" in headers:
            return "Netlify"

        # AWS ELB / ALB
        if "awselb" in server or "elastic load balancer" in server:
            return "AWS ELB/ALB"

        # Fly.io
        if (
            "x-fly-region" in headers
            or "fly.io" in server
            or "fly.io" in via
        ):
            return "Fly.io"

    # Step 2: fall back to CNAME fingerprints when headers are inconclusive.
    patterns = {
        "cloudflare": "Cloudflare",
        "akamai": "Akamai",
        "fastly": "Fastly",
        "incapdns": "Imperva",
        "cloudfront": "CloudFront",
        "wpengine": "WPEngine",
        "stackpath": "StackPath",
        "sucuri": "Sucuri",
    }

    try:
        answers = dns.resolver.resolve(domain, "CNAME")
        targets = [str(r.target).lower() for r in answers]
    except dns.exception.DNSException:
        targets = []

    for target in targets:
        for key, label in patterns.items():
            if key in target:
                return label

    return "None"
