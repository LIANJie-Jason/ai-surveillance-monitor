"""Tests for scripts/init_db.py and scripts/seed_data.py."""

import json
import os
import shutil
from datetime import datetime

import pytest


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with config files."""
    src_config = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config"
    )
    dst_config = tmp_path / "config"
    shutil.copytree(src_config, dst_config)

    (tmp_path / "data").mkdir()

    return tmp_path


def test_init_db_creates_database_and_loads_feeds(temp_project):
    """init_db should create monitor.db and load feeds from config."""
    from scripts.init_db import init_database

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    db = init_database(db_path=db_path, feeds_config_path=config_path)
    feeds = db.get_active_feeds()
    assert len(feeds) > 50  # we have 61 feeds in config
    db.close()
    assert os.path.exists(db_path)


def test_init_db_is_idempotent(temp_project):
    """Running init_db twice should not duplicate feeds."""
    from scripts.init_db import init_database

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    db1 = init_database(db_path=db_path, feeds_config_path=config_path)
    count1 = len(db1.get_active_feeds())
    db1.close()

    db2 = init_database(db_path=db_path, feeds_config_path=config_path)
    count2 = len(db2.get_active_feeds())
    db2.close()

    assert count1 == count2


def test_init_db_clean_flag_wipes_articles_and_reloads_feeds(temp_project):
    """init_database(clean=True) should drop stale articles and feeds, then reload feeds.

    Scenario: demo DB has stale (possibly fabricated) articles mixed with current ones.
    Calling init_database with clean=True should truncate both tables, recreate the
    schema, and reload feeds from config — leaving a zero-article DB ready for
    fresh seeding.
    """
    from scripts.init_db import init_database
    from src.models import Article, Feed

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    # Bootstrap DB with feeds and then inject a stale article + stale feed
    db = init_database(db_path=db_path, feeds_config_path=config_path)
    db.upsert_article(Article(
        id="stale1",
        url="https://example.invalid/stale",
        title="Stale fabricated article",
        source_name="Ghost Outlet",
        source_lang="en",
        source_tier=3,
        is_surveillance=True,
        confidence=0.95,
        country_code="IN",
        country_name="India",
    ))
    db.upsert_feed(Feed(
        name="Dropped legacy feed",
        url="https://example.invalid/rss.xml",
        language="en",
        tier=3,
        feed_type="specialty",
    ))
    assert db.count_articles() == 1
    stale_feed_urls_before = {f.url for f in db.get_active_feeds()}
    assert "https://example.invalid/rss.xml" in stale_feed_urls_before
    db.close()

    # Clean re-init — should wipe the stale article AND the stale feed,
    # then reload only the feeds from the current config
    db = init_database(
        db_path=db_path, feeds_config_path=config_path, clean=True,
    )
    assert db.count_articles() == 0
    feed_urls_after = {f.url for f in db.get_active_feeds()}
    assert "https://example.invalid/rss.xml" not in feed_urls_after
    assert len(feed_urls_after) > 50  # config feeds reloaded
    db.close()


def test_init_db_clean_flag_is_safe_on_missing_db(temp_project):
    """init_database(clean=True) on a fresh path should not error."""
    from scripts.init_db import init_database

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    # No prior DB exists — clean should still succeed and create schema
    db = init_database(
        db_path=db_path, feeds_config_path=config_path, clean=True,
    )
    assert db.count_articles() == 0
    assert len(db.get_active_feeds()) > 50
    db.close()


def test_init_db_cli_clean_flag(temp_project, monkeypatch, capsys):
    """`python scripts/init_db.py --clean` should wipe the DB and reload feeds."""
    from scripts.init_db import init_database, main
    from src.models import Article

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    # Pre-populate DB with a stale article
    db = init_database(db_path=db_path, feeds_config_path=config_path)
    db.upsert_article(Article(
        id="cli_stale1",
        url="https://example.invalid/cli_stale",
        title="Stale CLI test article",
        source_name="Ghost Outlet",
        source_lang="en",
        source_tier=3,
    ))
    assert db.count_articles() == 1
    db.close()

    # Invoke CLI with --clean
    monkeypatch.setattr(
        "sys.argv",
        ["init_db.py", "--db", db_path, "--config", config_path, "--clean"],
    )
    main()

    # Confirm the warning banner was printed so operators notice the wipe
    captured = capsys.readouterr()
    assert "[--clean]" in captured.out
    assert "Wiping articles and feeds tables" in captured.out

    # Re-open read-only and confirm the stale row is gone
    from src.database import Database
    verify = Database(db_path, read_only=True)
    try:
        assert verify.count_articles() == 0
        assert len(verify.get_active_feeds()) > 50
    finally:
        verify.close()


def test_seed_data_loads_articles(temp_project):
    """seed_data should load articles from seed_articles.json into the database."""
    from scripts.init_db import init_database
    from scripts.seed_data import seed_database

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    db = init_database(db_path=db_path, feeds_config_path=config_path)

    seed_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "seed_articles.json"
    )
    loaded, total, _exists = seed_database(db=db, seed_path=seed_path)
    assert loaded > 0
    assert loaded == total, f"Partial seed: {loaded}/{total} articles loaded"

    db_total = db.count_articles()
    assert db_total == loaded

    # Verify articles are flagged
    flagged = db.get_flagged_articles(min_confidence=0.0)
    assert len(flagged) == loaded
    db.close()


def test_seed_data_is_idempotent(temp_project):
    """Running seed_data twice should not duplicate articles (upsert)."""
    from scripts.init_db import init_database
    from scripts.seed_data import seed_database

    db_path = str(temp_project / "data" / "monitor.db")
    config_path = str(temp_project / "config" / "feeds.yaml")

    db = init_database(db_path=db_path, feeds_config_path=config_path)

    seed_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "seed_articles.json"
    )
    loaded1, total1, _exists1 = seed_database(db=db, seed_path=seed_path)
    loaded2, total2, exists2 = seed_database(db=db, seed_path=seed_path)

    assert loaded1 == total1, f"First seed partial: {loaded1}/{total1}"
    assert loaded2 == 0, "Second seed should skip all existing articles"
    assert exists2 == total2, "All articles should already exist on second run"
    assert db.count_articles() == loaded1
    db.close()


def test_seed_articles_json_is_valid():
    """seed_articles.json should be valid JSON with required fields."""
    seed_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "seed_articles.json"
    )
    with open(seed_path) as f:
        articles = json.load(f)

    assert isinstance(articles, list)
    assert len(articles) >= 30  # at least 30 for initial seed

    valid_categories = {
        "surveillance", "censorship", "facial_recognition", "internet_shutdown",
        "data_collection", "social_media_control", "digital_rights", "other",
    }
    required_fields = {"url", "title", "source_name", "country_code", "country_name", "category"}
    seen_urls: set[str] = set()
    for i, article in enumerate(articles):
        for field in required_fields:
            assert field in article, f"Article {i} missing field: {field}"
        assert article["url"].startswith("http"), f"Article {i} has invalid URL: {article['url']}"
        cc = article["country_code"]
        assert len(cc) == 2 and cc.isupper() and cc.isalpha(), \
            f"Article {i} has invalid country_code: {cc}"
        assert article["category"] in valid_categories, \
            f"Article {i} has invalid category: {article['category']}"
        assert article.get("source_tier") in (1, 2, 3, 4), \
            f"Article {i} has invalid source_tier: {article.get('source_tier')}"
        conf = article.get("confidence")
        assert isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0, \
            f"Article {i} has invalid confidence: {conf}"
        pub = article.get("published_at")
        if pub:
            dt = datetime.fromisoformat(pub)
            assert dt.tzinfo is not None, \
                f"Article {i} published_at missing timezone: {pub}"
        assert article["url"] not in seen_urls, \
            f"Article {i} has duplicate URL: {article['url']}"
        seen_urls.add(article["url"])


def test_seed_source_names_overlap_with_feed_names():
    """M16 invariant: sources present in both seed data AND config/feeds.yaml
    must use the exact feed name so dashboard groupings align.

    Not every seed source is in feeds.yaml — the seed dataset includes
    ~30 "legacy" sources (Scroll.in, Biometric Update, etc.) that came from
    broader web research and are not part of the live RSS ingestion. Those
    are intentionally left alone. But whenever a source name DOES overlap,
    it must match feed.name exactly (case + punctuation).
    """
    import yaml

    project_root = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(project_root, "config", "feeds.yaml")) as f:
        feed_names = {x["name"] for x in yaml.safe_load(f)["feeds"]}
    with open(os.path.join(project_root, "data", "seed_articles.json")) as f:
        seed_articles = json.load(f)
    seed_sources = {a["source_name"] for a in seed_articles}

    # After M16, the renamed sources should appear in the overlap set
    expected_overlap = {
        "Al Jazeera English",
        "TechCrunch Security",
        "Committee to Protect Journalists",
        "The Wire India",
        "Premium Times Nigeria",
        "News24 South Africa",
        "CNN World",
    }
    for name in expected_overlap:
        assert name in feed_names, (
            f"M16 regression: '{name}' expected in config/feeds.yaml"
        )
        assert name in seed_sources, (
            f"M16 regression: '{name}' expected as a seed source"
        )

    # Conversely, the legacy (unrenamed) names must NOT reappear in seed data
    legacy_names_that_must_not_exist = {
        "Al Jazeera", "TechCrunch",
        "Committee to Protect Journalists (CPJ)",
        "The Wire", "Premium Times", "News24", "CNN",
        "Reporters Without Borders",
    }
    for name in legacy_names_that_must_not_exist:
        assert name not in seed_sources, (
            f"M16 regression: legacy source name '{name}' still in seed data — "
            f"should have been renamed to its feed equivalent"
        )


def test_seed_articles_use_canonical_urls():
    """Seed article URLs should already be in canonical form."""
    from src.models import Article

    seed_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "seed_articles.json"
    )
    with open(seed_path) as f:
        articles = json.load(f)

    for i, entry in enumerate(articles):
        canonical = Article._canonicalize_url(entry["url"])
        assert canonical == entry["url"], \
            f"Article {i} URL is not canonical. Original: {entry['url']}, Canonical: {canonical}"


def test_seed_tiers_match_feeds_yaml_taxonomy():
    """R5 invariant: sources in both seed data and feeds.yaml must have matching tiers."""
    import yaml

    project_root = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(project_root, "config", "feeds.yaml")) as f:
        feeds = yaml.safe_load(f)["feeds"]
    # Build name→tier lookup (some names appear twice — use lowest tier)
    feed_tiers: dict[str, int] = {}
    for feed in feeds:
        name = feed["name"]
        tier = feed["tier"]
        if name not in feed_tiers or tier < feed_tiers[name]:
            feed_tiers[name] = tier

    with open(os.path.join(project_root, "data", "seed_articles.json")) as f:
        seed_articles = json.load(f)

    mismatches = []
    for article in seed_articles:
        name = article["source_name"]
        if name in feed_tiers:
            expected_tier = feed_tiers[name]
            actual_tier = article["source_tier"]
            if actual_tier != expected_tier:
                mismatches.append(
                    f"{name}: seed={actual_tier}, feeds.yaml={expected_tier}"
                )
    assert not mismatches, (
        f"R5 regression: seed/feed tier mismatches: {'; '.join(mismatches)}"
    )

    # Also check sub-brands: any seed source whose name starts with a
    # feed source name (e.g. "Global Voices Advox" → "Global Voices")
    # should not have a LOWER tier number (higher trust) than the parent.
    # Regional variants (e.g. "Amnesty International Malaysia" tier 4
    # vs parent "Amnesty International" tier 3) are acceptable — tier 4
    # is the correct classification for regional sub-brands.
    sub_brand_mismatches = []
    for article in seed_articles:
        name = article["source_name"]
        if name in feed_tiers:
            continue  # exact match already checked above
        for feed_name, feed_tier in feed_tiers.items():
            if name.startswith(feed_name) and article["source_tier"] < feed_tier:
                sub_brand_mismatches.append(
                    f"{name}: seed={article['source_tier']}, parent "
                    f"'{feed_name}'={feed_tier} (sub-brand more trusted than parent)"
                )
    assert not sub_brand_mismatches, (
        f"R5 regression: sub-brand tier mismatches: "
        f"{'; '.join(sub_brand_mismatches)}"
    )
