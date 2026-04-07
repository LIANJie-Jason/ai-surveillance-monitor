import pytest
from datetime import datetime, timezone


def test_article_from_rss_entry():
    """Article.from_rss_entry should hash URL and extract fields."""
    from src.models import Article

    entry = {
        "title": "India deploys facial recognition at airports",
        "link": "https://example.com/article/123",
        "summary": "The Indian government announced...",
        "published_parsed": (2026, 3, 31, 12, 0, 0, 0, 90, 0),
    }
    article = Article.from_rss_entry(
        entry, source_name="The Wire", source_lang="en", source_tier=4
    )

    assert article.url == "https://example.com/article/123"
    assert article.title == "India deploys facial recognition at airports"
    assert article.source_name == "The Wire"
    assert article.source_lang == "en"
    assert article.source_tier == 4
    assert len(article.id) == 64  # SHA256 hex digest
    assert article.is_surveillance is False  # default
    assert article.confidence is None


def test_article_id_is_deterministic():
    """Same URL should always produce the same article ID."""
    from src.models import Article

    entry = {
        "title": "Test",
        "link": "https://example.com/same-url",
        "summary": "",
    }
    a1 = Article.from_rss_entry(entry, "Src", "en", 1)
    a2 = Article.from_rss_entry(entry, "Src", "en", 1)
    assert a1.id == a2.id


def test_article_url_canonicalization():
    """Should strip UTM params and fragments from URLs."""
    from src.models import Article

    entry = {
        "title": "Test",
        "link": "https://example.com/article?utm_source=twitter&utm_medium=social&id=42#comments",
        "summary": "",
    }
    article = Article.from_rss_entry(entry, "Src", "en", 1)
    assert "utm_source" not in article.url
    assert "#comments" not in article.url
    assert "id=42" in article.url


def test_article_same_url_different_utm_same_id():
    """Articles with same URL but different UTM params should get same ID."""
    from src.models import Article

    e1 = {"title": "T", "link": "https://example.com/art?utm_source=twitter", "summary": ""}
    e2 = {"title": "T", "link": "https://example.com/art?utm_source=facebook", "summary": ""}
    a1 = Article.from_rss_entry(e1, "S", "en", 1)
    a2 = Article.from_rss_entry(e2, "S", "en", 1)
    assert a1.id == a2.id


def test_article_empty_link_returns_none():
    """Entries with no link should return None."""
    from src.models import Article

    entry = {"title": "No link", "summary": ""}
    result = Article.from_rss_entry(entry, "Src", "en", 1)
    assert result is None


def test_article_javascript_url_rejected():
    """javascript: URLs should be rejected (XSS prevention)."""
    from src.models import Article

    entry = {"title": "XSS", "link": "javascript:alert(1)", "summary": ""}
    result = Article.from_rss_entry(entry, "Src", "en", 1)
    assert result is None


def test_article_mailto_url_rejected():
    """mailto: URLs should be rejected."""
    from src.models import Article

    entry = {"title": "Mail", "link": "mailto:test@example.com", "summary": ""}
    result = Article.from_rss_entry(entry, "Src", "en", 1)
    assert result is None


def test_article_malformed_http_url_rejected():
    """HTTP URLs with no host should be rejected."""
    from src.models import Article

    for bad_url in [
        "http:example.com", "http://", "https:///path",
        "http://:80", "http://@/path", "https://user@:443/x",
    ]:
        result = Article.from_rss_entry(
            {"title": "Bad", "link": bad_url, "summary": ""}, "Src", "en", 1
        )
        assert result is None, f"Should reject {bad_url}"


def test_article_host_case_normalization():
    """URLs with different host case should produce same ID."""
    from src.models import Article

    e1 = {"title": "T", "link": "HTTP://Example.COM/path", "summary": ""}
    e2 = {"title": "T", "link": "http://example.com/path", "summary": ""}
    a1 = Article.from_rss_entry(e1, "S", "en", 1)
    a2 = Article.from_rss_entry(e2, "S", "en", 1)
    assert a1.id == a2.id
    assert a1.url == a2.url


def test_article_time_parsing_is_utc():
    """_parse_time_tuple should treat feedparser tuples as UTC, not local time."""
    from src.models import Article

    # 2026-03-31 12:00:00 UTC
    t = (2026, 3, 31, 12, 0, 0, 0, 90, 0)
    dt = Article._parse_time_tuple(t)
    assert dt is not None
    assert dt.hour == 12  # must be 12 UTC, not shifted by local timezone
    assert dt.tzinfo == timezone.utc


def test_feed_from_dict():
    """Feed.from_dict should populate all fields from a YAML-style dict."""
    from src.models import Feed

    data = {
        "name": "Reuters World",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "language": "en",
        "tier": 1,
        "feed_type": "wire",
        "country_focus": None,
    }
    feed = Feed.from_dict(data)
    assert feed.name == "Reuters World"
    assert feed.tier == 1
    assert feed.feed_type == "wire"
    assert feed.country_focus is None
    assert feed.active is True


