# tests/test_map_global.py
"""Tests for the global map component."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_STATIC_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "static"
_DECK_MAP_PATH = _STATIC_DIR / "deck_map.html"


# --- deck_map.html tests ---


def test_deck_map_html_exists():
    """The deck_map.html template must exist."""
    assert _DECK_MAP_PATH.is_file()


def test_deck_map_html_not_empty():
    """Template should contain meaningful content."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert len(text) > 200


def test_deck_map_html_uses_dark_basemap():
    """Map should use Carto Dark Matter basemap (no API key needed)."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "dark_all" in text.lower() or "dark-matter" in text.lower() or "dark_matter" in text.lower()


def test_deck_map_html_has_deckgl_reference():
    """Template must reference the deck.gl library."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "deck.gl" in text.lower() or "deckgl" in text.lower() or "deck.gl" in text


def test_deck_map_html_has_data_placeholder():
    """Template must have the __DATA__ placeholder used by render_map_html."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "__DATA__" in text


def test_deck_map_html_has_view_state_placeholder():
    """R2: Template must have __INITIAL_VIEW_STATE__ placeholder."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "__INITIAL_VIEW_STATE__" in text


def test_deck_map_html_has_scatterplot_layer():
    """Template must use a ScatterplotLayer."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "ScatterplotLayer" in text


def test_deck_map_html_tooltip_uses_textcontent():
    """Tooltip must use textContent (not innerHTML) to prevent XSS."""
    text = _DECK_MAP_PATH.read_text(encoding="utf-8")
    assert "textContent" in text
    # Should NOT use innerHTML for tooltip content
    assert "innerHTML" not in text


# --- Country coordinates lookup ---


def test_country_coords_has_major_countries():
    """Lookup table should include at least 190 countries with lat/lng."""
    from dashboard.components.map_global import COUNTRY_COORDS
    assert len(COUNTRY_COORDS) >= 190
    # Check drill-down countries specifically
    for cc in ["MY", "NG", "IN", "ZA"]:
        assert cc in COUNTRY_COORDS, f"Missing drill-down country: {cc}"
        assert "lat" in COUNTRY_COORDS[cc]
        assert "lng" in COUNTRY_COORDS[cc]


def test_country_coords_values_are_valid():
    """All coordinates should be valid lat/lng ranges."""
    from dashboard.components.map_global import COUNTRY_COORDS
    for cc, coord in COUNTRY_COORDS.items():
        assert -90 <= coord["lat"] <= 90, f"{cc} lat out of range: {coord['lat']}"
        assert -180 <= coord["lng"] <= 180, f"{cc} lng out of range: {coord['lng']}"


# --- build_map_data ---


def test_build_map_data_maps_country_codes_to_coords():
    """Should convert country counts dict into list of dicts with lat/lng."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": 10, "IN": 5, "ZA": 3}
    data = build_map_data(counts)
    assert isinstance(data, list)
    assert len(data) == 3
    for item in data:
        assert "lat" in item
        assert "lng" in item
        assert "count" in item
        assert "country_code" in item
        assert "country_name" in item


def test_build_map_data_skips_unknown_country_codes():
    """Countries not in the lookup should be silently skipped."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": 10, "XX": 5}  # XX is not a real country
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "US"


def test_build_map_data_empty_counts():
    """Empty counts dict should return empty list."""
    from dashboard.components.map_global import build_map_data
    assert build_map_data({}) == []


def test_build_map_data_includes_country_name():
    """Each data point should include a human-readable country name."""
    from dashboard.components.map_global import build_map_data
    counts = {"IN": 7}
    data = build_map_data(counts)
    assert data[0]["country_name"] == "India"


# --- render_map_html ---


def test_render_map_html_injects_data():
    """render_map_html should inject JSON data into the template."""
    from dashboard.components.map_global import render_map_html
    data = [{"lat": 28.6, "lng": 77.2, "count": 5, "country_code": "IN", "country_name": "India"}]
    html = render_map_html(data)
    assert isinstance(html, str)
    assert "28.6" in html
    assert "India" in html


def test_render_map_html_empty_data():
    """Empty data should still produce valid HTML."""
    from dashboard.components.map_global import render_map_html
    html = render_map_html([])
    assert "<html" in html.lower() or "<!doctype" in html.lower() or "deck" in html.lower()


def test_render_map_html_escapes_json():
    """Data with special characters should be safely JSON-encoded."""
    from dashboard.components.map_global import render_map_html
    data = [{"lat": 0, "lng": 0, "count": 1, "country_code": "XX",
             "country_name": 'Test "quotes" & <tags>'}]
    html = render_map_html(data)
    # JSON encoding should handle quotes — escaped form must be present
    assert r'\"quotes\"' in html
    # < and > must be escaped for script safety (CC2-C4)
    assert r"\u003ctags\u003e" in html
    # & must be escaped too
    assert r"\u0026" in html


# --- DRILL_DOWN_COUNTRIES ---


def test_render_map_html_escapes_script_tag():
    """Data containing </script> must not break out of the script block (XSS)."""
    from dashboard.components.map_global import render_map_html
    data = [{"lat": 0, "lng": 0, "count": 1, "country_code": "XX",
             "country_name": '</script><script>alert(1)</script>'}]
    html = render_map_html(data)
    # The literal </script> must NOT appear in the rendered output
    assert "</script><script>" not in html
    # The escaped form should be present
    assert r"\u003c/script>" in html or r"\u003c/script\u003e" in html


def test_build_map_data_rejects_negative_count():
    """Negative counts should be silently skipped."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": -5, "IN": 3}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "IN"


def test_build_map_data_coerces_count_to_int():
    """Float counts should be coerced to int."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": 3.7}
    data = build_map_data(counts)
    assert data[0]["count"] == 3
    assert isinstance(data[0]["count"], int)


def test_build_map_data_skips_non_numeric_count():
    """Non-numeric count values should be silently skipped."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": "bad", "IN": 5}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "IN"


def test_build_map_data_skips_inf_count():
    """Infinite count values should be silently skipped."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": float("inf"), "IN": float("-inf"), "ZA": 3}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "ZA"


def test_build_map_data_rejects_negative_fractional():
    """Negative fractional counts like -0.1 should be rejected."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": -0.1, "IN": 2}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "IN"


def test_build_map_data_skips_huge_int():
    """Extremely large integers that overflow float should be skipped."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": 10**10000, "IN": 3}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "IN"


def test_build_map_data_skips_nan():
    """NaN count should be rejected by isfinite check."""
    from dashboard.components.map_global import build_map_data
    counts = {"US": float("nan"), "IN": 4}
    data = build_map_data(counts)
    assert len(data) == 1
    assert data[0]["country_code"] == "IN"


def test_render_map_html_replaces_view_state_placeholder():
    """R2: render_map_html should replace __INITIAL_VIEW_STATE__ with defaults."""
    from dashboard.components.map_global import render_map_html
    html = render_map_html([])
    assert "__INITIAL_VIEW_STATE__" not in html
    assert "latitude: 20," in html
    assert "longitude: 30," in html
    assert "zoom: 1.8," in html


def test_drill_down_countries_defined():
    """The drill-down countries constant must exist with the 4 expected countries."""
    from dashboard.components.map_global import DRILL_DOWN_COUNTRIES
    assert set(DRILL_DOWN_COUNTRIES) == {"MY", "NG", "IN", "ZA"}
