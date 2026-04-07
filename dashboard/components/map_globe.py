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


def render_globe(
    article_data: list[dict[str, Any]],
    height: int = 550,
    key: str | None = None,
) -> str | None:
    """Render the interactive globe and return the clicked country code.

    Uses ``declare_component`` for bidirectional communication: the globe
    iframe sends the ISO-2 country code back to Python when a focus
    country polygon is clicked.

    Parameters
    ----------
    article_data:
        Output of ``build_globe_data``.
    height:
        Pixel height for the globe iframe.
    key:
        Streamlit component key (for widget identity across reruns).

    Returns
    -------
    str | None:
        The ISO-2 country code if a focus country was clicked, else None.
    """
    countries_geojson = _load_countries_geojson()
    if countries_geojson is None:
        countries_geojson = {"type": "FeatureCollection", "features": []}

    clicked: str | None = _globe_component(
        article_data=article_data,
        countries_geojson=countries_geojson,
        focus_countries=list(FOCUS_COUNTRIES),
        height=height,
        default=None,
        key=key,
    )
    return clicked


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
