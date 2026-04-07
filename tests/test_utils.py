"""Tests for dashboard/components/_utils.py — safe_embed_url security gate."""

import pytest

from dashboard.components._utils import safe_embed_url


class TestSafeEmbedUrl:
    """Verify safe_embed_url accepts only https URLs with valid hostnames."""

    def test_accepts_valid_https(self) -> None:
        url = "https://www.youtube.com/embed/abc123"
        assert safe_embed_url(url) == url

    def test_accepts_https_with_port(self) -> None:
        url = "https://example.com:8443/path"
        assert safe_embed_url(url) == url

    def test_rejects_http(self) -> None:
        assert safe_embed_url("http://example.com/video") == ""

    def test_rejects_javascript_scheme(self) -> None:
        assert safe_embed_url("javascript:alert(1)") == ""

    def test_rejects_data_scheme(self) -> None:
        assert safe_embed_url("data:text/html,<h1>XSS</h1>") == ""

    def test_rejects_empty_string(self) -> None:
        assert safe_embed_url("") == ""

    def test_rejects_hostless_https(self) -> None:
        assert safe_embed_url("https://") == ""

    def test_rejects_https_colon_javascript(self) -> None:
        """Scheme-confusion vector: https:javascript:alert(1)."""
        assert safe_embed_url("https:javascript:alert(1)") == ""

    def test_rejects_ftp_scheme(self) -> None:
        assert safe_embed_url("ftp://files.example.com/video.mp4") == ""

    def test_rejects_file_scheme(self) -> None:
        assert safe_embed_url("file:///etc/passwd") == ""

    def test_rejects_none_like_falsy(self) -> None:
        """None is not a valid URL — should return empty string."""
        # safe_embed_url expects str; passing None tests the falsy guard
        assert safe_embed_url(None) == ""  # type: ignore[arg-type]

    def test_rejects_relative_url(self) -> None:
        assert safe_embed_url("/path/to/resource") == ""

    def test_rejects_protocol_relative(self) -> None:
        assert safe_embed_url("//example.com/embed") == ""

    def test_accepts_skylinewebcams(self) -> None:
        url = "https://www.skylinewebcams.com/en/webcam/south-africa.html"
        assert safe_embed_url(url) == url

    def test_rejects_null_byte_injection(self) -> None:
        """Null byte in URL must not pass through to iframe src."""
        assert safe_embed_url("https://evil.com\x00https://good.com") == ""

    def test_strips_leading_whitespace(self) -> None:
        """Leading whitespace is stripped before validation (YAML tolerance)."""
        assert safe_embed_url("  https://example.com/embed") == "https://example.com/embed"

    def test_strips_trailing_whitespace(self) -> None:
        """Trailing whitespace is stripped before validation (YAML tolerance)."""
        assert safe_embed_url("https://example.com/embed ") == "https://example.com/embed"

    def test_rejects_integer_input(self) -> None:
        """Non-string input (int) should return empty, not raise TypeError."""
        assert safe_embed_url(123) == ""  # type: ignore[arg-type]

    def test_rejects_malformed_ipv6(self) -> None:
        """Malformed IPv6 that may raise ValueError in urlparse."""
        assert safe_embed_url("https://[::::::invalid/path") == ""
