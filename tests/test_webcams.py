# tests/test_webcams.py
"""Tests for the webcam grid component."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


# --- Fixtures / helpers ---

_MOCK_WEBCAMS: dict[str, Any] = {
    "webcams": {
        "IN": [
            {
                "city": "Delhi",
                "embed_url": "https://www.youtube.com/embed/abc123?autoplay=1&mute=1",
                "type": "webcam",
                "lat": 28.6139,
                "lng": 77.2090,
                "source": "SkylineWebcams",
            },
            {
                "city": "Mumbai",
                "embed_url": "https://www.youtube.com/embed/def456?autoplay=1&mute=1",
                "type": "webcam",
                "lat": 19.0760,
                "lng": 72.8777,
                "source": "SkylineWebcams",
            },
            {
                "city": "Bangalore",
                "embed_url": "https://www.youtube.com/embed/ghi789?autoplay=1&mute=1",
                "type": "webcam",
                "lat": 12.9716,
                "lng": 77.5946,
                "source": "wxyzwebcams.com",
            },
            {
                "city": "Chennai",
                "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCtest",
                "type": "news_fallback",
                "lat": 13.0827,
                "lng": 80.2707,
                "source": "ABP News",
            },
        ],
        "ZA": [
            {
                "city": "Cape Town",
                "embed_url": "https://www.youtube.com/embed/xyz999?autoplay=1&mute=1",
                "type": "webcam",
                "lat": -33.9249,
                "lng": 18.4241,
                "source": "SkylineWebcams",
            },
        ],
    }
}


def _patch_webcams(mock_data: dict | None = None):
    """Patch load_webcams to return mock data."""
    data = mock_data if mock_data is not None else _MOCK_WEBCAMS
    return patch(
        "dashboard.components.webcams.load_webcams",
        return_value=data,
    )


# ===================================================================
# load_webcams tests
# ===================================================================


def test_load_webcams_returns_dict():
    """load_webcams should return a dict with 'webcams' key."""
    from dashboard.components.webcams import load_webcams
    data = load_webcams()
    assert isinstance(data, dict)
    assert "webcams" in data


def test_load_webcams_cached():
    """load_webcams should be cached."""
    from dashboard.components.webcams import load_webcams
    a = load_webcams()
    b = load_webcams()
    assert a is b


def test_load_webcams_handles_missing_file(tmp_path):
    """Should return empty structure if YAML is missing."""
    from dashboard.components.webcams import load_webcams
    import dashboard.components.webcams as mod
    original = mod._CONFIG_PATH
    mod._CONFIG_PATH = tmp_path / "nonexistent.yaml"
    load_webcams.cache_clear()
    try:
        result = load_webcams()
        assert result == {"webcams": {}}
    finally:
        mod._CONFIG_PATH = original
        load_webcams.cache_clear()


def test_load_webcams_handles_malformed_yaml(tmp_path):
    """Should return empty structure if YAML is malformed."""
    from dashboard.components.webcams import load_webcams
    import dashboard.components.webcams as mod
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("{{{invalid", encoding="utf-8")
    original = mod._CONFIG_PATH
    mod._CONFIG_PATH = bad_file
    load_webcams.cache_clear()
    try:
        result = load_webcams()
        assert result == {"webcams": {}}
    finally:
        mod._CONFIG_PATH = original
        load_webcams.cache_clear()


# ===================================================================
# get_webcams_for_country tests
# ===================================================================


def test_get_webcams_known_country():
    """Should return list of webcam dicts for a known country."""
    from dashboard.components.webcams import get_webcams_for_country
    with _patch_webcams():
        cams = get_webcams_for_country("IN")
    assert isinstance(cams, list)
    assert len(cams) == 4


def test_get_webcams_unknown_country():
    """Should return empty list for unknown country."""
    from dashboard.components.webcams import get_webcams_for_country
    with _patch_webcams():
        cams = get_webcams_for_country("XX")
    assert cams == []


def test_get_webcams_returns_copies():
    """Should return copies, not references to config."""
    from dashboard.components.webcams import get_webcams_for_country
    with _patch_webcams():
        a = get_webcams_for_country("IN")
        b = get_webcams_for_country("IN")
    assert a == b
    assert a is not b


# ===================================================================
# render_webcam_grid tests
# ===================================================================


def test_render_webcam_grid_returns_html():
    """Should return an HTML string."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert isinstance(html, str)
    assert len(html) > 0


