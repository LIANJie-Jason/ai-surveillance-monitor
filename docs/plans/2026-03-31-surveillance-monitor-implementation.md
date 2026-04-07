# AI Surveillance News Monitor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-process news monitoring prototype (ingestion worker + Streamlit dashboard) that collects RSS feeds, classifies surveillance/censorship articles via LLM, and displays results on a dark command-center web dashboard.

**Architecture:** Ingestion worker fetches RSS feeds, deduplicates by URL hash, classifies via OpenAI (Anthropic fallback), and stores to SQLite. Streamlit dashboard reads the same SQLite and renders a deck.gl map with drill-down views including live video. Pre-seeded data ensures demo reliability.

**Tech Stack:** Python 3.11+, Streamlit, feedparser, openai, anthropic, pydeck, SQLite, deck.gl (embedded HTML/JS), PyYAML

**Design doc:** `docs/plans/2026-03-31-surveillance-monitor-design.md`

---

## Codex Review Changelog (2026-03-31)

All issues found by Codex evaluation have been addressed in this plan:

| # | Severity | Issue | Fix Applied |
|---|----------|-------|-------------|
| 1 | HIGH | `time.mktime` interprets UTC tuples as local time | Replaced with `calendar.timegm` |
| 2 | HIGH | URL dedup too naive (no UTM stripping, empty URL collision) | Added `_canonicalize_url()`, empty URL returns `None` |
| 3 | HIGH | `llm_provider` always "unknown" | `LLMClient.complete()` returns `(text, provider)` tuple |
| 4 | HIGH | SQLite concurrency: no `busy_timeout`, no read-only mode | Added `busy_timeout=5000`, `read_only` param for dashboard |
| 5 | HIGH | `upsert_article` doesn't update timestamps on conflict | Added `fetched_at`, `published_at`, `content_snippet` to ON CONFLICT |
| 6 | HIGH | Confidence threshold not enforced in DB queries | `get_flagged_articles` defaults `min_confidence=0.6` |
| 7 | HIGH | Drill-down region geocoding unreliable (free-form LLM text) | Added `config/regions.yaml` with aliases + lat/lng |
| 8 | HIGH | Streamlit `postMessage` click won't work in iframe | Replaced with native Streamlit buttons for country selection |
| 9 | MEDIUM | DB API missing date-range filter | Added `date_from`/`date_to` params to queries |
| 10 | MEDIUM | `get_country_counts` can't filter by category/date | Added filter params to `get_country_counts()` |
| 11 | MEDIUM | RSS ingestion needs User-Agent, timeout, bozo handling | Added to ingestion worker spec |
| 12 | MEDIUM | `VALID_CATEGORIES` defined but never enforced | Classifier validates and normalizes LLM output |
| 13 | MEDIUM | Task dependency: URL research should precede dashboard | Moved Task 16 before Task 14 in dependency graph |
| 14 | MEDIUM | Tier taxonomy inconsistent | Noted — will align during Task 4 implementation |
| 15 | LOW | streams.yaml eNCA `youtube_channel` wrong | Flagged for verification in Task 16 |
| 16 | LOW | `.gitignore` missing WAL sidecar files | Added `monitor.db-wal` and `monitor.db-shm` |
| 17 | LOW | Test count mismatch (said 7, was 8) | Corrected to 8 |

**Test gaps addressed (pass 1):**
- Added URL canonicalization tests, empty URL test, timezone correctness test
- Added LLM output validation test (clamping, category normalization)
- Added dual-provider failure test
- Fixed malformed JSON test to use non-empty article list

**Codex pass 2 fixes (2026-03-31):**
- WAL pragma no longer runs on read-only connections
- Dashboard now uses `Database(..., read_only=True)`
- `ClassificationResult` now has `llm_provider` field
- All classifier tests mock `complete()` as tuple `(text, provider)`
- Ingestion tests now patch `requests.get` + `feedparser.parse` (not just feedparser)
- Added `test_fetch_feed_handles_bozo()` test
- Seed data uses `Article._canonicalize_url()` and `published_at` as `fetched_at`
- Tier taxonomy given concrete rubric in Task 4
- Task 14 (URL research) moved before Task 15 (stream/webcam components) in plan body
- Fixed all test count mismatches (models: 8, LLM client: 3, database: 8)

**Codex pass 3 fixes (2026-03-31):**
- Fixed dependency graph to match renumbered tasks (14=URLs, 15=streams, 16=main app)
- Fixed eNCA streams.yaml task reference to point to Task 14
- Remaining MEDIUM items (classifier/ingestion prose-only) are by design — tests define contract, prose specifies validation logic, implementer fills in code

---

## Phase 1: Foundation (Database + Models + Config)

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `dashboard/__init__.py`
- Create: `dashboard/components/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Create requirements.txt**

```
streamlit>=1.38.0
streamlit-autorefresh>=1.0.1
feedparser>=6.0.11
openai>=1.40.0
anthropic>=0.34.0
pydeck>=0.9.0
requests>=2.32.0
pyyaml>=6.0.2
python-dotenv>=1.0.1
schedule>=1.2.2
pytest>=8.3.0
```

**Step 2: Create .env.example**

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

**Step 3: Create .gitignore**

```
data/monitor.db
data/monitor.db-wal
data/monitor.db-shm
.env
__pycache__/
*.pyc
.pytest_cache/
```

**Step 4: Create empty __init__.py files**

Empty files for `src/`, `dashboard/`, `dashboard/components/`, `tests/`.

**Step 5: Install dependencies**

Run: `pip install -r requirements.txt`

**Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore src/__init__.py dashboard/__init__.py dashboard/components/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding — deps, env template, gitignore"
```

