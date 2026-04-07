"""SQLite database operations for the surveillance news monitor."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from src.models import Article, Feed

logger = logging.getLogger(__name__)


class Database:
    """Thin wrapper around SQLite for article and feed persistence.

    Supports both read-write (ingestion worker) and read-only (dashboard)
    connection modes.  Uses WAL journal mode for concurrent read/write access.
    """

    def __init__(self, db_path: str = "data/monitor.db", read_only: bool = False):
        # check_same_thread=False: safe for current single-writer model
        # (dashboard is read-only, ingestion is single-threaded).
        # If ingestion ever becomes multi-threaded, add explicit locking.
        if read_only:
            uri = f"file:{db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        if not read_only:
            self._conn.execute("PRAGMA journal_mode=WAL")
        # Validate that required tables exist for read-only connections
        if read_only:
            tables = {
                row[0]
                for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "articles" not in tables or "feeds" not in tables:
                self._conn.close()
                raise RuntimeError(
                    f"Database at {db_path!r} is missing required tables. "
                    "Run 'python scripts/init_db.py' first."
                )

    # ------------------------------------------------------------------ #
    #  Schema                                                              #
    # ------------------------------------------------------------------ #

    def init_tables(self) -> None:
        """Create tables and indexes if they do not exist.

        Auto-migration: earlier versions of the feeds table used a ``category``
        column that collided with the topical ``articles.category`` column.
        When this method sees the old schema it drops the feeds table; the
        next ``init_db`` run reloads feeds from config into the new schema.
        The articles table is untouched (its ``category`` column is the
        article topic and is still correct).
        """
        # Step 1: migrate legacy feeds schema if present
        try:
            cols = [
                row["name"]
                for row in self._conn.execute(
                    "PRAGMA table_info(feeds)"
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            cols = []
        if cols and "category" in cols and "feed_type" not in cols:
            self._conn.execute("DROP TABLE feeds")
            self._conn.commit()

        # Step 2: create schema (IF NOT EXISTS for articles, always-recreate
        # for feeds only when the drop above fired).
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id              TEXT PRIMARY KEY,
                url             TEXT UNIQUE,
                title           TEXT,
                title_en        TEXT,
                source_name     TEXT,
                source_lang     TEXT,
                source_tier     INTEGER,
                published_at    TEXT,
                fetched_at      TEXT,
                content_snippet TEXT,
                is_surveillance INTEGER DEFAULT 0,
                confidence      REAL,
                category        TEXT,
                country_code    TEXT,
                country_name    TEXT,
                region          TEXT,
                summary_en      TEXT,
                classified_at   TEXT,
                llm_provider    TEXT
            );

            CREATE TABLE IF NOT EXISTS feeds (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT,
                url             TEXT UNIQUE,
                language        TEXT,
                tier            INTEGER,
                feed_type       TEXT,
                country_focus   TEXT,
                active          INTEGER DEFAULT 1,
                last_fetched_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_articles_surveillance
                ON articles(is_surveillance);
            CREATE INDEX IF NOT EXISTS idx_articles_country
                ON articles(country_code);
            CREATE INDEX IF NOT EXISTS idx_articles_fetched
                ON articles(fetched_at);
        """)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.close()

    def list_tables(self) -> list[str]:
        """Return names of all user tables in the database."""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    def drop_all_tables(self) -> None:
        """Drop articles and feeds tables (for --clean reset)."""
        self._conn.executescript(
            "DROP TABLE IF EXISTS articles;"
            "DROP TABLE IF EXISTS feeds;"
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    #  Articles                                                            #
    # ------------------------------------------------------------------ #

    # Shared SQL and params for article upsert (DRY — CC3-M5)
    _UPSERT_ARTICLE_SQL = """INSERT INTO articles (
        id, url, title, title_en, source_name, source_lang,
        source_tier, published_at, fetched_at, content_snippet,
        is_surveillance, confidence, category, country_code,
        country_name, region, summary_en, classified_at, llm_provider
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        title           = COALESCE(excluded.title, articles.title),
        title_en        = COALESCE(excluded.title_en, articles.title_en),
        fetched_at      = excluded.fetched_at,
        published_at    = COALESCE(excluded.published_at, articles.published_at),
        content_snippet = COALESCE(excluded.content_snippet, articles.content_snippet),
        is_surveillance = CASE WHEN excluded.confidence IS NOT NULL THEN excluded.is_surveillance ELSE articles.is_surveillance END,
        confidence      = COALESCE(excluded.confidence, articles.confidence),
        category        = COALESCE(excluded.category, articles.category),
        country_code    = COALESCE(excluded.country_code, articles.country_code),
        country_name    = COALESCE(excluded.country_name, articles.country_name),
        region          = COALESCE(excluded.region, articles.region),
        summary_en      = COALESCE(excluded.summary_en, articles.summary_en),
        classified_at   = COALESCE(excluded.classified_at, articles.classified_at),
        llm_provider    = COALESCE(excluded.llm_provider, articles.llm_provider)
    """

    @staticmethod
    def _article_params(a: Article) -> tuple:
        """Build the parameter tuple for an article upsert."""
        return (
            a.id,
            a.url,
            a.title,
            a.title_en,
            a.source_name,
            a.source_lang,
            a.source_tier,
            a.published_at.isoformat() if a.published_at else None,
            a.fetched_at.isoformat() if a.fetched_at else None,
            a.content_snippet,
            int(a.is_surveillance),
            a.confidence,
            a.category,
            a.country_code,
            a.country_name,
            a.region,
            a.summary_en,
            a.classified_at.isoformat() if a.classified_at else None,
            a.llm_provider,
        )

    def upsert_article(self, a: Article) -> None:
        """Insert or update an article by primary key (id).

        On conflict the row is updated.  ``published_at`` and
        ``content_snippet`` use COALESCE so that a re-fetch without those
        fields does not blank out previously stored values.
        """
        self._conn.execute(self._UPSERT_ARTICLE_SQL, self._article_params(a))
        self._conn.commit()

    def upsert_articles_batch(self, articles: list[Article]) -> None:
        """Insert or update multiple articles in a single transaction.

        Wraps all upserts in one BEGIN/COMMIT for ~5-10x throughput vs
        per-article commits when processing batches.  Uses the connection
        as a context manager so that a mid-batch failure triggers an
        automatic rollback instead of leaving the connection in an
        undefined transaction state.
        """
        if not articles:
            return
        with self._conn:
            for a in articles:
                self._conn.execute(
                    self._UPSERT_ARTICLE_SQL, self._article_params(a),
                )

    def get_article(self, article_id: str) -> Optional[Article]:
        """Fetch a single article by its ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return self._row_to_article(row) if row else None

    def article_exists(self, article_id: str) -> bool:
        """Return True if an article with the given ID exists."""
        row = self._conn.execute(
            "SELECT 1 FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return row is not None

    def article_needs_classification(self, article_id: str) -> bool:
        """Return True if the article exists but has no LLM classification.

        Articles with ``confidence IS NULL`` and ``llm_provider != 'failed'``
        were stored during a failed classification attempt and should be
        re-classified on the next run. Articles marked ``llm_provider='failed'``
        have exhausted retries and will not be re-queued.
        """
        row = self._conn.execute(
            "SELECT 1 FROM articles WHERE id = ? AND confidence IS NULL "
            "AND (llm_provider IS NULL OR llm_provider != 'failed')",
            (article_id,),
        ).fetchone()
        return row is not None

    def count_articles(self) -> int:
        """Return the total number of articles in the database."""
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM articles"
        ).fetchone()
        return row["cnt"]

    def get_flagged_articles(
        self,
        country_code: Optional[str] = None,
        country_codes: Optional[list[str]] = None,
        category: Optional[str] = None,
        min_confidence: float = 0.6,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 200,
    ) -> list[Article]:
        """Return surveillance-flagged articles above the confidence threshold.

        Supports optional filters for country, category, and date range.
        ``country_codes`` filters to multiple countries (IN clause);
        ``country_code`` filters to a single country. If both are given,
        ``country_code`` takes precedence.
        Results are ordered by published_at descending (NULLs sort last).
        """
        query = "SELECT * FROM articles WHERE is_surveillance = 1 AND confidence >= ?"
        params: list = [min_confidence]

        if country_code:
            query += " AND country_code = ?"
            params.append(country_code)
        elif country_codes:
            placeholders = ",".join("?" for _ in country_codes)
            query += f" AND country_code IN ({placeholders})"
            params.extend(country_codes)
        if category:
            query += " AND category = ?"
            params.append(category)
        if date_from:
            query += " AND published_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND published_at <= ?"
            params.append(date_to)

        query += " ORDER BY published_at DESC NULLS LAST LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_article(r) for r in rows]

    def get_country_counts(
        self,
        min_confidence: float = 0.6,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, int]:
        """Return {country_code: count} for flagged articles above threshold."""
        query = (
            "SELECT country_code, COUNT(*) as cnt "
            "FROM articles "
            "WHERE is_surveillance = 1 AND country_code IS NOT NULL "
            "AND confidence >= ?"
        )
        params: list = [min_confidence]

        if category:
            query += " AND category = ?"
            params.append(category)
        if date_from:
            query += " AND published_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND published_at <= ?"
            params.append(date_to)

        query += " GROUP BY country_code"

        rows = self._conn.execute(query, params).fetchall()
        return {r["country_code"]: r["cnt"] for r in rows}

    # ------------------------------------------------------------------ #
    #  Feeds                                                               #
    # ------------------------------------------------------------------ #

    def upsert_feed(self, f: Feed) -> None:
        """Insert or update a feed by URL."""
        self._conn.execute(
            """INSERT INTO feeds (name, url, language, tier, feed_type, country_focus, active)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                   name          = excluded.name,
                   language      = excluded.language,
                   tier          = excluded.tier,
                   feed_type     = excluded.feed_type,
                   country_focus = excluded.country_focus,
                   active        = excluded.active
            """,
            (
                f.name,
                f.url,
                f.language,
                f.tier,
                f.feed_type,
                f.country_focus,
                int(f.active),
            ),
        )
        self._conn.commit()

    def get_active_feeds(self) -> list[Feed]:
        """Return all feeds where active = 1."""
        rows = self._conn.execute(
            "SELECT * FROM feeds WHERE active = 1"
        ).fetchall()
        return [
            Feed(
                name=r["name"],
                url=r["url"],
                language=r["language"] or "en",
                tier=r["tier"],
                feed_type=r["feed_type"],
                country_focus=r["country_focus"],
                active=bool(r["active"]),
                last_fetched_at=Database._parse_dt(r["last_fetched_at"]),
            )
            for r in rows
        ]

    def update_feed_fetched(self, feed_url: str) -> None:
        """Mark a feed as just-fetched with the current UTC timestamp."""
        self._conn.execute(
            "UPDATE feeds SET last_fetched_at = ? WHERE url = ?",
            (datetime.now(tz=timezone.utc).isoformat(), feed_url),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_dt(val: Optional[str]) -> Optional[datetime]:
        """Parse an ISO-format datetime string, returning None on failure.

        Naive datetimes (missing timezone) are assumed UTC.
        Logs a warning on malformed strings so they are distinguishable
        from legitimately null timestamps.
        """
        if val is None:
            return None
        try:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            logger.warning(
                "Malformed datetime string in DB: %r", val[:50],
            )
            return None

    @classmethod
    def _row_to_article(cls, row: sqlite3.Row) -> Article:
        """Convert a sqlite3.Row into an Article dataclass."""
        return Article(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            title_en=row["title_en"],
            source_name=row["source_name"],
            source_lang=row["source_lang"] or "en",
            source_tier=row["source_tier"],
            published_at=cls._parse_dt(row["published_at"]),
            fetched_at=cls._parse_dt(row["fetched_at"]),
            content_snippet=row["content_snippet"],
            is_surveillance=bool(row["is_surveillance"]),
            confidence=row["confidence"],
            category=row["category"],
            country_code=row["country_code"],
            country_name=row["country_name"],
            region=row["region"],
            summary_en=row["summary_en"],
            classified_at=cls._parse_dt(row["classified_at"]),
            llm_provider=row["llm_provider"],
        )
