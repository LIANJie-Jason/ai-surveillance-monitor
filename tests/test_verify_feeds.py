"""Unit tests for scripts/verify_feeds.py — mocked HTTP, no network calls."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
import requests

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Load the script module via importlib so it doesn't require packaging as a module.
# Register in sys.modules BEFORE exec_module so @dataclass can resolve type hints.
import importlib.util
_script_path = os.path.join(_REPO_ROOT, "scripts", "verify_feeds.py")
_spec = importlib.util.spec_from_file_location("verify_feeds", _script_path)
verify_feeds = importlib.util.module_from_spec(_spec)
sys.modules["verify_feeds"] = verify_feeds
_spec.loader.exec_module(verify_feeds)


_VALID_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <link>https://example.com</link>
  <description>Test</description>
  <item>
    <title>Article 1</title>
    <link>https://example.com/1</link>
    <description>Body</description>
  </item>
  <item>
    <title>Article 2</title>
    <link>https://example.com/2</link>
    <description>Body</description>
  </item>
</channel></rss>
"""

_VALID_EMPTY_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Empty Feed</title>
  <link>https://example.com</link>
  <description>Empty</description>
</channel></rss>
"""

_NOT_XML = b"<!DOCTYPE html><html><body>404 not found</body></html>"


def _mock_session(status_code: int, content: bytes = b"", headers: dict | None = None):
    """Build a MagicMock session whose .get() returns a scripted response."""
    session = MagicMock(spec=requests.Session)
    response = MagicMock()
    response.status_code = status_code
    response.content = content
    response.headers = headers or {}
    session.get.return_value = response
    return session


def test_verify_feed_ok_with_entries():
    session = _mock_session(200, _VALID_RSS)
    result = verify_feeds.verify_feed("Test", "https://a.example/rss", session=session)
    assert result.status == "OK"
    assert result.entry_count == 2


def test_verify_feed_ok_empty():
    session = _mock_session(200, _VALID_EMPTY_RSS)
    result = verify_feeds.verify_feed("Empty", "https://a.example/rss", session=session)
    assert result.status == "OK_EMPTY"
    assert result.entry_count == 0


def test_verify_feed_redirect_includes_target():
    session = _mock_session(
        301, b"", headers={"Location": "https://new.example/rss"},
    )
    result = verify_feeds.verify_feed(
        "Moved", "https://old.example/rss", session=session,
    )
    assert result.status == "REDIRECT"
    assert result.redirect_target == "https://new.example/rss"
    assert "301" in result.detail


def test_verify_feed_http_error():
    session = _mock_session(404, b"")
    result = verify_feeds.verify_feed(
        "Gone", "https://gone.example/rss", session=session,
    )
    assert result.status == "HTTP_ERROR"
    assert "404" in result.detail


def test_verify_feed_not_xml_is_bozo_no_entries():
    session = _mock_session(200, _NOT_XML)
    result = verify_feeds.verify_feed(
        "HTML", "https://html.example/rss", session=session,
    )
    assert result.status == "BOZO_NO_ENTRIES"
    assert result.entry_count == 0


def test_verify_feed_network_timeout():
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.Timeout("timed out after 15s")
    result = verify_feeds.verify_feed(
        "Slow", "https://slow.example/rss", session=session,
    )
    assert result.status == "NETWORK_ERROR"
    assert "timeout" in result.detail.lower()


def test_verify_feed_connection_error():
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("DNS failure")
    result = verify_feeds.verify_feed(
        "NoDNS", "https://nowhere.example/rss", session=session,
    )
    assert result.status == "NETWORK_ERROR"
    assert "connection" in result.detail.lower()


def test_verify_all_uses_config_order(tmp_path):
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        "feeds:\n"
        "  - name: First\n    url: https://a.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n"
        "  - name: Second\n    url: https://b.example/rss\n"
        "    language: en\n    tier: 2\n    feed_type: major\n",
        encoding="utf-8",
    )
    session = _mock_session(200, _VALID_RSS)
    results = verify_feeds.verify_all(
        str(config_path), max_workers=2, session=session,
    )
    assert len(results) == 2
    assert results[0].name == "First"
    assert results[1].name == "Second"


def test_verify_all_skips_inactive_feeds_by_default(tmp_path):
    """Feeds marked active: false should not be verified by default."""
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        "feeds:\n"
        "  - name: Live\n    url: https://live.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n"
        "  - name: Dead\n    url: https://dead.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n"
        "    active: false\n",
        encoding="utf-8",
    )
    session = _mock_session(200, _VALID_RSS)
    results = verify_feeds.verify_all(
        str(config_path), max_workers=2, session=session,
    )
    assert len(results) == 1
    assert results[0].name == "Live"


def test_verify_all_include_inactive_opts_in(tmp_path):
    """include_inactive=True should verify feeds with active: false too."""
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        "feeds:\n"
        "  - name: Live\n    url: https://live.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n"
        "  - name: Dead\n    url: https://dead.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n"
        "    active: false\n",
        encoding="utf-8",
    )
    session = _mock_session(200, _VALID_RSS)
    results = verify_feeds.verify_all(
        str(config_path), max_workers=2, session=session,
        include_inactive=True,
    )
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"Live", "Dead"}


def test_verify_feed_bozo_has_entries():
    """Malformed XML that still has entries should be BOZO_HAS_ENTRIES."""
    bozo_xml = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Messy Feed</title>
  <link>https://example.com</link>
  <description>Malformed</description>
  <item>
    <title>Article A</title>
    <link>https://example.com/a</link>
    <description>Body</description>
  </item>
</channel></rss>
<!-- intentionally broken: no closing tag for something -->
<unclosed>
"""
    import feedparser as fp
    parsed = fp.parse(bozo_xml)
    # feedparser may or may not set bozo for trailing junk; use mock to guarantee
    session = _mock_session(200, bozo_xml)
    # Patch feedparser so bozo=True and entries present
    bozo_parsed = MagicMock()
    bozo_parsed.bozo = True
    bozo_parsed.bozo_exception = Exception("junk after document element")
    bozo_parsed.entries = [MagicMock(), MagicMock(), MagicMock()]
    bozo_parsed.version = "rss20"

    import feedparser as fp_mod
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fp_mod, "parse", lambda content: bozo_parsed)
        result = verify_feeds.verify_feed("Messy", "https://messy.example/rss", session=session)
    assert result.status == "BOZO_HAS_ENTRIES"
    assert result.entry_count == 3


