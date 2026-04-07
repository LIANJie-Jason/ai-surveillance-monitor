# tests/test_geo_resolver.py
"""Tests for the geo_resolver module (city/region -> admin-1 mapping)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dashboard.components.geo_resolver import (
    REGION_TO_ADMIN1,
    build_admin1_article_counts,
    resolve_admin1,
)
from src.models import Article


# ---------------------------------------------------------------------------
# Helper: build a minimal Article with only the fields geo_resolver uses
# ---------------------------------------------------------------------------

def _make_article(
    region: str | None,
    country_code: str = "IN",
    url_suffix: str = "1",
) -> Article:
    """Create a minimal Article for geo-resolver testing."""
    url = f"https://example.com/article/{url_suffix}"
    return Article(
        id=Article._hash_url(url),
        url=url,
        title=f"Test article {url_suffix}",
        source_name="TestSource",
        source_lang="en",
        source_tier=1,
        country_code=country_code,
        region=region,
    )


# ===========================================================================
# resolve_admin1() tests
# ===========================================================================


class TestResolveAdmin1:
    """Tests for resolve_admin1()."""

    # -- India (IN) --

    def test_valid_city_returns_admin1_india(self) -> None:
        """Valid city name returns correct admin-1."""
        assert resolve_admin1("IN", "Mumbai") == "Maharashtra"

    def test_alias_returns_admin1_india(self) -> None:
        """Historical alias maps correctly."""
        assert resolve_admin1("IN", "Bombay") == "Maharashtra"

    def test_case_insensitive_uppercase(self) -> None:
        """All-uppercase input resolves correctly."""
        assert resolve_admin1("IN", "MUMBAI") == "Maharashtra"

    def test_case_insensitive_mixed(self) -> None:
        """Mixed-case input resolves correctly."""
        assert resolve_admin1("IN", "mUmBaI") == "Maharashtra"

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped before lookup."""
        assert resolve_admin1("IN", "  Mumbai  ") == "Maharashtra"

    def test_whitespace_and_case_combined(self) -> None:
        """Whitespace stripping and case folding work together."""
        assert resolve_admin1("IN", "  DELHI  ") == "Delhi"

    def test_unknown_region_returns_none(self) -> None:
        """Unrecognized region name returns None."""
        assert resolve_admin1("IN", "Atlantis") is None

    def test_unknown_country_returns_none(self) -> None:
        """Country code not in mapping returns None."""
        assert resolve_admin1("US", "New York") is None

    def test_empty_string_returns_none(self) -> None:
        """Empty region string returns None."""
        assert resolve_admin1("IN", "") is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only region string returns None."""
        assert resolve_admin1("IN", "   ") is None

    # -- Malaysia (MY) --

    def test_valid_city_malaysia(self) -> None:
        assert resolve_admin1("MY", "Kuala Lumpur") == "Kuala Lumpur"

    def test_alias_malaysia(self) -> None:
        assert resolve_admin1("MY", "KL") == "Kuala Lumpur"

    def test_penang_alias(self) -> None:
        assert resolve_admin1("MY", "George Town") == "Pulau Pinang"

    # -- Nigeria (NG) --

    def test_valid_city_nigeria(self) -> None:
        assert resolve_admin1("NG", "Lagos") == "Lagos"

    def test_alias_nigeria(self) -> None:
        assert resolve_admin1("NG", "FCT") == "Federal Capital Territory"

    def test_port_harcourt_nigeria(self) -> None:
        assert resolve_admin1("NG", "Port Harcourt") == "Rivers"

    # -- South Africa (ZA) --

    def test_valid_city_south_africa(self) -> None:
        assert resolve_admin1("ZA", "Johannesburg") == "Gauteng"

    def test_alias_south_africa(self) -> None:
        assert resolve_admin1("ZA", "Joburg") == "Gauteng"

    def test_cape_town_south_africa(self) -> None:
        assert resolve_admin1("ZA", "Cape Town") == "Western Cape"

    def test_durban_kwazulu_natal(self) -> None:
        assert resolve_admin1("ZA", "Durban") == "KwaZulu-Natal"


# ===========================================================================
# build_admin1_article_counts() tests
# ===========================================================================


class TestBuildAdmin1ArticleCounts:
    """Tests for build_admin1_article_counts()."""

    def test_single_article_counts(self) -> None:
        """Single article with valid region produces count of 1."""
        articles = [_make_article("Mumbai")]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 1}

    def test_multiple_cities_same_admin1(self) -> None:
        """Mumbai and Pune both map to Maharashtra; counts aggregate."""
        articles = [
            _make_article("Mumbai", url_suffix="1"),
            _make_article("Pune", url_suffix="2"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 2}

    def test_multiple_different_admin1(self) -> None:
        """Articles in different admin-1 regions produce separate counts."""
        articles = [
            _make_article("Mumbai", url_suffix="1"),
            _make_article("Delhi", url_suffix="2"),
            _make_article("Chennai", url_suffix="3"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 1, "Delhi": 1, "Tamil Nadu": 1}

    def test_none_region_skipped(self) -> None:
        """Articles with None region are silently skipped."""
        articles = [
            _make_article(None, url_suffix="1"),
            _make_article("Mumbai", url_suffix="2"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 1}

    def test_unknown_region_skipped(self) -> None:
        """Articles with unrecognized region are silently skipped."""
        articles = [
            _make_article("Atlantis", url_suffix="1"),
            _make_article("Mumbai", url_suffix="2"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 1}

    def test_empty_list_returns_empty_dict(self) -> None:
        """Empty article list returns empty dict."""
        result = build_admin1_article_counts([], "IN")
        assert result == {}

    def test_all_unresolvable_returns_empty_dict(self) -> None:
        """If no articles resolve, result is empty dict."""
        articles = [
            _make_article(None, url_suffix="1"),
            _make_article("Atlantis", url_suffix="2"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {}

    def test_mix_resolvable_and_unresolvable(self) -> None:
        """Mix of resolvable, unknown, and None regions."""
        articles = [
            _make_article("Mumbai", url_suffix="1"),
            _make_article(None, url_suffix="2"),
            _make_article("Atlantis", url_suffix="3"),
            _make_article("Delhi", url_suffix="4"),
            _make_article("Mumbai", url_suffix="5"),
        ]
        result = build_admin1_article_counts(articles, "IN")
        assert result == {"Maharashtra": 2, "Delhi": 1}

    def test_counts_with_malaysia(self) -> None:
        """Verify aggregation works for MY country code."""
        articles = [
            _make_article("KL", country_code="MY", url_suffix="1"),
            _make_article("Penang", country_code="MY", url_suffix="2"),
            _make_article("KL", country_code="MY", url_suffix="3"),
        ]
        result = build_admin1_article_counts(articles, "MY")
        assert result == {"Kuala Lumpur": 2, "Pulau Pinang": 1}


# ===========================================================================
# Mapping completeness: every city & alias from regions.yaml has a mapping
# ===========================================================================


class TestMappingCompleteness:
    """Ensure REGION_TO_ADMIN1 covers every name and alias from regions.yaml."""

    @staticmethod
    def _load_regions_yaml() -> dict:
        config_path = (
            Path(__file__).resolve().parent.parent / "config" / "regions.yaml"
        )
        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_all_city_names_mapped(self) -> None:
        """Every primary city name in regions.yaml has a mapping."""
        data = self._load_regions_yaml()
        missing: list[str] = []
        for country_code, region_list in data["regions"].items():
            country_map = REGION_TO_ADMIN1.get(country_code, {})
            for region in region_list:
                name = region["name"]
                if name.lower() not in country_map:
                    missing.append(f"{country_code}/{name}")
        assert missing == [], f"City names missing from REGION_TO_ADMIN1: {missing}"

    def test_all_aliases_mapped(self) -> None:
        """Every alias in regions.yaml has a mapping."""
        data = self._load_regions_yaml()
        missing: list[str] = []
        for country_code, region_list in data["regions"].items():
            country_map = REGION_TO_ADMIN1.get(country_code, {})
            for region in region_list:
                for alias in region.get("aliases", []):
                    if alias.lower() not in country_map:
                        missing.append(f"{country_code}/{alias}")
        assert missing == [], f"Aliases missing from REGION_TO_ADMIN1: {missing}"

    def test_all_four_countries_present(self) -> None:
        """REGION_TO_ADMIN1 contains entries for all 4 drill-down countries."""
        for cc in ["IN", "MY", "NG", "ZA"]:
            assert cc in REGION_TO_ADMIN1, f"Country {cc} missing from REGION_TO_ADMIN1"
            assert len(REGION_TO_ADMIN1[cc]) > 0, f"Country {cc} has empty mapping"
