"""Globe view component for the surveillance dashboard.

Renders a 3D rotating globe using deck.gl GlobeView with:
- GeoJsonLayer for country polygon boundaries (focus countries highlighted)
- ScatterplotLayer for article markers (count-based color/size)
- Auto-rotation with pause-on-interaction and idle resume
- Click-to-drill-down: clicking a focus country returns its ISO-2 code
  to Streamlit via the bidirectional component protocol.

Uses ``streamlit.components.v1.declare_component`` for bidirectional
communication (the globe iframe can send values back to Python).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import streamlit.components.v1 as st_components

from dashboard.components._utils import safe_json_for_script

logger = logging.getLogger(__name__)

from dashboard.components.map_global import (
    DRILL_DOWN_COUNTRIES,
    build_map_data,
)

# Countries highlighted on the globe (translucent red fill)
FOCUS_COUNTRIES: tuple[str, ...] = DRILL_DOWN_COUNTRIES

_COMPONENT_DIR = str(
    Path(__file__).resolve().parent.parent / "static" / "globe_component"
)
_GEOJSON_DIR = (
    Path(__file__).resolve().parent.parent / "static" / "geojson"
)

# Declare a bidirectional Streamlit component.
# The component's index.html implements the Streamlit component protocol
# (setComponentReady, setComponentValue, setFrameHeight) inline.
_globe_component = st_components.declare_component(
    "surveillance_globe",
    path=_COMPONENT_DIR,
)

# Module-level cache to avoid re-reading the ~257KB GeoJSON on every render.
# Protected by a lock since Streamlit may serve multiple sessions from
# different threads (CC2-M10).
_countries_geojson_cache: dict[str, Any] | None = None
_cache_lock = threading.Lock()


def _load_countries_geojson() -> dict[str, Any] | None:
    """Load and cache world country boundaries GeoJSON.

    Returns the full FeatureCollection dict (177 countries, ~257KB),
    or None if the file is missing (e.g. prepare_geojson.py not run).
    Cached in module-level variable after first load.  Thread-safe.
    """
    global _countries_geojson_cache
    if _countries_geojson_cache is not None:
        return _countries_geojson_cache
    with _cache_lock:
        # Double-check after acquiring lock
        if _countries_geojson_cache is not None:
            return _countries_geojson_cache
        path = _GEOJSON_DIR / "countries_110m.geojson"
        if not path.exists():
            logger.warning("countries_110m.geojson not found at %s", path)
            return None
        with open(path, encoding="utf-8") as f:
            _countries_geojson_cache = json.load(f)
    return _countries_geojson_cache


def _clear_countries_cache() -> None:
    """Clear the cached GeoJSON data.

    Intended for testing — allows tests to verify loading behavior
    without stale cached state.
    """
    global _countries_geojson_cache
    with _cache_lock:
        _countries_geojson_cache = None


def build_globe_data(country_counts: dict[str, int]) -> list[dict[str, Any]]:
    """Build scatter-layer data for the globe view.

    Delegates to ``build_map_data`` from the flat-map component so that
    both views share identical coordinate lookup and count validation.

    Parameters
    ----------
    country_counts:
        Mapping of ISO-3166-1 alpha-2 country codes to article counts.

    Returns
    -------
    list[dict]:
        Each dict has keys: lat, lng, count, country_code, country_name.
    """
    return build_map_data(country_counts)


# Country centers for flyTo animation (shared with index.html)
COUNTRY_CENTERS: dict[str, dict[str, Any]] = {
    "IN": {"lat": 20.59, "lng": 78.96, "zoom": 4.5, "name": "India"},
    "MY": {"lat": 4.21, "lng": 101.98, "zoom": 5.5, "name": "Malaysia"},
    "NG": {"lat": 9.08, "lng": 8.68, "zoom": 5.5, "name": "Nigeria"},
    "ZA": {"lat": -30.56, "lng": 22.94, "zoom": 5.0, "name": "South Africa"},
}

# Admin-1 GeoJSON cache (keyed by country code)
_admin1_cache: dict[str, dict[str, Any]] = {}
_admin1_lock = threading.Lock()


_ALLOWED_COUNTRY_CODES = frozenset({"IN", "MY", "NG", "ZA"})


def _load_admin1_geojson(country_code: str) -> dict[str, Any] | None:
    """Load admin-1 boundary GeoJSON for a country.

    Only allows codes in _ALLOWED_COUNTRY_CODES to prevent path traversal.
    Cached in module-level dict. Thread-safe.
    """
    if country_code not in _ALLOWED_COUNTRY_CODES:
        logger.warning("Rejected admin1 load for non-allowed country: %s", country_code)
        return None
    if country_code in _admin1_cache:
        return _admin1_cache[country_code]
    with _admin1_lock:
        if country_code in _admin1_cache:
            return _admin1_cache[country_code]
        path = _GEOJSON_DIR / f"admin1_{country_code}.geojson"
        if not path.exists():
            logger.warning("admin1_%s.geojson not found", country_code)
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _admin1_cache[country_code] = data
    return data


def render_globe(
    article_data: list[dict[str, Any]],
    height: int = 550,
    key: str | None = None,
    selected_country: str | None = None,
) -> str | None:
    """Render the interactive globe and return the clicked country code.

    Uses ``declare_component`` for bidirectional communication: the globe
    iframe sends the ISO-2 country code back to Python when a focus
    country polygon is clicked.

    When ``selected_country`` is set, the globe flies to that country
    and overlays admin-1 boundaries.

    Returns the ISO-2 country code if a focus country was clicked, else None.
    """
    countries_geojson = _load_countries_geojson()
    if countries_geojson is None:
        countries_geojson = {"type": "FeatureCollection", "features": []}

    # Load admin-1 GeoJSON if a country is selected
    admin1_geojson = None
    if selected_country and selected_country in COUNTRY_CENTERS:
        admin1_geojson = _load_admin1_geojson(selected_country)

    # Sentinel default so we can distinguish "no click" from "back button
    # sent null".  declare_component returns default on every rerun where
    # the JS side hasn't called setComponentValue with a *new* value.
    _NO_CLICK = "__no_click__"
    raw = _globe_component(
        article_data=article_data,
        countries_geojson=countries_geojson,
        focus_countries=list(FOCUS_COUNTRIES),
        country_centers=COUNTRY_CENTERS,
        selected_country=selected_country,
        admin1_geojson=admin1_geojson,
        height=height,
        default=_NO_CLICK,
        key=key,
    )
    # _NO_CLICK  → no interaction this rerun → return sentinel so caller
    #               knows not to act
    # None/null  → JS sent setComponentValue(null) → back button
    # "IN"/etc   → JS sent setComponentValue("IN") → country click
    if raw == _NO_CLICK:
        return _NO_CLICK  # type: ignore[return-value]
    if raw is None:
        return None
    return raw


# ---------------------------------------------------------------------------
# Legacy render function (non-interactive, kept for tests and fallback)
# ---------------------------------------------------------------------------

_GLOBE_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "deck_globe.html"
)


def render_globe_html(article_data: list[dict[str, Any]]) -> str:
    """Render the globe HTML template with injected data (non-interactive).

    This is the legacy render path that uses ``st.components.v1.html()``
    (one-way; no click-to-drill-down). Kept for tests and as a fallback
    if ``declare_component`` is unavailable.

    Parameters
    ----------
    article_data:
        Output of ``build_globe_data``.

    Returns
    -------
    str:
        Complete HTML document ready for ``st.components.v1.html()``.
    """
    template = _GLOBE_TEMPLATE_PATH.read_text(encoding="utf-8")
    countries_geojson = _load_countries_geojson()
    if countries_geojson is None:
        countries_geojson = {"type": "FeatureCollection", "features": []}

    rendered = template.replace(
        "__ARTICLE_DATA__",
        safe_json_for_script(article_data),
    )
    rendered = rendered.replace(
        "__COUNTRIES_GEOJSON__",
        safe_json_for_script(countries_geojson),
    )
    rendered = rendered.replace(
        "__FOCUS_COUNTRIES__",
        safe_json_for_script(list(FOCUS_COUNTRIES)),
    )

    return rendered
