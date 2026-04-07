"""End-to-end smoke tests verifying the full demo pipeline.

Tests the complete chain: init_db → seed_data → query → dashboard components.
No live Streamlit server required — exercises logic paths only.
"""

import html as html_mod
import json
import os
import shutil

import pytest

from src.models import VALID_CATEGORIES

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def e2e_db(tmp_path):
    """Create a fully initialized and seeded database.

    Yields (db, db_path) so tests can open secondary connections.
    """
    # Copy config files to tmp_path
    src_config = os.path.join(REPO_ROOT, "config")
    dst_config = tmp_path / "config"
    shutil.copytree(src_config, dst_config)

    (tmp_path / "data").mkdir()
    db_path = str(tmp_path / "data" / "monitor.db")
    config_path = str(tmp_path / "config" / "feeds.yaml")
    seed_path = os.path.join(REPO_ROOT, "data", "seed_articles.json")

    from scripts.init_db import init_database
    from scripts.seed_data import seed_database

    db = init_database(db_path=db_path, feeds_config_path=config_path)
    loaded, total, _exists = seed_database(db=db, seed_path=seed_path)
    assert loaded == total, f"Seed incomplete: {loaded}/{total}"

    yield db, db_path
    db.close()


# ------------------------------------------------------------------ #
#  Pipeline smoke tests                                                #
# ------------------------------------------------------------------ #


class TestPipelineIntegrity:
    """Verify the init → seed → query chain works end to end."""

    def test_feeds_loaded(self, e2e_db):
        """init_db loads feeds from config into the database."""
        db, _ = e2e_db
        feeds = db.get_active_feeds()
        assert len(feeds) > 50  # config has 61 feeds

    def test_seed_articles_loaded(self, e2e_db):
        """seed_data loads all 79 articles."""
        db, _ = e2e_db
        assert db.count_articles() == 79

    def test_all_articles_flagged_surveillance(self, e2e_db):
        """All seed articles are flagged as surveillance with confidence."""
        db, _ = e2e_db
        flagged = db.get_flagged_articles(min_confidence=0.0)
        assert len(flagged) == 79

    def test_country_counts_match_seed(self, e2e_db):
        """Country counts from DB match seed distribution."""
        db, _ = e2e_db
        counts = db.get_country_counts(min_confidence=0.0)
        # Drill-down countries must be present
        assert "IN" in counts
        assert "MY" in counts
        assert "NG" in counts
        assert "ZA" in counts
        # Sum of counts must equal total articles
        assert sum(counts.values()) == 79

    def test_filter_by_country(self, e2e_db):
        """Filtering by country_code returns only that country's articles."""
        db, _ = e2e_db
        articles = db.get_flagged_articles(
            country_code="IN", min_confidence=0.0
        )
        assert len(articles) > 0
        assert all(a.country_code == "IN" for a in articles)

    def test_filter_by_category(self, e2e_db):
        """Filtering by category returns only matching articles."""
        db, _ = e2e_db
        articles = db.get_flagged_articles(
            category="surveillance", min_confidence=0.0
        )
        assert len(articles) > 0
        assert all(a.category == "surveillance" for a in articles)

    def test_filter_by_confidence_threshold(self, e2e_db):
        """Min confidence filter excludes articles below threshold."""
        db, _ = e2e_db
        # Seed has 4 articles at 0.94 and 75 at >= 0.95
        high_conf = db.get_flagged_articles(min_confidence=0.95)
        all_conf = db.get_flagged_articles(min_confidence=0.0)
        assert len(high_conf) < len(all_conf), (
            "Threshold must exclude some articles to exercise the filter"
        )
        assert all(a.confidence >= 0.95 for a in high_conf)

    def test_article_round_trip(self, e2e_db):
        """Individual article fetch by ID matches seed data."""
        db, _ = e2e_db
        articles = db.get_flagged_articles(min_confidence=0.0, limit=1)
        assert len(articles) == 1
        fetched = db.get_article(articles[0].id)
        assert fetched is not None
        assert fetched.url == articles[0].url
        assert fetched.title == articles[0].title

    def test_get_article_nonexistent(self, e2e_db):
        """get_article returns None for a nonexistent ID."""
        db, _ = e2e_db
        assert db.get_article("nonexistent-id-000") is None

    def test_seed_idempotency(self, e2e_db):
        """Running seed a second time does not duplicate articles."""
        db, _ = e2e_db
        from scripts.seed_data import seed_database

        seed_path = os.path.join(REPO_ROOT, "data", "seed_articles.json")
        loaded2, total2, exists2 = seed_database(db=db, seed_path=seed_path)
        assert loaded2 == 0, "Second seed should skip all existing articles"
        assert exists2 == total2, "All articles should already exist"
        assert db.count_articles() == 79


