"""Shared URL validation utilities — private/reserved host detection."""

from __future__ import annotations

import ipaddress
import logging
import socket

logger = logging.getLogger(__name__)

# Hostnames that clients resolve to private/internal targets even though they
# are not numeric IPs. Blocked in addition to the numeric-IP check below.
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",  # GCP metadata
    "metadata",                   # shorthand sometimes routable
    "instance-data",              # AWS IMDS shorthand
    "instance-data.ec2.internal",
})


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the given IP address is private/reserved/loopback."""
    # IPv4-mapped IPv6 (e.g. ::ffff:192.168.1.1) — apply IPv4 classification
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_private_or_reserved_host(hostname: str) -> bool:
    """Return True if hostname is a loopback/private/link-local/reserved target.

    Covers numeric IP literals (via ``ipaddress``), non-standard IP notation
    (via ``socket.inet_aton``), a small blocklist of well-known internal
    hostnames, and DNS resolution of arbitrary hostnames to catch DNS rebinding
    attacks where a public-looking hostname resolves to a private IP.

    **TOCTOU note:** This function alone is advisory — ``requests`` performs its
    own independent DNS resolution.  The ingestion worker closes this gap by
    calling :func:`resolve_and_validate_host` and pinning the result via
    ``urllib3.util.connection`` (see ``ingestion.py``).  Other callers (e.g.
    ``Feed.from_dict``) still have the advisory-only window, which is
    acceptable for config-load-time validation.
    """
    host_lower = hostname.lower().rstrip(".")
    if host_lower in _BLOCKED_HOSTNAMES:
        return True
    # `.localhost` and `.internal` TLDs are conventionally internal
    if host_lower.endswith(".localhost") or host_lower.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host_lower)
    except ValueError:
        # ipaddress is strict — try socket.inet_aton which handles octal
        # (0177.0.0.1), decimal (2130706433), hex (0x7f000001), and
        # abbreviated (127.1) forms that OS resolvers accept as loopback/private.
        try:
            packed = socket.inet_aton(host_lower)
            ip = ipaddress.ip_address(socket.inet_ntoa(packed))
        except OSError:
            # Not a numeric IP — resolve via DNS and check all returned IPs.
            # This catches DNS rebinding attacks where a public hostname
            # resolves to a private/reserved IP at fetch time.
            return _dns_resolves_to_private(host_lower)
    return _is_private_ip(ip)


def _dns_resolves_to_private(hostname: str) -> bool:
    """Resolve hostname via DNS and return True if ANY resolved IP is private.

    Returns False on resolution failure (DNS errors are not treated as
    private — the subsequent HTTP request will fail with a clear error).
    """
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return False
    for family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_private_ip(ip):
            logger.warning(
                "Hostname %r resolves to private IP %s — blocking",
                hostname, ip,
            )
            return True
    return False


def resolve_and_validate_host(hostname: str) -> str:
    """Resolve hostname via DNS, validate ALL IPs are non-private, return first safe IP.

    Raises ``ValueError`` if any resolved IP is private/reserved, or if the
    hostname is in the blocked list.  Raises ``OSError`` on DNS failure.

    The returned IP string can be passed to :func:`pin_dns` to close the
    TOCTOU gap between validation and the actual HTTP connection.
    """
    host_lower = hostname.lower().rstrip(".")
    if host_lower in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname {hostname!r} is blocked")
    if host_lower.endswith(".localhost") or host_lower.endswith(".internal"):
        raise ValueError(f"Hostname {hostname!r} uses a reserved TLD")

    # Check numeric IP literals first
    try:
        ip = ipaddress.ip_address(host_lower)
    except ValueError:
        pass  # Not a numeric IP — fall through to DNS resolution
    else:
        if _is_private_ip(ip):
            raise ValueError(f"IP {ip} is private/reserved")
        return str(ip)

    # Resolve via DNS
    infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    first_safe: str | None = None
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_private_ip(ip):
            raise ValueError(
                f"Hostname {hostname!r} resolves to private IP {ip}"
            )
        if first_safe is None:
            first_safe = sockaddr[0]

    if first_safe is None:
        raise ValueError(f"Hostname {hostname!r} resolved to no usable addresses")

    return first_safe
