"""RSS ingestion worker — fetches feeds, classifies, summarizes, stores."""

from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests
import urllib3.util.connection

from src.classifier import Classifier
from src.database import Database
from src.models import Article, ClassificationResult, Feed
from src.summarizer import Summarizer
from src.url_utils import resolve_and_validate_host

logger = logging.getLogger(__name__)

_USER_AGENT = "AI-Surveillance-Monitor/1.0 (+research; RSS reader)"
_REQUEST_TIMEOUT = 15
_BATCH_SIZE = 10
_MAX_ARTICLES_PER_FEED = 100  # Cap per-feed to prevent LLM cost amplification
_MAX_ARTICLES_PER_RUN = 500   # Global cap per ingestion run

# ---------------------------------------------------------------------------
# DNS pinning — closes the TOCTOU gap between SSRF validation and HTTP fetch.
# We resolve the hostname ourselves, validate all IPs, then pin the result
# so urllib3 connects to the validated IP instead of re-resolving.
# ---------------------------------------------------------------------------
_orig_create_connection = urllib3.util.connection.create_connection
_pin_lock = threading.Lock()
_pinned_hosts: dict[str, str] = {}  # hostname -> validated IP


def _pinned_create_connection(address, *args, **kwargs):
    """urllib3 connection hook that uses pinned IPs when available."""
    host, port = address
    with _pin_lock:
        override = _pinned_hosts.get(host)
    if override is not None:
        return _orig_create_connection((override, port), *args, **kwargs)
    return _orig_create_connection(address, *args, **kwargs)


urllib3.util.connection.create_connection = _pinned_create_connection


@contextlib.contextmanager
def _pin_dns(hostname: str, validated_ip: str):
    """Pin DNS resolution for *hostname* to *validated_ip* for the request scope."""
    with _pin_lock:
        _pinned_hosts[hostname] = validated_ip
    try:
        yield
    finally:
        with _pin_lock:
            _pinned_hosts.pop(hostname, None)


def _default_result(provider: str = "failed") -> ClassificationResult:
    """Default classification for articles when LLM classification fails.

    Uses ``confidence=None`` so the database CASE guard does not overwrite
    existing classification data (see database.py upsert_article).
    """
    return ClassificationResult(
        is_surveillance=False,
        confidence=None,
        category="other",
        llm_provider=provider,
    )