---

### Task 2: Data models

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
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


def test_feed_from_dict():
    """Feed.from_dict should populate all fields from a YAML-style dict."""
    from src.models import Feed

    data = {
        "name": "Reuters World",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "language": "en",
        "tier": 1,
        "category": "wire",
        "country_focus": None,
    }
    feed = Feed.from_dict(data)
    assert feed.name == "Reuters World"
    assert feed.tier == 1
    assert feed.country_focus is None
    assert feed.active is True


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


def test_article_time_parsing_is_utc():
    """_parse_time_tuple should treat feedparser tuples as UTC, not local time."""
    from src.models import Article

    # 2026-03-31 12:00:00 UTC
    t = (2026, 3, 31, 12, 0, 0, 0, 90, 0)
    dt = Article._parse_time_tuple(t)
    assert dt is not None
    assert dt.hour == 12  # must be 12 UTC, not shifted by local timezone
    assert dt.tzinfo == timezone.utc


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
    )
    assert result.is_surveillance is True
    assert result.confidence == 0.92
    assert result.category == "facial_recognition"
    assert result.region == "Delhi"
```

**Step 2: Run test to verify it fails**

Run: `cd "/Users/lianjie/Desktop/NSF_AI survey/prototypes/AI surveillance news monitor" && python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models'`

**Step 3: Write implementation**

```python
# src/models.py
"""Data models for the surveillance news monitor."""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs


VALID_CATEGORIES = frozenset({
    "surveillance",
    "censorship",
    "facial_recognition",
    "internet_shutdown",
    "digital_rights",
    "social_media_control",
    "data_collection",
    "other",
})


@dataclass(frozen=True)
class Article:
    id: str
    url: str
    title: str
    source_name: str
    source_lang: str
    source_tier: int
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    content_snippet: Optional[str] = None
    title_en: Optional[str] = None
    is_surveillance: bool = False
    confidence: Optional[float] = None
    category: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region: Optional[str] = None
    summary_en: Optional[str] = None
    classified_at: Optional[datetime] = None
    llm_provider: Optional[str] = None

    # UTM and tracking params to strip during URL canonicalization
    _STRIP_PARAMS = frozenset({
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "source",
    })

    @classmethod
    def _canonicalize_url(cls, url: str) -> str:
        """Normalize URL: strip fragments, tracking params, trailing slashes."""
        if not url or not url.strip():
            return ""
        parsed = urlparse(url.strip())
        # Strip tracking params
        params = parse_qs(parsed.query, keep_blank_values=False)
        cleaned = {k: v for k, v in params.items() if k.lower() not in cls._STRIP_PARAMS}
        # Rebuild with sorted params (deterministic), no fragment
        query = urlencode(sorted(cleaned.items()), doseq=True) if cleaned else ""
        canonical = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path.rstrip("/"),
            parsed.params, query, "",  # no fragment
        ))
        return canonical

    @staticmethod
    def _hash_url(url: str) -> str:
        if not url:
            raise ValueError("Cannot hash empty URL — article has no link")
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_time_tuple(t) -> Optional[datetime]:
        if t is None:
            return None
        try:
            return datetime.utcfromtimestamp(calendar.timegm(t)).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def from_rss_entry(
        cls,
        entry: dict,
        source_name: str,
        source_lang: str,
        source_tier: int,
    ) -> Optional["Article"]:
        raw_url = entry.get("link", "")
        url = cls._canonicalize_url(raw_url)
        if not url:
            return None  # skip entries with no link
        return cls(
            id=cls._hash_url(url),
            url=url,
            title=entry.get("title", ""),
            source_name=source_name,
            source_lang=source_lang,
            source_tier=source_tier,
            published_at=cls._parse_time_tuple(entry.get("published_parsed")),
            fetched_at=datetime.now(tz=timezone.utc),
            content_snippet=(entry.get("summary", "") or "")[:500],
        )


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    language: str
    tier: int
    category: str
    country_focus: Optional[str] = None
    active: bool = True
    last_fetched_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> Feed:
        return cls(
            name=data["name"],
            url=data["url"],
            language=data["language"],
            tier=data["tier"],
            category=data["category"],
            country_focus=data.get("country_focus"),
            active=data.get("active", True),
        )


@dataclass(frozen=True)
class ClassificationResult:
    is_surveillance: bool
    confidence: float
    category: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region: Optional[str] = None
    llm_provider: Optional[str] = None  # "openai" or "anthropic" — set by classifier
```

**Step 4: Run test to verify it passes**

Run: `cd "/Users/lianjie/Desktop/NSF_AI survey/prototypes/AI surveillance news monitor" && python -m pytest tests/test_models.py -v`
Expected: 8 passed

**Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add Article, Feed, ClassificationResult data models"
```

---

### Task 3: Database layer

**Files:**
- Create: `src/database.py`
- Create: `tests/test_database.py`

**Step 1: Write the failing test**

```python
# tests/test_database.py
import pytest
import os
import tempfile
from datetime import datetime, timezone


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
    """Should return only articles where is_surveillance=True."""
    from src.models import Article

    flagged = Article(
        id="f1", url="https://a.com/1", title="Surveillance",
        source_name="BBC", source_lang="en", source_tier=1,
        is_surveillance=True, confidence=0.9, category="surveillance",
        country_code="IN", country_name="India",
    )
    normal = Article(
        id="n1", url="https://a.com/2", title="Sports",
        source_name="BBC", source_lang="en", source_tier=1,
    )
    db.upsert_article(flagged)
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
    """Should return article counts grouped by country."""
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

    counts = db.get_country_counts()
    assert counts["IN"] == 3
    assert counts["MY"] == 1


def test_insert_and_get_feeds(db):
    """Should insert feeds and retrieve active ones."""
    from src.models import Feed

    feed = Feed(
        name="Reuters", url="https://feeds.reuters.com/world",
        language="en", tier=1, category="wire",
    )
    db.upsert_feed(feed)

    feeds = db.get_active_feeds()
    assert len(feeds) == 1
    assert feeds[0].name == "Reuters"
```

**Step 2: Run test to verify it fails**

Run: `cd "/Users/lianjie/Desktop/NSF_AI survey/prototypes/AI surveillance news monitor" && python -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.database'`

**Step 3: Write implementation**

```python
# src/database.py
"""SQLite database operations for the surveillance news monitor."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from src.models import Article, Feed


class Database:
    def __init__(self, db_path: str = "data/monitor.db", read_only: bool = False):
        if read_only:
            uri = f"file:{db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        if not read_only:
            self._conn.execute("PRAGMA journal_mode=WAL")

    def init_tables(self) -> None:
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
                category        TEXT,
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
        self._conn.close()

    def list_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    # -- Articles --

    def upsert_article(self, a: Article) -> None:
        self._conn.execute(
            """INSERT INTO articles (
                id, url, title, title_en, source_name, source_lang,
                source_tier, published_at, fetched_at, content_snippet,
                is_surveillance, confidence, category, country_code,
                country_name, region, summary_en, classified_at, llm_provider
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, title_en=excluded.title_en,
                fetched_at=excluded.fetched_at,
                published_at=COALESCE(excluded.published_at, articles.published_at),
                content_snippet=COALESCE(excluded.content_snippet, articles.content_snippet),
                is_surveillance=excluded.is_surveillance,
                confidence=excluded.confidence, category=excluded.category,
                country_code=excluded.country_code,
                country_name=excluded.country_name, region=excluded.region,
                summary_en=excluded.summary_en,
                classified_at=excluded.classified_at,
                llm_provider=excluded.llm_provider
            """,
            (
                a.id, a.url, a.title, a.title_en, a.source_name, a.source_lang,
                a.source_tier,
                a.published_at.isoformat() if a.published_at else None,
                a.fetched_at.isoformat() if a.fetched_at else None,
                a.content_snippet,
                int(a.is_surveillance), a.confidence, a.category,
                a.country_code, a.country_name, a.region, a.summary_en,
                a.classified_at.isoformat() if a.classified_at else None,
                a.llm_provider,
            ),
        )
        self._conn.commit()

    def get_article(self, article_id: str) -> Optional[Article]:
        row = self._conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return self._row_to_article(row) if row else None

    def article_exists(self, article_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return row is not None

    def count_articles(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM articles").fetchone()
        return row["cnt"]

    def get_flagged_articles(
        self,
        country_code: Optional[str] = None,
        category: Optional[str] = None,
        min_confidence: float = 0.6,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 200,
    ) -> list[Article]:
        query = "SELECT * FROM articles WHERE is_surveillance = 1 AND confidence >= ?"
        params: list = [min_confidence]

        if country_code:
            query += " AND country_code = ?"
            params.append(country_code)
        if category:
            query += " AND category = ?"
            params.append(category)
        if date_from:
            query += " AND fetched_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND fetched_at <= ?"
            params.append(date_to)

        query += " ORDER BY fetched_at DESC LIMIT ?"
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
        query = """SELECT country_code, COUNT(*) as cnt
                   FROM articles
                   WHERE is_surveillance = 1 AND country_code IS NOT NULL
                   AND confidence >= ?"""
        params: list = [min_confidence]
        if category:
            query += " AND category = ?"
            params.append(category)
        if date_from:
            query += " AND fetched_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND fetched_at <= ?"
            params.append(date_to)
        query += " GROUP BY country_code"
        rows = self._conn.execute(query, params).fetchall()
        return {r["country_code"]: r["cnt"] for r in rows}

    # -- Feeds --

    def upsert_feed(self, f: Feed) -> None:
        self._conn.execute(
            """INSERT INTO feeds (name, url, language, tier, category, country_focus, active)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                   name=excluded.name, tier=excluded.tier,
                   category=excluded.category, active=excluded.active
            """,
            (f.name, f.url, f.language, f.tier, f.category, f.country_focus, int(f.active)),
        )
        self._conn.commit()

    def get_active_feeds(self) -> list[Feed]:
        rows = self._conn.execute(
            "SELECT * FROM feeds WHERE active = 1"
        ).fetchall()
        return [
            Feed(
                name=r["name"], url=r["url"], language=r["language"],
                tier=r["tier"], category=r["category"],
                country_focus=r["country_focus"], active=bool(r["active"]),
            )
            for r in rows
        ]

    def update_feed_fetched(self, feed_url: str) -> None:
        self._conn.execute(
            "UPDATE feeds SET last_fetched_at = ? WHERE url = ?",
            (datetime.now(tz=timezone.utc).isoformat(), feed_url),
        )
        self._conn.commit()

    # -- Helpers --

    @staticmethod
    def _parse_dt(val: Optional[str]) -> Optional[datetime]:
        if val is None:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    @classmethod
    def _row_to_article(cls, row: sqlite3.Row) -> Article:
        return Article(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            title_en=row["title_en"],
            source_name=row["source_name"],
            source_lang=row["source_lang"],
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
```

