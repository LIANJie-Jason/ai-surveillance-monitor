"""Dynamic resolution of YouTube channel IDs to live video IDs.

YouTube deprecated the ``live_stream?channel=`` embed format.  At dashboard
startup this module resolves channel IDs from the YAML configs into current
live video IDs using the YouTube Data API v3, producing working
``youtube.com/embed/<VIDEO_ID>`` URLs.

Fallback chain for webcams
--------------------------
1. Resolve configured YouTube channel → live video embed
2. Search YouTube for ``<city> live webcam`` → any matching live stream
3. Leave ``embed_url`` empty; the renderer shows a SkylineWebcams link
   (if ``skyline_url`` is set in config) or a placeholder.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

_YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/search"
_REQUEST_TIMEOUT = 10
_YT_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def extract_channel_id(embed_url: str) -> str | None:
    """Extract YouTube channel ID from a ``live_stream?channel=`` URL.

    >>> extract_channel_id(
    ...     "https://www.youtube.com/embed/live_stream?channel=UCxyz"
    ... )
    'UCxyz'
    >>> extract_channel_id("https://example.com") is None
    True
    """
    if not embed_url or not isinstance(embed_url, str):
        return None
    try:
        parsed = urlparse(embed_url)
        params = parse_qs(parsed.query)
        channels = params.get("channel", [])
        return channels[0] if channels else None
    except (ValueError, TypeError):
        return None


def resolve_live_video_id(channel_id: str, api_key: str) -> str | None:
    """Find the current live video ID for a YouTube channel.

    Uses the YouTube Data API v3 ``search.list`` endpoint.
    Costs 100 quota units per call (daily free quota: 10,000 units).
    Returns ``None`` if the channel has no active live stream.
    """
    try:
        resp = requests.get(
            _YOUTUBE_API_URL,
            params={
                "part": "id",
                "channelId": channel_id,
                "type": "video",
                "eventType": "live",
                "maxResults": 1,
                "key": api_key,
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return items[0]["id"]["videoId"]
    except requests.RequestException as exc:
        logger.warning("YouTube API request failed for channel %s: %s", channel_id, exc)
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected API response for channel %s", channel_id)
    return None


def search_youtube_live(query: str, api_key: str) -> str | None:
    """Search YouTube for any currently-live stream matching *query*.

    Used as fallback when a configured channel is not live — e.g. to
    find a ``"Delhi live webcam"`` stream from any channel.
    """
    if not query or not isinstance(query, str):
        return None
    try:
        resp = requests.get(
            _YOUTUBE_API_URL,
            params={
                "part": "id",
                "q": query,
                "type": "video",
                "eventType": "live",
                "maxResults": 1,
                "key": api_key,
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return items[0]["id"]["videoId"]
    except requests.RequestException as exc:
        logger.warning("YouTube search failed for '%s': %s", query, exc)
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected search response for '%s'", query)
    return None


def video_embed_url(video_id: str) -> str:
    """Build an embeddable YouTube URL from a video ID.

    Validates that *video_id* matches the expected YouTube format
    (alphanumeric + hyphens/underscores, max 20 chars) to prevent
    path traversal if the API ever returns a crafted value.
    """
    if not _YT_VIDEO_ID_RE.match(video_id):
        logger.warning("Invalid YouTube video ID: %r", video_id)
        return ""
    return f"https://www.youtube.com/embed/{video_id}"


# ------------------------------------------------------------------ #
#  Batch resolution for config dicts                                  #
# ------------------------------------------------------------------ #


def _is_direct_embed(url: str) -> bool:
    """Check if a URL is already a direct ``/embed/<VIDEO_ID>`` URL.

    Returns True for URLs like ``/embed/dQw4w9WgXcQ`` but False for
    deprecated ``/embed/live_stream?channel=`` URLs.
    """
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    # Must be /embed/<something> but NOT /embed/live_stream
    if not path.startswith("/embed/"):
        return False
    video_part = path[len("/embed/"):]
    return bool(video_part) and video_part != "live_stream"


def resolve_streams(
    streams_config: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Resolve all stream channel IDs to current live video embed URLs.

    Returns a new config dict with the same structure as the input
    (``{"streams": {...}, "fallbacks": {...}}``), but with ``embed_url``
    fields pointing to resolved ``/embed/<VIDEO_ID>`` URLs.  Streams
    that already have direct ``/embed/<VIDEO_ID>`` URLs are kept as-is.
    Streams that cannot be resolved keep their original ``embed_url``.
    """
    result: dict[str, Any] = {}
    for section in ("streams", "fallbacks"):
        result[section] = {}
        for cc, stream in (streams_config.get(section) or {}).items():
            new = dict(stream)
            embed_url = stream.get("embed_url", "")

            # Already a direct video embed — skip resolution
            if _is_direct_embed(embed_url):
                logger.info("Stream %s/%s already direct — skipping", section, cc)
                result[section][cc] = new
                continue

            cid = extract_channel_id(embed_url)
            vid: str | None = None

            # Step 1: channel ID lookup
            if cid:
                vid = resolve_live_video_id(cid, api_key)

            # Step 2: search by stream name (more reliable)
            name = stream.get("name", "")
            if not vid and name:
                vid = search_youtube_live(f"{name} live", api_key)

            if vid:
                url = video_embed_url(vid)
                if url:
                    new["embed_url"] = url
                    logger.info(
                        "Stream %s/%s resolved → video %s",
                        section, cc, vid,
                    )
            result[section][cc] = new
    return result


def resolve_webcams(
    webcams_config: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Resolve webcam channel IDs to current live video embed URLs.

    Fallback chain per webcam:

    1. Resolve configured YouTube channel → live video
    2. Search YouTube for ``"<city> live webcam"``
    3. Clear ``embed_url`` so the renderer falls through to the
       ``skyline_url`` link or a placeholder.
    """
    result: dict[str, Any] = {"webcams": {}}
    for cc, cams in (webcams_config.get("webcams") or {}).items():
        resolved_cams: list[dict[str, Any]] = []
        for cam in cams:
            new = dict(cam)
            city = cam.get("city", "")
            embed_url = cam.get("embed_url", "")

            # Already a direct video embed — skip resolution
            if _is_direct_embed(embed_url):
                logger.info("Webcam %s/%s already direct — skipping", cc, city)
                resolved_cams.append(new)
                continue

            cid = extract_channel_id(embed_url)
            vid: str | None = None

            # Step 1: try configured channel
            if cid:
                vid = resolve_live_video_id(cid, api_key)

            # Step 2: search YouTube for city webcam
            if not vid and city:
                vid = search_youtube_live(f"{city} live webcam", api_key)

            resolved = False
            if vid:
                url = video_embed_url(vid)
                if url:
                    new["embed_url"] = url
                    resolved = True
                    logger.info("Webcam %s/%s resolved → video %s", cc, city, vid)

            if not resolved:
                # Clear broken channel URL; renderer will use skyline_url
                # fallback or show a placeholder.
                new["embed_url"] = ""
                logger.warning("No live feed for webcam %s/%s", cc, city)

            resolved_cams.append(new)
        result["webcams"][cc] = resolved_cams
    return result
