# tests/test_news_feed.py
"""Tests for the news feed and article detail components."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from src.models import Article


# --- Helper to build test articles ---


def _make_article(**overrides: Any) -> Article:
    """Build an Article with sensible defaults, overriding any field."""
    defaults = dict(
        id="a1",
        url="https://example.com/1",
        title="Test headline",
        source_name="TestSource",
        source_lang="en",
        source_tier=1,
        is_surveillance=True,
        confidence=0.92,
        category="surveillance",
        country_code="IN",
        country_name="India",
        region="Delhi",
        summary_en="A test summary of the article.",
        published_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 4, 1, 12, 5, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


# ===================================================================
# news_feed.py tests
# ===================================================================


# --- format_time_ago ---


def test_format_time_ago_seconds():
    """Times < 60s ago should show 'just now'."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 12, 0, 30, tzinfo=timezone.utc)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert format_time_ago(t, now) == "just now"


def test_format_time_ago_minutes():
    """Times < 60min ago should show 'Xm ago'."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 12, 30, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert format_time_ago(t, now) == "30m ago"


def test_format_time_ago_hours():
    """Times < 24h ago should show 'Xh ago'."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 15, 0, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert format_time_ago(t, now) == "3h ago"


def test_format_time_ago_days():
    """Times >= 24h ago should show 'Xd ago'."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert format_time_ago(t, now) == "2d ago"


def test_format_time_ago_none():
    """None published_at should return 'unknown'."""
    from dashboard.components.news_feed import format_time_ago
    assert format_time_ago(None) == "unknown"


def test_format_time_ago_future():
    """Future times should return 'just now' (not negative)."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    t = datetime(2026, 4, 1, 13, 0, 0, tzinfo=timezone.utc)
    assert format_time_ago(t, now) == "just now"


# --- confidence_class ---


def test_confidence_class_high():
    """Confidence >= 0.8 should return 'confidence-high'."""
    from dashboard.components.news_feed import confidence_class
    assert confidence_class(0.92) == "confidence-high"
    assert confidence_class(0.80) == "confidence-high"


def test_confidence_class_medium():
    """Confidence < 0.8 should return 'confidence-medium'."""
    from dashboard.components.news_feed import confidence_class
    assert confidence_class(0.79) == "confidence-medium"
    assert confidence_class(0.60) == "confidence-medium"


def test_confidence_class_none():
    """None confidence should return 'confidence-medium'."""
    from dashboard.components.news_feed import confidence_class
    assert confidence_class(None) == "confidence-medium"


# --- render_article_card ---


def test_render_article_card_returns_html():
    """Should return an HTML string with article-card class."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article()
    html = render_article_card(article)
    assert isinstance(html, str)
    assert "article-card" in html


def test_render_article_card_contains_title():
    """Card should include the article title."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(title="Facial recognition in Delhi")
    html = render_article_card(article)
    assert "Facial recognition in Delhi" in html


def test_render_article_card_contains_confidence():
    """Card should show the confidence score."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(confidence=0.92)
    html = render_article_card(article)
    assert "0.92" in html


def test_render_article_card_contains_source():
    """Card should show the source name."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(source_name="The Wire")
    html = render_article_card(article)
    assert "The Wire" in html


def test_render_article_card_contains_country():
    """Card should show the country name."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(country_name="India")
    html = render_article_card(article)
    assert "India" in html


def test_render_article_card_escapes_xss():
    """HTML special characters in title must be escaped."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(title='<script>alert("xss")</script>')
    html = render_article_card(article)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_article_card_escapes_source_xss():
    """HTML special characters in source_name must be escaped."""
    from dashboard.components.news_feed import render_article_card
    article = _make_article(source_name='<img onerror="alert(1)">')
    html = render_article_card(article)
    assert '<img onerror' not in html


# --- render_news_feed ---


def test_render_news_feed_returns_html():
    """Should return HTML with news-feed class."""
    from dashboard.components.news_feed import render_news_feed
    articles = [_make_article()]
    html = render_news_feed(articles)
    assert "news-feed" in html


