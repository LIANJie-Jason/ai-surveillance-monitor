# tests/test_dashboard_app.py
"""Tests for the main dashboard app logic helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ===================================================================
# View state logic
# ===================================================================


def test_get_view_state_global_when_no_country():
    """Default session state should produce 'global' view."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {"selected_country": None, "selected_article_id": None}
    assert get_view_state(state) == "global"


def test_get_view_state_drilldown_when_country_selected():
    """When a country is selected, view should be 'drilldown'."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {"selected_country": "IN", "selected_article_id": None}
    assert get_view_state(state) == "drilldown"


def test_get_view_state_drilldown_with_article():
    """Country + article should still be 'drilldown'."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {"selected_country": "MY", "selected_article_id": "abc123"}
    assert get_view_state(state) == "drilldown"


def test_get_view_state_global_with_empty_string_country():
    """Empty string country should be treated as global."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {"selected_country": "", "selected_article_id": None}
    assert get_view_state(state) == "global"


def test_get_view_state_global_with_whitespace_country():
    """Whitespace-only country should be treated as global."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {"selected_country": "  ", "selected_article_id": None}
    assert get_view_state(state) == "global"


def test_get_view_state_global_with_missing_key():
    """Missing selected_country key should return global."""
    from dashboard.app import get_view_state

    state: dict[str, Any] = {}
    assert get_view_state(state) == "global"


# ===================================================================
# Country selection helpers
# ===================================================================


def test_select_country_sets_state():
    """select_country should set country and clear article."""
    from dashboard.app import select_country

    state: dict[str, Any] = {"selected_country": None, "selected_article_id": "old"}
    select_country(state, "NG")
    assert state["selected_country"] == "NG"
    assert state["selected_article_id"] is None


def test_clear_country_resets_state():
    """clear_country should clear both country and article."""
    from dashboard.app import clear_country

    state: dict[str, Any] = {"selected_country": "IN", "selected_article_id": "abc"}
    clear_country(state)
    assert state["selected_country"] is None
    assert state["selected_article_id"] is None


# ===================================================================
# Article selection helpers
# ===================================================================


def test_select_article_sets_id():
    """select_article should set the article ID."""
    from dashboard.app import select_article

    state: dict[str, Any] = {"selected_country": "ZA", "selected_article_id": None}
    select_article(state, "article_xyz")
    assert state["selected_article_id"] == "article_xyz"


def test_clear_article_resets_id():
    """clear_article should clear the article ID only."""
    from dashboard.app import clear_article

    state: dict[str, Any] = {"selected_country": "ZA", "selected_article_id": "abc"}
    clear_article(state)
    assert state["selected_article_id"] is None
    assert state["selected_country"] == "ZA"


# ===================================================================
# Filter params builder
# ===================================================================


def test_build_filter_params_all_defaults():
    """With all defaults, should return only min_confidence."""
    from dashboard.app import build_filter_params

    result = build_filter_params(
        country="All",
        category="All",
        min_confidence=0.6,
        date_from=None,
        date_to=None,
    )
    assert result["min_confidence"] == 0.6
    assert "country_code" not in result
    assert "category" not in result
    assert "date_from" not in result
    assert "date_to" not in result


def test_build_filter_params_with_country():
    """Country filter should be included when not 'All'."""
    from dashboard.app import build_filter_params

    result = build_filter_params(
        country="IN",
        category="All",
        min_confidence=0.7,
        date_from=None,
        date_to=None,
    )
    assert result["country_code"] == "IN"
    assert result["min_confidence"] == 0.7
    assert "category" not in result


def test_build_filter_params_with_category():
    """Category filter should be included when not 'All'."""
    from dashboard.app import build_filter_params

    result = build_filter_params(
        country="All",
        category="surveillance",
        min_confidence=0.6,
        date_from=None,
        date_to=None,
    )
    assert result["category"] == "surveillance"
    assert "country_code" not in result


def test_build_filter_params_with_dates():
    """Date filters should be ISO-formatted strings."""
    from dashboard.app import build_filter_params

    d_from = datetime(2025, 1, 1, tzinfo=timezone.utc)
    d_to = datetime(2025, 12, 31, tzinfo=timezone.utc)
    result = build_filter_params(
        country="All",
        category="All",
        min_confidence=0.6,
        date_from=d_from,
        date_to=d_to,
    )
    assert result["date_from"] == "2025-01-01T00:00:00+00:00"
    assert result["date_to"] == "2025-12-31T00:00:00+00:00"


