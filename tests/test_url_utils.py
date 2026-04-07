"""Tests for src/url_utils.py — SSRF/private-host validation (CC2-H27).

This is a security-critical module: all tests verify that private, reserved,
and internal hosts are correctly blocked while public hosts pass through.
"""

from unittest.mock import patch

import pytest


# ------------------------------------------------------------------ #
#  is_private_or_reserved_host — numeric IPv4                         #
# ------------------------------------------------------------------ #


class TestPrivateIPv4:
    """Standard private/reserved IPv4 addresses must be blocked."""

    @pytest.mark.parametrize("ip", [
        "127.0.0.1",       # loopback
        "192.168.1.1",     # RFC 1918 Class C
        "10.0.0.1",        # RFC 1918 Class A
        "10.255.255.255",  # Class A upper bound
        "172.16.0.1",      # RFC 1918 Class B lower
        "172.31.255.255",  # RFC 1918 Class B upper
        "169.254.1.1",     # link-local
        "0.0.0.0",         # unspecified
        "255.255.255.255", # broadcast / reserved
    ])
    def test_private_ipv4_blocked(self, ip):
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host(ip) is True, f"{ip} should be blocked"


# ------------------------------------------------------------------ #
#  Non-standard IP notation (octal, abbreviated)                      #
# ------------------------------------------------------------------ #


class TestNonStandardIPNotation:
    """OS-level inet_aton accepts octal/hex/abbreviated forms that resolve
    to loopback or private addresses.  These MUST be caught."""

    def test_octal_loopback(self):
        """0177.0.0.1 == 127.0.0.1 in octal — must be blocked."""
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host("0177.0.0.1") is True

    def test_abbreviated_loopback(self):
        """127.1 resolves to 127.0.0.1 on most OSes — must be blocked."""
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host("127.1") is True


# ------------------------------------------------------------------ #
#  _BLOCKED_HOSTNAMES                                                  #
# ------------------------------------------------------------------ #


class TestBlockedHostnames:
    """Well-known internal hostnames in the explicit blocklist."""

    @pytest.mark.parametrize("hostname", [
        "localhost",
        "metadata.google.internal",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "instance-data",
        "instance-data.ec2.internal",
    ])
    def test_blocked_hostname(self, hostname):
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host(hostname) is True, (
            f"{hostname} should be in _BLOCKED_HOSTNAMES"
        )

    def test_blocked_hostname_case_insensitive(self):
        """Blocklist check should be case-insensitive (lowered)."""
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host("LOCALHOST") is True
        assert is_private_or_reserved_host("Metadata.Google.Internal") is True


# ------------------------------------------------------------------ #
#  .localhost and .internal TLD blocking                               #
# ------------------------------------------------------------------ #


class TestInternalTLDs:
    """.localhost and .internal TLDs are conventionally internal."""

    @pytest.mark.parametrize("hostname", [
        "app.localhost",
        "my-service.localhost",
        "deep.nested.localhost",
        "kubernetes.internal",
        "service.my-cluster.internal",
    ])
    def test_internal_tld_blocked(self, hostname):
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host(hostname) is True, (
            f"{hostname} should be blocked (internal TLD)"
        )

    def test_trailing_dot_internal_tld(self):
        """Trailing dot should be stripped before TLD check."""
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host("app.localhost.") is True
        assert is_private_or_reserved_host("service.internal.") is True


# ------------------------------------------------------------------ #
#  IPv4-mapped IPv6                                                    #
# ------------------------------------------------------------------ #


class TestIPv4MappedIPv6:
    """IPv4-mapped IPv6 addresses must apply IPv4 classification."""

    @pytest.mark.parametrize("ip", [
        "::ffff:192.168.1.1",
        "::ffff:10.0.0.1",
        "::ffff:127.0.0.1",
    ])
    def test_ipv4_mapped_ipv6_blocked(self, ip):
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host(ip) is True, (
            f"IPv4-mapped IPv6 {ip} should be blocked"
        )

    def test_ipv6_loopback(self):
        """Pure IPv6 loopback (::1) should also be blocked."""
        from src.url_utils import is_private_or_reserved_host

        assert is_private_or_reserved_host("::1") is True


# ------------------------------------------------------------------ #
#  Public hostnames that should NOT be blocked                         #
# ------------------------------------------------------------------ #


class TestPublicHostsAllowed:
    """Legitimate public hostnames and IPs must pass through."""

    @pytest.mark.parametrize("hostname", [
        "google.com",
        "example.com",
        "bbc.co.uk",
        "feeds.reuters.com",
        "8.8.8.8",          # Google public DNS
        "1.1.1.1",          # Cloudflare public DNS
        "93.184.216.34",    # example.com IP
    ])
    def test_public_host_not_blocked(self, hostname):
        from src.url_utils import is_private_or_reserved_host

        # Mock DNS resolution to return a public IP so we don't depend
        # on actual DNS lookups in the test environment.
        with patch("src.url_utils.socket.getaddrinfo") as mock_dns:
            # For hostnames that are not IPs, getaddrinfo returns public IP
            mock_dns.return_value = [
                (2, 1, 0, "", ("93.184.216.34", 0)),
            ]
            assert is_private_or_reserved_host(hostname) is False, (
                f"Public host {hostname} should NOT be blocked"
            )


# ------------------------------------------------------------------ #
#  _dns_resolves_to_private (mocked DNS resolution)                    #
# ------------------------------------------------------------------ #


class TestDNSResolvesToPrivate:
    """DNS resolution check should detect hostnames that resolve to
    private IPs (DNS rebinding attack vector)."""

    def test_hostname_resolving_to_private_ip_blocked(self):
        """A public-looking hostname that resolves to 192.168.x.x must be blocked."""
        from src.url_utils import is_private_or_reserved_host

        with patch("src.url_utils.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (2, 1, 0, "", ("192.168.1.100", 0)),
            ]
            assert is_private_or_reserved_host("evil-rebind.example.com") is True

    def test_hostname_resolving_to_loopback_blocked(self):
        """A hostname resolving to 127.0.0.1 must be blocked."""
        from src.url_utils import is_private_or_reserved_host

        with patch("src.url_utils.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (2, 1, 0, "", ("127.0.0.1", 0)),
            ]
            assert is_private_or_reserved_host("rebind-loopback.example.com") is True

    def test_hostname_resolving_to_public_ip_allowed(self):
        """A hostname resolving to a public IP should pass."""
        from src.url_utils import is_private_or_reserved_host

        with patch("src.url_utils.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (2, 1, 0, "", ("93.184.216.34", 0)),
            ]
            assert is_private_or_reserved_host("example.com") is False

    def test_dns_failure_returns_false(self):
        """DNS resolution failure should NOT be treated as private."""
        from src.url_utils import _dns_resolves_to_private
        import socket

        with patch("src.url_utils.socket.getaddrinfo", side_effect=socket.gaierror):
            assert _dns_resolves_to_private("nonexistent.example.com") is False

    def test_multiple_resolved_ips_any_private_blocks(self):
        """If any resolved IP is private, the hostname is blocked."""
        from src.url_utils import is_private_or_reserved_host

        with patch("src.url_utils.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (2, 1, 0, "", ("93.184.216.34", 0)),  # public
                (2, 1, 0, "", ("10.0.0.1", 0)),       # private
            ]
            assert is_private_or_reserved_host("multi-ip.example.com") is True