def test_render_news_feed_empty():
    """Empty article list should show a 'no articles' message."""
    from dashboard.components.news_feed import render_news_feed
    html = render_news_feed([])
    assert "no" in html.lower() or "empty" in html.lower()


def test_render_news_feed_multiple_cards():
    """Multiple articles should produce multiple cards."""
    from dashboard.components.news_feed import render_news_feed
    articles = [
        _make_article(id="a1", title="Article 1"),
        _make_article(id="a2", title="Article 2"),
        _make_article(id="a3", title="Article 3"),
    ]
    html = render_news_feed(articles)
    assert html.count("article-card") == 3


def test_render_news_feed_sorted_by_confidence():
    """Articles should be rendered highest confidence first."""
    from dashboard.components.news_feed import render_news_feed
    articles = [
        _make_article(id="a1", title="Low", confidence=0.60),
        _make_article(id="a2", title="High", confidence=0.95),
        _make_article(id="a3", title="Mid", confidence=0.75),
    ]
    html = render_news_feed(articles)
    pos_high = html.index("High")
    pos_mid = html.index("Mid")
    pos_low = html.index("Low")
    assert pos_high < pos_mid < pos_low


# ===================================================================
# article_detail.py tests
# ===================================================================


# --- render_article_detail ---


def test_render_detail_returns_html():
    """Should return an HTML string."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article()
    html = render_article_detail(article)
    assert isinstance(html, str)


def test_render_detail_shows_title():
    """Should display the article title."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(title="Delhi surveillance expansion")
    html = render_article_detail(article)
    assert "Delhi surveillance expansion" in html


def test_render_detail_shows_title_en():
    """Should display the English title when available."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(title="Título original", title_en="English Title")
    html = render_article_detail(article)
    assert "English Title" in html


def test_render_detail_shows_original_title_when_different():
    """Should show both titles when title_en differs from title."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(title="Título original", title_en="English Title")
    html = render_article_detail(article)
    assert "Título original" in html
    assert "English Title" in html


def test_render_detail_shows_summary():
    """Should display the AI summary."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(summary_en="Surveillance cameras deployed across Delhi.")
    html = render_article_detail(article)
    assert "Surveillance cameras deployed across Delhi." in html


def test_render_detail_shows_confidence():
    """Should display the confidence score."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(confidence=0.87)
    html = render_article_detail(article)
    assert "0.87" in html


def test_render_detail_shows_category():
    """Should display the category."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(category="facial_recognition")
    html = render_article_detail(article)
    assert "facial_recognition" in html


def test_render_detail_shows_source_with_tier():
    """Should display the source name and tier."""
    from dashboard.components.article_detail import render_article_detail
    # The Wire is an India regional outlet → tier 4 under the 4-tier rubric
    # (wire / major international / specialty / regional). See config/feeds.yaml.
    article = _make_article(source_name="The Wire", source_tier=4)
    html = render_article_detail(article)
    assert "The Wire" in html
    assert "Tier 4" in html or "tier 4" in html.lower()


def test_render_detail_shows_published_date():
    """Should display the published date."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(published_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc))
    html = render_article_detail(article)
    assert "2026-04-01" in html


def test_render_detail_shows_link():
    """Should include a link to the original article."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(url="https://thewire.in/article/123")
    html = render_article_detail(article)
    assert "https://thewire.in/article/123" in html


def test_render_detail_link_opens_new_tab():
    """Link should open in a new tab (target=_blank)."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article()
    html = render_article_detail(article)
    assert 'target="_blank"' in html


def test_render_detail_link_has_noopener():
    """Link should have rel=noopener for security."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article()
    html = render_article_detail(article)
    assert "noopener" in html


def test_render_detail_escapes_xss_title():
    """HTML in title must be escaped."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(title='<script>alert(1)</script>')
    html = render_article_detail(article)
    assert "<script>" not in html


