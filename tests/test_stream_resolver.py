# tests/test_stream_resolver.py
"""Tests for src/stream_resolver.py — YouTube channel → live video resolution."""

import pytest
from unittest.mock import MagicMock, patch

from src.stream_resolver import (
    _is_direct_embed,
    extract_channel_id,
    resolve_live_video_id,
    search_youtube_live,
    video_embed_url,
    resolve_streams,
    resolve_webcams,
)


# ------------------------------------------------------------------ #
#  extract_channel_id                                                  #
# ------------------------------------------------------------------ #


class TestExtractChannelId:

    def test_extracts_from_standard_url(self):
        url = "https://www.youtube.com/embed/live_stream?channel=UCwm3CPHM4bQup8sYMgLYGOw"
        assert extract_channel_id(url) == "UCwm3CPHM4bQup8sYMgLYGOw"

    def test_extracts_with_extra_params(self):
        url = "https://www.youtube.com/embed/live_stream?channel=UCxyz&autoplay=1"
        assert extract_channel_id(url) == "UCxyz"

    def test_returns_none_for_no_channel_param(self):
        assert extract_channel_id("https://example.com") is None

    def test_returns_none_for_video_url(self):
        assert extract_channel_id("https://www.youtube.com/embed/dQw4w9WgXcQ") is None

    def test_returns_none_for_empty_string(self):
        assert extract_channel_id("") is None

    def test_returns_none_for_none(self):
        assert extract_channel_id(None) is None

    def test_returns_none_for_non_string(self):
        assert extract_channel_id(42) is None


# ------------------------------------------------------------------ #
#  video_embed_url                                                     #
# ------------------------------------------------------------------ #


class TestVideoEmbedUrl:

    def test_builds_correct_url(self):
        assert video_embed_url("abc123") == "https://www.youtube.com/embed/abc123"

    def test_handles_typical_youtube_id(self):
        url = video_embed_url("dQw4w9WgXcQ")
        assert url == "https://www.youtube.com/embed/dQw4w9WgXcQ"

    def test_rejects_path_traversal(self):
        assert video_embed_url("../steal") == ""

    def test_rejects_empty_string(self):
        assert video_embed_url("") == ""

    def test_rejects_too_long(self):
        assert video_embed_url("a" * 21) == ""

    def test_allows_hyphens_and_underscores(self):
        assert video_embed_url("a-b_c-D_E1") == "https://www.youtube.com/embed/a-b_c-D_E1"


# ------------------------------------------------------------------ #
#  resolve_live_video_id                                               #
# ------------------------------------------------------------------ #