**Step 4: Run test to verify it passes**

Run: `cd "/Users/lianjie/Desktop/NSF_AI survey/prototypes/AI surveillance news monitor" && python -m pytest tests/test_database.py -v`
Expected: 8 passed

**Step 5: Commit**

```bash
git add src/database.py tests/test_database.py
git commit -m "feat: add SQLite database layer with upsert, query, and country counts"
```

---

### Task 4: Config files (feeds, streams, webcams, regions)

**Files:**
- Create: `config/feeds.yaml`
- Create: `config/streams.yaml`
- Create: `config/webcams.yaml`
- Create: `config/regions.yaml` — normalized region names + lat/lng for drill-down countries

**Step 1: Create feeds.yaml**

Populate with ~55-60 RSS feed entries. Each entry has: `name`, `url`, `language`, `tier`, `category`, `country_focus`. Research actual RSS URLs for each source at creation time.

**Tier rubric (aligned with schema):**
- `tier: 1` — Wire services (Reuters, AP, AFP) — highest reliability
- `tier: 2` — Major international outlets (BBC, Guardian, NYT, Al Jazeera, WaPo)
- `tier: 3` — Specialty/digital rights (EFF, Intercept, Citizen Lab, CPJ, Access Now, Wired Security)
- `tier: 4` — Regional sources (Malaysiakini, The Wire, Premium Times, Daily Maverick, non-English international)

This replaces the inconsistent "Tier 1-4" labels used in the design doc. The schema comment `1=wire, 2=major, 3=specialty, 4=regional` is canonical.

**Step 2: Create streams.yaml**

```yaml
# Live news streams (YouTube Live) per drill-down country
streams:
  IN:
    name: "NDTV 24x7"
    youtube_channel: "ndtv"
    embed_url: "https://www.youtube.com/embed/live_stream?channel=UCwm3CPHM4bQup8sYMgLYGOw"
  MY:
    name: "Astro Awani"
    youtube_channel: "astroawani"
    embed_url: "https://www.youtube.com/embed/live_stream?channel=UCk_UfPnSJVkdL0lFJElsnNQ"
  NG:
    name: "Channels TV"
    youtube_channel: "channelstv"
    embed_url: "https://www.youtube.com/embed/live_stream?channel=UCuEuVMJbqljmjNSn_RPOLNQ"
  ZA:
    name: "eNCA"
    youtube_channel: "eaborignaltv"  # PLACEHOLDER: replace with actual eNCA channel ID during Task 14 (URL research)
    embed_url: "https://www.youtube.com/embed/live_stream?channel=UCDGkUGMkOxuMe2HUfVFyGGA"
```

**Step 3: Create webcams.yaml**

```yaml
# City webcam embeds per drill-down country
webcams:
  IN:
    - city: "Delhi"
      embed_url: ""  # to be populated with actual webcam URL
      source: "SkylineWebcams"
    - city: "Mumbai"
      embed_url: ""
      source: "Webcamtaxi"
    - city: "Bangalore"
      embed_url: ""
      source: "SkylineWebcams"
    - city: "Chennai"
      embed_url: ""
      source: "Webcamtaxi"
  MY:
    - city: "Kuala Lumpur"
      embed_url: ""
      source: "SkylineWebcams"
    - city: "Penang"
      embed_url: ""
      source: "Webcamtaxi"
    - city: "Johor Bahru"
      embed_url: ""
      source: "Webcamtaxi"
  NG:
    - city: "Lagos"
      embed_url: ""
      source: "YouTube"
    - city: "Abuja"
      embed_url: ""
      source: "YouTube"
  ZA:
    - city: "Cape Town"
      embed_url: ""
      source: "SkylineWebcams"
    - city: "Johannesburg"
      embed_url: ""
      source: "EarthCam"
    - city: "Durban"
      embed_url: ""
      source: "SkylineWebcams"
```

Note: `embed_url` fields will be populated with actual working URLs during implementation. Research each city's available webcam embeds at that time.

**Step 4: Commit**

```bash
git add config/
git commit -m "feat: add feeds, streams, and webcams YAML config"
```

---

### Task 5: DB init and seed scripts

**Files:**
- Create: `scripts/init_db.py`
- Create: `scripts/seed_data.py`
- Create: `data/seed_articles.json`

**Step 1: Create init_db.py**

```python
#!/usr/bin/env python3
"""Initialize the SQLite database and load feeds from config."""

import os
import yaml
from src.database import Database
from src.models import Feed


def main():
    os.makedirs("data", exist_ok=True)
    db = Database("data/monitor.db")
    db.init_tables()

    with open("config/feeds.yaml") as f:
        feeds_config = yaml.safe_load(f)

    for entry in feeds_config.get("feeds", []):
        feed = Feed.from_dict(entry)
        db.upsert_feed(feed)

    feeds = db.get_active_feeds()
    print(f"Database initialized. {len(feeds)} feeds loaded.")
    db.close()


if __name__ == "__main__":
    main()
```

