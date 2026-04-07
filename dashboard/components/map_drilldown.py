"""Drill-down map component — region-level deck.gl map for selected countries."""

from __future__ import annotations

import json
import logging
import math
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from dashboard.components._utils import safe_json_for_script
from dashboard.components.geo_resolver import build_admin1_article_counts
from src.models import Article

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "regions.yaml"
_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static" / "deck_map.html"

# Country centers for drill-down view (lat, lng, zoom)
_COUNTRY_CENTERS: dict[str, dict[str, float]] = {
    "IN": {"lat": 20.59, "lng": 78.96, "zoom": 4.5},
    "MY": {"lat": 4.21, "lng": 101.98, "zoom": 5.5},
    "NG": {"lat": 9.08, "lng": 8.68, "zoom": 5.5},
    "ZA": {"lat": -30.56, "lng": 22.94, "zoom": 5.0},
}

# Successful-load cache. Failures are NOT cached so transient errors (file
# being written during deployment) can recover on the next call.
_regions_cache: dict[str, list[dict[str, Any]]] | None = None


def load_regions() -> dict[str, list[dict[str, Any]]]:
    """Load region definitions from config/regions.yaml.

    Returns a dict keyed by country code (e.g. "IN"), each value a list of
    region dicts with keys: name, lat, lng, aliases.
    Returns an empty dict if the file is missing or malformed — such failures
    are NOT cached, so a later call after the file becomes available will
    reload it.
    """
    global _regions_cache
    if _regions_cache is not None:
        return _regions_cache
    try:
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("regions.yaml not found at %s", _CONFIG_PATH)
        return {}
    except yaml.YAMLError:
        logger.warning("regions.yaml is malformed")
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("regions"), dict):
        logger.warning("regions.yaml missing 'regions' dict at top level")
        return {}
    _regions_cache = raw["regions"]
    return _regions_cache


def _clear_regions_cache() -> None:
    """Clear the successful-load cache (for tests and deployment reloads)."""
    global _regions_cache
    _regions_cache = None


# Preserve the `load_regions.cache_clear()` API that tests rely on.
load_regions.cache_clear = _clear_regions_cache  # type: ignore[attr-defined]


def get_country_center(country_code: str) -> dict[str, float] | None:
    """Return {lat, lng, zoom} for a drill-down country, or None if unknown."""
    center = _COUNTRY_CENTERS.get(country_code)
    if center is None:
        return None
    return dict(center)


