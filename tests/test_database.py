"""Tests for src/database.py — SQLite persistence layer."""

import os
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture
def db():
    """Create a temp database for each test."""
    from src.database import Database

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_tables()
    yield database
    database.close()
    os.unlink(path)


def test_init_creates_tables(db):
    """init_tables should create articles and feeds tables."""
    tables = db.list_tables()
    assert "articles" in tables
    assert "feeds" in tables


def test_insert_and_get_article(db):
    """Should insert an article and retrieve it by ID."""
    from src.models import Article

    article = Article(
        id="abc123",
        url="https://example.com/1",
        title="Test Article",
        source_name="Reuters",
        source_lang="en",
        source_tier=1,
        fetched_at=datetime.now(tz=timezone.utc),
    )
    db.upsert_article(article)
    result = db.get_article("abc123")
    assert result is not None
    assert result.title == "Test Article"
    assert result.source_name == "Reuters"


def test_upsert_updates_existing(db):
    """Upserting same ID should update, not duplicate."""
    from dataclasses import replace

    from src.models import Article

    article = Article(
        id="abc123",
        url="https://example.com/1",
        title="Original",
        source_name="Reuters",
        source_lang="en",
        source_tier=1,
    )
    db.upsert_article(article)

    updated = replace(article, title="Updated", is_surveillance=True, confidence=0.9)
    db.upsert_article(updated)

    result = db.get_article("abc123")
    assert result.title == "Updated"
    assert result.is_surveillance is True
    assert db.count_articles() == 1


def test_get_flagged_articles(db):
    """Should return only articles where is_surveillance=True AND confidence >= 0.6."""
    from src.models import Article

    flagged = Article(
        id="f1", url="https://a.com/1", title="Surveillance",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.9, category="surveillance",
        country_code="IN", country_name="India",
    )
    low_conf = Article(
        id="lc1", url="https://a.com/lc", title="Low confidence",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.3, category="surveillance",
        country_code="IN", country_name="India",
    )
    normal = Article(
        id="n1", url="https://a.com/2", title="Sports",
        source_name="BBC", source_lang="en", source_tier=1,
    )
    db.upsert_article(flagged)
    db.upsert_article(low_conf)
    db.upsert_article(normal)

    results = db.get_flagged_articles()
    assert len(results) == 1
    assert results[0].id == "f1"


def test_get_flagged_articles_by_country(db):
    """Should filter flagged articles by country_code."""
    from src.models import Article

    a1 = Article(
        id="a1", url="https://a.com/1", title="IN article",
        source_name="Wire", source_lang="en", source_tier=3,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
    )
    a2 = Article(
        id="a2", url="https://a.com/2", title="MY article",
        source_name="Star", source_lang="en", source_tier=4,
        is_surveillance=True, confidence=0.7, country_code="MY",
        country_name="Malaysia",
    )
    db.upsert_article(a1)
    db.upsert_article(a2)

    results = db.get_flagged_articles(country_code="IN")
    assert len(results) == 1
    assert results[0].country_code == "IN"


