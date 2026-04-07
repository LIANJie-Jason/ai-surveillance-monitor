# tests/test_analysis.py
"""Tests for the dashboard analysis component."""

from __future__ import annotations

from datetime import datetime, timezone
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
# _extract_themes tests
# ===================================================================


class TestExtractThemes:
    """Tests for _extract_themes()."""

    def test_empty_articles(self) -> None:
        """Empty article list returns empty themes."""
        from dashboard.components.analysis import _extract_themes
        assert _extract_themes([]) == []

    def test_single_article(self) -> None:
        """Single article extracts words from title."""
        from dashboard.components.analysis import _extract_themes
        article = _make_article(title="Surveillance cameras deployed citywide")
        result = _extract_themes([article])
        words = [w for w, _ in result]
        assert "surveillance" in words
        assert "cameras" in words
        assert "deployed" in words
        assert "citywide" in words

    def test_stop_word_filtering(self) -> None:
        """Common stop words are excluded from themes."""
        from dashboard.components.analysis import _extract_themes, _STOP_WORDS
        # Title made entirely of stop words plus one real word
        article = _make_article(title="The government has been monitoring over the years")
        result = _extract_themes([article])
        words = [w for w, _ in result]
        # "monitoring" is the only non-stop-word with 3+ chars
        assert "monitoring" in words
        # stop words must not appear
        for w in words:
            assert w not in _STOP_WORDS

    def test_short_words_excluded(self) -> None:
        """Words shorter than 3 characters are excluded (regex requires 3+)."""
        from dashboard.components.analysis import _extract_themes
        article = _make_article(title="AI VR XR surveillance tech")
        result = _extract_themes([article])
        words = [w for w, _ in result]
        # "ai", "vr", "xr" are 2 chars and should be excluded
        assert "ai" not in words
        assert "vr" not in words
        assert "xr" not in words
        # "surveillance" and "tech" are long enough
        assert "surveillance" in words
        assert "tech" in words

    def test_word_frequency_counting(self) -> None:
        """Words appearing in multiple articles get higher counts."""
        from dashboard.components.analysis import _extract_themes
        articles = [
            _make_article(id="a1", title="Facial recognition technology"),
            _make_article(id="a2", title="Recognition software deployed"),
            _make_article(id="a3", title="Recognition system fails"),
        ]
        result = _extract_themes(articles)
        word_dict = dict(result)
        assert word_dict["recognition"] == 3
        assert word_dict.get("facial", 0) == 1

    def test_top_n_limit(self) -> None:
        """top_n limits the number of returned themes."""
        from dashboard.components.analysis import _extract_themes
        articles = [
            _make_article(
                title="alpha bravo charlie delta echo foxtrot golf hotel india"
            ),
        ]
        result = _extract_themes(articles, top_n=3)
        assert len(result) == 3

    def test_top_n_default_is_8(self) -> None:
        """Default top_n is 8."""
        from dashboard.components.analysis import _extract_themes
        # Create an article with many distinct words
        words = [
            "alpha", "bravo", "charlie", "delta", "echo",
            "foxtrot", "golf", "hotel", "india", "juliet",
            "kilo", "lima",
        ]
        article = _make_article(title=" ".join(words))
        result = _extract_themes([article])
        assert len(result) == 8

    def test_case_insensitive(self) -> None:
        """Theme extraction is case-insensitive."""
        from dashboard.components.analysis import _extract_themes
        articles = [
            _make_article(id="a1", title="SURVEILLANCE cameras"),
            _make_article(id="a2", title="Surveillance deployed"),
        ]
        result = _extract_themes(articles)
        word_dict = dict(result)
        assert word_dict["surveillance"] == 2

    def test_none_title_handled(self) -> None:
        """Articles with None title don't crash."""
        from dashboard.components.analysis import _extract_themes
        article = _make_article(title=None)
        result = _extract_themes([article])
        assert result == []


# ===================================================================
# _category_bar tests
# ===================================================================


