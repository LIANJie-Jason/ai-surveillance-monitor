# tests/test_ingestion.py
import pytest
from unittest.mock import MagicMock, patch, call
from src.models import Feed, Article, ClassificationResult


@pytest.fixture(autouse=True)
def _bypass_dns_resolution():
    """Auto-mock DNS resolution so ingestion tests don't hit real DNS."""
    with patch(
        "src.ingestion.resolve_and_validate_host",
        return_value="93.184.216.34",  # example.com IP
    ):
        yield


def _make_feed(name="Test", url="https://example.com/rss", lang="en", tier=1):
    return Feed(name=name, url=url, language=lang, tier=tier, feed_type="wire")


def _make_article(id_suffix="1", title="Test Article"):
    return Article(
        id=f"art-{id_suffix}",
        url=f"https://example.com/{id_suffix}",
        title=title,
        source_name="Wire",
        source_lang="en",
        source_tier=1,
    )


# --- fetch_feed tests ---


def test_fetch_feed_returns_articles_and_success():
    """Should return (articles, True) on successful fetch."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "Test Article", "link": "https://example.com/1", "summary": "Content here"},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response) as mock_get, \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        feed = _make_feed()
        articles, success = worker.fetch_feed(feed)
        assert success is True
        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert "timeout" in call_kwargs.kwargs
        assert "headers" in call_kwargs.kwargs


def test_fetch_feed_skips_duplicates():
    """Should skip articles that already exist in the database and are classified."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = True
    mock_db.article_needs_classification.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "Old Article", "link": "https://example.com/old", "summary": ""},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is True
        assert len(articles) == 0


def test_fetch_feed_requeues_unclassified_articles():
    """Should re-queue articles that exist but were never classified (confidence IS NULL)."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = True
    mock_db.article_needs_classification.return_value = True
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "Unclassified Article", "link": "https://example.com/unclass", "summary": "x"},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is True
        assert len(articles) == 1
        assert articles[0].title == "Unclassified Article"


def test_fetch_feed_handles_bozo():
    """Should log warning but still process valid entries from bozo feeds."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = True
    fake_feed_data.bozo_exception = Exception("not well-formed")
    fake_feed_data.entries = [
        {"title": "Still Valid", "link": "https://example.com/valid", "summary": "ok"},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is True
        assert len(articles) == 1


def test_fetch_feed_http_error_returns_empty_and_false():
    """Should return ([], False) on HTTP errors without crashing."""
    from src.ingestion import IngestionWorker
    import requests

    mock_db = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    with patch("src.ingestion.requests.get", side_effect=requests.RequestException("timeout")):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is False
        assert articles == []


def test_fetch_feed_skips_none_articles():
    """Should skip entries where Article.from_rss_entry returns None (no link)."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "No Link Entry", "summary": "Missing link field"},  # no "link"
        {"title": "Good Entry", "link": "https://example.com/good", "summary": "ok"},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is True
        assert len(articles) == 1
        assert articles[0].title == "Good Entry"


def test_fetch_feed_bozo_empty_returns_false():
    """Bozo feed with no valid entries should return ([], False)."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = True
    fake_feed_data.bozo_exception = Exception("not well-formed")
    fake_feed_data.entries = []  # bozo AND empty
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<broken xml"

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())
        assert success is False
        assert articles == []


def test_fetch_feed_cross_feed_dedup():
    """seen_ids should prevent duplicate articles across multiple fetch_feed calls."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "Shared Article", "link": "https://example.com/shared", "summary": "dup"},
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<rss>...</rss>"

    shared_seen: set[str] = set()

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles1, _ = worker.fetch_feed(_make_feed("Feed1", "https://a.com/rss"), seen_ids=shared_seen)
        articles2, _ = worker.fetch_feed(_make_feed("Feed2", "https://b.com/rss"), seen_ids=shared_seen)

    assert len(articles1) == 1
    assert len(articles2) == 0  # duplicate suppressed


# --- process_batch tests ---


def test_process_batch_classifies_and_summarizes():
    """Should classify batch, summarize flagged articles, and upsert all."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    mock_classifier.classify_batch.return_value = [
        ClassificationResult(
            is_surveillance=True, confidence=0.9, category="surveillance",
            country_code="IN", country_name="India", region="Delhi", llm_provider="openai",
        ),
        ClassificationResult(
            is_surveillance=False, confidence=0.1, category="other",
            country_code="US", country_name="United States", llm_provider="openai",
        ),
    ]
    mock_summarizer.summarize.return_value = ("Summary of article.", "Translated title")

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    articles = [_make_article("1", "Surveillance in India"), _make_article("2", "Tech earnings")]

    worker.process_batch(articles)

    mock_classifier.classify_batch.assert_called_once_with(articles)
    # Summarizer called only for flagged article
    mock_summarizer.summarize.assert_called_once()
    # All articles upserted in a single batch call
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 2