def test_verify_feed_explicit_bozo_zero_entries():
    """Explicit bozo=True with zero entries (e.g. SAXParseException) → BOZO_NO_ENTRIES."""
    session = _mock_session(200, b"<broken xml with no closing tags")
    bozo_parsed = MagicMock()
    bozo_parsed.bozo = True
    bozo_parsed.bozo_exception = Exception("SAXParseException")
    bozo_parsed.entries = []
    bozo_parsed.version = ""

    import feedparser as fp_mod
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fp_mod, "parse", lambda content: bozo_parsed)
        result = verify_feeds.verify_feed("Broken", "https://broken.example/rss", session=session)
    assert result.status == "BOZO_NO_ENTRIES"
    assert result.entry_count == 0


def test_verify_feed_request_kwargs():
    """Verify exact request kwargs match ingestion worker contract."""
    session = _mock_session(200, _VALID_RSS)
    verify_feeds.verify_feed("Check", "https://check.example/rss", session=session)

    session.get.assert_called_once()
    call_kwargs = session.get.call_args
    assert call_kwargs.args == ("https://check.example/rss",)
    assert call_kwargs.kwargs["headers"] == {
        "User-Agent": "AI-Surveillance-Monitor/1.0 (+research; RSS reader)",
    }
    assert call_kwargs.kwargs["timeout"] == (5, 10)
    assert call_kwargs.kwargs["allow_redirects"] is False


def test_summarize_counts_statuses():
    results = [
        verify_feeds.VerifyResult("A", "u1", "OK", "", entry_count=5),
        verify_feeds.VerifyResult("B", "u2", "OK", "", entry_count=3),
        verify_feeds.VerifyResult("C", "u3", "HTTP_ERROR", "404"),
        verify_feeds.VerifyResult("D", "u4", "REDIRECT", "301", redirect_target="u4b"),
    ]
    counts = verify_feeds.summarize(results)
    assert counts == {"OK": 2, "HTTP_ERROR": 1, "REDIRECT": 1}


def test_main_exits_nonzero_on_broken_feeds(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        "feeds:\n"
        "  - name: Broken\n    url: https://broken.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n",
        encoding="utf-8",
    )
    broken_session = _mock_session(404, b"")
    monkeypatch.setattr(
        verify_feeds, "verify_all",
        lambda config, max_workers=8, session=None, include_inactive=False: [
            verify_feeds.VerifyResult(
                "Broken", "https://broken.example/rss", "HTTP_ERROR", "HTTP 404",
            )
        ],
    )
    monkeypatch.setattr(sys, "argv", ["verify_feeds.py", "--config", str(config_path)])
    exit_code = verify_feeds.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Broken" in captured.out
    assert "HTTP_ERROR" in captured.out


def test_main_exits_zero_when_all_healthy(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        "feeds:\n"
        "  - name: Good\n    url: https://good.example/rss\n"
        "    language: en\n    tier: 1\n    feed_type: wire\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        verify_feeds, "verify_all",
        lambda config, max_workers=8, session=None, include_inactive=False: [
            verify_feeds.VerifyResult(
                "Good", "https://good.example/rss", "OK", "5 entries", entry_count=5,
            )
        ],
    )
    monkeypatch.setattr(sys, "argv", ["verify_feeds.py", "--config", str(config_path)])
    exit_code = verify_feeds.main()
    assert exit_code == 0
