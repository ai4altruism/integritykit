"""URL safety validation for SSRF prevention.

Used by webhook delivery and external-source ingestion to block requests
targeting internal/private addresses. Resolves hostnames via DNS and
re-validates after every HTTP redirect hop.

Maps to security-review.md §3, §4, §10 (A10:2021 SSRF).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)


class UnsafeURLError(ValueError):
    """Raised when a URL targets a blocked / private / reserved address."""


_DEFAULT_MAX_REDIRECTS = 5
_DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0

# Literal IPs that pass the public-address check but must always be blocked.
# AWS/GCP/Azure instance metadata endpoints (IMDS).
_BLOCKED_LITERAL_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS, GCP, Azure IMDS (IPv4 link-local — already
        # caught by is_link_local; listed for clarity)
        "fd00:ec2::254",  # AWS IMDS over IPv6 (IPv6 ULA — also caught by
        # is_private; listed for clarity)
    }
)


def _classify_address(address: str) -> str | None:
    """Return a reason string if the address is blocked, else None.

    Uses stdlib classifiers from `ipaddress` which cover:
      - loopback (127.0.0.0/8, ::1)
      - private (RFC 1918: 10/8, 172.16/12, 192.168/16; IPv6 ULA fc00::/7)
      - link-local (169.254.0.0/16, fe80::/10)
      - reserved / multicast / unspecified
    """
    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return f"unparseable address {address!r}"

    if address in _BLOCKED_LITERAL_IPS:
        return f"cloud metadata address {address}"
    if addr.is_loopback:
        return f"loopback address {address}"
    if addr.is_link_local:
        return f"link-local address {address}"
    if addr.is_private:
        return f"private address {address}"
    if addr.is_reserved:
        return f"reserved address {address}"
    if addr.is_multicast:
        return f"multicast address {address}"
    if addr.is_unspecified:
        return f"unspecified address {address}"
    return None


async def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve all A/AAAA records for a hostname.

    Raises UnsafeURLError if resolution fails — a host we cannot resolve
    must not be requested.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, OSError) as exc:
        raise UnsafeURLError(f"Hostname {hostname!r} did not resolve: {exc}") from exc
    # info is (family, type, proto, canonname, sockaddr); sockaddr[0] is the IP
    return [info[4][0] for info in infos]


def _extract_hostname(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme {parsed.scheme!r}; only http/https allowed")
    if not parsed.hostname:
        raise UnsafeURLError(f"URL has no hostname: {url!r}")
    return parsed.hostname


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


async def _validate_single_url(url: str) -> None:
    """Validate one URL by DNS resolution and address classification."""
    hostname = _extract_hostname(url)

    # If the hostname is an IP literal, classify it directly. We must not
    # wrap this in a try/except ValueError, since UnsafeURLError subclasses
    # ValueError and would be swallowed.
    if _is_ip_literal(hostname):
        reason = _classify_address(hostname)
        if reason is not None:
            raise UnsafeURLError(f"URL {url!r} targets {reason}")
        return

    addresses = await _resolve_hostname(hostname)
    if not addresses:
        raise UnsafeURLError(f"Hostname {hostname!r} produced no addresses")

    for addr in addresses:
        reason = _classify_address(addr)
        if reason is not None:
            raise UnsafeURLError(f"URL {url!r} resolves to {reason}")


async def validate_external_url(
    url: str,
    *,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
    probe_timeout_seconds: float = _DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> None:
    """Validate that `url` is safe to fetch (no SSRF).

    Resolves DNS for the URL's hostname and rejects any address in:
      - loopback (127.0.0.0/8, ::1)
      - RFC 1918 private (10/8, 172.16/12, 192.168/16)
      - link-local (169.254.0.0/16) — includes cloud metadata (169.254.169.254)
      - IPv6 ULA (fc00::/7)
      - reserved, multicast, unspecified

    Then issues HEAD probes to follow up to `max_redirects` HTTP redirects,
    re-validating the destination on every hop. If a HEAD probe fails for
    network reasons (target down, HEAD not supported), validation succeeds
    for the current URL and stops following — the caller's real request
    will surface the underlying error.

    Raises:
        UnsafeURLError: if any hop targets a blocked address, the scheme is
            unsupported, the hostname does not resolve, the redirect chain
            loops, or the chain exceeds `max_redirects` hops.
    """
    visited: set[str] = set()
    current = url

    for _hop in range(max_redirects + 1):
        if current in visited:
            raise UnsafeURLError(f"Redirect loop detected at {current!r}")
        visited.add(current)

        await _validate_single_url(current)

        # Probe for a redirect. We do not need the response body.
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(probe_timeout_seconds),
            ) as client:
                response = await client.head(current)
        except httpx.RequestError as exc:
            logger.debug(
                "URL safety HEAD probe failed; current URL is safe, stopping",
                url=current,
                error=str(exc),
            )
            return

        if not response.is_redirect:
            return

        location = response.headers.get("Location")
        if not location:
            return

        # Resolve relative redirects against the current URL.
        current = str(httpx.URL(current).join(location))

    raise UnsafeURLError(f"Too many redirects (>{max_redirects}) starting from {url!r}")