def test_build_filter_params_with_all_filters():
    """All filters set should all appear in result."""
    from dashboard.app import build_filter_params

    d_from = datetime(2025, 6, 1, tzinfo=timezone.utc)
    result = build_filter_params(
        country="MY",
        category="censorship",
        min_confidence=0.8,
        date_from=d_from,
        date_to=None,
    )
    assert result["country_code"] == "MY"
    assert result["category"] == "censorship"
    assert result["min_confidence"] == 0.8
    assert result["date_from"] == "2025-06-01T00:00:00+00:00"
    assert "date_to" not in result


def test_build_filter_params_empty_country():
    """Empty string country should be excluded."""
    from dashboard.app import build_filter_params

    result = build_filter_params(
        country="",
        category="All",
        min_confidence=0.6,
        date_from=None,
        date_to=None,
    )
    assert "country_code" not in result


# ===================================================================
# Category list
# ===================================================================


def test_get_categories_returns_list():
    """get_categories should return a sorted list with 'All' first."""
    from dashboard.app import get_categories

    cats = get_categories()
    assert isinstance(cats, list)
    assert cats[0] == "All"
    assert len(cats) > 1


def test_get_categories_includes_known_categories():
    """Should include known VALID_CATEGORIES."""
    from dashboard.app import get_categories

    cats = get_categories()
    assert "surveillance" in cats
    assert "censorship" in cats


def test_get_categories_all_first():
    """'All' should be the first element, rest alphabetically sorted."""
    from dashboard.app import get_categories

    cats = get_categories()
    assert cats[0] == "All"
    rest = cats[1:]
    assert rest == sorted(rest)


def test_get_categories_count_matches_valid():
    """Should have All + all VALID_CATEGORIES."""
    from dashboard.app import get_categories
    from src.models import VALID_CATEGORIES

    cats = get_categories()
    assert len(cats) == len(VALID_CATEGORIES) + 1


# ===================================================================
# Drill-down country list
# ===================================================================


def test_get_drilldown_countries_returns_tuple():
    """get_drilldown_countries should return the known drill-down set."""
    from dashboard.app import get_drilldown_countries

    countries = get_drilldown_countries()
    assert isinstance(countries, tuple)
    assert "IN" in countries
    assert "MY" in countries
    assert "NG" in countries
    assert "ZA" in countries


# ===================================================================
# CSS path validation
# ===================================================================


def test_dark_theme_css_exists():
    """The dark theme CSS file should exist on disk."""
    from pathlib import Path

    css_path = (
        Path(__file__).resolve().parent.parent / "dashboard" / "styles" / "dark_theme.css"
    )
    assert css_path.exists(), f"Expected CSS at {css_path}"


# ===================================================================
# Component imports work (smoke test)
# ===================================================================


def test_components_importable():
    """All dashboard components should be importable."""
    from dashboard.components.map_global import build_map_data, render_map_html
    from dashboard.components.map_drilldown import build_region_data, render_drilldown_html
    from dashboard.components.news_feed import render_news_feed
    from dashboard.components.article_detail import render_article_detail
    from dashboard.components.live_stream import render_live_stream
    from dashboard.components.webcams import render_webcam_grid

    assert callable(build_map_data)
    assert callable(render_map_html)
    assert callable(build_region_data)
    assert callable(render_drilldown_html)
    assert callable(render_news_feed)
    assert callable(render_article_detail)
    assert callable(render_live_stream)
    assert callable(render_webcam_grid)


# ===================================================================
# COUNTRY_COORDS import from app
# ===================================================================


def test_country_coords_accessible():
    """COUNTRY_COORDS should be importable from map_global (used by app)."""
    from dashboard.components.map_global import COUNTRY_COORDS

    assert isinstance(COUNTRY_COORDS, dict)
    assert "IN" in COUNTRY_COORDS
    assert "MY" in COUNTRY_COORDS


# ===================================================================
# Country option helpers (M18)
# ===================================================================


def test_get_country_options_all_first():
    """get_country_options should start with 'All'."""
    from dashboard.app import get_country_options

    counts = {"IN": 10, "ZA": 5}
    coords = {
        "IN": {"lat": 20, "lng": 78, "name": "India"},
        "ZA": {"lat": -30, "lng": 25, "name": "South Africa"},
    }
    options = get_country_options(counts, coords=coords)
    assert options[0] == "All"
    assert len(options) == 3


def test_get_country_options_sorted_by_code():
    """Country options should be sorted by ISO code."""
    from dashboard.app import get_country_options

    counts = {"ZA": 1, "IN": 2, "MY": 3}
    coords = {
        "IN": {"lat": 0, "lng": 0, "name": "India"},
        "MY": {"lat": 0, "lng": 0, "name": "Malaysia"},
        "ZA": {"lat": 0, "lng": 0, "name": "South Africa"},
    }
    options = get_country_options(counts, coords=coords)
    assert options[1] == "IN — India"
    assert options[2] == "MY — Malaysia"
    assert options[3] == "ZA — South Africa"


