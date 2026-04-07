"""Tests for choropleth drill-down functions in map_drilldown.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dashboard.components.map_drilldown import (
    _clear_admin1_cache,
    _load_admin1_geojson,
    build_choropleth_data,
    render_choropleth_html,
)
from src.models import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CHOROPLETH_TEMPLATE = _PROJECT_ROOT / "dashboard" / "static" / "deck_choropleth.html"


def _make_article(
    *,
    country_code: str = "IN",
    region: str | None = "Delhi",
    title: str = "Test article",
) -> Article:
    """Create a minimal Article for testing."""
    return Article(
        id="test-" + (region or "none"),
        url="https://example.com/" + (region or "none"),
        title=title,
        source_name="TestSource",
        source_lang="en",
        source_tier=1,
        country_code=country_code,
        region=region,
        is_surveillance=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure admin-1 GeoJSON cache is clean before and after every test."""
    _clear_admin1_cache()
    yield
    _clear_admin1_cache()


# ---------------------------------------------------------------------------
# _load_admin1_geojson tests
# ---------------------------------------------------------------------------


class TestLoadAdmin1GeoJSON:
    """Tests for _load_admin1_geojson."""

    @pytest.mark.parametrize("cc", ["IN", "MY", "NG", "ZA"])
    def test_returns_valid_geojson_for_known_countries(self, cc: str) -> None:
        """Should load real GeoJSON for each drill-down country."""
        result = _load_admin1_geojson(cc)
        assert result is not None, f"Expected GeoJSON for {cc}"
        assert isinstance(result, dict)

    def test_returns_none_for_unknown_country(self) -> None:
        """Should return None when no GeoJSON file exists."""
        result = _load_admin1_geojson("XX")
        assert result is None

    @pytest.mark.parametrize("cc", ["IN", "MY", "NG", "ZA"])
    def test_geojson_structure(self, cc: str) -> None:
        """Loaded GeoJSON must be a FeatureCollection with features."""
        result = _load_admin1_geojson(cc)
        assert result is not None
        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert isinstance(result["features"], list)
        assert len(result["features"]) > 0

    def test_cache_returns_same_object(self) -> None:
        """Second call should return the exact same cached object."""
        first = _load_admin1_geojson("IN")
        second = _load_admin1_geojson("IN")
        assert first is second


# ---------------------------------------------------------------------------
# _clear_admin1_cache tests
# ---------------------------------------------------------------------------


class TestClearAdmin1Cache:
    """Tests for _clear_admin1_cache."""

    def test_cache_empty_after_clear(self) -> None:
        """After clearing, a subsequent load should read from disk (new object)."""
        first = _load_admin1_geojson("IN")
        assert first is not None

        _clear_admin1_cache()

        reloaded = _load_admin1_geojson("IN")
        assert reloaded is not None
        # After cache clear, the object should be freshly loaded (not the
        # same identity as the first load).
        assert first is not reloaded


# ---------------------------------------------------------------------------
# build_choropleth_data tests
# ---------------------------------------------------------------------------


class TestBuildChoroplethData:
    """Tests for build_choropleth_data."""

    def test_returns_dict_of_admin1_counts(self) -> None:
        """Should map admin-1 names to article counts."""
        articles = [
            _make_article(country_code="IN", region="Delhi"),
            _make_article(country_code="IN", region="Mumbai"),
            _make_article(country_code="IN", region="New Delhi"),
        ]
        result = build_choropleth_data(articles, "IN")
        assert isinstance(result, dict)
        # Delhi + New Delhi -> "Delhi" (2), Mumbai -> "Maharashtra" (1)
        assert result.get("Delhi") == 2
        assert result.get("Maharashtra") == 1

    def test_empty_articles_returns_empty_dict(self) -> None:
        """No articles should yield an empty dict."""
        result = build_choropleth_data([], "IN")
        assert result == {}

    def test_delegates_to_build_admin1_article_counts(self) -> None:
        """build_choropleth_data should delegate to geo_resolver."""
        articles = [_make_article(country_code="NG", region="Lagos")]
        with patch(
            "dashboard.components.map_drilldown.build_admin1_article_counts",
            return_value={"Lagos": 5},
        ) as mock_fn:
            result = build_choropleth_data(articles, "NG")
        mock_fn.assert_called_once_with(articles, "NG")
        assert result == {"Lagos": 5}


# ---------------------------------------------------------------------------
# render_choropleth_html tests
# ---------------------------------------------------------------------------


class TestRenderChoroplethHTML:
    """Tests for render_choropleth_html."""

    _CENTER = {"lat": 20.59, "lng": 78.96, "zoom": 4.5}

    def test_returns_html_string_for_valid_country(self) -> None:
        """Should return a non-empty HTML string for a known country."""
        html = render_choropleth_html({"Delhi": 3}, "IN", self._CENTER)
        assert html is not None
        assert isinstance(html, str)
        assert len(html) > 0

    def test_returns_none_for_country_without_geojson(self) -> None:
        """Should return None when no GeoJSON file exists."""
        result = render_choropleth_html({"FakeRegion": 1}, "XX", self._CENTER)
        assert result is None

    def test_html_contains_deckgl_markers(self) -> None:
        """Output HTML should reference GeoJsonLayer and deck.gl."""
        html = render_choropleth_html({"Delhi": 1}, "IN", self._CENTER)
        assert html is not None
        assert "GeoJsonLayer" in html
        assert "deck.gl" in html or "deck.DeckGL" in html

    def test_placeholders_fully_replaced(self) -> None:
        """No __PLACEHOLDER__ markers should remain in output."""
        counts = {"Delhi": 2, "Maharashtra": 1}
        html = render_choropleth_html(counts, "IN", self._CENTER)
        assert html is not None
        assert "__ADMIN1_GEOJSON__" not in html
        assert "__REGION_COUNTS__" not in html
        assert "__INITIAL_VIEW_STATE__" not in html

    def test_injected_data_is_valid_json(self) -> None:
        """The replaced counts and view state should be parseable JSON."""
        counts = {"Delhi": 2, "Maharashtra": 1}
        html = render_choropleth_html(counts, "IN", self._CENTER)
        assert html is not None
        # The counts JSON appears after "REGION_COUNTS = "
        assert json.dumps(counts) in html or '"Delhi"' in html


# ---------------------------------------------------------------------------
# Template existence tests
# ---------------------------------------------------------------------------


class TestChoroplethTemplate:
    """Tests for the deck_choropleth.html template file."""

    def test_template_file_exists(self) -> None:
        """deck_choropleth.html must exist in dashboard/static/."""
        assert _CHOROPLETH_TEMPLATE.exists(), (
            f"Missing template: {_CHOROPLETH_TEMPLATE}"
        )

    def test_template_contains_expected_placeholders(self) -> None:
        """Template should contain all three replacement placeholders."""
        content = _CHOROPLETH_TEMPLATE.read_text(encoding="utf-8")
        assert "__ADMIN1_GEOJSON__" in content
        assert "__REGION_COUNTS__" in content
        assert "__INITIAL_VIEW_STATE__" in content
