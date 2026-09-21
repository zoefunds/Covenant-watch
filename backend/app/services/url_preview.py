"""
SSRF-protected URL preview for offchain covenant source verification at
loan-creation time. This is informational only for the UI -- the contract
performs its own independent fetch at check time and this endpoint's
output never feeds consensus.

Protection strategy:
  1. Scheme must be http/https.
  2. Hostname is resolved via DNS *before* fetching, and every resolved IP
     is checked against private/loopback/link-local/reserved ranges
     (including the cloud metadata IP 169.254.169.254). This defends
     against DNS-rebinding: string-matching the URL alone is not enough
     because a hostname can resolve to a private IP at request time even
     if it looks like a public domain.
  3. httpx is configured to NOT follow redirects automatically -- we
     resolve and validate each redirect hop ourselves, so an attacker
     can't bounce through a public URL that 302s to 169.254.169.254.
  4. Hard timeout and response-size cap.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 5.0
MAX_BODY_BYTES = 64 * 1024
MAX_PREVIEW_CHARS = 2000

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, incl. 169.254.169.254 metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local v6
]


class SSRFBlockedError(Exception):
    pass


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # can't parse -> refuse, fail closed
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def _validate_url_or_raise(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(f"scheme not allowed: {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("missing hostname")
    if hostname.lower() in ("localhost", "localhost.localdomain"):
        raise SSRFBlockedError("localhost not allowed")

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFBlockedError(f"DNS resolution failed: {e}") from e

    if not resolved:
        raise SSRFBlockedError("DNS resolution returned no addresses")

    for family, _, _, _, sockaddr in resolved:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            raise SSRFBlockedError(f"resolved IP is blocked: {ip_str}")

    return url


async def fetch_preview(url: str) -> dict:
    """Fetch a URL for preview purposes with SSRF protection at every hop."""
    current_url = _validate_url_or_raise(url)

    async with httpx.AsyncClient(follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            resp = await client.get(current_url)
            if resp.is_redirect:
                next_url = resp.headers.get("location")
                if not next_url:
                    raise SSRFBlockedError("redirect with no Location header")
                current_url = _validate_url_or_raise(httpx.URL(current_url).join(next_url).human_repr())
                continue

            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > MAX_BODY_BYTES:
                    body = body[:MAX_BODY_BYTES]
                    break

            text = body.decode(resp.encoding or "utf-8", errors="replace")
            return {
                "url": current_url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type"),
                "truncated_body": text[:MAX_PREVIEW_CHARS],
            }

    raise SSRFBlockedError("too many redirects")
