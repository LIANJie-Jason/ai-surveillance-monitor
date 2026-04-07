"""Webcam grid component — city webcam embeds for drill-down countries."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import yaml

from dashboard.components._utils import safe_embed_url

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "webcams.yaml"

_EMPTY: dict[str, Any] = {"webcams": {}}

# Successful-load cache. Failures return _EMPTY but are NOT cached.
_webcams_cache: dict[str, Any] | None = None


def load_webcams() -> dict[str, Any]:
    """Load webcam definitions from config/webcams.yaml.

    Returns a dict with a 'webcams' key.
    Returns empty structure if file is missing or malformed — failures are
    NOT cached so the dashboard can recover after transient read errors.
    """
    global _webcams_cache
    if _webcams_cache is not None:
        return _webcams_cache
    try:
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("webcams.yaml not found at %s", _CONFIG_PATH)
        return _EMPTY
    except yaml.YAMLError:
        logger.warning("webcams.yaml is malformed")
        return _EMPTY
    if not isinstance(raw, dict) or not isinstance(raw.get("webcams"), dict):
        logger.warning("webcams.yaml missing 'webcams' dict")
        return _EMPTY
    _webcams_cache = {"webcams": raw["webcams"]}
    return _webcams_cache


def _clear_webcams_cache() -> None:
    """Clear the successful-load cache (for tests and deployment reloads)."""
    global _webcams_cache
    _webcams_cache = None


# Preserve the `load_webcams.cache_clear()` API that tests rely on.
load_webcams.cache_clear = _clear_webcams_cache  # type: ignore[attr-defined]


def get_webcams_for_country(country_code: str) -> list[dict[str, Any]]:
    """Return list of webcam dicts for a country, or empty list."""
    data = load_webcams()
    cams = data["webcams"].get(country_code)
    if cams is None:
        return []
    return [dict(c) for c in cams]


def _render_cam_cell(cam: dict[str, Any], cam_height: int) -> str:
    """Render a single webcam cell with city label, badge, and iframe or placeholder."""
    city = html.escape(cam.get("city", "Unknown"))
    cam_type = cam.get("type", "webcam")
    embed_url = safe_embed_url(cam.get("embed_url", ""))

    # Badge: LIVE for webcams, NEWS for news fallbacks
    if cam_type == "news_fallback":
        badge = (
            '<span style="background:#1565c0;color:#fff;padding:2px 6px;'
            'border-radius:3px;font-size:11px;margin-left:6px;">NEWS</span>'
        )
    else:
        badge = (
            '<span style="background:#e53935;color:#fff;padding:2px 6px;'
            'border-radius:3px;font-size:11px;margin-left:6px;">LIVE</span>'
        )

    label_html = (
        f'<div style="color:#e6edf3;font-size:13px;font-weight:600;'
        f'margin-bottom:4px;">{city}{badge}</div>'
    )

    if embed_url:
        escaped_url = html.escape(embed_url)
        content_html = (
            f'<iframe src="{escaped_url}" '
            f'width="100%" height="{cam_height}" '
            f'frameborder="0" allowfullscreen '
            f'allow="autoplay; encrypted-media" '
            f'style="border-radius:6px;"></iframe>'
        )
    else:
        content_html = (
            f'<div style="width:100%;height:{cam_height}px;'
            f"background:#161b22;border-radius:6px;display:flex;"
            f'align-items:center;justify-content:center;color:#8b949e;">'
            f"No live feed available</div>"
        )

    return f'<div style="min-width:0;">{label_html}{content_html}</div>'


def render_webcam_grid(
    country_code: str,
    *,
    cam_height: int = 200,
) -> str:
    """Render a 2x2 CSS grid of webcam iframes for the given country.

    All user-facing text is HTML-escaped. URLs are validated for https scheme.
    Shows placeholder if no webcams exist for the country.
    """
    cam_height = int(cam_height)  # defense-in-depth: ensure numeric
    cams = get_webcams_for_country(country_code)

    if not cams:
        return (
            '<div class="webcam-grid-container">'
            '<p style="color:#8b949e;text-align:center;padding:20px;">'
            "No webcams available for this country."
            "</p></div>"
        )

    cells = [_render_cam_cell(cam, cam_height) for cam in cams]
    cells_html = "\n".join(cells)

    return (
        f'<div class="webcam-grid-container">'
        f'<div style="display:grid;grid-template-columns:repeat(2,1fr);'
        f'gap:12px;">'
        f"{cells_html}"
        f"</div></div>"
    )