# ------------------------------------------------------------------ #
#  Dashboard component smoke tests                                     #
# ------------------------------------------------------------------ #


class TestDashboardComponents:
    """Verify dashboard components render without errors on real data."""

    def test_global_map_builds_from_db(self, e2e_db):
        """build_map_data produces renderable data from DB country counts."""
        db, _ = e2e_db
        from dashboard.components.map_global import build_map_data

        counts = db.get_country_counts(min_confidence=0.0)
        map_data = build_map_data(counts)
        assert len(map_data) > 0
        # Each entry must have lat, lng, count, country_name
        for entry in map_data:
            assert "lat" in entry
            assert "lng" in entry
            assert "count" in entry
            assert "country_name" in entry

    def test_global_map_renders_html(self, e2e_db):
        """render_map_html produces valid HTML from real data."""
        db, _ = e2e_db
        from dashboard.components.map_global import build_map_data, render_map_html

        counts = db.get_country_counts(min_confidence=0.0)
        map_data = build_map_data(counts)
        html = render_map_html(map_data)
        assert isinstance(html, str)
        assert "<script" in html
        assert len(html) > 100

    def test_drilldown_map_for_each_country(self, e2e_db):
        """Drill-down map builds data and renders for all 4 countries."""
        db, _ = e2e_db
        from dashboard.components.map_drilldown import (
            build_region_data,
            get_country_center,
            render_drilldown_html,
        )

        for cc in ("IN", "MY", "NG", "ZA"):
            articles = db.get_flagged_articles(
                country_code=cc, min_confidence=0.0
            )
            region_data = build_region_data(articles, cc)
            center = get_country_center(cc)
            assert center is not None, f"No center for {cc}"
            html = render_drilldown_html(region_data, center)
            assert isinstance(html, str)
            assert len(html) > 100

    def test_news_feed_renders_articles(self, e2e_db):
        """render_news_feed produces HTML for real articles."""
        db, _ = e2e_db
        from dashboard.components.news_feed import render_news_feed

        articles = db.get_flagged_articles(min_confidence=0.0, limit=10)
        html = render_news_feed(articles)
        assert isinstance(html, str)
        assert "article-card" in html
        # Title should appear HTML-escaped in the rendered output
        assert html_mod.escape(articles[0].title) in html

    def test_article_detail_renders(self, e2e_db):
        """render_article_detail produces HTML for a real article."""
        db, _ = e2e_db
        from dashboard.components.article_detail import render_article_detail

        articles = db.get_flagged_articles(min_confidence=0.0, limit=1)
        html = render_article_detail(articles[0])
        assert isinstance(html, str)
        assert len(html) > 0

    def test_news_feed_empty(self, e2e_db):
        """render_news_feed handles empty article list."""
        from dashboard.components.news_feed import render_news_feed

        html = render_news_feed([])
        assert "No articles found" in html

    def test_article_detail_none(self, e2e_db):
        """render_article_detail handles None article."""
        from dashboard.components.article_detail import render_article_detail

        html = render_article_detail(None)
        assert isinstance(html, str)
        assert "Select an article" in html


# ------------------------------------------------------------------ #
#  Dashboard logic smoke tests                                         #
# ------------------------------------------------------------------ #


class TestDashboardLogic:
    """Verify dashboard pure-logic helpers work with real data."""

    def test_view_state_routing(self):
        """get_view_state routes correctly."""
        from dashboard.app import get_view_state

        assert get_view_state({}) == "global"
        assert get_view_state({"selected_country": None}) == "global"
        assert get_view_state({"selected_country": "IN"}) == "drilldown"

    def test_select_and_clear_country(self):
        """select_country and clear_country manage state."""
        from dashboard.app import clear_country, select_country

        state: dict = {}
        select_country(state, "MY")
        assert state["selected_country"] == "MY"
        assert state["selected_article_id"] is None

        clear_country(state)
        assert state["selected_country"] is None

    def test_build_filter_params(self):
        """build_filter_params converts UI values to DB kwargs."""
        from dashboard.app import build_filter_params

        params = build_filter_params(
            country="IN",
            category="surveillance",
            min_confidence=0.7,
            date_from=None,
            date_to=None,
        )
        assert params["country_code"] == "IN"
        assert params["category"] == "surveillance"
        assert params["min_confidence"] == 0.7
        assert "date_from" not in params
        assert "date_to" not in params

    def test_build_filter_params_all_values(self):
        """build_filter_params skips 'All' sentinel values."""
        from dashboard.app import build_filter_params

        params = build_filter_params(
            country="All",
            category="All",
            min_confidence=0.6,
            date_from=None,
            date_to=None,
        )
        assert "country_code" not in params
        assert "category" not in params

    def test_get_categories(self):
        """get_categories returns 'All' plus sorted valid categories."""
        from dashboard.app import get_categories

        cats = get_categories()
        assert cats[0] == "All"
        assert len(cats) == len(VALID_CATEGORIES) + 1
        # Rest should be sorted
        assert cats[1:] == sorted(cats[1:])

    def test_get_drilldown_countries(self):
        """get_drilldown_countries returns the 4 expected countries."""
        from dashboard.app import get_drilldown_countries

        countries = get_drilldown_countries()
        assert set(countries) == {"IN", "MY", "NG", "ZA"}