**Step 2: Create seed_data.py**

```python
#!/usr/bin/env python3
"""Seed the database with curated surveillance/censorship articles for demo."""

import json
from datetime import datetime, timezone
from src.database import Database
from src.models import Article


def main():
    db = Database("data/monitor.db")

    with open("data/seed_articles.json") as f:
        seed_data = json.load(f)

    count = 0
    for entry in seed_data:
        # Use same URL canonicalization as live ingestion to prevent ID mismatches
        canonical_url = Article._canonicalize_url(entry["url"])
        if not canonical_url:
            continue
        pub_dt = datetime.fromisoformat(entry["published_at"]) if entry.get("published_at") else None
        article = Article(
            id=Article._hash_url(canonical_url),
            url=canonical_url,
            title=entry["title"],
            title_en=entry.get("title_en"),
            source_name=entry["source_name"],
            source_lang=entry.get("source_lang", "en"),
            source_tier=entry.get("source_tier", 2),
            published_at=pub_dt,
            fetched_at=pub_dt or datetime.now(tz=timezone.utc),  # use published_at as fetched_at for seeds
            content_snippet=entry.get("content_snippet"),
            is_surveillance=True,
            confidence=entry.get("confidence", 0.85),
            category=entry.get("category", "surveillance"),
            country_code=entry.get("country_code"),
            country_name=entry.get("country_name"),
            region=entry.get("region"),
            summary_en=entry.get("summary_en"),
            classified_at=datetime.now(tz=timezone.utc),
            llm_provider="seed",
        )
        db.upsert_article(article)
        count += 1

    print(f"Seeded {count} articles.")
    db.close()


if __name__ == "__main__":
    main()
```

**Step 3: Create seed_articles.json**

Create `data/seed_articles.json` with ~200 curated entries. Research real surveillance/censorship news articles across all four drill-down countries plus global stories. Each entry needs: `url`, `title`, `source_name`, `published_at`, `country_code`, `country_name`, `category`, `confidence`, `summary_en`, and optionally `region` for MY/NG/IN/ZA.

Distribute across countries: ~40 India, ~30 Malaysia, ~25 Nigeria, ~25 South Africa, ~80 global (China, Russia, Iran, USA, UK, etc.).

**Step 4: Run init + seed**

```bash
python scripts/init_db.py
python scripts/seed_data.py
```

**Step 5: Commit**

```bash
git add scripts/ data/seed_articles.json
git commit -m "feat: add DB init script and seed data (200 curated articles)"
```

---

## Phase 2: Ingestion Pipeline (RSS + LLM)

### Task 6: LLM client with fallback

**Files:**
- Create: `src/llm_client.py`
- Create: `tests/test_llm_client.py`

**Step 1: Write the failing test**

```python
# tests/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock


def test_llm_client_tries_openai_first():
    """Should call OpenAI first, return result and provider without trying Anthropic."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"result": "test"}'

    with patch.object(client._openai.chat.completions, "create", return_value=mock_response) as mock_oai:
        text, provider = client.complete("Test prompt", model_primary="gpt-4.1-mini")
        mock_oai.assert_called_once()
        assert text == '{"result": "test"}'
        assert provider == "openai"


def test_llm_client_falls_back_to_anthropic():
    """Should fall back to Anthropic when OpenAI fails, return anthropic as provider."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = '{"fallback": true}'

    with patch.object(
        client._openai.chat.completions, "create", side_effect=Exception("OpenAI down")
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response
    ) as mock_ant:
        text, provider = client.complete(
            "Test prompt",
            model_primary="gpt-4.1-mini",
            model_fallback="claude-haiku-4-5-20251001",
        )
        mock_ant.assert_called_once()
        assert text == '{"fallback": true}'
        assert provider == "anthropic"


def test_llm_client_both_providers_fail():
    """Should raise when both OpenAI and Anthropic fail."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    with patch.object(
        client._openai.chat.completions, "create", side_effect=Exception("OpenAI down")
    ), patch.object(
        client._anthropic.messages, "create", side_effect=Exception("Anthropic down")
    ):
        with pytest.raises(Exception):
            client.complete("Test prompt")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/llm_client.py
"""LLM client with OpenAI primary / Anthropic fallback."""

from __future__ import annotations

import openai
import anthropic


class LLMClient:
    def __init__(self, openai_key: str, anthropic_key: str):
        self._openai = openai.OpenAI(api_key=openai_key)
        self._anthropic = anthropic.Anthropic(api_key=anthropic_key)

    def complete(
        self,
        prompt: str,
        model_primary: str = "gpt-4.1-mini",
        model_fallback: str = "claude-haiku-4-5-20251001",
        system: str = "",
        max_tokens: int = 2048,
    ) -> tuple[str, str]:
        """Returns (response_text, provider_used). Provider is 'openai' or 'anthropic'."""
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = self._openai.chat.completions.create(
                model=model_primary,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return (response.choices[0].message.content, "openai")
        except Exception:
            response = self._anthropic.messages.create(
                model=model_fallback,
                max_tokens=max_tokens,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
            )
            return (response.content[0].text, "anthropic")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/llm_client.py tests/test_llm_client.py
git commit -m "feat: add LLM client with OpenAI primary / Anthropic fallback"
```

