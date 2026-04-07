# tests/test_config_urls.py
"""Tests that validate config files have properly populated URLs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# --- Helper ---


def _load_yaml(name: str) -> dict:
    path = _CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ===================================================================
# feeds.yaml validation
# ===================================================================


def test_feeds_yaml_exists():
    """feeds.yaml must exist."""
    assert (_CONFIG_DIR / "feeds.yaml").is_file()


def test_feeds_has_minimum_count():
    """Should have at least 40 feeds across all tiers."""
    data = _load_yaml("feeds.yaml")
    assert len(data["feeds"]) >= 40


def test_feeds_all_have_valid_urls():
    """Every feed must have a syntactically valid http/https URL."""
    data = _load_yaml("feeds.yaml")
    for feed in data["feeds"]:
        url = feed["url"]
        parsed = urlparse(url)
        assert parsed.scheme in {"http", "https"}, (
            f"{feed['name']}: invalid scheme in {url}"
        )
        assert parsed.hostname, f"{feed['name']}: no hostname in {url}"


def test_feeds_no_verify_in_url():
    """No feed URL should contain the VERIFY marker (should be in comments only)."""
    data = _load_yaml("feeds.yaml")
    for feed in data["feeds"]:
        assert "VERIFY" not in feed["url"], (
            f"{feed['name']}: VERIFY marker in URL value"
        )


def test_feeds_required_fields():
    """Every feed must have name, url, language, tier, feed_type."""
    data = _load_yaml("feeds.yaml")
    for feed in data["feeds"]:
        for field in ("name", "url", "language", "tier", "feed_type"):
            assert field in feed, f"Feed missing '{field}': {feed.get('name', '?')}"


def test_feeds_tiers_valid():
    """Tier must be 1, 2, 3, or 4."""
    data = _load_yaml("feeds.yaml")
    for feed in data["feeds"]:
        assert feed["tier"] in {1, 2, 3, 4}, (
            f"{feed['name']}: invalid tier {feed['tier']}"
        )


def test_feeds_has_all_four_drill_down_countries():
    """Must have at least 2 feeds per drill-down country."""
    data = _load_yaml("feeds.yaml")
    for cc in ["MY", "NG", "IN", "ZA"]:
        country_feeds = [
            f for f in data["feeds"] if f.get("country_focus") == cc
        ]
        assert len(country_feeds) >= 2, (
            f"Country {cc} has only {len(country_feeds)} feeds"
        )


def test_feeds_no_duplicate_urls():
    """No two feeds should have the same URL."""
    data = _load_yaml("feeds.yaml")
    urls = [f["url"] for f in data["feeds"]]
    duplicates = [u for u in urls if urls.count(u) > 1]
    assert not duplicates, f"Duplicate URLs: {set(duplicates)}"


# ===================================================================
# streams.yaml validation
# ===================================================================


def test_streams_yaml_exists():
    """streams.yaml must exist."""
    assert (_CONFIG_DIR / "streams.yaml").is_file()


def test_streams_has_all_four_countries():
    """Must have a primary stream for each drill-down country."""
    data = _load_yaml("streams.yaml")
    for cc in ["IN", "MY", "NG", "ZA"]:
        assert cc in data["streams"], f"Missing stream for {cc}"


def test_streams_embed_urls_valid():
    """Each stream must have a valid YouTube embed URL."""
    data = _load_yaml("streams.yaml")
    for cc, stream in data["streams"].items():
        url = stream["embed_url"]
        assert "youtube.com/embed" in url, (
            f"{cc}: stream URL not a YouTube embed: {url}"
        )
        parsed = urlparse(url)
        assert parsed.scheme == "https", f"{cc}: stream not HTTPS"


def test_streams_have_required_fields():
    """Each stream must have name, embed_url, language, description."""
    data = _load_yaml("streams.yaml")
    for cc, stream in data["streams"].items():
        for field in ("name", "embed_url", "language", "description"):
            assert field in stream, f"{cc} stream missing '{field}'"


def test_streams_fallbacks_exist():
    """Must have fallback streams for all four countries."""
    data = _load_yaml("streams.yaml")
    assert "fallbacks" in data
    for cc in ["IN", "MY", "NG", "ZA"]:
        assert cc in data["fallbacks"], f"Missing fallback for {cc}"


def test_streams_fallback_urls_valid():
    """Fallback stream URLs must also be valid YouTube embeds with HTTPS."""
    data = _load_yaml("streams.yaml")
    for cc, stream in data["fallbacks"].items():
        url = stream["embed_url"]
        assert "youtube.com/embed" in url, (
            f"{cc} fallback: not a YouTube embed: {url}"
        )
        parsed = urlparse(url)
        assert parsed.scheme == "https", f"{cc} fallback: not HTTPS"


def test_streams_primary_fallback_no_overlap():
    """Primary and fallback streams for the same country should differ when possible."""
    data = _load_yaml("streams.yaml")
    duplicates = []
    for cc in data["streams"]:
        if cc in data["fallbacks"]:
            if data["streams"][cc]["embed_url"] == data["fallbacks"][cc]["embed_url"]:
                duplicates.append(cc)
    # Allow up to 1 duplicate (some countries lack a distinct fallback)
    assert len(duplicates) <= 1, (
        f"Too many primary/fallback duplicates: {duplicates}"
    )


# ===================================================================
# webcams.yaml validation
# ===================================================================


def test_webcams_yaml_exists():
    """webcams.yaml must exist."""
    assert (_CONFIG_DIR / "webcams.yaml").is_file()


def test_webcams_has_all_four_countries():
    """Must have webcams for each drill-down country."""
    data = _load_yaml("webcams.yaml")
    for cc in ["IN", "MY", "NG", "ZA"]:
        assert cc in data["webcams"], f"Missing webcams for {cc}"


def test_webcams_embed_urls_populated():
    """Most webcams should have a non-empty embed_url (some cities lack streams)."""
    data = _load_yaml("webcams.yaml")
    empty = []
    total = 0
    for cc, cams in data["webcams"].items():
        for cam in cams:
            total += 1
            if not cam["embed_url"]:
                empty.append(f"{cc}/{cam['city']}")
    # Allow up to 3 empty (cities with no YouTube live stream)
    assert len(empty) <= 3, (
        f"Too many empty embed_urls ({len(empty)}/{total}): {empty}"
    )


def test_webcams_embed_urls_valid_scheme():
    """Webcam embed URLs must use https."""
    data = _load_yaml("webcams.yaml")
    for cc, cams in data["webcams"].items():
        for cam in cams:
            if cam["embed_url"]:
                parsed = urlparse(cam["embed_url"])
                assert parsed.scheme == "https", (
                    f"{cc}/{cam['city']}: not HTTPS: {cam['embed_url']}"
                )


def test_webcams_have_required_fields():
    """Each webcam must have city, embed_url, type, lat, lng."""
    data = _load_yaml("webcams.yaml")
    for cc, cams in data["webcams"].items():
        for cam in cams:
            for field in ("city", "embed_url", "type", "lat", "lng"):
                assert field in cam, (
                    f"{cc} webcam missing '{field}'"
                )


def test_webcams_type_valid():
    """Webcam type must be 'webcam' or 'news_fallback'."""
    data = _load_yaml("webcams.yaml")
    for cc, cams in data["webcams"].items():
        for cam in cams:
            assert cam["type"] in {"webcam", "news_fallback"}, (
                f"{cc}/{cam['city']}: invalid type '{cam['type']}'"
            )


def test_webcams_coords_valid():
    """Webcam coordinates must be valid lat/lng."""
    data = _load_yaml("webcams.yaml")
    for cc, cams in data["webcams"].items():
        for cam in cams:
            assert -90 <= cam["lat"] <= 90, (
                f"{cc}/{cam['city']}: lat out of range"
            )
            assert -180 <= cam["lng"] <= 180, (
                f"{cc}/{cam['city']}: lng out of range"
            )


def test_webcams_minimum_per_country():
    """Each country should have at least 2 webcams."""
    data = _load_yaml("webcams.yaml")
    for cc in ["IN", "MY", "NG", "ZA"]:
        assert len(data["webcams"][cc]) >= 2, (
            f"{cc} has only {len(data['webcams'][cc])} webcams"
        )


def test_webcams_no_duplicate_embed_urls():
    """No two webcams with populated URLs should share the same embed_url."""
    data = _load_yaml("webcams.yaml")
    urls = []
    for cc, cams in data["webcams"].items():
        for cam in cams:
            if cam["embed_url"]:  # skip empty placeholders
                urls.append((f"{cc}/{cam['city']}", cam["embed_url"]))
    seen: dict[str, str] = {}
    for label, url in urls:
        assert url not in seen, (
            f"Duplicate embed_url: {label} and {seen[url]} share {url}"
        )
        seen[url] = label


def test_webcams_embed_urls_are_embeddable():
    """Populated webcam URLs must use iframe-embeddable hosts."""
    data = _load_yaml("webcams.yaml")
    embeddable_hosts = {"www.youtube.com", "youtube.com"}
    for cc, cams in data["webcams"].items():
        for cam in cams:
            if not cam["embed_url"]:  # skip empty placeholders
                continue
            parsed = urlparse(cam["embed_url"])
            assert parsed.hostname in embeddable_hosts, (
                f"{cc}/{cam['city']}: {parsed.hostname} may block iframe embedding"
            )


def test_streams_fallback_required_fields():
    """Fallback streams must have all required fields."""
    data = _load_yaml("streams.yaml")
    for cc, stream in data["fallbacks"].items():
        for field in ("name", "embed_url", "language", "description"):
            assert field in stream, f"{cc} fallback missing '{field}'"


def test_webcams_no_overlap_with_primary_streams():
    """No webcam should use the same URL as its country's primary live stream."""
    streams = _load_yaml("streams.yaml")
    webcams = _load_yaml("webcams.yaml")
    primary_urls = {cc: s["embed_url"] for cc, s in streams["streams"].items()}
    for cc, cams in webcams["webcams"].items():
        primary = primary_urls.get(cc)
        if primary is None:
            continue
        for cam in cams:
            assert cam["embed_url"] != primary, (
                f"{cc}/{cam['city']} webcam duplicates {cc} primary stream"
            )


def test_webcams_no_overlap_with_fallback_streams():
    """No webcam should use the same URL as its country's fallback live stream."""
    streams = _load_yaml("streams.yaml")
    webcams = _load_yaml("webcams.yaml")
    fallback_urls = {cc: s["embed_url"] for cc, s in streams["fallbacks"].items()}
    for cc, cams in webcams["webcams"].items():
        fallback = fallback_urls.get(cc)
        if fallback is None:
            continue
        for cam in cams:
            assert cam["embed_url"] != fallback, (
                f"{cc}/{cam['city']} webcam duplicates {cc} fallback stream"
            )
