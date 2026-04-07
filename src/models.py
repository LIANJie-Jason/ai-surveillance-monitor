"""Data models for the surveillance news monitor."""

from __future__ import annotations

import calendar
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from src.url_utils import is_private_or_reserved_host

logger = logging.getLogger(__name__)

# BCP 47 language tag (simplified): primary subtag + optional script/region/variant
_BCP47_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


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

_STRIP_PARAMS = frozenset({
    # Tracking params only. "source" is NOT stripped because some news sites
    # use it as a content discriminator (e.g. ?source=africa vs ?source=asia);
    # stripping would merge distinct articles into one SHA-256 bucket.
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref",
})


@dataclass(frozen=True)
class Article:
    """An RSS article with optional classification metadata."""

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
    classify_attempts: int = 0

    @classmethod
    def _canonicalize_url(cls, url: str) -> str:
        """Normalize URL: strip fragments, tracking params, trailing slashes."""
        if not url or not url.strip():
            return ""
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        if not parsed.hostname:
            return ""
        params = parse_qs(parsed.query, keep_blank_values=False)
        cleaned = {
            k: v for k, v in params.items()
            if k.lower() not in _STRIP_PARAMS
        }
        query = urlencode(sorted(cleaned.items()), doseq=True) if cleaned else ""
        canonical = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            query,
            "",  # drop fragment
        ))
        return canonical

    @staticmethod
    def _hash_url(url: str) -> str:
        """Produce a deterministic SHA-256 hex digest from a URL."""
        if not url:
            raise ValueError("Cannot hash empty URL — article has no link")
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_time_tuple(t) -> Optional[datetime]:
        """Convert a feedparser time tuple to a UTC datetime, or None.

        feedparser tuples are always UTC (struct_time in GMT).
        We use calendar.timegm (inverse of time.gmtime) so no local-
        timezone shift is applied. Logs a warning when a non-None input
        fails to parse so operators can detect malformed feed dates.
        """
        if t is None:
            return None
        try:
            ts = calendar.timegm(t)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            logger.warning("Unparseable RSS time tuple %r: %s", t, exc)
            return None

    @classmethod
    def from_rss_entry(
        cls,
        entry: dict,
        source_name: str,
        source_lang: str,
        source_tier: int,
    ) -> Optional[Article]:
        """Construct an Article from a feedparser entry dict.

        Returns None when the entry has no usable link.
        """
        raw_url = entry.get("link", "")
        url = cls._canonicalize_url(raw_url)
        if not url:
            return None
        return cls(
            id=cls._hash_url(url),
            url=url,
            title=entry.get("title") or "",
            source_name=source_name,
            source_lang=source_lang,
            source_tier=source_tier,
            published_at=cls._parse_time_tuple(
                entry.get("published_parsed") or entry.get("updated_parsed")
            ),
            fetched_at=datetime.now(tz=timezone.utc),
            content_snippet=(entry.get("summary", "") or "")[:500],
        )


@dataclass(frozen=True)
class Feed:
    """An RSS/Atom feed source definition.

    Note: ``feed_type`` is a descriptive label classifying the *source* of a
    feed. Actual values used in ``config/feeds.yaml`` include ``wire``,
    ``major``, ``international``, ``regional``, ``specialty``,
    ``digital_rights``, ``human_rights``, ``press_freedom``, ``cybersecurity``,
    ``democracy_rights``, ``tech_global``, ``tech_policy``, ``law_security``,
    ``investigative``, and ``citizen_media``. The field is free-form (no
    enumeration is enforced) so operators can add new feed categories without a
    code change.

    This is distinct from ``Article.category``, which classifies the *topic* of
    a story (e.g. "surveillance", "facial_recognition"). Earlier versions of
    this code used ``category`` for both concepts; that collision is resolved
    by M17 in BUGLOG.md.
    """

    name: str
    url: str
    language: str
    tier: int
    feed_type: str
    country_focus: Optional[str] = None
    active: bool = True
    last_fetched_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> Feed:
        """Construct a Feed from a YAML-style config dict.

        Accepts either ``feed_type`` (new canonical key) or ``category``
        (legacy key) so older configs continue to load during the migration
        window. New configs should use ``feed_type``.
        """
        url = data["url"]
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"Feed URL must use http/https: {url!r}")
        if not parsed.hostname:
            raise ValueError(f"Feed URL has no hostname: {url!r}")
        if is_private_or_reserved_host(parsed.hostname):
            raise ValueError(f"Feed URL resolves to a private/reserved host: {url!r}")
        language = data["language"]
        if not isinstance(language, str) or not _BCP47_RE.match(language):
            raise ValueError(
                f"Feed language must be a BCP 47 tag (e.g. 'en', 'zh-Hant'): {language!r}"
            )
        # Prefer feed_type; fall back to legacy `category` key for back-compat
        if "feed_type" in data:
            feed_type = data["feed_type"]
        elif "category" in data:
            logger.warning(
                "Feed %r uses legacy 'category' key for feed_type; "
                "rename to 'feed_type' in config",
                data.get("name", "<unnamed>"),
            )
            feed_type = data["category"]
        else:
            raise KeyError("Feed config missing 'feed_type' key")
        tier = data["tier"]
        if not isinstance(tier, int) or tier < 1 or tier > 4:
            raise ValueError(
                f"Feed tier must be an integer 1-4, got {tier!r}"
            )
        return cls(
            name=data["name"],
            url=url,
            language=language,
            tier=tier,
            feed_type=feed_type,
            country_focus=data.get("country_focus"),
            active=data.get("active", True),
        )


@dataclass(frozen=True)
class ClassificationResult:
    """LLM classification output for an article."""

    is_surveillance: bool
    confidence: Optional[float]
    category: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region: Optional[str] = None
    llm_provider: Optional[str] = None
