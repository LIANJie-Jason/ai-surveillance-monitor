# tests/test_map_globe.py
"""Tests for the globe view component (dashboard/components/map_globe.py)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


_STATIC_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "static"
_DECK_GLOBE_PATH = _STATIC_DIR / "deck_globe.html"


# ── FOCUS_COUNTRIES constant ─────────────────────────────────────────────


def test_focus_countries_matches_drill_down_countries():
    """FOCUS_COUNTRIES must be the same object/value as DRILL_DOWN_COUNTRIES."""
    from dashboard.components.map_global import DRILL_DOWN_COUNTRIES
    from dashboard.components.map_globe import FOCUS_COUNTRIES

    assert FOCUS_COUNTRIES is DRILL_DOWN_COUNTRIES


def test_focus_countries_contains_expected_codes():
    """FOCUS_COUNTRIES must contain IN, MY, NG, ZA."""
    from dashboard.components.map_globe import FOCUS_COUNTRIES

    assert set(FOCUS_COUNTRIES) == {"IN", "MY", "NG", "ZA"}


# ── build_globe_data ─────────────────────────────────────────────────────


def test_build_globe_data_delegates_to_build_map_data():
    """build_globe_data must produce identical output to build_map_data."""
    from dashboard.components.map_global import build_map_data
    from dashboard.components.map_globe import build_globe_data

    counts = {"US": 10, "IN": 5, "ZA": 3}
    assert build_globe_data(counts) == build_map_data(counts)


def test_build_globe_data_empty_input():
    """Empty dict should return empty list."""
    from dashboard.components.map_globe import build_globe_data

    assert build_globe_data({}) == []


def test_build_globe_data_valid_countries_return_lat_lng_count():
    """Valid country codes should produce dicts with lat, lng, count, country_code, country_name."""
    from dashboard.components.map_globe import build_globe_data

    data = build_globe_data({"IN": 7, "MY": 2})
    assert len(data) == 2
    for item in data:
        assert "lat" in item
        assert "lng" in item
        assert "count" in item
        assert "country_code" in item
        assert "country_name" in item
        assert isinstance(item["lat"], float)
        assert isinstance(item["lng"], float)
        assert isinstance(item["count"], int)


# ── render_globe_html ────────────────────────────────────────────────────


def test_render_globe_html_returns_string_with_html_markers():
    """Rendered output should be a string containing deck.gl and GlobeView references."""
    from dashboard.components.map_globe import render_globe_html

    html = render_globe_html([])
    assert isinstance(html, str)
    assert "deck.gl" in html or "deck.gl" in html.lower()
    assert "GlobeView" in html


def test_render_globe_html_replaces_article_data_placeholder():
    """__ARTICLE_DATA__ placeholder must be replaced with actual JSON."""
    from dashboard.components.map_globe import render_globe_html

    data = [{"lat": 20.59, "lng": 78.96, "count": 5,
             "country_code": "IN", "country_name": "India"}]
    html = render_globe_html(data)
    assert "__ARTICLE_DATA__" not in html
    assert "20.59" in html
    assert "India" in html


def test_render_globe_html_replaces_countries_geojson_placeholder():
    """__COUNTRIES_GEOJSON__ placeholder must be replaced."""
    from dashboard.components.map_globe import render_globe_html

    html = render_globe_html([])
    assert "__COUNTRIES_GEOJSON__" not in html
    # The GeoJSON FeatureCollection should be present
    assert "FeatureCollection" in html


def test_render_globe_html_replaces_focus_countries_placeholder():
    """__FOCUS_COUNTRIES__ placeholder must be replaced with JSON array."""
    from dashboard.components.map_globe import render_globe_html

    html = render_globe_html([])
    assert "__FOCUS_COUNTRIES__" not in html
    # All four focus country codes should appear in the rendered output
    for cc in ("IN", "MY", "NG", "ZA"):
        assert f'"{cc}"' in html


def test_render_globe_html_no_unreplaced_placeholders():
    """No double-underscore placeholders should remain after rendering."""
    from dashboard.components.map_globe import render_globe_html

    html = render_globe_html([])
    # Check for the three specific placeholders used by the template
    assert "__ARTICLE_DATA__" not in html
    assert "__COUNTRIES_GEOJSON__" not in html
    assert "__FOCUS_COUNTRIES__" not in html


def test_render_globe_html_xss_protection():
    """HTML-unsafe chars in data must be escaped to prevent </script> breakout."""
    from dashboard.components.map_globe import render_globe_html

    data = [{"lat": 0, "lng": 0, "count": 1, "country_code": "XX",
             "country_name": '</script><script>alert(1)</script>'}]
    html = render_globe_html(data)
    # Literal </script> inside data must NOT appear
    assert "</script><script>" not in html
    # The < should be escaped as \u003c
    assert r"\u003c/script>" in html or r"\u003c" in html


# ── _load_countries_geojson ──────────────────────────────────────────────


def test_load_countries_geojson_structure():
    """Loaded GeoJSON must have 'type' and 'features' keys."""
    from dashboard.components.map_globe import _load_countries_geojson, _clear_countries_cache

    _clear_countries_cache()
    geojson = _load_countries_geojson()
    assert isinstance(geojson, dict)
    assert geojson["type"] == "FeatureCollection"
    assert "features" in geojson
    assert len(geojson["features"]) > 0


def test_load_countries_geojson_features_have_iso2():
    """Each feature should contain an iso2 property for focus-country matching."""
    from dashboard.components.map_globe import _load_countries_geojson, _clear_countries_cache

    _clear_countries_cache()
    geojson = _load_countries_geojson()
    for feature in geojson["features"]:
        props = feature.get("properties", {})
        assert "iso2" in props, f"Feature missing iso2: {props}"


def test_load_countries_geojson_cache_returns_same_object():
    """Second call should return the exact same cached object (identity check)."""
    from dashboard.components.map_globe import _load_countries_geojson, _clear_countries_cache

    _clear_countries_cache()
    first = _load_countries_geojson()
    second = _load_countries_geojson()
    assert first is second


# ── _clear_countries_cache ───────────────────────────────────────────────


def test_clear_countries_cache_forces_reload():
    """After clearing cache, the next load should read from file again (new object)."""
    from dashboard.components.map_globe import _load_countries_geojson, _clear_countries_cache

    _clear_countries_cache()
    first = _load_countries_geojson()
    _clear_countries_cache()
    second = _load_countries_geojson()
    # Both should be equal in value but be different objects (freshly loaded)
    assert first == second
    assert first is not second


# ── Template file existence & placeholders ───────────────────────────────


def test_deck_globe_html_exists():
    """The deck_globe.html template must exist at the expected path."""
    assert _DECK_GLOBE_PATH.is_file()


def test_deck_globe_html_contains_all_placeholders():
    """Template must contain all three expected placeholders before rendering."""
    text = _DECK_GLOBE_PATH.read_text(encoding="utf-8")
    assert "__ARTICLE_DATA__" in text
    assert "__COUNTRIES_GEOJSON__" in text
    assert "__FOCUS_COUNTRIES__" in text
