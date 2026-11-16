"""TLS probing with safe, anonymized error categories."""
from __future__ import annotations

import datetime
import socket
import ssl
from typing import Any, Dict

from config import config as cfg

# OpenSSL verification error codes -> our categories. These numbers are stable
# across OpenSSL versions, unlike the wording of the error messages.
_VERIFY_CODES = {
    9: "not_yet_valid",
    10: "expired",
    18: "self_signed",
    19: "self_signed",
    20: "untrusted_issuer",
    21: "untrusted_issuer",
    62: "hostname_mismatch",
}


def classify_tls_error(exc: Exception) -> str:
    """Map a failed TLS check to a category. Never returns raw error text."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        code = getattr(exc, "verify_code", None)
        return _VERIFY_CODES.get(code, "certificate_invalid")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "port_closed"
    if isinstance(exc, socket.gaierror):
        return "dns_error"
    if isinstance(exc, ssl.SSLError):
        return "handshake_failed"
    return "connection_error"


def check_tls(domain: str, port: int = 443) -> Dict[str, Any]:
    """Handshake with certificate and hostname verification on port 443."""
    info: Dict[str, Any] = {
        "tls_handshake_ok": None,
        "tls_protocol": None,
        "tls_cert_expiry": None,
        "tls_issue_category": "not_checked",
    }
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((domain, port), timeout=cfg.CONNECT_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                info["tls_handshake_ok"] = True
                info["tls_protocol"] = ssock.version()
                cert = ssock.getpeercert()
                if cert and "notAfter" in cert:
                    ts = ssl.cert_time_to_seconds(cert["notAfter"])
                    info["tls_cert_expiry"] = datetime.datetime.fromtimestamp(
                        ts, datetime.timezone.utc
                    ).isoformat()
                info["tls_issue_category"] = "none"
    except Exception as exc:
        info["tls_handshake_ok"] = False
        info["tls_issue_category"] = classify_tls_error(exc)
    return info
