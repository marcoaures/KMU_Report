"""DNS checks: MX, SPF, DMARC and a DNSSEC heuristic."""
from __future__ import annotations

from typing import List, Optional, Tuple

import dns.exception
import dns.resolver

from http_tools.client import registrable_domain

# Our own resolver with short timeouts; dnspython's global default stays untouched.
resolver = dns.resolver.Resolver(configure=True)
resolver.lifetime = 4.0   # overall time per query
resolver.timeout = 2.0    # per nameserver attempt

_NO_DATA = (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN)


def _query(name: str, rtype: str) -> Optional[list]:
    """Records, [] if the name has none, None if the lookup itself failed."""
    try:
        return list(resolver.resolve(name, rtype))
    except _NO_DATA:
        return []
    except dns.exception.DNSException:
        return None


def get_txt_records(name: str) -> Optional[List[str]]:
    answers = _query(name, "TXT")
    if answers is None:
        return None
    records = []
    for r in answers:
        parts = getattr(r, "strings", None)
        if parts:
            records.append("".join(p.decode("utf-8", "replace") if isinstance(p, bytes) else p
                                   for p in parts))
        else:
            records.append(str(r).strip('"'))
    return records


def check_mx(domain: str) -> Optional[bool]:
    """Does the registrable domain accept mail? A "null MX" (RFC 7505) counts as no."""
    answers = _query(registrable_domain(domain), "MX")
    if answers is None:
        return None
    return any(str(r.exchange).rstrip(".") for r in answers)


def check_spf(domain: str) -> Tuple[Optional[bool], str]:
    """(present, record) for the registrable domain; present is None on lookup errors."""
    txts = get_txt_records(registrable_domain(domain))
    if txts is None:
        return None, ""
    for txt in txts:
        if txt.lower().startswith("v=spf1"):
            return True, txt
    return False, ""


def check_dmarc(domain: str) -> Tuple[Optional[bool], str]:
    """(present, policy). Looks at the exact host first, then at the
    registrable domain, as receivers do."""
    names = [f"_dmarc.{domain}"]
    base = f"_dmarc.{registrable_domain(domain)}"
    if base not in names:
        names.append(base)

    failed = False
    for name in names:
        txts = get_txt_records(name)
        if txts is None:
            failed = True
            continue
        for txt in txts:
            if txt.lower().startswith("v=dmarc1"):
                policy = "unknown"
                for part in txt.split(";"):
                    part = part.strip()
                    if part.lower().startswith("p="):
                        policy = part.split("=", 1)[1].strip().lower()
                        break
                return True, policy
    return (None, "") if failed else (False, "")


def check_dnssec(domain: str) -> str:
    """Heuristic DNSSEC status of the registrable domain.

        enabled                           DS at the parent and DNSKEY in the zone
        not_enabled                       neither
        dnskey_without_ds                 keys published, chain of trust not closed
        misconfigured_ds_without_dnskey   DS at the parent but no usable DNSKEY
        indeterminate                     lookups failed
    """
    base = registrable_domain(domain)
    ds = _query(base, "DS")
    if ds is None:
        return "indeterminate"
    keys = _query(base, "DNSKEY")

    if not ds:
        return "dnskey_without_ds" if keys else "not_enabled"
    if keys is None:
        return "indeterminate"
    sane = any(
        getattr(k, "protocol", None) == 3
        and getattr(k, "algorithm", 0) != 0
        and int(getattr(k, "flags", 0)) in (256, 257)
        for k in keys
    )
    return "enabled" if sane else "misconfigured_ds_without_dnskey"
