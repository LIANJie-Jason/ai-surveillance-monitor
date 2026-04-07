#!/usr/bin/env python3
"""Seed the database with curated surveillance/censorship articles for demo."""

import os
import sys

# Ensure repo root is on sys.path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import sqlite3
from datetime import datetime, timezone

from scripts.init_db import init_database
from src.database import Database
from src.models import Article

logger = logging.getLogger(__name__)


def seed_database(
    db: Database,
    seed_path: str = "data/seed_articles.json",
) -> tuple[int, int, int]:
    """Load seed articles into database.

    Returns (loaded_count, total_count, already_exists_count) so callers
    can detect partial loads vs idempotent re-runs.
    """
    with open(seed_path, encoding="utf-8") as f:
        seed_data = json.load(f)

    total = len(seed_data)
    loaded = 0
    already_exists = 0
    skipped: list[str] = []
    for i, entry in enumerate(seed_data):
        try:
            canonical_url = Article._canonicalize_url(entry["url"])
            if not canonical_url:
                skipped.append(f"Article {i}: empty URL after canonicalization")
                continue
            pub_dt_raw = (
                datetime.fromisoformat(entry["published_at"])
                if entry.get("published_at")
                else None
            )
            # Ensure timezone-aware (naive datetimes assumed UTC)
            pub_dt = (
                pub_dt_raw.replace(tzinfo=timezone.utc)
                if pub_dt_raw is not None and pub_dt_raw.tzinfo is None
                else pub_dt_raw
            )
            article = Article(
                id=Article._hash_url(canonical_url),
                url=canonical_url,
                title=entry["title"],
                title_en=entry.get("title_en"),
                source_name=entry["source_name"],
                source_lang=entry.get("source_lang", "en"),
                source_tier=entry.get("source_tier", 2),
                published_at=pub_dt,
                fetched_at=datetime.now(tz=timezone.utc),
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
            if db.article_exists(article.id):
                already_exists += 1
                logger.debug("Article %d already exists — skipping seed", i)
                continue
            db.upsert_article(article)
            loaded += 1
        except (KeyError, ValueError, TypeError, sqlite3.Error) as exc:
            skipped.append(f"Article {i}: {exc}")
            logger.warning("Article %d: skipping due to error: %s", i, exc)

    if skipped:
        logger.error(
            "Partial seed: %d/%d loaded, %d already exist, %d skipped:\n  %s",
            loaded, total, already_exists, len(skipped), "\n  ".join(skipped),
        )

    return loaded, total, already_exists


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    db = init_database(
        db_path=os.path.join(repo_root, "data", "monitor.db"),
        feeds_config_path=os.path.join(repo_root, "config", "feeds.yaml"),
    )
    try:
        loaded, total, already_exists = seed_database(
            db, seed_path=os.path.join(repo_root, "data", "seed_articles.json"),
        )
    finally:
        db.close()
    if loaded + already_exists < total:
        logger.error(
            "PARTIAL SEED: only %d/%d articles loaded (%d already existed).",
            loaded, total, already_exists,
        )
        sys.exit(1)
    logger.info(
        "Seeded %d/%d articles (%d already existed).",
        loaded, total, already_exists,
    )


if __name__ == "__main__":
    main()
