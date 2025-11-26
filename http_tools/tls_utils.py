"""TLS probing utilities with safe, anonymized error categorization."""
from __future__ import annotations

import datetime
import socket
import ssl
from typing import Any, Dict

from http_tools.http_utils import REQUEST_TIMEOUT


def classify_tls_error(exc: Exception) -> str:
    """
    Map SSL/TLS failures to one of the 7 safe categories.
    Never include domain names or any raw error text.
    """
    msg = repr(exc).lower()

    if "hostname" in msg and "doesn't match" in msg:
        return "hostname_mismatch"
    if "self signed" in msg:
        return "self_signed"
    if "certificate has expired" in msg:
        return "expired"
    if "certificate verify failed" in msg:
        # Covers untrusted CAs, missing chains, or similar verification gaps.
        return "untrusted_issuer"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"

    # Generic bucket for unexpected TLS failures.
    return "no_tls_or_other_error"


def check_tls(domain: str, port: int = 443) -> Dict[str, Any]:
    """
    Safe TLS check intended for public datasets.
    No raw error messages or identifying data.
    """
    info: Dict[str, Any] = {
        "tls_handshake_ok": None,
        "tls_protocol": None,
        "tls_cert_expiry": None,
        "tls_issue_category": "no_tls_or_other_error",
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    try:
        with socket.create_connection((domain, port), timeout=REQUEST_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                info["tls_handshake_ok"] = True
                info["tls_protocol"] = ssock.version()

                cert = ssock.getpeercert()
                if cert and "notAfter" in cert:
                    dt = datetime.datetime.strptime(
                        cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                    ).replace(tzinfo=datetime.timezone.utc)
                    info["tls_cert_expiry"] = dt.isoformat()

                info["tls_issue_category"] = "none"
                return info

    except Exception as e:
        info["tls_handshake_ok"] = False
        info["tls_protocol"] = None
        info["tls_cert_expiry"] = None
        info["tls_issue_category"] = classify_tls_error(e)
        return info