def test_process_batch_empty_list():
    """Empty batch should not call classifier or summarizer."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    worker.process_batch([])
    mock_classifier.classify_batch.assert_not_called()
    mock_summarizer.summarize.assert_not_called()
    mock_db.upsert_articles_batch.assert_not_called()


def test_process_batch_pads_short_classifier_results():
    """When classifier returns fewer results than articles, pad with defaults."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    # Classifier returns only 1 result for 3 articles
    mock_classifier.classify_batch.return_value = [
        ClassificationResult(
            is_surveillance=True, confidence=0.8, category="surveillance",
            llm_provider="openai",
        ),
    ]
    mock_summarizer.summarize.return_value = ("Summary.", None)

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1"), _make_article("2"), _make_article("3")]

    worker.process_batch(articles)

    # All 3 articles should be upserted in one batch call
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 3


def test_process_batch_classifier_returns_empty():
    """When classifier returns [], all articles still upserted with defaults."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    mock_classifier.classify_batch.return_value = []  # total failure

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1"), _make_article("2")]

    worker.process_batch(articles)

    # Both should be upserted with default classification in one batch
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 2
    # Summarizer never called (defaults have is_surveillance=False)
    mock_summarizer.summarize.assert_not_called()


def test_process_batch_summarizer_exception_still_upserts():
    """If summarizer raises, article is still upserted (without summary)."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    mock_classifier.classify_batch.return_value = [
        ClassificationResult(
            is_surveillance=True, confidence=0.9, category="surveillance",
            llm_provider="openai",
        ),
    ]
    mock_summarizer.summarize.side_effect = RuntimeError("LLM down")

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1")]

    worker.process_batch(articles)

    # Article still upserted in batch despite summarizer failure
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 1


def test_process_batch_classifier_exception_still_upserts_defaults():
    """If classify_batch raises, all articles upserted with default classification."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    mock_classifier.classify_batch.side_effect = RuntimeError("LLM crash")

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1"), _make_article("2")]

    worker.process_batch(articles)

    # All articles still upserted with defaults in one batch
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 2
    # Summarizer never called (defaults have is_surveillance=False)
    mock_summarizer.summarize.assert_not_called()


def test_process_batch_upsert_failure_logged():
    """If upsert_articles_batch fails, exception is logged (not raised)."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    mock_classifier.classify_batch.return_value = [
        ClassificationResult(is_surveillance=False, confidence=0.1, category="other", llm_provider="openai"),
        ClassificationResult(is_surveillance=False, confidence=0.2, category="other", llm_provider="openai"),
    ]

    mock_db.upsert_articles_batch.side_effect = Exception("DB error")

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1"), _make_article("2")]

    worker.process_batch(articles)  # should not raise

    # Batch upsert attempted once
    mock_db.upsert_articles_batch.assert_called_once()


# --- run_once tests ---


def test_run_once_fetches_all_active_feeds():
    """run_once should fetch all active feeds and process articles."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.get_active_feeds.return_value = [
        _make_feed("Feed1", "https://a.com/rss"),
        _make_feed("Feed2", "https://b.com/rss"),
    ]

    mock_classifier = MagicMock()
    mock_classifier.classify_batch.return_value = []
    mock_summarizer = MagicMock()

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = []
    fake_feed_data.version = "rss20"
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        worker.run_once()

    mock_db.get_active_feeds.assert_called_once()
    # update_feed_fetched called for each successful feed
    assert mock_db.update_feed_fetched.call_count == 2


def test_run_once_batching_processes_all_articles():
    """run_once with >_BATCH_SIZE articles should process multiple batches."""
    from src.ingestion import IngestionWorker, _BATCH_SIZE

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    mock_db.get_active_feeds.return_value = [_make_feed("BigFeed", "https://big.com/rss")]

    mock_classifier = MagicMock()
    mock_classifier.classify_batch.return_value = []  # will be padded with defaults
    mock_summarizer = MagicMock()

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    # Create 15 entries (> _BATCH_SIZE=10) to force 2 batches
    entries = [
        {"title": f"Article {i}", "link": f"https://big.com/{i}", "summary": f"s{i}"}
        for i in range(15)
    ]
    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = entries
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<rss>...</rss>"

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        worker.run_once()

    # classify_batch called twice: once with 10 articles, once with 5
    assert mock_classifier.classify_batch.call_count == 2
    batch1 = mock_classifier.classify_batch.call_args_list[0][0][0]
    batch2 = mock_classifier.classify_batch.call_args_list[1][0][0]
    assert len(batch1) == _BATCH_SIZE
    assert len(batch2) == 15 - _BATCH_SIZE
    # All 15 articles upserted in 2 batch calls
    assert mock_db.upsert_articles_batch.call_count == 2


def test_run_once_skips_feed_fetched_on_failure():
    """update_feed_fetched should NOT be called for feeds that fail to fetch."""
    from src.ingestion import IngestionWorker
    import requests as req

    mock_db = MagicMock()
    mock_db.get_active_feeds.return_value = [
        _make_feed("GoodFeed", "https://good.com/rss"),
        _make_feed("BadFeed", "https://bad.com/rss"),
    ]

    mock_classifier = MagicMock()
    mock_classifier.classify_batch.return_value = []
    mock_summarizer = MagicMock()

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = []
    fake_feed_data.version = "rss20"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<rss>...</rss>"

    def mock_get(url, **kwargs):
        if "bad.com" in url:
            raise req.RequestException("refused")
        return mock_response

    with patch("src.ingestion.requests.get", side_effect=mock_get), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        worker.run_once()

    # Only the good feed should be marked as fetched
    mock_db.update_feed_fetched.assert_called_once_with("https://good.com/rss")


def test_run_once_per_feed_exception_does_not_crash():
    """An unexpected exception in one feed should not crash the entire run."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.get_active_feeds.return_value = [
        _make_feed("CrashFeed", "https://crash.com/rss"),
        _make_feed("GoodFeed", "https://good.com/rss"),
    ]

    mock_classifier = MagicMock()
    mock_classifier.classify_batch.return_value = []
    mock_summarizer = MagicMock()

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = []
    fake_feed_data.version = "rss20"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<rss>...</rss>"

    call_count = 0

    def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "crash.com" in url:
            raise RuntimeError("unexpected crash")
        return mock_response

    with patch("src.ingestion.requests.get", side_effect=mock_get), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        worker.run_once()  # should not raise

    # Second feed still processed despite first crashing
    assert mock_db.update_feed_fetched.call_count == 1
    mock_db.update_feed_fetched.assert_called_once_with("https://good.com/rss")


