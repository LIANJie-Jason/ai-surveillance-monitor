# tests/test_map_drilldown.py
"""Tests for the drill-down map component."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# --- load_regions tests ---


def test_load_regions_returns_dict():
    """load_regions should return a dict keyed by country code."""
    from dashboard.components.map_drilldown import load_regions
    regions = load_regions()
    assert isinstance(regions, dict)
    assert len(regions) == 4  # IN, MY, NG, ZA


def test_load_regions_has_drill_down_countries():
    """All 4 drill-down countries must be present."""
    from dashboard.components.map_drilldown import load_regions
    regions = load_regions()
    for cc in ["IN", "MY", "NG", "ZA"]:
        assert cc in regions, f"Missing country: {cc}"


def test_load_regions_structure():
    """Each region should have name, lat, lng, and aliases."""
    from dashboard.components.map_drilldown import load_regions
    regions = load_regions()
    for cc, region_list in regions.items():
        assert isinstance(region_list, list)
        assert len(region_list) >= 5, f"{cc} should have at least 5 regions"
        for region in region_list:
            assert "name" in region
            assert "lat" in region
            assert "lng" in region
            assert "aliases" in region
            assert isinstance(region["aliases"], list)


def test_load_regions_coords_valid():
    """All region coordinates must be valid lat/lng."""
    from dashboard.components.map_drilldown import load_regions
    regions = load_regions()
    for cc, region_list in regions.items():
        for region in region_list:
            assert -90 <= region["lat"] <= 90, f"{cc}/{region['name']} lat out of range"
            assert -180 <= region["lng"] <= 180, f"{cc}/{region['name']} lng out of range"


# --- get_country_center tests ---


def test_get_country_center_returns_coords():
    """Should return lat/lng/zoom for drill-down countries."""
    from dashboard.components.map_drilldown import get_country_center
    for cc in ["IN", "MY", "NG", "ZA"]:
        center = get_country_center(cc)
        assert "lat" in center
        assert "lng" in center
        assert "zoom" in center
        assert -90 <= center["lat"] <= 90
        assert -180 <= center["lng"] <= 180
        assert center["zoom"] >= 3


def test_get_country_center_unknown_returns_none():
    """Unknown country code should return None."""
    from dashboard.components.map_drilldown import get_country_center
    assert get_country_center("XX") is None


# --- build_region_data tests ---


def test_build_region_data_aggregates_by_region():
    """Should group articles by region and return coords + counts."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code="IN", is_surveillance=True, confidence=0.9),
        Article(id="a2", url="https://a.com/2", title="T2", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code="IN", is_surveillance=True, confidence=0.8),
        Article(id="a3", url="https://a.com/3", title="T3", source_name="S",
                source_lang="en", source_tier=1, region="Mumbai",
                country_code="IN", is_surveillance=True, confidence=0.7),
    ]
    data = build_region_data(articles, "IN")
    assert isinstance(data, list)
    # Should have 2 regions: Delhi (2 articles) and Mumbai (1)
    names = {d["region_name"] for d in data}
    assert "Delhi" in names
    assert "Mumbai" in names
    delhi = next(d for d in data if d["region_name"] == "Delhi")
    assert delhi["count"] == 2
    assert "lat" in delhi
    assert "lng" in delhi


def test_build_region_data_resolves_aliases():
    """Should resolve alias names to canonical region."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Bombay",
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 1
    assert data[0]["region_name"] == "Mumbai"  # Bombay → Mumbai


def test_build_region_data_skips_unknown_region():
    """Articles with unrecognized region should be skipped."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Atlantis",
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 0


def test_build_region_data_skips_none_region():
    """Articles with no region should be skipped."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region=None,
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 0


def test_build_region_data_empty_articles():
    """Empty article list should return empty data."""
    from dashboard.components.map_drilldown import build_region_data
    assert build_region_data([], "IN") == []


def test_build_region_data_case_insensitive():
    """Region matching should be case-insensitive."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="DELHI",
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 1
    assert data[0]["region_name"] == "Delhi"


# --- render_drilldown_html tests ---


def test_render_drilldown_html_injects_data():
    """Should produce HTML with injected region data."""
    from dashboard.components.map_drilldown import render_drilldown_html
    data = [{"lat": 28.6, "lng": 77.2, "count": 5, "region_name": "Delhi"}]
    center = {"lat": 20.59, "lng": 78.96, "zoom": 4.5}
    html = render_drilldown_html(data, center)
    assert isinstance(html, str)
    assert "Delhi" in html
    assert "28.6" in html


def test_render_drilldown_html_empty_data():
    """Empty data should still produce valid HTML."""
    from dashboard.components.map_drilldown import render_drilldown_html
    center = {"lat": 20.59, "lng": 78.96, "zoom": 4.5}
    html = render_drilldown_html([], center)
    assert "deck" in html.lower() or "script" in html.lower()


def test_render_drilldown_html_escapes_script():
    """Data containing </script> must not break out of the script block."""
    from dashboard.components.map_drilldown import render_drilldown_html
    data = [{"lat": 0, "lng": 0, "count": 1, "region_name": '</script><script>alert(1)</script>'}]
    center = {"lat": 0, "lng": 0, "zoom": 5}
    html = render_drilldown_html(data, center)
    assert "</script><script>" not in html


# --- Error handling tests ---


def test_load_regions_caches_result():
    """load_regions should return the same object on repeated calls (cached)."""
    from dashboard.components.map_drilldown import load_regions
    r1 = load_regions()
    r2 = load_regions()
    assert r1 is r2


def test_get_country_center_returns_copy():
    """Returned dict must be a copy so callers can't mutate shared state."""
    from dashboard.components.map_drilldown import get_country_center
    c1 = get_country_center("IN")
    c2 = get_country_center("IN")
    assert c1 is not c2
    assert c1 == c2


def test_build_region_data_skips_wrong_country():
    """Articles with mismatched country_code should be skipped."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code="NG", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 0


def test_build_region_data_includes_country_fields():
    """Output dicts should include country_code and country_name for tooltip."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 1
    assert "country_code" in data[0]
    assert "country_name" in data[0]
    assert data[0]["country_code"] == "IN"


def test_build_region_data_skips_none_country_code():
    """M24: Articles with country_code=None should be excluded from drilldown."""
    from dashboard.components.map_drilldown import build_region_data
    from src.models import Article

    articles = [
        Article(id="a1", url="https://a.com/1", title="T1", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code=None, is_surveillance=True, confidence=0.9),
        Article(id="a2", url="https://a.com/2", title="T2", source_name="S",
                source_lang="en", source_tier=1, region="Delhi",
                country_code="IN", is_surveillance=True, confidence=0.9),
    ]
    data = build_region_data(articles, "IN")
    assert len(data) == 1
    assert data[0]["count"] == 1  # Only a2 counted, not a1


def test_render_drilldown_html_overrides_view_state():
    """Rendered HTML should use the provided center, not the global default."""
    from dashboard.components.map_drilldown import render_drilldown_html
    center = {"lat": -30.56, "lng": 22.94, "zoom": 5.0}
    html = render_drilldown_html([], center)
    assert "-30.56" in html
    assert "22.94" in html


def test_render_drilldown_html_replaces_placeholder():
    """R2: render_drilldown_html should replace __INITIAL_VIEW_STATE__ placeholder."""
    from dashboard.components.map_drilldown import render_drilldown_html
    center = {"lat": 20.59, "lng": 78.96, "zoom": 4.5}
    html = render_drilldown_html([], center)
    assert "__INITIAL_VIEW_STATE__" not in html
    assert "latitude: 20.59," in html