---

### Task 7: Classifier

**Files:**
- Create: `src/classifier.py`
- Create: `tests/test_classifier.py`

**Step 1: Write the failing test**

```python
# tests/test_classifier.py
import pytest
from unittest.mock import MagicMock
import json


def test_classify_batch_parses_llm_response():
    """Should send batch of articles and parse JSON classification results."""
    from src.classifier import Classifier
    from src.models import Article

    mock_client = MagicMock()
    mock_client.complete.return_value = (json.dumps({
        "articles": [
            {
                "index": 0,
                "is_surveillance": True,
                "confidence": 0.92,
                "category": "facial_recognition",
                "country_code": "IN",
                "country_name": "India",
                "region": "Delhi",
            },
            {
                "index": 1,
                "is_surveillance": False,
                "confidence": 0.15,
                "category": "other",
                "country_code": "US",
                "country_name": "United States",
                "region": None,
            },
        ]
    }), "openai")

    classifier = Classifier(mock_client)
    articles = [
        Article(id="a1", url="https://a.com/1", title="Delhi facial recognition",
                source_name="Wire", source_lang="en", source_tier=3,
                content_snippet="The government deployed..."),
        Article(id="a2", url="https://a.com/2", title="US tech earnings rise",
                source_name="Reuters", source_lang="en", source_tier=1,
                content_snippet="Apple reported record..."),
    ]

    results = classifier.classify_batch(articles)
    assert len(results) == 2
    assert results[0].is_surveillance is True
    assert results[0].confidence == 0.92
    assert results[0].country_code == "IN"
    assert results[0].llm_provider == "openai"
    assert results[1].is_surveillance is False


def test_classify_batch_handles_malformed_json():
    """Should return empty results on malformed LLM response."""
    from src.classifier import Classifier
    from src.models import Article

    mock_client = MagicMock()
    mock_client.complete.return_value = ("not valid json {", "openai")

    classifier = Classifier(mock_client)
    articles = [
        Article(id="a1", url="https://a.com/1", title="Test",
                source_name="BBC", source_lang="en", source_tier=1),
    ]
    results = classifier.classify_batch(articles)
    assert results == []


def test_classify_batch_validates_output():
    """Should clamp confidence, normalize category, validate country code."""
    from src.classifier import Classifier
    from src.models import Article

    mock_client = MagicMock()
    mock_client.complete.return_value = (json.dumps({
        "articles": [{
            "index": 0,
            "is_surveillance": True,
            "confidence": 1.5,  # out of range — should clamp to 1.0
            "category": "INVALID_CATEGORY",  # should default to "other"
            "country_code": "india",  # should normalize to "IN" or None
            "country_name": "India",
            "region": None,
        }]
    }), "openai")

    classifier = Classifier(mock_client)
    articles = [
        Article(id="a1", url="https://a.com/1", title="Test",
                source_name="BBC", source_lang="en", source_tier=1),
    ]
    results = classifier.classify_batch(articles)
    assert len(results) == 1
    assert results[0].confidence == 1.0  # clamped
    assert results[0].category == "other"  # normalized
```

**Step 2: Run test, verify fails, write implementation, run test, commit.**

Implementation: `Classifier` class with `classify_batch(articles: list[Article]) -> list[ClassificationResult]`. Builds a prompt with indexed article titles+snippets, calls `llm_client.complete()`, parses the JSON response into `ClassificationResult` objects.

**LLM output validation (addresses Codex finding):**
- Validate `category` against `VALID_CATEGORIES`; default to `"other"` if invalid
- Clamp `confidence` to `[0.0, 1.0]` range
- Validate `country_code` is 2-char uppercase; set to `None` if invalid
- Normalize `region` against `config/regions.yaml` aliases for drill-down countries (fuzzy match)
- Only set `is_surveillance=True` when confidence >= 0.6 (threshold enforcement)
- Handle missing/duplicate/out-of-order indexes gracefully

**Step 3: Commit**

```bash
git add src/classifier.py tests/test_classifier.py
git commit -m "feat: add LLM classifier with batch classification"
```

---

### Task 8: Summarizer

**Files:**
- Create: `src/summarizer.py`
- Create: `tests/test_summarizer.py`

Follows same TDD pattern. `Summarizer` class with `summarize(article: Article) -> tuple[str, Optional[str]]` returning `(summary_en, title_en)`. Only called for flagged articles. Translates non-English titles. Uses gpt-4.1 primary / claude-sonnet-4-6 fallback.

**Commit:** `feat: add LLM summarizer with translation for non-English articles`

---

### Task 9: RSS ingestion worker

**Files:**
- Create: `src/ingestion.py`
- Create: `tests/test_ingestion.py`

**Step 1: Write the failing test**