def _build_alias_map(regions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lowercase-name → region dict from a list of region definitions.

    Maps both the canonical name and every alias to the region dict.
    """
    alias_map: dict[str, dict[str, Any]] = {}
    for region in regions:
        canonical = region["name"]
        alias_map[canonical.lower()] = region
        for alias in region.get("aliases", []):
            alias_map[alias.lower()] = region
    return alias_map


def build_region_data(
    articles: list[Article],
    country_code: str,
) -> list[dict[str, Any]]:
    """Aggregate articles by region for a given country.

    Resolves aliases and case-insensitive matching.  Articles with
    unrecognized or None region, or whose country_code doesn't match
    the requested country, are silently skipped.

    Returns a list of dicts: {region_name, lat, lng, count, country_code}.
    """
    if not articles:
        return []

    all_regions = load_regions()
    region_defs = all_regions.get(country_code, [])
    if not region_defs:
        return []

    alias_map = _build_alias_map(region_defs)

    # Accumulate counts per canonical region name
    counts: dict[str, int] = defaultdict(int)
    for article in articles:
        if article.region is None:
            continue
        if article.country_code != country_code:
            continue
        region_key = article.region.strip().lower()
        region_def = alias_map.get(region_key)
        if region_def is None:
            continue
        counts[region_def["name"]] += 1

    # Build output with coords
    name_to_def = {r["name"]: r for r in region_defs}
    data: list[dict[str, Any]] = []
    for region_name, count in counts.items():
        region_def = name_to_def[region_name]
        data.append({
            "region_name": region_name,
            "lat": region_def["lat"],
            "lng": region_def["lng"],
            "count": count,
            "country_code": country_code,
            "country_name": region_name,
        })
    return data


def _validate_center(center: dict[str, float]) -> None:
    """Validate that center coordinates are finite numbers.

    Raises ValueError if lat, lng, or zoom is missing, non-numeric, or non-finite.
    """
    for key in ("lat", "lng", "zoom"):
        val = center.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(
                f"center[{key!r}] must be a finite number, got {val!r}"
            )


def render_drilldown_html(
    data: list[dict[str, Any]],
    center: dict[str, float],
) -> str:
    """Render a deck.gl drill-down map with injected region data.

    Reads the base template and replaces __DATA__ with safely escaped JSON.
    Overrides the initial view state to center on the target country.
    """
    _validate_center(center)
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    json_blob = safe_json_for_script(data)
    rendered = template.replace("__DATA__", json_blob)

    # Override initial view state for the drill-down country via placeholder.
    # Use json.dumps for defense-in-depth (values are hardcoded in
    # _COUNTRY_CENTERS but pattern should be consistent with data injection).
    import json as _json
    center_js = (
        f"latitude: {_json.dumps(center['lat'])},\n"
        f"        longitude: {_json.dumps(center['lng'])},\n"
        f"        zoom: {_json.dumps(center['zoom'])},"
    )
    rendered = rendered.replace("__INITIAL_VIEW_STATE__", center_js)
    return rendered


# ---------------------------------------------------------------------------
# Choropleth drill-down support
# ---------------------------------------------------------------------------

_CHOROPLETH_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "deck_choropleth.html"
)

# Module-level cache for admin-1 GeoJSON (keyed by country code).
# Only successful loads are cached; missing files return None each time
# so a later deployment can supply the file without restarting.
# Protected by a lock for thread safety (CC2-M10).
_admin1_geojson_cache: dict[str, dict] = {}
_admin1_cache_lock = threading.Lock()


def _load_admin1_geojson(country_code: str) -> dict | None:
    """Load and cache admin-1 GeoJSON for a country.

    Returns None if the file does not exist.  Thread-safe.
    """
    if country_code in _admin1_geojson_cache:
        return _admin1_geojson_cache[country_code]
    with _admin1_cache_lock:
        # Double-check after acquiring lock
        if country_code in _admin1_geojson_cache:
            return _admin1_geojson_cache[country_code]
        path = (
            Path(__file__).resolve().parent.parent
            / "static"
            / "geojson"
            / f"admin1_{country_code}.geojson"
        )
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _admin1_geojson_cache[country_code] = data
    return data


def _clear_admin1_cache() -> None:
    """Clear admin-1 GeoJSON cache (for testing)."""
    with _admin1_cache_lock:
        _admin1_geojson_cache.clear()


def build_choropleth_data(
    articles: list[Article],
    country_code: str,
) -> dict[str, int]:
    """Build admin-1 article counts for choropleth rendering."""
    return build_admin1_article_counts(articles, country_code)


def render_choropleth_html(
    admin1_counts: dict[str, int],
    country_code: str,
    center: dict[str, float],
) -> str | None:
    """Render choropleth map HTML with admin-1 region fills.

    Returns None if admin-1 GeoJSON is not available for the country.
    """
    _validate_center(center)
    geojson = _load_admin1_geojson(country_code)
    if geojson is None:
        return None

    template = _CHOROPLETH_TEMPLATE_PATH.read_text(encoding="utf-8")

    view_state = {
        "latitude": center["lat"],
        "longitude": center["lng"],
        "zoom": center["zoom"],
    }

    html = template.replace(
        "__ADMIN1_GEOJSON__",
        safe_json_for_script(geojson),
    )
    html = html.replace(
        "__REGION_COUNTS__",
        safe_json_for_script(admin1_counts),
    )
    html = html.replace(
        "__INITIAL_VIEW_STATE__",
        safe_json_for_script(view_state),
    )

    return html