# ------------------------------------------------------------------ #
#  Cross-component integration                                         #
# ------------------------------------------------------------------ #


class TestCrossComponent:
    """Verify components interact correctly across the pipeline."""

    def test_filter_to_map_to_feed(self, e2e_db):
        """Full flow: build filter params → query DB → build map → render feed."""
        db, _ = e2e_db
        from dashboard.app import build_filter_params
        from dashboard.components.map_global import build_map_data
        from dashboard.components.news_feed import render_news_feed

        params = build_filter_params(
            country="All",
            category="surveillance",
            min_confidence=0.7,
            date_from=None,
            date_to=None,
        )
        articles = db.get_flagged_articles(**params)
        assert len(articles) > 0

        # get_country_counts accepts only these keys
        count_keys = {"min_confidence", "category", "date_from", "date_to"}
        counts = db.get_country_counts(
            **{k: v for k, v in params.items() if k in count_keys}
        )
        map_data = build_map_data(counts)
        assert len(map_data) > 0

        # Feed should render filtered articles
        html = render_news_feed(articles)
        assert len(html) > 0

    def test_drilldown_flow(self, e2e_db):
        """Full drill-down: select country → query → build region map → feed."""
        db, _ = e2e_db
        from dashboard.app import select_country
        from dashboard.components.map_drilldown import (
            build_region_data,
            get_country_center,
            render_drilldown_html,
        )
        from dashboard.components.news_feed import render_news_feed

        state: dict = {}
        select_country(state, "IN")
        assert state["selected_country"] == "IN"

        articles = db.get_flagged_articles(
            country_code="IN", min_confidence=0.0
        )
        assert len(articles) > 0

        region_data = build_region_data(articles, "IN")
        center = get_country_center("IN")
        html = render_drilldown_html(region_data, center)
        assert len(html) > 100

        feed_html = render_news_feed(articles)
        assert len(feed_html) > 0

    def test_article_detail_from_feed(self, e2e_db):
        """Select article from feed → render detail."""
        db, _ = e2e_db
        from dashboard.app import select_article
        from dashboard.components.article_detail import render_article_detail

        articles = db.get_flagged_articles(min_confidence=0.0, limit=5)
        target = articles[0]

        state: dict = {}
        select_article(state, target.id)
        assert state["selected_article_id"] == target.id

        fetched = db.get_article(target.id)
        assert fetched is not None
        html = render_article_detail(fetched)
        assert len(html) > 0

    def test_seed_data_matches_json_source(self, e2e_db):
        """Every article in DB can be traced back to seed_articles.json."""
        db, _ = e2e_db
        seed_path = os.path.join(REPO_ROOT, "data", "seed_articles.json")
        with open(seed_path, encoding="utf-8") as f:
            seed_data = json.load(f)

        seed_urls = {entry["url"] for entry in seed_data}
        db_articles = db.get_flagged_articles(min_confidence=0.0, limit=200)
        db_urls = {a.url for a in db_articles}

        assert db_urls == seed_urls, (
            f"Mismatch: {len(db_urls)} DB URLs vs {len(seed_urls)} seed URLs"
        )

    def test_read_only_mode_works(self, e2e_db):
        """Dashboard read-only DB connection can query seeded data."""
        _, db_path = e2e_db
        from src.database import Database

        ro_db = Database(db_path, read_only=True)
        try:
            count = ro_db.count_articles()
            assert count == 79
            flagged = ro_db.get_flagged_articles(min_confidence=0.0)
            assert len(flagged) == 79
            counts = ro_db.get_country_counts(min_confidence=0.0)
            assert sum(counts.values()) == 79
        finally:
            ro_db.close()