def test_get_flagged_articles_date_filter(db):
    """Should filter flagged articles by publication date range."""
    from src.models import Article

    old = Article(
        id="old1", url="https://a.com/old", title="Old",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    recent = Article(
        id="new1", url="https://a.com/new", title="New",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
        published_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )
    db.upsert_article(old)
    db.upsert_article(recent)

    results = db.get_flagged_articles(date_from="2026-03-01T00:00:00+00:00")
    assert len(results) == 1
    assert results[0].id == "new1"


def test_get_flagged_articles_date_to_filter(db):
    """M23: date_to SQL branch should exclude articles after the cutoff."""
    from src.models import Article

    old = Article(
        id="dto_old", url="https://a.com/dto_old", title="Old",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
        published_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    recent = Article(
        id="dto_new", url="https://a.com/dto_new", title="New",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
        published_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )
    db.upsert_article(old)
    db.upsert_article(recent)

    # date_to cuts off the recent article
    results = db.get_flagged_articles(date_to="2026-02-01T00:00:00+00:00")
    assert len(results) == 1
    assert results[0].id == "dto_old"

    # Both date_from and date_to together
    results = db.get_flagged_articles(
        date_from="2026-01-01T00:00:00+00:00",
        date_to="2026-04-01T00:00:00+00:00",
    )
    assert len(results) == 2


def test_get_country_counts_date_filters(db):
    """M23: get_country_counts date_from/date_to SQL branches."""
    from src.models import Article

    db.upsert_article(Article(
        id="cc_old", url="https://a.com/cc_old", title="Old",
        source_name="Wire", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India",
        published_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    ))
    db.upsert_article(Article(
        id="cc_new", url="https://a.com/cc_new", title="New",
        source_name="Wire", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="MY",
        country_name="Malaysia",
        published_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
    ))

    # date_from only
    counts = db.get_country_counts(date_from="2026-02-01T00:00:00+00:00")
    assert "IN" not in counts
    assert counts.get("MY") == 1

    # date_to only
    counts = db.get_country_counts(date_to="2026-02-01T00:00:00+00:00")
    assert counts.get("IN") == 1
    assert "MY" not in counts

    # Both
    counts = db.get_country_counts(
        date_from="2026-01-01T00:00:00+00:00",
        date_to="2026-04-01T00:00:00+00:00",
    )
    assert counts.get("IN") == 1
    assert counts.get("MY") == 1


def test_article_exists(db):
    """Should check if an article ID already exists."""
    from src.models import Article

    article = Article(
        id="exists1", url="https://a.com/exists", title="Exists",
        source_name="AP", source_lang="en", source_tier=1,
    )
    assert db.article_exists("exists1") is False
    db.upsert_article(article)
    assert db.article_exists("exists1") is True


def test_get_country_counts(db):
    """Should return article counts grouped by country, respecting confidence threshold."""
    from src.models import Article

    for i in range(3):
        db.upsert_article(Article(
            id=f"in{i}", url=f"https://a.com/in{i}", title=f"IN {i}",
            source_name="Wire", source_lang="en", source_tier=3,
            is_surveillance=True, confidence=0.8, country_code="IN",
            country_name="India",
        ))
    db.upsert_article(Article(
        id="my1", url="https://a.com/my1", title="MY 1",
        source_name="Star", source_lang="en", source_tier=4,
        is_surveillance=True, confidence=0.7, country_code="MY",
        country_name="Malaysia",
    ))
    # Low confidence — should NOT count
    db.upsert_article(Article(
        id="low1", url="https://a.com/low1", title="Low",
        source_name="Wire", source_lang="en", source_tier=3,
        is_surveillance=True, confidence=0.3, country_code="IN",
        country_name="India",
    ))

    counts = db.get_country_counts()
    assert counts["IN"] == 3  # not 4 — low confidence excluded
    assert counts["MY"] == 1


def test_get_country_counts_with_category_filter(db):
    """Should filter country counts by category."""
    from src.models import Article

    db.upsert_article(Article(
        id="s1", url="https://a.com/s1", title="Surv",
        source_name="Wire", source_lang="en", source_tier=3,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India", category="surveillance",
    ))
    db.upsert_article(Article(
        id="c1", url="https://a.com/c1", title="Cens",
        source_name="Wire", source_lang="en", source_tier=3,
        is_surveillance=True, confidence=0.8, country_code="IN",
        country_name="India", category="censorship",
    ))

    counts = db.get_country_counts(category="surveillance")
    assert counts["IN"] == 1


def test_insert_and_get_feeds(db):
    """Should insert feeds and retrieve active ones."""
    from src.models import Feed

    feed = Feed(
        name="Reuters", url="https://feeds.reuters.com/world",
        language="en", tier=1, feed_type="wire",
    )
    db.upsert_feed(feed)

    feeds = db.get_active_feeds()
    assert len(feeds) == 1
    assert feeds[0].name == "Reuters"


def test_upsert_preserves_classification_on_reingest(db):
    """Re-ingesting an article (no classification) should NOT wipe existing classification."""
    from dataclasses import replace
    from src.models import Article

    # First insert: classified article
    classified = Article(
        id="cls1", url="https://a.com/cls", title="Surveillance Story",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.92, category="surveillance",
        country_code="IN", country_name="India", region="Delhi",
        summary_en="Government deployed facial recognition.",
        llm_provider="openai",
        fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db.upsert_article(classified)

    # Re-ingest: same URL from RSS, no classification data
    reingested = Article(
        id="cls1", url="https://a.com/cls", title="Surveillance Story (updated)",
        source_name="BBC", source_lang="en", source_tier=1,
        fetched_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
        # all classification fields are default/None
    )
    db.upsert_article(reingested)

    result = db.get_article("cls1")
    assert result.title == "Surveillance Story (updated)"  # title updated
    assert result.is_surveillance is True  # preserved
    assert result.confidence == 0.92  # preserved
    assert result.category == "surveillance"  # preserved
    assert result.country_code == "IN"  # preserved
    assert result.summary_en == "Government deployed facial recognition."  # preserved
    assert result.llm_provider == "openai"  # preserved


def test_upsert_preserves_title_en_on_reingest(db):
    """Re-ingesting should NOT wipe a previously translated title_en."""
    from dataclasses import replace
    from src.models import Article

    original = Article(
        id="ten1", url="https://a.com/ten", title="Original ZH Title",
        source_name="Caixin", source_lang="zh", source_tier=4,
        title_en="Translated English Title",
    )
    db.upsert_article(original)

    reingested = Article(
        id="ten1", url="https://a.com/ten", title="Original ZH Title",
        source_name="Caixin", source_lang="zh", source_tier=4,
        # title_en is None on re-ingest
    )
    db.upsert_article(reingested)

    result = db.get_article("ten1")
    assert result.title_en == "Translated English Title"  # preserved


def test_feed_upsert_updates_all_fields(db):
    """Upserting a feed should update language and country_focus too."""
    from src.models import Feed

    feed_v1 = Feed(
        name="Test Feed", url="https://example.com/rss",
        language="en", tier=2, feed_type="major", country_focus=None,
    )
    db.upsert_feed(feed_v1)

    feed_v2 = Feed(
        name="Test Feed Updated", url="https://example.com/rss",
        language="ms", tier=4, feed_type="regional", country_focus="MY",
    )
    db.upsert_feed(feed_v2)

    feeds = db.get_active_feeds()
    assert len(feeds) == 1
    assert feeds[0].name == "Test Feed Updated"
    assert feeds[0].language == "ms"
    assert feeds[0].country_focus == "MY"
    assert feeds[0].tier == 4
    assert feeds[0].feed_type == "regional"


def test_init_tables_migrates_legacy_feeds_schema():
    """init_tables should detect feeds.category legacy schema and drop it.

    Reproduces the M17 auto-migration path: a pre-existing feeds table with
    ``category TEXT`` (and no ``feed_type``) must be dropped so the new schema
    can be recreated on next init. Articles table must be untouched.
    """
    import sqlite3
    import tempfile
    import os
    from src.database import Database

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # First, create the modern articles schema via Database.init_tables(),
        # insert a sentinel row, then drop+recreate feeds with the LEGACY
        # 'category' schema so we can verify auto-migration on next init.
        from src.models import Article
        bootstrap = Database(path)
        bootstrap.init_tables()
        bootstrap.upsert_article(Article(
            id="keep1", url="https://a.example/1", title="Kept",
            source_name="Test", source_lang="en", source_tier=1,
        ))
        bootstrap.close()

        conn = sqlite3.connect(path)
        conn.executescript("""
            DROP TABLE feeds;
            CREATE TABLE feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                url TEXT UNIQUE,
                language TEXT,
                tier INTEGER,
                category TEXT,
                country_focus TEXT,
                active INTEGER DEFAULT 1,
                last_fetched_at TEXT
            );
            INSERT INTO feeds (name, url, language, tier, category)
            VALUES ('Legacy', 'https://legacy.example/rss', 'en', 3, 'specialty');
        """)
        conn.commit()
        conn.close()

        # Re-open via Database — should auto-migrate
        database = Database(path)
        database.init_tables()

        # New schema should have feed_type column, no category column
        cols = [
            row["name"]
            for row in database._conn.execute("PRAGMA table_info(feeds)").fetchall()
        ]
        assert "feed_type" in cols
        assert "category" not in cols

        # Legacy feed row should be gone (table was dropped + recreated)
        assert len(database.get_active_feeds()) == 0

        # Articles must NOT have been touched by the migration
        row = database._conn.execute(
            "SELECT id FROM articles WHERE id = 'keep1'"
        ).fetchone()
        assert row is not None
        assert row["id"] == "keep1"

        database.close()
    finally:
        os.unlink(path)


def test_init_tables_idempotent_on_already_migrated_schema():
    """init_tables should be a no-op on a DB that already uses feed_type."""
    import tempfile
    import os
    from src.database import Database
    from src.models import Feed

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db1 = Database(path)
        db1.init_tables()
        db1.upsert_feed(Feed(
            name="Stable", url="https://stable.example/rss",
            language="en", tier=2, feed_type="major",
        ))
        db1.close()

        # Re-open — init_tables should NOT drop the feed
        db2 = Database(path)
        db2.init_tables()
        feeds = db2.get_active_feeds()
        assert len(feeds) == 1
        assert feeds[0].feed_type == "major"
        db2.close()
    finally:
        os.unlink(path)


def test_update_feed_fetched_roundtrip(db):
    """update_feed_fetched should persist and be hydrated by get_active_feeds."""
    from src.models import Feed

    feed = Feed(
        name="Reuters", url="https://feeds.reuters.com/world",
        language="en", tier=1, feed_type="wire",
    )
    db.upsert_feed(feed)

    db.update_feed_fetched("https://feeds.reuters.com/world")

    feeds = db.get_active_feeds()
    assert len(feeds) == 1
    assert feeds[0].last_fetched_at is not None


def test_read_only_mode(db):
    """read_only=True should open DB without WAL pragma and allow reads."""
    import tempfile, os
    from src.database import Database
    from src.models import Article

    # Write some data first using the normal db fixture
    db.upsert_article(Article(
        id="ro1", url="https://a.com/ro", title="ReadOnly Test",
        source_name="AP", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.8, country_code="US",
        country_name="United States",
    ))

    # Get the db path from the fixture's connection
    db_path = db._conn.execute("PRAGMA database_list").fetchone()[2]
    db.close()

    # Open read-only
    ro_db = Database(db_path, read_only=True)
    result = ro_db.get_article("ro1")
    assert result is not None
    assert result.title == "ReadOnly Test"

    counts = ro_db.get_country_counts()
    assert "US" in counts
    ro_db.close()

    # Re-open the write db for fixture cleanup
    db._conn = __import__("sqlite3").connect(db_path, check_same_thread=False)
    db._conn.row_factory = __import__("sqlite3").Row


def test_empty_db_queries(db):
    """Queries on empty DB should return empty results, not errors."""
    results = db.get_flagged_articles()
    assert results == []

    counts = db.get_country_counts()
    assert counts == {}

    assert db.article_exists("nonexistent") is False
    assert db.get_article("nonexistent") is None
    assert db.count_articles() == 0


def test_upsert_updates_fetched_at_on_conflict(db):
    """ON CONFLICT should update fetched_at (last-seen) and preserve published_at via COALESCE."""
    from dataclasses import replace

    from src.models import Article

    original = Article(
        id="ts1", url="https://a.com/ts", title="Original",
        source_name="BBC", source_lang="en", source_tier=1,
        published_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
    )
    db.upsert_article(original)

    # Re-upsert with new fetched_at, no published_at
    updated = replace(original, title="Updated", published_at=None,
                      fetched_at=datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc))
    db.upsert_article(updated)

    result = db.get_article("ts1")
    assert result.title == "Updated"
    # published_at preserved via COALESCE
    assert result.published_at is not None
    assert result.published_at.month == 3
    assert result.published_at.day == 1
    # fetched_at updated to new value (CC2-H1: last-seen semantics)
    assert result.fetched_at.day == 31
    assert result.fetched_at.month == 3


def test_upsert_articles_batch(db):
    """CC2-H28: upsert_articles_batch should insert multiple articles in one call."""
    from src.models import Article

    articles = [
        Article(
            id=f"batch{i}", url=f"https://a.com/batch{i}", title=f"Batch Article {i}",
            source_name="Reuters", source_lang="en", source_tier=1,
            is_surveillance=True, confidence=0.8 + i * 0.01,
            category="surveillance", country_code="IN", country_name="India",
            fetched_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]
    db.upsert_articles_batch(articles)

    assert db.count_articles() == 5
    for i in range(5):
        result = db.get_article(f"batch{i}")
        assert result is not None, f"Article batch{i} missing after batch upsert"
        assert result.title == f"Batch Article {i}"
        assert result.source_name == "Reuters"
        assert result.confidence == pytest.approx(0.8 + i * 0.01)


def test_upsert_articles_batch_empty_list(db):
    """CC2-H28: empty list should be a no-op, not an error."""
    db.upsert_articles_batch([])
    assert db.count_articles() == 0


def test_upsert_articles_batch_updates_existing(db):
    """CC2-H28: batch upsert should update an already-existing article."""
    from dataclasses import replace
    from src.models import Article

    original = Article(
        id="bup1", url="https://a.com/bup", title="Original",
        source_name="BBC", source_lang="en", source_tier=1,
        fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db.upsert_article(original)

    updated = replace(original, title="Updated via Batch",
                      fetched_at=datetime(2026, 3, 31, tzinfo=timezone.utc))
    db.upsert_articles_batch([updated])

    result = db.get_article("bup1")
    assert result.title == "Updated via Batch"
    assert db.count_articles() == 1


def test_context_manager_enter_exit():
    """CC2-H29: Database context manager should work and close on exit."""
    import os
    import tempfile
    from src.database import Database
    from src.models import Article

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with Database(path) as database:
            database.init_tables()
            database.upsert_article(Article(
                id="ctx1", url="https://a.com/ctx", title="Context Test",
                source_name="AP", source_lang="en", source_tier=1,
            ))
            result = database.get_article("ctx1")
            assert result is not None
            assert result.title == "Context Test"

        # After exiting, the connection should be closed.
        # Attempting to use the connection should raise an error.
        with pytest.raises(Exception):
            database._conn.execute("SELECT 1")
    finally:
        os.unlink(path)


def test_parse_dt_malformed_iso_string(caplog):
    """CC2-M29: _parse_dt with malformed ISO string should return None and log a warning."""
    import logging
    from src.database import Database

    with caplog.at_level(logging.WARNING, logger="src.database"):
        result = Database._parse_dt("not-a-date-at-all")

    assert result is None
    assert any(
        "Malformed datetime string" in rec.message for rec in caplog.records
    ), "Expected a warning log for malformed datetime"


def test_parse_dt_none_returns_none():
    """_parse_dt with None should return None without logging."""
    from src.database import Database

    result = Database._parse_dt(None)
    assert result is None


def test_parse_dt_valid_iso_with_tz():
    """_parse_dt with a valid ISO string (with timezone) should return datetime."""
    from src.database import Database

    result = Database._parse_dt("2026-03-31T12:00:00+00:00")
    assert result is not None
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 31
    assert result.tzinfo is not None


def test_parse_dt_naive_iso_assumes_utc():
    """_parse_dt with a naive ISO string should assume UTC."""
    from src.database import Database

    result = Database._parse_dt("2026-03-31T12:00:00")
    assert result is not None
    assert result.tzinfo == timezone.utc


# ------------------------------------------------------------------ #
#  get_flagged_articles — country_codes (multi-country IN clause)     #
# ------------------------------------------------------------------ #


def _seed_multi_country_articles(db):
    """Insert flagged articles for IN, MY, NG, ZA, and US."""
    from src.models import Article

    countries = [
        ("IN", "India"),
        ("MY", "Malaysia"),
        ("NG", "Nigeria"),
        ("ZA", "South Africa"),
        ("US", "United States"),
    ]
    for cc, name in countries:
        db.upsert_article(Article(
            id=f"cc_{cc}", url=f"https://a.com/{cc.lower()}", title=f"{name} article",
            source_name="Wire", source_lang="en", source_tier=1,
            is_surveillance=True, confidence=0.9,
            category="surveillance", country_code=cc, country_name=name,
        ))


def test_get_flagged_articles_country_codes_filters_multiple(db):
    """country_codes=['IN', 'MY'] should return only articles from those countries."""
    _seed_multi_country_articles(db)

    results = db.get_flagged_articles(country_codes=["IN", "MY"])
    returned_codes = {a.country_code for a in results}
    assert returned_codes == {"IN", "MY"}
    assert len(results) == 2


def test_get_flagged_articles_country_code_takes_precedence(db):
    """When both country_code and country_codes are provided, country_code wins."""
    _seed_multi_country_articles(db)

    results = db.get_flagged_articles(
        country_code="NG", country_codes=["IN", "MY"],
    )
    assert len(results) == 1
    assert results[0].country_code == "NG"


def test_get_flagged_articles_empty_country_codes_returns_all(db):
    """country_codes=[] (empty list) should apply no filter — return all articles."""
    _seed_multi_country_articles(db)

    results = db.get_flagged_articles(country_codes=[])
    assert len(results) == 5


def test_get_flagged_articles_country_codes_none_returns_all(db):
    """country_codes=None should apply no filter — return all articles."""
    _seed_multi_country_articles(db)

    results = db.get_flagged_articles(country_codes=None)
    assert len(results) == 5