```python
# tests/test_ingestion.py
import pytest
from unittest.mock import MagicMock, patch


def test_fetch_feed_returns_articles():
    """Should fetch via requests, parse with feedparser, and return Article objects."""
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
        from src.models import Feed
        feed = Feed(name="Test", url="https://example.com/rss", language="en", tier=1, category="wire")
        articles = worker.fetch_feed(feed)
        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        # Verify User-Agent was set
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert "timeout" in call_kwargs.kwargs or call_kwargs[1].get("timeout")


def test_fetch_feed_skips_duplicates():
    """Should skip articles that already exist in the database."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = True  # already exists
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
        from src.models import Feed
        feed = Feed(name="Test", url="https://example.com/rss", language="en", tier=1, category="wire")
        articles = worker.fetch_feed(feed)
        assert len(articles) == 0


def test_fetch_feed_handles_bozo():
    """Should log warning but still process valid entries from bozo feeds."""
    from src.ingestion import IngestionWorker

    mock_db = MagicMock()
    mock_db.article_exists.return_value = False
    worker = IngestionWorker(db=mock_db, classifier=MagicMock(), summarizer=MagicMock())

    fake_feed_data = MagicMock()
    fake_feed_data.bozo = True  # malformed feed
    fake_feed_data.bozo_exception = Exception("not well-formed")
    fake_feed_data.entries = [
        {"title": "Still Valid", "link": "https://example.com/valid", "summary": "ok"},
    ]
    mock_response = MagicMock()
    mock_response.content = b"<rss>...</rss>"
    mock_response.status_code = 200

    with patch("src.ingestion.requests.get", return_value=mock_response), \
         patch("src.ingestion.feedparser.parse", return_value=fake_feed_data):
        from src.models import Feed
        feed = Feed(name="Test", url="https://example.com/rss", language="en", tier=1, category="wire")
        articles = worker.fetch_feed(feed)
        assert len(articles) == 1  # still processes valid entries
```

**Step 2: Write implementation**

`IngestionWorker` class with:
- `fetch_feed(feed) -> list[Article]` — parse RSS, deduplicate, return new articles
  - Set `User-Agent` header via `requests` (some feeds block default feedparser UA)
  - Use `requests.get(url, timeout=15)` then `feedparser.parse(response.content)`
  - Check `feed.bozo` flag — log warning but still process valid entries
  - Skip entries where `Article.from_rss_entry()` returns `None` (no link)
- `process_batch(articles) -> None` — classify batch, summarize flagged, store all
- `run_once() -> None` — fetch all active feeds, process in batches of 10
- `run_scheduled(interval_minutes=30)` — loop with `schedule` library

**Step 3: Add `__main__` entry point**

```python
# At bottom of src/ingestion.py
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    # ... init db, llm_client, classifier, summarizer, worker
    # worker.run_once() or worker.run_scheduled()
```

**Step 4: Commit**

```bash
git add src/ingestion.py tests/test_ingestion.py
git commit -m "feat: add RSS ingestion worker with dedup, classify, summarize pipeline"
```

---

## Phase 3: Dashboard

### Task 10: Dark theme CSS

**Files:**
- Create: `dashboard/styles/dark_theme.css`

Command-center dark theme. Background `#0d1117`, card backgrounds `#161b22`, borders `#30363d`, text `#e6edf3`, accent red/orange for confidence indicators. Style the Streamlit sidebar, metric cards, and scrollable containers.

**Commit:** `feat: add dark command-center CSS theme`

---

### Task 11: Global map component

**Files:**
- Create: `dashboard/static/deck_map.html`
- Create: `dashboard/components/map_global.py`

**deck_map.html:** Self-contained HTML/JS file using deck.gl CDN. Renders a dark basemap (Carto Dark Matter, no API key needed) with a ScatterplotLayer. Receives data as a JSON blob injected by Streamlit. Markers sized by article count, colored yellow-to-red. Hover tooltips show country name + count. **Important:** Set explicit `height` parameter in `st.components.html(height=500)` to prevent iframe cropping.

**Map click interaction:** Since `st.components.html()` runs in an iframe and cannot directly set `st.session_state`, use a **Streamlit selectbox/radio** below the map for country selection instead of map clicks. The map is purely visual — country selection is via Streamlit native widgets. For drill-down countries (MY/NG/IN/ZA), show prominent buttons that set `st.session_state.selected_country`.

**map_global.py:** Streamlit component that queries `db.get_country_counts()`, maps country codes to lat/lng coordinates (hardcoded lookup table of ~200 countries), and renders the deck.gl map via `st.components.html(height=500)`. Below the map, renders country selection buttons for drill-down navigation.

**Commit:** `feat: add deck.gl global map with country markers`

---

### Task 12: Drill-down map component

**Files:**
- Create: `dashboard/components/map_drilldown.py`

Similar to global map but zoomed to a specific country. Shows regional markers (if available) within that country. Only for MY, NG, IN, ZA.

**Region normalization:** LLM-generated `region` values are free-form text ("Delhi" vs "New Delhi" vs "NCT Delhi"). To map these reliably, use a `config/regions.yaml` lookup that maps normalized region names to lat/lng for each drill-down country. The classifier should normalize LLM region output against this list (fuzzy match). Example:

```yaml
# config/regions.yaml
regions:
  IN:
    - name: "Delhi"
      aliases: ["New Delhi", "NCT Delhi", "Delhi NCR"]
      lat: 28.6139
      lng: 77.2090
    - name: "Mumbai"
      aliases: ["Bombay"]
      lat: 19.0760
      lng: 72.8777
    # ... more regions
  MY:
    - name: "Kuala Lumpur"
      aliases: ["KL"]
      lat: 3.1390
      lng: 101.6869
    # ... more regions
  # NG, ZA similarly
```

The drill-down map reads from `regions.yaml` to place markers at known coordinates, aggregating articles whose `region` field matches any alias.