def test_feed_from_dict_legacy_category_key(caplog):
    """Feed.from_dict should accept legacy 'category' key and log a warning."""
    import logging

    from src.models import Feed

    data = {
        "name": "Legacy Feed",
        "url": "https://example.com/legacy/rss",
        "language": "en",
        "tier": 2,
        "category": "specialty",  # legacy key
    }
    with caplog.at_level(logging.WARNING, logger="src.models"):
        feed = Feed.from_dict(data)
    assert feed.feed_type == "specialty"
    assert any(
        "legacy 'category' key" in rec.message for rec in caplog.records
    ), "Legacy key load should emit a deprecation warning"


def test_feed_from_dict_feed_type_preferred_over_category():
    """When both keys are present, feed_type (canonical) should win."""
    from src.models import Feed

    data = {
        "name": "Both Keys",
        "url": "https://example.com/both/rss",
        "language": "en",
        "tier": 3,
        "feed_type": "digital_rights",
        "category": "wire",  # should be ignored
    }
    feed = Feed.from_dict(data)
    assert feed.feed_type == "digital_rights"


def test_feed_from_dict_missing_feed_type_raises():
    """Feed.from_dict should raise KeyError when neither feed_type nor category is present."""
    import pytest

    from src.models import Feed

    data = {
        "name": "Missing Type",
        "url": "https://example.com/missing/rss",
        "language": "en",
        "tier": 1,
    }
    with pytest.raises(KeyError, match="feed_type"):
        Feed.from_dict(data)


def test_article_atom_updated_parsed_fallback():
    """Atom entries with only updated_parsed should still get published_at."""
    from src.models import Article

    entry = {
        "title": "Atom article",
        "link": "https://example.com/atom/1",
        "summary": "Content",
        "updated_parsed": (2026, 3, 15, 8, 30, 0, 0, 74, 0),
        # no published_parsed — Atom feed
    }
    article = Article.from_rss_entry(entry, "Citizen Lab", "en", 3)
    assert article is not None
    assert article.published_at is not None
    assert article.published_at.hour == 8
    assert article.published_at.tzinfo == timezone.utc


def test_article_content_snippet_truncated():
    """Content snippet should be truncated to 500 characters."""
    from src.models import Article

    long_summary = "x" * 1000
    entry = {
        "title": "Long",
        "link": "https://example.com/long",
        "summary": long_summary,
    }
    article = Article.from_rss_entry(entry, "Src", "en", 1)
    assert len(article.content_snippet) == 500


def test_article_is_frozen():
    """Article dataclass should be immutable."""
    from src.models import Article

    entry = {"title": "T", "link": "https://example.com/frozen", "summary": ""}
    article = Article.from_rss_entry(entry, "Src", "en", 1)
    with pytest.raises(AttributeError):
        article.title = "Modified"


def test_strip_params_not_in_article_fields():
    """_STRIP_PARAMS should NOT be a dataclass field on Article."""
    from src.models import Article
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(Article)}
    assert "_STRIP_PARAMS" not in field_names


def test_classification_result_fields():
    """ClassificationResult should hold LLM output fields."""
    from src.models import ClassificationResult

    result = ClassificationResult(
        is_surveillance=True,
        confidence=0.92,
        category="facial_recognition",
        country_code="IN",
        country_name="India",
        region="Delhi",
        llm_provider="openai",
    )
    assert result.is_surveillance is True
    assert result.confidence == 0.92
    assert result.category == "facial_recognition"
    assert result.region == "Delhi"
    assert result.llm_provider == "openai"


def test_feed_from_dict_private_ip_url_rejected():
    """CC2-H30: Feed.from_dict with private IP URL should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Evil Feed",
        "url": "http://192.168.1.1/rss",
        "language": "en",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="private/reserved"):
        Feed.from_dict(data)


def test_feed_from_dict_loopback_ip_url_rejected():
    """CC2-H30: Feed.from_dict with loopback URL should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Loopback Feed",
        "url": "http://127.0.0.1/rss",
        "language": "en",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="private/reserved"):
        Feed.from_dict(data)


def test_feed_from_dict_ten_network_url_rejected():
    """CC2-H30: Feed.from_dict with 10.x.x.x URL should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Internal Feed",
        "url": "http://10.0.0.1/rss",
        "language": "en",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="private/reserved"):
        Feed.from_dict(data)


def test_feed_from_dict_invalid_bcp47_numeric(caplog):
    """CC2-H31: Feed.from_dict with numeric language '123' should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Bad Lang Feed",
        "url": "https://example.com/rss",
        "language": "123",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="BCP 47"):
        Feed.from_dict(data)


def test_feed_from_dict_invalid_bcp47_space():
    """CC2-H31: Feed.from_dict with space in language 'en US' should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Space Lang Feed",
        "url": "https://example.com/rss",
        "language": "en US",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="BCP 47"):
        Feed.from_dict(data)


def test_feed_from_dict_invalid_bcp47_empty_string():
    """CC2-H31: Feed.from_dict with empty language string should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Empty Lang Feed",
        "url": "https://example.com/rss",
        "language": "",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="BCP 47"):
        Feed.from_dict(data)


def test_feed_from_dict_invalid_bcp47_single_char():
    """CC2-H31: Feed.from_dict with single-char language 'e' should raise ValueError."""
    from src.models import Feed

    data = {
        "name": "Short Lang Feed",
        "url": "https://example.com/rss",
        "language": "e",
        "tier": 1,
        "feed_type": "wire",
    }
    with pytest.raises(ValueError, match="BCP 47"):
        Feed.from_dict(data)