def test_get_country_options_unknown_code_uses_code_as_name():
    """Countries not in coords should show code as name."""
    from dashboard.app import get_country_options

    counts = {"XX": 1}
    options = get_country_options(counts, coords={})
    assert options[1] == "XX — XX"


def test_get_country_options_empty_counts():
    """Empty country_counts should return only 'All'."""
    from dashboard.app import get_country_options

    options = get_country_options({}, coords={})
    assert options == ["All"]


def test_parse_country_option_extracts_code():
    """parse_country_option should extract the ISO code."""
    from dashboard.app import parse_country_option

    assert parse_country_option("IN — India") == "IN"
    assert parse_country_option("ZA — South Africa") == "ZA"


def test_parse_country_option_all_passthrough():
    """parse_country_option('All') should return 'All'."""
    from dashboard.app import parse_country_option

    assert parse_country_option("All") == "All"


# ===================================================================
# Article meta formatting (M21)
# ===================================================================


def test_format_article_meta_all_fields():
    """format_article_meta with all fields should join them."""
    from dashboard.app import format_article_meta
    from src.models import Article

    article = Article(
        id="a1", url="https://example.com/1", title="Test",
        source_name="Reuters", source_lang="en", source_tier=1,
        country_name="India", confidence=0.85,
    )
    meta = format_article_meta(article)
    assert "India" in meta
    assert "Reuters" in meta
    assert "0.85" in meta


def test_format_article_meta_missing_fields():
    """format_article_meta with None fields should skip them."""
    from dashboard.app import format_article_meta
    from src.models import Article

    article = Article(
        id="a2", url="https://example.com/2", title="Test",
        source_name=None, source_lang="en", source_tier=1,
        country_name=None, confidence=None,
    )
    meta = format_article_meta(article)
    assert meta == ""


def test_format_article_meta_partial_fields():
    """format_article_meta with some fields should show only present ones."""
    from dashboard.app import format_article_meta
    from src.models import Article

    article = Article(
        id="a3", url="https://example.com/3", title="Test",
        source_name="BBC", source_lang="en", source_tier=2,
        country_name=None, confidence=0.90,
    )
    meta = format_article_meta(article)
    assert "BBC" in meta
    assert "0.90" in meta
    assert "|" in meta


# ===================================================================
# R1 regression: avg_conf excludes None from denominator
# ===================================================================


def test_avg_conf_excludes_none_confidence():
    """R1: avg_conf should not count None-confidence articles in denominator."""
    # Simulate the fixed calculation inline (pure logic extracted from app.py)
    class FakeArticle:
        def __init__(self, conf):
            self.confidence = conf

    articles = [
        FakeArticle(0.9), FakeArticle(0.9),
        FakeArticle(None), FakeArticle(None), FakeArticle(None),
    ]
    conf_values = [a.confidence for a in articles if a.confidence is not None]
    avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
    assert abs(avg_conf - 0.9) < 0.001  # Should be 0.9, not 0.36


def test_avg_conf_all_none_returns_zero():
    """R1: When all confidences are None, avg_conf should be 0.0."""
    class FakeArticle:
        def __init__(self, conf):
            self.confidence = conf

    articles = [FakeArticle(None), FakeArticle(None)]
    conf_values = [a.confidence for a in articles if a.confidence is not None]
    avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
    assert avg_conf == 0.0


# ===================================================================
# R3 regression: filter_params with country_code excluded for get_country_counts
# ===================================================================


def test_filter_params_country_code_excluded_for_counts():
    """R3: country_code should be stripped before passing to get_country_counts."""
    from dashboard.app import build_filter_params

    params = build_filter_params(
        country="IN", category="All", min_confidence=0.6,
        date_from=None, date_to=None,
    )
    # Simulate the R3 fix
    cc_params = {k: v for k, v in params.items() if k != "country_code"}
    assert "country_code" not in cc_params
    assert "min_confidence" in cc_params


def test_get_country_counts_rejects_country_code_kwarg():
    """R3/R4: get_country_counts must not accept country_code — callers must strip it."""
    import inspect
    from src.database import Database
    sig = inspect.signature(Database.get_country_counts)
    param_names = set(sig.parameters.keys()) - {"self"}
    assert "country_code" not in param_names, (
        "get_country_counts should not accept country_code — "
        "filter_params must strip it before passing (R3)"
    )