**Commit:** `feat: add country drill-down map component with region geocoding`

---

### Task 13: News feed and article detail components

**Files:**
- Create: `dashboard/components/news_feed.py`
- Create: `dashboard/components/article_detail.py`

**news_feed.py:** Scrollable card list of flagged articles. Each card shows confidence badge (colored), country, headline, source, time ago. Clicking a card stores selected article ID in `st.session_state`.

**article_detail.py:** Right panel showing full detail for selected article: EN headline, original headline, AI summary, confidence, category, source tier, published date, link to original.

**Commit:** `feat: add news feed and article detail dashboard components`

---

### Task 14: Research and populate actual URLs

> **Moved here from Phase 4** — stream/webcam components need real URLs to work.

**Files:**
- Modify: `config/feeds.yaml` — verify all RSS URLs work
- Modify: `config/streams.yaml` — find working YouTube Live embed URLs
- Modify: `config/webcams.yaml` — find working webcam embed URLs

Research each URL, test in browser. Remove broken feeds. Fix eNCA youtube_channel. This is a manual research task.

**Commit:** `fix: populate and verify all feed, stream, and webcam URLs`

---

### Task 15: Live stream and webcam components

**Files:**
- Create: `dashboard/components/live_stream.py`
- Create: `dashboard/components/webcams.py`

**live_stream.py:** Reads `config/streams.yaml`, embeds YouTube live iframe for the selected country via `st.components.html(height=400)`.

**webcams.py:** Reads `config/webcams.yaml`, renders 2x2 grid of webcam iframes with city labels and "LIVE" badges via `st.components.html()`. Gracefully show "No live feed available" placeholder if embed_url is empty.

**Commit:** `feat: add live stream and webcam embed components`

---

### Task 16: Main dashboard app

**Files:**
- Create: `dashboard/app.py`

**Step 1: Wire everything together**

```python
# dashboard/app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from src.database import Database

st.set_page_config(
    page_title="AI Surveillance Monitor",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load dark theme CSS
with open("dashboard/styles/dark_theme.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Auto-refresh every 60s
st_autorefresh(interval=60_000, key="refresh")

# Init DB connection (read-only — ingestion writes, dashboard reads)
db = Database("data/monitor.db", read_only=True)

# State management
if "selected_country" not in st.session_state:
    st.session_state.selected_country = None
if "selected_article_id" not in st.session_state:
    st.session_state.selected_article_id = None

# ... route to global view or drill-down view based on session state
# ... render filter bar, map, news feed, article detail
# ... if drill-down: render regional map + live stream + webcams
```

**Step 2: Add filter bar** — country dropdown, category dropdown, date range, confidence slider. Pass filter values to `db.get_flagged_articles()` and `db.get_country_counts()`.

**Step 3: Global view** — map + news feed + article detail in columns. Country selection via Streamlit buttons below the map (not via iframe postMessage).

**Step 4: Drill-down view** — back button, regional map + live stream + webcams in columns, country-filtered news feed below.

**Step 5: Test manually**

```bash
streamlit run dashboard/app.py
```

**Step 6: Commit**

```bash
git add dashboard/
git commit -m "feat: wire up Streamlit dashboard with global and drill-down views"
```

---

## Phase 4: Polish & Demo-Ready

### Task 17: Curate seed dataset

**Files:**
- Modify: `data/seed_articles.json`

Research ~200 real surveillance/censorship news articles. For each: find URL, write summary, assign category, country, confidence. Distribute across countries and categories.

**Commit:** `feat: curate 200 seed articles for demo dataset`

---

### Task 18: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

Update with build/run commands, architecture overview, and key file descriptions now that the codebase exists.

**Commit:** `docs: update CLAUDE.md with build commands and architecture`

---

### Task 19: End-to-end smoke test

Run the full pipeline:
1. `python scripts/init_db.py` — verify DB + feeds created
2. `python scripts/seed_data.py` — verify seed data loaded
3. `streamlit run dashboard/app.py` — verify dashboard renders
4. Verify: map shows markers, news feed shows cards, drill-down works, live streams load
5. (Optional) `python -m src.ingestion --once` — verify live ingestion works with real API keys

**Commit:** `test: verify end-to-end demo flow`

---

## Task Dependency Graph

```
Phase 1 (Foundation):
  Task 1 (scaffold) -> Task 2 (models) -> Task 3 (database) -> Task 4 (config) -> Task 5 (scripts)

Phase 2 (Ingestion):
  Task 3 + Task 2 -> Task 6 (llm_client) -> Task 7 (classifier) -> Task 8 (summarizer) -> Task 9 (ingestion)

Phase 3 (Dashboard):
  Task 3 -> Task 10 (CSS) -> Task 11 (global map) -> Task 12 (drill-down map)
  Task 3 -> Task 13 (news feed + detail)
  Task 4 -> Task 14 (populate URLs) -> Task 15 (streams + webcams)
  Tasks 10-13, 15 -> Task 16 (main app)

Phase 4 (Polish):
  Task 5 -> Task 17 (seed data)
  Task 16 -> Tasks 18, 19

Parallel opportunities:
  - Tasks 10-13 can run in parallel (independent dashboard components)
  - Tasks 6-8 can be developed while dashboard work proceeds
  - Task 14 (URL research) runs before Task 15 (stream/webcam components need real URLs)
  - Task 17 can run in parallel with dashboard work
```
