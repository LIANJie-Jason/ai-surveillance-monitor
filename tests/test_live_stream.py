# tests/test_live_stream.py
"""Tests for the live stream component."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


# --- Fixtures / helpers ---

_MOCK_STREAMS: dict[str, Any] = {
    "streams": {
        "IN": {
            "name": "NDTV 24x7",
            "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCtest1",
            "language": "en",
            "description": "India's leading news channel",
        },
        "MY": {
            "name": "Astro Awani",
            "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCtest2",
            "language": "ms",
            "description": "Malaysia's news channel",
        },
    },
    "fallbacks": {
        "IN": {
            "name": "India Today",
            "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCfallback1",
            "language": "en",
            "description": "India Today's news channel",
        },
        "MY": {
            "name": "Bernama TV",
            "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCfallback2",
            "language": "ms",
            "description": "Malaysian National News Agency",
        },
    },
}


def _patch_streams(mock_data: dict | None = None):
    """Patch load_streams to return mock data."""
    data = mock_data if mock_data is not None else _MOCK_STREAMS
    return patch(
        "dashboard.components.live_stream.load_streams",
        return_value=data,
    )


# ===================================================================
# load_streams tests
# ===================================================================


def test_load_streams_returns_dict():
    """load_streams should return a dict with 'streams' and 'fallbacks' keys."""
    from dashboard.components.live_stream import load_streams
    data = load_streams()
    assert isinstance(data, dict)
    assert "streams" in data
    assert "fallbacks" in data


def test_load_streams_cached():
    """load_streams should be cached (same object on repeated calls)."""
    from dashboard.components.live_stream import load_streams
    a = load_streams()
    b = load_streams()
    assert a is b


def test_load_streams_handles_missing_file(tmp_path):
    """Should return empty structure if YAML file is missing."""
    from dashboard.components.live_stream import load_streams
    import dashboard.components.live_stream as mod
    original = mod._CONFIG_PATH
    mod._CONFIG_PATH = tmp_path / "nonexistent.yaml"
    # Clear cache
    load_streams.cache_clear()
    try:
        result = load_streams()
        assert result == {"streams": {}, "fallbacks": {}}
    finally:
        mod._CONFIG_PATH = original
        load_streams.cache_clear()


def test_load_streams_handles_malformed_yaml(tmp_path):
    """Should return empty structure if YAML is malformed."""
    from dashboard.components.live_stream import load_streams
    import dashboard.components.live_stream as mod
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("[[[invalid yaml", encoding="utf-8")
    original = mod._CONFIG_PATH
    mod._CONFIG_PATH = bad_file
    load_streams.cache_clear()
    try:
        result = load_streams()
        assert result == {"streams": {}, "fallbacks": {}}
    finally:
        mod._CONFIG_PATH = original
        load_streams.cache_clear()


# ===================================================================
# get_stream_for_country tests
# ===================================================================


def test_get_stream_known_country():
    """Should return the primary stream dict for a known country."""
    from dashboard.components.live_stream import get_stream_for_country
    with _patch_streams():
        stream = get_stream_for_country("IN")
    assert stream is not None
    assert stream["name"] == "NDTV 24x7"
    assert "embed_url" in stream


def test_get_stream_unknown_country():
    """Should return None for an unknown country code."""
    from dashboard.components.live_stream import get_stream_for_country
    with _patch_streams():
        stream = get_stream_for_country("XX")
    assert stream is None


def test_get_stream_returns_copy():
    """Returned dict should be a copy, not a reference to the config."""
    from dashboard.components.live_stream import get_stream_for_country
    with _patch_streams():
        a = get_stream_for_country("IN")
        b = get_stream_for_country("IN")
    assert a == b
    assert a is not b


# ===================================================================
# get_fallback_stream tests
# ===================================================================


def test_get_fallback_known_country():
    """Should return the fallback stream dict."""
    from dashboard.components.live_stream import get_fallback_stream
    with _patch_streams():
        stream = get_fallback_stream("IN")
    assert stream is not None
    assert stream["name"] == "India Today"


def test_get_fallback_unknown_country():
    """Should return None for unknown country."""
    from dashboard.components.live_stream import get_fallback_stream
    with _patch_streams():
        stream = get_fallback_stream("XX")
    assert stream is None


# ===================================================================
# render_live_stream tests
# ===================================================================


def test_render_live_stream_returns_html():
    """Should return an HTML string."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN")
    assert isinstance(html, str)
    assert len(html) > 0


def test_render_live_stream_contains_iframe():
    """Should contain a YouTube iframe."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN")
    assert "<iframe" in html
    assert "youtube.com" in html


def test_render_live_stream_contains_stream_name():
    """Should show the stream name."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN")
    assert "NDTV 24x7" in html


def test_render_live_stream_contains_embed_url():
    """Should embed the correct URL."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN")
    assert "UCtest1" in html


def test_render_live_stream_iframe_attributes():
    """Iframe should have frameborder=0 and allowfullscreen."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN")
    assert 'frameborder="0"' in html
    assert "allowfullscreen" in html


def test_render_live_stream_unknown_country():
    """Unknown country should show a 'no stream available' placeholder."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("XX")
    assert "no" in html.lower() or "unavailable" in html.lower()
    assert "<iframe" not in html


def test_render_live_stream_escapes_name():
    """Stream name must be HTML-escaped."""
    import html as html_mod
    from dashboard.components.live_stream import render_live_stream
    xss_streams = {
        "streams": {
            "XX": {
                "name": '<script>alert("xss")</script>',
                "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCtest",
                "language": "en",
                "description": "test",
            },
        },
        "fallbacks": {},
    }
    with _patch_streams(xss_streams):
        html = render_live_stream("XX")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_live_stream_escapes_description():
    """Description must be HTML-escaped."""
    from dashboard.components.live_stream import render_live_stream
    xss_streams = {
        "streams": {
            "XX": {
                "name": "Safe Name",
                "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCtest",
                "language": "en",
                "description": '<img onerror="alert(1)">',
            },
        },
        "fallbacks": {},
    }
    with _patch_streams(xss_streams):
        html = render_live_stream("XX")
    assert '<img onerror' not in html


def test_render_live_stream_url_scheme_validation():
    """Embed URL with non-https scheme should not render as iframe."""
    from dashboard.components.live_stream import render_live_stream
    bad_streams = {
        "streams": {
            "XX": {
                "name": "Bad Stream",
                "embed_url": "javascript:alert(1)",
                "language": "en",
                "description": "test",
            },
        },
        "fallbacks": {},
    }
    with _patch_streams(bad_streams):
        html = render_live_stream("XX")
    assert "javascript:" not in html


def test_render_live_stream_with_fallback_flag():
    """When use_fallback=True, should show fallback stream."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN", use_fallback=True)
    assert "India Today" in html
    assert "UCfallback1" in html


def test_render_live_stream_fallback_no_country():
    """Fallback for unknown country should show placeholder."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("XX", use_fallback=True)
    assert "<iframe" not in html


def test_render_live_stream_height_customizable():
    """Should respect custom height parameter."""
    from dashboard.components.live_stream import render_live_stream
    with _patch_streams():
        html = render_live_stream("IN", height=500)
    assert "500" in html
