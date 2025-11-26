"""DNS-related security checks for SPF, DMARC, DNSSEC and related helpers."""
from __future__ import annotations

from typing import List, Tuple, Optional

import dns.resolver
import dns.exception
import tldextract

from http_tools.http_utils import safe_get

# Configure the shared resolver with short, predictable timeouts to keep
# SPF/DMARC and DNSSEC checks responsive.
dns.resolver.default_resolver = dns.resolver.Resolver(configure=True)
dns.resolver.default_resolver.lifetime = 3.0   # overall timeout per query set
dns.resolver.default_resolver.timeout = 2.0    # per nameserver attempt

def base_domain_for_email(domain: str) -> str:
    """
    Use tldextract to derive the registrable base domain for SPF/DMARC checks.

    Example:
        www.example.co.uk -> example.co.uk
    """
    ext = tldextract.extract(domain)
    if not ext.domain or not ext.suffix:
        return domain
    return f"{ext.domain}.{ext.suffix}"


def base_domain_for_dnssec(domain: str) -> str:
    """
    Similar idea to base_domain_for_email. We want the zone apex:
    example.ch from www.example.ch.
    """
    return base_domain_for_email(domain)

def get_txt_records(name: str) -> List[str]:
    """
    Return DNS TXT records for a name as clean strings
    (joined fragments, quotes stripped).
    """
    try:
        answers = dns.resolver.resolve(name, "TXT")
        records: List[str] = []
        for r in answers:
            if hasattr(r, "strings") and r.strings:
                s = "".join(
                    part.decode() if isinstance(part, bytes) else part
                    for part in r.strings
                )
            else:
                s = str(r)
            records.append(s.strip('"'))
        return records
    except dns.exception.DNSException:
        return []


def get_ds_records(name: str) -> list:
    try:
        answers = dns.resolver.resolve(name, "DS")
        return [r for r in answers]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except dns.exception.DNSException:
        # Escalate network or resolver failures so callers can classify them.
        raise


def get_dnskey_records(name: str) -> list:
    try:
        answers = dns.resolver.resolve(name, "DNSKEY")
        return [r for r in answers]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except dns.exception.DNSException:
        # Escalate network or resolver failures so callers can classify them.
        raise


# High-level DNS security checks

def check_dnssec(domain: str) -> str:
    """
    Heuristic DNSSEC status:

        - not-enabled                     → no DS and no DNSKEY
        - enabled (DS & DNSKEY)           → DS in parent + DNSKEY at zone
        - misconfigured (DS but no DNSKEY)→ DS but DNSKEY missing / failing
        - indeterminate (lookup error)    → DNS queries failed in a generic way
    """
    base = base_domain_for_dnssec(domain)

    try:
        ds_records = get_ds_records(base)
    except dns.exception.DNSException:
        return "indeterminate (DS lookup error)"

    # No DS: the parent zone does not delegate a signed child.
    if not ds_records:
        # Optional: if you still want to distinguish "DNSKEY only", check here
        try:
            dnskeys = get_dnskey_records(base)
        except dns.exception.DNSException:
            # Without DS we already know the zone is effectively unsigned.
            return "not-enabled"

        if dnskeys:
            # Publishing DNSKEY without DS leaves the chain of trust incomplete.
            return "not-enabled"
        else:
            return "not-enabled"

    # DS exists → the zone should publish DNSKEY material
    try:
        dnskeys = get_dnskey_records(base)
    except dns.exception.DNSException:
        return "misconfigured (DS but DNSKEY query failed)"

    if not dnskeys:
        return "misconfigured (DS but no DNSKEY)"

    # Basic sanity: expect at least one key with a plausible algorithm/flags.
    sane_dnskey_present = False
    for r in dnskeys:
        try:
            # dnspython DNSKEY fields: flags, protocol, algorithm
            if r.protocol != 3:
                continue
            if r.algorithm == 0:
                continue
            # typical flags: 256 (ZSK), 257 (KSK)
            if r.flags in (256, 257):
                sane_dnskey_present = True
                break
        except Exception:
            continue

    if not sane_dnskey_present:
        return "misconfigured (DNSKEYs look invalid)"

    return "enabled (DS & DNSKEY)"


def check_spf(domain: str) -> Tuple[bool, str]:
    """Check for presence of an SPF TXT record on the base domain."""
    base = base_domain_for_email(domain)
    txts = get_txt_records(base)
    for txt in txts:
        if txt.lower().startswith("v=spf1"):
            return True, txt
    return False, ""


def check_dmarc(domain: str) -> Optional[str]:
    """
    Check for a DMARC policy on the base domain and extract the policy (p=).

    Returns:
        policy string (e.g. "none", "quarantine", "reject") or None if not found.
    """
    base = base_domain_for_email(domain)
    name = f"_dmarc.{base}"
    txts = get_txt_records(name)
    for txt in txts:
        if txt.lower().startswith("v=dmarc1"):
            policy = "unknown"
            parts = txt.split(";")
            for part in parts:
                part = part.strip()
                if part.lower().startswith("p="):
                    policy = part.split("=", 1)[1].strip()
                    break
            return policy
    return None
