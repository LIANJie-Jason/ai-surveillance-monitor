"""Live stream component — YouTube live news embed for drill-down countries."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import yaml

from dashboard.components._utils import safe_embed_url

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "streams.yaml"

_EMPTY: dict[str, Any] = {"streams": {}, "fallbacks": {}}

# Successful-load cache. Failures return _EMPTY but are NOT cached.
_streams_cache: dict[str, Any] | None = None


def load_streams() -> dict[str, Any]:
    """Load stream definitions from config/streams.yaml.

    Returns a dict with 'streams' and 'fallbacks' keys.
    Returns empty structure if file is missing or malformed — failures are
    NOT cached so the dashboard can recover after transient read errors.
    """
    global _streams_cache
    if _streams_cache is not None:
        return _streams_cache
    try:
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("streams.yaml not found at %s", _CONFIG_PATH)
        return _EMPTY
    except yaml.YAMLError:
        logger.warning("streams.yaml is malformed")
        return _EMPTY
    if not isinstance(raw, dict):
        logger.warning("streams.yaml top-level is not a dict")
        return _EMPTY
    if "streams" not in raw and "fallbacks" not in raw:
        # Schema mismatch — don't cache so the file can be fixed in place.
        logger.warning("streams.yaml missing both 'streams' and 'fallbacks' keys")
        return _EMPTY
    _streams_cache = {
        "streams": raw.get("streams", {}),
        "fallbacks": raw.get("fallbacks", {}),
    }
    return _streams_cache


def _clear_streams_cache() -> None:
    """Clear the successful-load cache (for tests and deployment reloads)."""
    global _streams_cache
    _streams_cache = None


# Preserve the `load_streams.cache_clear()` API that tests rely on.
load_streams.cache_clear = _clear_streams_cache  # type: ignore[attr-defined]


def get_stream_for_country(country_code: str) -> dict[str, Any] | None:
    """Return the primary stream dict for a country, or None."""
    data = load_streams()
    stream = data["streams"].get(country_code)
    if stream is None:
        return None
    return dict(stream)


def get_fallback_stream(country_code: str) -> dict[str, Any] | None:
    """Return the fallback stream dict for a country, or None."""
    data = load_streams()
    stream = data["fallbacks"].get(country_code)
    if stream is None:
        return None
    return dict(stream)


def render_live_stream(
    country_code: str,
    *,
    use_fallback: bool = False,
    height: int = 400,
) -> str:
    """Render a YouTube live stream iframe for the given country.

    All user-facing text is HTML-escaped. URLs are validated for https scheme.
    Returns a placeholder if no stream is available.
    """
    height = int(height)  # defense-in-depth: ensure numeric
    if use_fallback:
        stream = get_fallback_stream(country_code)
    else:
        stream = get_stream_for_country(country_code)

    if stream is None:
        return (
            '<div class="live-stream-container">'
            '<p style="color:#8b949e;text-align:center;padding:40px;">'
            "No live stream available for this country."
            "</p></div>"
        )

    name = html.escape(stream.get("name", ""))
    description = html.escape(stream.get("description", ""))
    embed_url = safe_embed_url(stream.get("embed_url", ""))

    if not embed_url:
        return (
            '<div class="live-stream-container">'
            f'<h4 style="color:#e6edf3;">{name}</h4>'
            '<p style="color:#8b949e;">Stream URL is unavailable.</p>'
            "</div>"
        )

    escaped_url = html.escape(embed_url)

    return (
        f'<div class="live-stream-container">'
        f'<h4 style="color:#e6edf3;margin:0 0 8px 0;">'
        f'<span style="background:#e53935;color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:12px;margin-right:8px;">LIVE</span>'
        f"{name}</h4>"
        f'<p style="color:#8b949e;margin:0 0 8px 0;font-size:13px;">'
        f"{description}</p>"
        f'<iframe src="{escaped_url}" '
        f'width="100%" height="{height}" '
        f'frameborder="0" allowfullscreen '
        f'allow="autoplay; encrypted-media" '
        f'style="border-radius:8px;"></iframe>'
        f"</div>"
    )