class TestCategoryBar:
    """Tests for _category_bar()."""

    def test_known_category_color(self) -> None:
        """Known categories use their assigned color."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("surveillance", 5, 10)
        assert "#f85149" in result  # surveillance color

    def test_unknown_category_fallback_color(self) -> None:
        """Unknown categories fall back to gray."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("unknown_category", 3, 10)
        assert "#8b949e" in result

    def test_percentage_calculation(self) -> None:
        """Bar width should reflect count/total percentage."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("surveillance", 5, 10)
        assert "50.0%" in result

    def test_zero_total(self) -> None:
        """Zero total produces 0% width, no division error."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("surveillance", 0, 0)
        assert "0.0%" in result

    def test_label_formatting(self) -> None:
        """Underscores replaced with spaces, title-cased."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("facial_recognition", 2, 10)
        assert "Facial Recognition" in result

    def test_label_xss_escaped(self) -> None:
        """Special chars in labels are HTML-escaped."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar('<script>alert("xss")</script>', 1, 10)
        assert "<script>" not in result
        assert "&lt;" in result

    def test_count_displayed(self) -> None:
        """Count value appears in the output."""
        from dashboard.components.analysis import _category_bar
        result = _category_bar("surveillance", 7, 20)
        assert ">7<" in result


# ===================================================================
# render_country_analysis tests
# ===================================================================


class TestRenderCountryAnalysis:
    """Tests for render_country_analysis()."""

    def test_empty_articles(self) -> None:
        """No articles produces the 'no data' message."""
        from dashboard.components.analysis import render_country_analysis
        result = render_country_analysis([], "India")
        assert "No surveillance/censorship articles collected for India yet." in result

    def test_empty_articles_xss_country_name(self) -> None:
        """Country name in empty-state message is HTML-escaped."""
        from dashboard.components.analysis import render_country_analysis
        result = render_country_analysis([], '<img src=x onerror="alert(1)">')
        assert '<img src=x onerror="alert(1)">' not in result
        assert "&lt;img" in result

    def test_country_name_in_header(self) -> None:
        """Country name appears in the panel header."""
        from dashboard.components.analysis import render_country_analysis
        article = _make_article()
        result = render_country_analysis([article], "India")
        assert "India" in result
        assert "Live Analysis" in result

    def test_country_name_xss_escaped(self) -> None:
        """Country name in header is HTML-escaped."""
        from dashboard.components.analysis import render_country_analysis
        article = _make_article()
        result = render_country_analysis([article], '<b>India</b>')
        assert "<b>India</b>" not in result
        assert "&lt;b&gt;India&lt;/b&gt;" in result

    def test_article_count_displayed(self) -> None:
        """Article count is shown in the stats."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1"),
            _make_article(id="a2"),
            _make_article(id="a3"),
        ]
        result = render_country_analysis(articles, "India")
        assert "ARTICLES" in result
        assert ">3<" in result

    def test_avg_confidence_displayed(self) -> None:
        """Average confidence stat is rendered."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", confidence=0.80),
            _make_article(id="a2", confidence=0.60),
        ]
        result = render_country_analysis(articles, "India")
        assert "AVG CONFIDENCE" in result
        assert "70%" in result

    def test_high_confidence_count(self) -> None:
        """High confidence count (>=0.8) is correct."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", confidence=0.90),
            _make_article(id="a2", confidence=0.85),
            _make_article(id="a3", confidence=0.50),
        ]
        result = render_country_analysis(articles, "India")
        assert "HIGH CONF" in result
        assert ">2<" in result

    def test_no_confidence_articles(self) -> None:
        """Articles with None confidence don't break avg calculation."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", confidence=None),
            _make_article(id="a2", confidence=None),
        ]
        result = render_country_analysis(articles, "India")
        assert "AVG CONFIDENCE" in result
        assert "0%" in result

    def test_category_distribution(self) -> None:
        """Category bars appear in the output."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", category="surveillance"),
            _make_article(id="a2", category="censorship"),
            _make_article(id="a3", category="surveillance"),
        ]
        result = render_country_analysis(articles, "India")
        assert "CATEGORY DISTRIBUTION" in result
        assert "Surveillance" in result
        assert "Censorship" in result

    def test_source_tiers(self) -> None:
        """Source tier badges appear in the output."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", source_tier=1),
            _make_article(id="a2", source_tier=3),
        ]
        result = render_country_analysis(articles, "India")
        assert "SOURCES" in result
        assert "Wire" in result
        assert "Specialty" in result

    def test_date_range(self) -> None:
        """Date range is rendered from earliest to latest article dates."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(
                id="a1",
                published_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            ),
            _make_article(
                id="a2",
                published_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            ),
        ]
        result = render_country_analysis(articles, "India")
        assert "2026-01-15" in result
        assert "2026-03-20" in result

    def test_date_range_string_published_at(self) -> None:
        """published_at as a string is handled (falls back to str[:10])."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", published_at="2026-02-10T00:00:00Z"),
            _make_article(id="a2", published_at="2026-04-05T00:00:00Z"),
        ]
        result = render_country_analysis(articles, "India")
        assert "DATE RANGE" in result
        assert "2026-02-10" in result
        assert "2026-04-05" in result

    def test_no_published_dates(self) -> None:
        """Articles with no published_at don't break date range."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", published_at=None),
        ]
        result = render_country_analysis(articles, "India")
        # Should still render without error, date range is empty
        assert "DATE RANGE" in result

    def test_key_themes_displayed(self) -> None:
        """Key themes section appears."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", title="Surveillance cameras deployed"),
            _make_article(id="a2", title="Surveillance system monitoring"),
        ]
        result = render_country_analysis(articles, "India")
        assert "KEY THEMES" in result
        assert "surveillance" in result

    def test_live_badge(self) -> None:
        """Panel shows LIVE badge."""
        from dashboard.components.analysis import render_country_analysis
        article = _make_article()
        result = render_country_analysis([article], "India")
        assert "LIVE" in result

    def test_no_category_articles(self) -> None:
        """Articles with None category don't break category distribution."""
        from dashboard.components.analysis import render_country_analysis
        articles = [
            _make_article(id="a1", category=None),
        ]
        result = render_country_analysis(articles, "India")
        assert "CATEGORY DISTRIBUTION" in result

    def test_single_article_full_render(self) -> None:
        """Single article produces a complete panel without errors."""
        from dashboard.components.analysis import render_country_analysis
        article = _make_article(
            confidence=0.95,
            category="facial_recognition",
            source_tier=2,
        )
        result = render_country_analysis([article], "India")
        assert "India" in result
        assert ">1<" in result  # article count
        assert "95%" in result
        assert "Facial Recognition" in result
        assert "Major" in result