def test_render_detail_escapes_xss_summary():
    """HTML in summary must be escaped."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(summary_en='<img onerror="alert(1)">')
    html = render_article_detail(article)
    assert '<img onerror' not in html


def test_render_detail_escapes_xss_url():
    """URL with javascript: scheme must be escaped or sanitized."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(url="javascript:alert(1)")
    html = render_article_detail(article)
    assert 'href="javascript:' not in html


def test_render_detail_none_article():
    """None article should return a placeholder message."""
    from dashboard.components.article_detail import render_article_detail
    html = render_article_detail(None)
    assert "select" in html.lower() or "click" in html.lower()


def test_render_detail_missing_summary():
    """Article with no summary should still render."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(summary_en=None)
    html = render_article_detail(article)
    assert isinstance(html, str)


def test_render_detail_missing_published_at():
    """Article with no published_at should show 'Unknown'."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(published_at=None)
    html = render_article_detail(article)
    assert "Unknown" in html


def test_render_detail_missing_summary_shows_fallback():
    """Article with no summary should show fallback text."""
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(summary_en=None)
    html = render_article_detail(article)
    assert "No summary available" in html


# --- Additional edge-case and security tests ---


def test_format_time_ago_naive_datetime():
    """Naive (no tzinfo) datetime should not crash — assumes UTC."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 12, 30, 0)  # naive
    t = datetime(2026, 4, 1, 12, 0, 0)  # naive
    assert format_time_ago(t, now) == "30m ago"


def test_format_time_ago_mixed_tz_aware_naive():
    """Mixed tz-aware published_at and naive now should not crash."""
    from dashboard.components.news_feed import format_time_ago
    now = datetime(2026, 4, 1, 12, 30, 0)  # naive
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)  # aware
    result = format_time_ago(t, now)
    assert result == "30m ago"


def test_safe_url_rejects_hostless_https():
    """Hostless https: URL should be rejected."""
    from dashboard.components.article_detail import _safe_url
    assert _safe_url("https:javascript:alert(1)") == ("", False)


def test_safe_url_rejects_hostless_http():
    """Hostless http: URL should be rejected."""
    from dashboard.components.article_detail import _safe_url
    assert _safe_url("http:example.com") == ("", False)


def test_safe_url_accepts_valid_https():
    """Valid https URL should pass and report is_https=True."""
    from dashboard.components.article_detail import _safe_url
    assert _safe_url("https://example.com/path") == ("https://example.com/path", True)


def test_safe_url_accepts_valid_http():
    """Valid http URL should pass but report is_https=False."""
    from dashboard.components.article_detail import _safe_url
    assert _safe_url("http://example.com/path") == ("http://example.com/path", False)


def test_safe_url_rejects_malformed_ipv6():
    """Malformed bracketed IPv6 should not raise — returns empty tuple."""
    from dashboard.components.article_detail import _safe_url
    assert _safe_url("http://[::1") == ("", False)
    assert _safe_url("https://[zzz]") == ("", False)


def test_render_detail_escapes_source_tier():
    """source_tier must be escaped to prevent HTML injection."""
    from dashboard.components.article_detail import render_article_detail
    # source_tier is typed as int on frozen Article, so we test defense-in-depth
    # by verifying html.escape() is called (it wraps the value in str() first).
    # We verify the code path by checking render_article_detail directly.
    article = _make_article(source_tier=3)
    result = render_article_detail(article)
    assert "Tier 3" in result


def test_render_detail_source_tier_escape_path():
    """Verify source_tier goes through html.escape by testing the internal call."""
    import html as html_mod
    from unittest.mock import patch
    from dashboard.components.article_detail import render_article_detail
    article = _make_article(source_tier=3)
    with patch.object(html_mod, "escape", wraps=html_mod.escape) as mock_escape:
        render_article_detail(article)
    # html.escape should be called with "3" (str of source_tier) among its calls
    escaped_values = [call.args[0] for call in mock_escape.call_args_list]
    assert "3" in escaped_values