def test_render_webcam_grid_contains_iframes():
    """Should contain iframes for each webcam."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert html.count("<iframe") == 4


def test_render_webcam_grid_contains_city_labels():
    """Should show city names."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert "Delhi" in html
    assert "Mumbai" in html
    assert "Bangalore" in html
    assert "Chennai" in html


def test_render_webcam_grid_contains_live_badge():
    """Should show LIVE badge on webcam entries."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert "LIVE" in html


def test_render_webcam_grid_news_fallback_badge():
    """news_fallback type should show a different badge (NEWS) instead of LIVE."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert "NEWS" in html


def test_render_webcam_grid_contains_embed_urls():
    """Should embed the correct URLs."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert "abc123" in html
    assert "def456" in html


def test_render_webcam_grid_uses_grid_layout():
    """Should use CSS grid or flex for 2x2 layout."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN")
    assert "grid" in html.lower() or "flex" in html.lower()


def test_render_webcam_grid_unknown_country():
    """Unknown country should show placeholder."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("XX")
    assert "no" in html.lower() or "unavailable" in html.lower()
    assert "<iframe" not in html


def test_render_webcam_grid_empty_embed_url():
    """Webcam with empty embed_url should show placeholder, not iframe."""
    from dashboard.components.webcams import render_webcam_grid
    empty_data = {
        "webcams": {
            "XX": [
                {
                    "city": "TestCity",
                    "embed_url": "",
                    "type": "webcam",
                    "lat": 0.0,
                    "lng": 0.0,
                    "source": "test",
                },
            ],
        }
    }
    with _patch_webcams(empty_data):
        html = render_webcam_grid("XX")
    assert "TestCity" in html
    assert "<iframe" not in html
    assert "no" in html.lower() or "unavailable" in html.lower()


def test_render_webcam_grid_escapes_city_name():
    """City name must be HTML-escaped."""
    from dashboard.components.webcams import render_webcam_grid
    xss_data = {
        "webcams": {
            "XX": [
                {
                    "city": '<script>alert("xss")</script>',
                    "embed_url": "https://www.youtube.com/embed/test?autoplay=1",
                    "type": "webcam",
                    "lat": 0.0,
                    "lng": 0.0,
                    "source": "test",
                },
            ],
        }
    }
    with _patch_webcams(xss_data):
        html = render_webcam_grid("XX")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_webcam_grid_validates_url_scheme():
    """Webcam with non-https URL should not render as iframe."""
    from dashboard.components.webcams import render_webcam_grid
    bad_data = {
        "webcams": {
            "XX": [
                {
                    "city": "BadCity",
                    "embed_url": "javascript:alert(1)",
                    "type": "webcam",
                    "lat": 0.0,
                    "lng": 0.0,
                    "source": "test",
                },
            ],
        }
    }
    with _patch_webcams(bad_data):
        html = render_webcam_grid("XX")
    assert "javascript:" not in html


def test_render_webcam_grid_iframe_attributes():
    """Iframes should have muted autoplay and no border."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("ZA")
    assert 'frameborder="0"' in html
    assert "allowfullscreen" in html


def test_render_webcam_grid_single_cam():
    """Country with 1 webcam should still render grid."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("ZA")
    assert "Cape Town" in html
    assert "<iframe" in html


def test_render_webcam_grid_height_customizable():
    """Should respect custom height parameter."""
    from dashboard.components.webcams import render_webcam_grid
    with _patch_webcams():
        html = render_webcam_grid("IN", cam_height=300)
    assert "300" in html