def test_run_once_get_active_feeds_failure_aborts_gracefully():
    """If get_active_feeds raises, run_once returns without crashing."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.get_active_feeds.side_effect = RuntimeError("DB unreachable")

    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())
    worker.run_once()  # should not raise

    mock_db.update_feed_fetched.assert_not_called()


def test_fetch_feed_entry_exception_continues():
    """One bad entry should not prevent processing of remaining entries."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    # First call raises, second returns False (article not seen)
    mock_db.article_exists.side_effect = [RuntimeError("DB glitch"), False]
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = False
    fake_feed_data.entries = [
        {"title": "Bad Entry", "link": "https://example.com/bad", "summary": "x"},
        {"title": "Good Entry", "link": "https://example.com/good", "summary": "ok"},
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<rss>...</rss>"

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        articles, success = worker.fetch_feed(_make_feed())

    assert success is True
    assert len(articles) == 1
    assert articles[0].title == "Good Entry"


def test_process_batch_classifier_returns_tuple():
    """classify_batch returning a tuple (non-list iterable) should still work."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_classifier = MagicMock()
    mock_summarizer = MagicMock()

    # Return a tuple instead of list
    mock_classifier.classify_batch.return_value = (
        ClassificationResult(
            is_surveillance=False, confidence=0.2, category="other", llm_provider="openai",
        ),
    )

    worker = IngestionWorker(db=mock_db, classifier=mock_classifier, summarizer=mock_summarizer)
    articles = [_make_article("1"), _make_article("2")]

    worker.process_batch(articles)

    # Both articles upserted in one batch (1 real result + 1 padded default)
    mock_db.upsert_articles_batch.assert_called_once()
    assert len(mock_db.upsert_articles_batch.call_args[0][0]) == 2


# --- H14 parity tests: verifier and ingestion agree on edge cases ---


def test_fetch_feed_redirect_returns_false():
    """3xx with allow_redirects=False should return ([], False) — H14 parity."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    mock_response = MagicMock()
    mock_response.status_code = 301
    mock_response.headers = {"Location": "https://new.example/rss"}
    mock_response.raise_for_status.return_value = None  # 3xx does not raise

    with patch("src.ingestion.requests.get", return_value=mock_response):
        articles, success = worker.fetch_feed(_make_feed())
    assert success is False
    assert articles == []


def test_fetch_feed_non_feed_content_returns_false():
    """HTML page (200 OK but empty feedparser.version) → ([], False) — H14 parity."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    html_parsed = MagicMock()
    html_parsed.bozo = False
    html_parsed.entries = []
    html_parsed.version = ""  # feedparser returns "" for non-feed content

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<!DOCTYPE html><html><body>Not a feed</body></html>"
    mock_response.raise_for_status.return_value = None

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=html_parsed):
        articles, success = worker.fetch_feed(_make_feed())
    assert success is False
    assert articles == []


def test_fetch_feed_non_200_success_code_returns_false():
    """204 No Content (raise_for_status passes) should still fail — H14 parity."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_response.raise_for_status.return_value = None  # 2xx does not raise

    with patch("src.ingestion.requests.get", return_value=mock_response):
        articles, success = worker.fetch_feed(_make_feed())
    assert success is False
    assert articles == []
