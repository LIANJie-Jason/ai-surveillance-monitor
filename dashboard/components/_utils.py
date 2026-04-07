"""Shared utilities for dashboard components."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from src.url_utils import is_private_or_reserved_host


def safe_json_for_script(data: Any) -> str:
    """JSON-encode data and escape HTML-sensitive chars for safe <script> embedding.

    Used when injecting JSON data into HTML <script> blocks in deck.gl
    templates. Escapes ``<``, ``>``, and ``&`` as their Unicode escape
    sequences — matching the approach used by Django and Google Closure
    to prevent ``</script>`` breakout and related XSS vectors.
    """
    blob = json.dumps(data, ensure_ascii=True)
    # ensure_ascii=True already escapes U+2028/U+2029 as \u2028/\u2029
    return (
        blob
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
    )


def safe_embed_url(url: str) -> str:
    """Return url only if it uses https scheme with a non-private hostname; empty string otherwise."""
    if not url or not isinstance(url, str):
        return ""
    # Strip leading/trailing whitespace (YAML parsers may preserve trailing
    # spaces in quoted strings) then reject null bytes.
    url = url.strip()
    if "\x00" in url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return ""
        if not parsed.hostname:
            return ""
        if is_private_or_reserved_host(parsed.hostname):
            return ""
    except (ValueError, TypeError):
        return ""
    return url