class IngestionWorker:
    """Fetches RSS feeds, classifies articles, and stores results."""

    def __init__(
        self,
        db: Database,
        classifier: Classifier,
        summarizer: Summarizer,
    ):
        self._db = db
        self._classifier = classifier
        self._summarizer = summarizer

    def fetch_feed(
        self, feed: Feed, seen_ids: set[str] | None = None,
    ) -> tuple[list[Article], bool]:
        """Fetch a single feed and return (new_articles, success).

        Sets User-Agent header, respects timeout, handles bozo feeds.
        Returns ([], False) on HTTP errors, (articles, True) on success.
        seen_ids: optional set of IDs already seen in this run for cross-feed dedup.
        **Mutated in place** — new article IDs from this feed are added so the
        caller can pass the same set to subsequent ``fetch_feed`` calls.
        """
        if seen_ids is None:
            seen_ids = set()

        # SSRF defense: resolve DNS, validate all IPs, then pin the result
        # so urllib3 connects to the validated IP (no TOCTOU gap).
        _hostname = urlparse(feed.url).hostname
        if not _hostname:
            logger.warning("Feed %s has no hostname — skipping", feed.name)
            return ([], False)
        try:
            validated_ip = resolve_and_validate_host(_hostname)
        except ValueError as exc:
            logger.warning(
                "Feed %s blocked by SSRF check: %s", feed.name, exc,
            )
            return ([], False)
        except OSError:
            logger.warning(
                "Feed %s DNS resolution failed — skipping", feed.name,
            )
            return ([], False)

        try:
            with _pin_dns(_hostname, validated_ip):
                response = requests.get(
                    feed.url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=_REQUEST_TIMEOUT,
                    allow_redirects=False,
                )
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("HTTP error fetching feed %s (%s)", feed.name, feed.url)
            return ([], False)

        # Reject redirects — with allow_redirects=False a 3xx means the
        # config URL is stale (301/308 are permanent) or temporarily
        # moved (302/303/307 are temporary).
        if 300 <= response.status_code < 400:
            raw_target = response.headers.get("Location", "<unknown>")
            # Sanitize Location header: strip control chars, bidi overrides,
            # and null bytes to prevent CRLF log injection and log spoofing.
            target = repr(raw_target[:200])
            if response.status_code in (301, 308):
                logger.error(
                    "Feed %s permanently redirects to %s (HTTP %d) — UPDATE CONFIG URL",
                    feed.name, target, response.status_code,
                )
            else:
                logger.warning(
                    "Feed %s temporarily redirects to %s (HTTP %d) — transient, will retry",
                    feed.name, target, response.status_code,
                )
            return ([], False)

        # Reject any non-200 that raise_for_status() let through (e.g. 204,
        # 206) — mirrors verify_feeds.py HTTP_ERROR classification.
        if response.status_code != 200:
            logger.warning(
                "Feed %s returned HTTP %d — expected 200",
                feed.name, response.status_code,
            )
            return ([], False)

        parsed = feedparser.parse(
            response.content,
            response_headers={"content-type": response.headers.get("Content-Type", "")},
        )

        if parsed.bozo:
            logger.warning(
                "Bozo feed %s: %s — processing valid entries",
                feed.name, getattr(parsed, "bozo_exception", "unknown"),
            )
            if not parsed.entries:
                return ([], False)

        # Non-feed content (HTML error page, JSON, etc.) — feedparser
        # sets .version to empty string for non-RSS/Atom (H14 parity).
        feed_version = getattr(parsed, "version", "") or ""
        if not parsed.entries and not feed_version:
            logger.warning(
                "Feed %s returned non-feed content (no RSS/Atom version)",
                feed.name,
            )
            return ([], False)

        new_articles: list[Article] = []
        for entry in parsed.entries:
            if len(new_articles) >= _MAX_ARTICLES_PER_FEED:
                logger.warning(
                    "Feed %s hit per-feed cap (%d) — skipping remaining entries",
                    feed.name, _MAX_ARTICLES_PER_FEED,
                )
                break
            try:
                article = Article.from_rss_entry(
                    entry,
                    source_name=feed.name,
                    source_lang=feed.language,
                    source_tier=feed.tier,
                )
                if article is None:
                    continue
                if article.id in seen_ids:
                    continue
                if self._db.article_exists(article.id):
                    if not self._db.article_needs_classification(article.id):
                        seen_ids.add(article.id)
                        continue
                    # Article exists but failed classification — retry
                    logger.info("Re-queuing unclassified article %s", article.id)
                seen_ids.add(article.id)
                new_articles.append(article)
            except Exception:
                logger.exception("Error processing entry in feed %s", feed.name)

        return (new_articles, True)

    def process_batch(self, articles: list[Article]) -> None:
        """Classify a batch, summarize flagged articles, and upsert all to DB.

        All articles are always upserted, even if classification fails.
        Uses batch upsert for ~5-10x throughput vs per-article commits.
        """
        if not articles:
            return

        try:
            results = list(self._classifier.classify_batch(articles))
        except Exception:
            logger.exception("classify_batch failed — defaulting all %d articles", len(articles))
            results = []

        # Pad results with defaults if classifier returned fewer than expected
        while len(results) < len(articles):
            results.append(_default_result())

        updated_articles: list[Article] = []
        for article, result in zip(articles, results):
            updated = replace(
                article,
                is_surveillance=result.is_surveillance,
                confidence=result.confidence,
                category=result.category,
                country_code=result.country_code,
                country_name=result.country_name,
                region=result.region,
                classified_at=datetime.now(tz=timezone.utc),
                llm_provider=result.llm_provider,
            )

            if result.is_surveillance:
                try:
                    summary_en, title_en = self._summarizer.summarize(article)
                    updated = replace(
                        updated,
                        summary_en=summary_en,
                        title_en=title_en,
                    )
                except Exception:
                    logger.exception("Summarization failed for %s", article.id)

            updated_articles.append(updated)

        try:
            self._db.upsert_articles_batch(updated_articles)
        except Exception:
            logger.exception("upsert_articles_batch failed for batch of %d", len(updated_articles))

    def run_once(self) -> None:
        """Fetch all active feeds and process new articles in batches.

        Feeds are processed in ascending tier order (tier 1 = highest trust)
        so that cross-feed dedup lets higher-tier sources claim an article
        over lower-tier sources that publish the same link (M13).
        """
        try:
            feeds = self._db.get_active_feeds()
        except Exception:
            logger.exception("Failed to load active feeds — aborting ingestion run")
            return
        logger.info("Starting ingestion run: %d active feeds", len(feeds))

        # Sort by tier ASC so tier 1 feeds get first pick on duplicates.
        # Use (tier, name) as a stable secondary sort.
        feeds = sorted(feeds, key=lambda f: (f.tier if f.tier is not None else 99, f.name or ""))

        # Process articles incrementally per-feed instead of accumulating all
        # in memory first (CC2-M6).  This bounds peak memory usage to ~one
        # feed's worth of articles + one _BATCH_SIZE classification batch.
        seen_ids: set[str] = set()
        total_fetched = 0
        total_processed = 0
        pending: list[Article] = []

        for feed in feeds:
            if total_fetched >= _MAX_ARTICLES_PER_RUN:
                logger.warning(
                    "Hit per-run article cap (%d) — skipping remaining feeds",
                    _MAX_ARTICLES_PER_RUN,
                )
                break
            try:
                new_articles, success = self.fetch_feed(feed, seen_ids=seen_ids)
                pending.extend(new_articles)
                total_fetched += len(new_articles)
                if success:
                    self._db.update_feed_fetched(feed.url)
                logger.info(
                    "Feed %s: %d new articles (success=%s)",
                    feed.name, len(new_articles), success,
                )
            except Exception:
                logger.exception("Unexpected error processing feed %s", feed.name)

            # Flush pending articles when we have a full batch
            while len(pending) >= _BATCH_SIZE:
                batch = pending[:_BATCH_SIZE]
                pending = pending[_BATCH_SIZE:]
                try:
                    self.process_batch(batch)
                    total_processed += len(batch)
                except Exception:
                    logger.exception(
                        "Batch processing failed (%d articles)", len(batch)
                    )

        # Process any remaining articles
        if pending:
            try:
                self.process_batch(pending)
                total_processed += len(pending)
            except Exception:
                logger.exception(
                    "Final batch processing failed (%d articles)", len(pending)
                )

        logger.info(
            "Ingestion run complete: %d fetched, %d processed",
            total_fetched, total_processed,
        )