class TestResolveLiveVideoId:

    @patch("src.stream_resolver.requests.get")
    def test_returns_video_id_when_live(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"id": {"videoId": "LIVE_VID_123"}}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = resolve_live_video_id("UCxyz", "fake-key")
        assert result == "LIVE_VID_123"

        # Verify API call params
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["channelId"] == "UCxyz"
        assert call_kwargs[1]["params"]["eventType"] == "live"
        assert call_kwargs[1]["params"]["key"] == "fake-key"

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_when_not_live(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert resolve_live_video_id("UCxyz", "fake-key") is None

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_on_connection_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.ConnectionError("connection refused")
        assert resolve_live_video_id("UCxyz", "fake-key") is None

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("403 Forbidden")
        mock_get.return_value = mock_resp
        assert resolve_live_video_id("UCxyz", "fake-key") is None

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_on_malformed_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "bad request"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert resolve_live_video_id("UCxyz", "fake-key") is None

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_on_key_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [{"wrong_key": "val"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert resolve_live_video_id("UCxyz", "fake-key") is None


# ------------------------------------------------------------------ #
#  search_youtube_live                                                 #
# ------------------------------------------------------------------ #


class TestSearchYoutubeLive:

    @patch("src.stream_resolver.requests.get")
    def test_returns_video_id_for_matching_search(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"id": {"videoId": "SEARCH_VID_456"}}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = search_youtube_live("Delhi live webcam", "fake-key")
        assert result == "SEARCH_VID_456"

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["q"] == "Delhi live webcam"

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_for_no_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert search_youtube_live("Nonexistent city", "fake-key") is None

    def test_returns_none_for_empty_query(self):
        assert search_youtube_live("", "fake-key") is None

    def test_returns_none_for_none_query(self):
        assert search_youtube_live(None, "fake-key") is None

    @patch("src.stream_resolver.requests.get")
    def test_returns_none_on_network_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.Timeout("timed out")
        assert search_youtube_live("Delhi webcam", "fake-key") is None


# ------------------------------------------------------------------ #
#  _is_direct_embed                                                    #
# ------------------------------------------------------------------ #


class TestIsDirectEmbed:

    def test_true_for_direct_video_embed(self):
        assert _is_direct_embed("https://www.youtube.com/embed/ABC123") is True

    def test_false_for_live_stream_channel_url(self):
        url = "https://www.youtube.com/embed/live_stream?channel=UCxyz"
        assert _is_direct_embed(url) is False

    def test_false_for_non_embed_youtube_url(self):
        assert _is_direct_embed("https://www.youtube.com/watch?v=ABC123") is False

    def test_false_for_empty_string(self):
        assert _is_direct_embed("") is False


# ------------------------------------------------------------------ #
#  resolve_streams                                                     #
# ------------------------------------------------------------------ #


class TestResolveStreams:

    @patch("src.stream_resolver.resolve_live_video_id")
    def test_resolves_live_channels(self, mock_resolve):
        mock_resolve.return_value = "VID_001"

        config = {
            "streams": {
                "IN": {
                    "name": "NDTV",
                    "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCndtv",
                },
            },
            "fallbacks": {
                "IN": {
                    "name": "India Today",
                    "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCit",
                },
            },
        }

        result = resolve_streams(config, "fake-key")

        assert result["streams"]["IN"]["embed_url"] == "https://www.youtube.com/embed/VID_001"
        assert result["streams"]["IN"]["name"] == "NDTV"
        assert result["fallbacks"]["IN"]["embed_url"] == "https://www.youtube.com/embed/VID_001"

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_falls_back_to_name_search(self, mock_resolve, mock_search):
        mock_resolve.return_value = None  # channel lookup fails
        mock_search.return_value = "SEARCH_VID"

        config = {
            "streams": {
                "IN": {
                    "name": "NDTV 24x7",
                    "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCndtv",
                },
            },
            "fallbacks": {},
        }

        result = resolve_streams(config, "fake-key")
        assert result["streams"]["IN"]["embed_url"] == "https://www.youtube.com/embed/SEARCH_VID"
        mock_search.assert_called_once_with("NDTV 24x7 live", "fake-key")

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_keeps_original_url_when_not_live(self, mock_resolve, mock_search):
        mock_resolve.return_value = None
        mock_search.return_value = None  # search also fails

        config = {
            "streams": {
                "IN": {
                    "name": "NDTV",
                    "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCndtv",
                },
            },
            "fallbacks": {},
        }

        result = resolve_streams(config, "fake-key")

        # Original URL is preserved (not cleared)
        assert result["streams"]["IN"]["embed_url"] == (
            "https://www.youtube.com/embed/live_stream?channel=UCndtv"
        )

    @patch("src.stream_resolver.resolve_live_video_id")
    def test_handles_empty_config(self, mock_resolve):
        result = resolve_streams({}, "fake-key")
        assert result == {"streams": {}, "fallbacks": {}}
        mock_resolve.assert_not_called()

    @patch("src.stream_resolver.resolve_live_video_id")
    def test_handles_none_sections(self, mock_resolve):
        result = resolve_streams({"streams": None, "fallbacks": None}, "fake-key")
        assert result == {"streams": {}, "fallbacks": {}}


# ------------------------------------------------------------------ #
#  resolve_webcams                                                     #
# ------------------------------------------------------------------ #


class TestResolveWebcams:

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_resolves_via_channel_id(self, mock_resolve, mock_search):
        mock_resolve.return_value = "CAM_VID_001"

        config = {
            "webcams": {
                "ZA": [
                    {
                        "city": "Cape Town",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCct",
                    },
                ],
            },
        }

        result = resolve_webcams(config, "fake-key")
        cam = result["webcams"]["ZA"][0]

        assert cam["embed_url"] == "https://www.youtube.com/embed/CAM_VID_001"
        mock_search.assert_not_called()  # channel resolved, no search needed

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_falls_back_to_youtube_search(self, mock_resolve, mock_search):
        mock_resolve.return_value = None  # channel not live
        mock_search.return_value = "SEARCH_VID_002"

        config = {
            "webcams": {
                "IN": [
                    {
                        "city": "Delhi",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCdel",
                    },
                ],
            },
        }

        result = resolve_webcams(config, "fake-key")
        cam = result["webcams"]["IN"][0]

        assert cam["embed_url"] == "https://www.youtube.com/embed/SEARCH_VID_002"
        mock_search.assert_called_once_with("Delhi live webcam", "fake-key")

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_clears_url_when_all_fail(self, mock_resolve, mock_search):
        mock_resolve.return_value = None
        mock_search.return_value = None

        config = {
            "webcams": {
                "NG": [
                    {
                        "city": "Lagos",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UClag",
                        "skyline_url": "https://skylinewebcams.com/lagos",
                    },
                ],
            },
        }

        result = resolve_webcams(config, "fake-key")
        cam = result["webcams"]["NG"][0]

        assert cam["embed_url"] == ""  # cleared so renderer uses skyline fallback
        assert cam["skyline_url"] == "https://skylinewebcams.com/lagos"

    @patch("src.stream_resolver.resolve_live_video_id")
    def test_handles_empty_config(self, mock_resolve):
        result = resolve_webcams({}, "fake-key")
        assert result == {"webcams": {}}

    @patch("src.stream_resolver.resolve_live_video_id")
    def test_handles_none_webcams(self, mock_resolve):
        result = resolve_webcams({"webcams": None}, "fake-key")
        assert result == {"webcams": {}}

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_preserves_other_cam_fields(self, mock_resolve, mock_search):
        mock_resolve.return_value = "VID_X"

        config = {
            "webcams": {
                "ZA": [
                    {
                        "city": "Cape Town",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCct",
                        "type": "webcam",
                        "lat": -33.9249,
                        "lng": 18.4241,
                        "skyline_url": "https://skylinewebcams.com/ct",
                    },
                ],
            },
        }

        result = resolve_webcams(config, "fake-key")
        cam = result["webcams"]["ZA"][0]

        assert cam["city"] == "Cape Town"
        assert cam["type"] == "webcam"
        assert cam["lat"] == -33.9249
        assert cam["skyline_url"] == "https://skylinewebcams.com/ct"
        assert cam["embed_url"] == "https://www.youtube.com/embed/VID_X"

    @patch("src.stream_resolver.search_youtube_live")
    @patch("src.stream_resolver.resolve_live_video_id")
    def test_multiple_cams_per_country(self, mock_resolve, mock_search):
        # First cam resolves, second doesn't
        mock_resolve.side_effect = ["VID_A", None]
        mock_search.return_value = None

        config = {
            "webcams": {
                "IN": [
                    {
                        "city": "Delhi",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UC1",
                    },
                    {
                        "city": "Mumbai",
                        "embed_url": "https://www.youtube.com/embed/live_stream?channel=UC2",
                    },
                ],
            },
        }

        result = resolve_webcams(config, "fake-key")
        cams = result["webcams"]["IN"]

        assert cams[0]["embed_url"] == "https://www.youtube.com/embed/VID_A"
        assert cams[1]["embed_url"] == ""  # search also returned None


# ------------------------------------------------------------------ #
#  Webcam renderer — SkylineWebcams fallback                          #
# ------------------------------------------------------------------ #


class TestWebcamSkylineFallback:
    """Test that webcams.py renders SkylineWebcams link when embed_url is empty."""

    def test_skyline_link_rendered_when_no_embed(self):
        from dashboard.components.webcams import _render_cam_cell

        cam = {
            "city": "Cape Town",
            "type": "webcam",
            "embed_url": "",
            "skyline_url": "https://www.skylinewebcams.com/en/webcam/south-africa/ct.html",
        }

        html = _render_cam_cell(cam, cam_height=200)

        assert "SkylineWebcams" in html
        assert "skylinewebcams.com" in html
        assert "target=\"_blank\"" in html
        assert "Cape Town" in html

    def test_iframe_rendered_when_embed_url_present(self):
        from dashboard.components.webcams import _render_cam_cell

        cam = {
            "city": "Delhi",
            "type": "webcam",
            "embed_url": "https://www.youtube.com/embed/abc123",
        }

        html = _render_cam_cell(cam, cam_height=200)

        assert "<iframe" in html
        assert "abc123" in html
        assert "SkylineWebcams" not in html

    def test_skyline_javascript_scheme_blocked(self):
        """skyline_url with javascript: scheme must not render as link."""
        from dashboard.components.webcams import _render_cam_cell

        cam = {
            "city": "Evil",
            "type": "webcam",
            "embed_url": "",
            "skyline_url": "javascript:alert(1)",
        }

        html = _render_cam_cell(cam, cam_height=200)

        # Should render as placeholder, NOT as a clickable link
        assert "SkylineWebcams" not in html
        assert "javascript" not in html
        assert "No live feed available" in html

    def test_skyline_http_scheme_blocked(self):
        """skyline_url with http: (not https:) must not render as link."""
        from dashboard.components.webcams import _render_cam_cell

        cam = {
            "city": "Insecure",
            "type": "webcam",
            "embed_url": "",
            "skyline_url": "http://skylinewebcams.com/cam.html",
        }

        html = _render_cam_cell(cam, cam_height=200)

        assert "SkylineWebcams" not in html
        assert "No live feed available" in html

    def test_placeholder_when_no_embed_and_no_skyline(self):
        from dashboard.components.webcams import _render_cam_cell

        cam = {
            "city": "Abuja",
            "type": "news_fallback",
            "embed_url": "",
        }

        html = _render_cam_cell(cam, cam_height=200)

        assert "No live feed available" in html
        assert "SkylineWebcams" not in html
        assert "<iframe" not in html