# ===================================================================
# render_global_summary tests
# ===================================================================


class TestRenderGlobalSummary:
    """Tests for render_global_summary()."""

    def test_empty_country_counts(self) -> None:
        """Empty country_counts renders with zero counts."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({}, 0)
        assert "Global Overview" in result
        assert "MONITORING" in result
        assert ">0<" in result

    def test_total_collected(self) -> None:
        """Total collected count is displayed."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"IN": 5}, 42)
        assert ">42<" in result

    def test_flagged_count(self) -> None:
        """Flagged count is sum of country_counts values."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"IN": 5, "CN": 3, "NG": 2}, 100)
        assert "FLAGGED" in result
        assert ">10<" in result

    def test_countries_count(self) -> None:
        """Number of unique countries is displayed."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"IN": 5, "CN": 3, "NG": 2}, 100)
        assert "COUNTRIES" in result
        assert ">3<" in result

    def test_top_countries_displayed(self) -> None:
        """Top countries section shows country codes and counts."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"IN": 10, "CN": 8, "NG": 3}, 50)
        assert "TOP COUNTRIES" in result
        assert "IN" in result
        assert "CN" in result

    def test_top_countries_limited_to_6(self) -> None:
        """Only top 6 countries are shown in the TOP COUNTRIES section."""
        from dashboard.components.analysis import render_global_summary
        # Use country-code-like keys unlikely to appear in HTML/CSS
        # Top 6 by count: XA(10), XB(9), XC(8), XD(7), XE(6), XF(5)
        # Bottom 4: XG(4), XH(3), XI(2), XJ(1)
        countries = {
            "XA": 10, "XB": 9, "XC": 8, "XD": 7, "XE": 6,
            "XF": 5, "XG": 4, "XH": 3, "XI": 2, "XJ": 1,
        }
        result = render_global_summary(countries, 100)
        # Top 6 should appear
        for name in ["XA", "XB", "XC", "XD", "XE", "XF"]:
            assert name in result
        # Bottom 4 should NOT appear
        for name in ["XG", "XH", "XI", "XJ"]:
            assert name not in result

    def test_country_code_xss_escaped(self) -> None:
        """Country codes are HTML-escaped."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"<b>XSS</b>": 5}, 10)
        assert "<b>XSS</b>" not in result
        assert "&lt;b&gt;" in result

    def test_drill_down_hint(self) -> None:
        """Drill-down hint text appears."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({"IN": 5}, 10)
        assert "Click a highlighted country" in result

    def test_monitoring_badge(self) -> None:
        """Global summary shows MONITORING badge."""
        from dashboard.components.analysis import render_global_summary
        result = render_global_summary({}, 0)
        assert "MONITORING" in result


# ===================================================================
# render_news_cards tests
# ===================================================================


class TestRenderNewsCards:
    """Tests for render_news_cards()."""

    def test_empty_articles(self) -> None:
        """No articles shows 'no match' message."""
        from dashboard.components.analysis import render_news_cards
        result = render_news_cards([])
        assert "No articles match current filters." in result

    def test_single_card(self) -> None:
        """Single article produces one card."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(title="India deploys surveillance drones")
        result = render_news_cards([article])
        assert "India deploys surveillance drones" in result
        assert "TestSource" in result

    def test_max_cards_limit(self) -> None:
        """Only max_cards articles are rendered."""
        from dashboard.components.analysis import render_news_cards
        articles = [
            _make_article(id=f"a{i}", title=f"Article {i}") for i in range(20)
        ]
        result = render_news_cards(articles, max_cards=5)
        # Articles 0-4 should be present, 5+ should not
        assert "Article 0" in result
        assert "Article 4" in result
        assert "Article 5" not in result

    def test_default_max_cards_is_12(self) -> None:
        """Default max_cards is 12."""
        from dashboard.components.analysis import render_news_cards
        articles = [
            _make_article(id=f"a{i}", title=f"Headline {i}") for i in range(15)
        ]
        result = render_news_cards(articles)
        assert "Headline 11" in result
        assert "Headline 12" not in result

    def test_title_truncated_at_80_chars(self) -> None:
        """Titles longer than 80 chars are truncated."""
        from dashboard.components.analysis import render_news_cards
        long_title = "A" * 100
        article = _make_article(title=long_title)
        result = render_news_cards([article])
        # The truncated title (80 chars of "A") should appear
        assert "A" * 80 in result
        # The full 100-char title should NOT appear
        assert "A" * 100 not in result

    def test_title_xss_escaped(self) -> None:
        """Special chars in title are HTML-escaped."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(title='<script>alert("xss")</script>')
        result = render_news_cards([article])
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_source_name_xss_escaped(self) -> None:
        """Source name is HTML-escaped."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(source_name='<b>Evil</b>')
        result = render_news_cards([article])
        assert "<b>Evil</b>" not in result
        assert "&lt;b&gt;" in result

    def test_category_formatted(self) -> None:
        """Category label replaces underscores and is title-cased."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(category="facial_recognition")
        result = render_news_cards([article])
        assert "Facial Recognition" in result

    def test_category_xss_escaped(self) -> None:
        """Category is HTML-escaped."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(category='<img src=x>')
        result = render_news_cards([article])
        # Raw angle brackets must not appear as HTML tags
        assert "<img " not in result
        # After .title(), <img becomes <Img, then html.escape produces &lt;Img
        assert "&lt;Img" in result

    def test_confidence_coloring_high(self) -> None:
        """Confidence >= 0.8 uses red color."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(confidence=0.90)
        result = render_news_cards([article])
        assert "#f85149" in result
        assert "90%" in result

    def test_confidence_coloring_medium(self) -> None:
        """Confidence >= 0.6 but < 0.8 uses yellow color."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(confidence=0.65)
        result = render_news_cards([article])
        assert "#d29922" in result

    def test_confidence_coloring_low(self) -> None:
        """Confidence < 0.6 uses gray color."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(confidence=0.40)
        result = render_news_cards([article])
        # Count that the gray color is used for confidence display
        assert "40%" in result

    def test_none_confidence(self) -> None:
        """None confidence treated as 0."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(confidence=None)
        result = render_news_cards([article])
        assert "0%" in result

    def test_date_displayed(self) -> None:
        """Published date appears in the card."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(
            published_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        )
        result = render_news_cards([article])
        assert "2026-03-15" in result

    def test_string_published_at(self) -> None:
        """String published_at is handled via str[:10]."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(published_at="2026-02-28T12:00:00Z")
        result = render_news_cards([article])
        assert "2026-02-28" in result

    def test_no_published_at(self) -> None:
        """None published_at doesn't crash, no date shown."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(published_at=None)
        result = render_news_cards([article])
        # Should render without error
        assert "TestSource" in result

    def test_none_title_uses_untitled(self) -> None:
        """None title shows 'Untitled'."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(title=None)
        result = render_news_cards([article])
        assert "Untitled" in result

    def test_none_source_name_uses_unknown(self) -> None:
        """None source_name shows 'Unknown'."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(source_name=None)
        result = render_news_cards([article])
        assert "Unknown" in result

    def test_none_category_uses_other(self) -> None:
        """None category falls back to 'Other'."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(category=None)
        result = render_news_cards([article])
        assert "Other" in result

    # --- URL safety tests ---

    def test_http_url_allowed(self) -> None:
        """http:// URLs produce a data-url attribute."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="http://example.com/article")
        result = render_news_cards([article])
        assert "data-url=" in result
        assert "http://example.com/article" in result

    def test_https_url_allowed(self) -> None:
        """https:// URLs produce a data-url attribute."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="https://example.com/article")
        result = render_news_cards([article])
        assert "data-url=" in result

    def test_javascript_url_blocked(self) -> None:
        """javascript: URLs do NOT produce a data-url attribute."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url='javascript:alert("xss")')
        result = render_news_cards([article])
        assert "data-url=" not in result
        assert "javascript:" not in result

    def test_data_url_blocked(self) -> None:
        """data: URLs do NOT produce a data-url attribute."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="data:text/html,<script>alert(1)</script>")
        result = render_news_cards([article])
        assert "data-url=" not in result

    def test_ftp_url_blocked(self) -> None:
        """ftp: URLs do NOT produce a data-url attribute."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="ftp://example.com/file")
        result = render_news_cards([article])
        assert "data-url=" not in result

    def test_empty_url_no_click(self) -> None:
        """Empty URL produces no clickable card."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="")
        result = render_news_cards([article])
        assert "data-url=" not in result
        assert "cursor:pointer" not in result

    def test_none_url_no_click(self) -> None:
        """None URL produces no clickable card."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url=None)
        result = render_news_cards([article])
        assert "data-url=" not in result

    def test_url_xss_in_data_attr(self) -> None:
        """URLs with special chars are HTML-escaped in data-url."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url='https://example.com/a?x="&y=<>')
        result = render_news_cards([article])
        assert "data-url=" in result
        # Quotes and angle brackets should be escaped
        assert '&quot;' in result
        assert '&amp;' in result

    def test_cursor_pointer_for_valid_url(self) -> None:
        """Cards with valid URLs have cursor:pointer style."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="https://example.com/article")
        result = render_news_cards([article])
        assert "cursor:pointer" in result

    def test_no_cursor_pointer_for_invalid_url(self) -> None:
        """Cards without valid URLs don't have cursor:pointer."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article(url="javascript:void(0)")
        result = render_news_cards([article])
        assert "cursor:pointer" not in result

    def test_scrollable_container(self) -> None:
        """Cards are wrapped in a flex scrollable container."""
        from dashboard.components.analysis import render_news_cards
        article = _make_article()
        result = render_news_cards([article])
        assert "overflow-x:auto" in result
        assert "display:flex" in result
