#!/usr/bin/env python3
"""Initialize the SQLite database and load feeds from config."""

import argparse
import os
import sys

# Ensure repo root is on sys.path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from src.database import Database
from src.models import Feed


def init_database(
    db_path: str = "data/monitor.db",
    feeds_config_path: str = "config/feeds.yaml",
    clean: bool = False,
) -> Database:
    """Create database, init tables, and load feeds. Returns the Database instance.

    When ``clean=True``, any existing ``articles`` and ``feeds`` tables are
    dropped before the schema is recreated. This purges stale or fabricated
    rows left over from earlier runs (see H10 in ``docs/BUGLOG.md``) so that
    a subsequent ``seed_data`` run starts from a clean slate. Safe to call on
    a path with no existing DB — ``DROP TABLE IF EXISTS`` is a no-op in that
    case.
    """
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    db = Database(db_path)

    if clean:
        db.drop_all_tables()

    db.init_tables()

    with open(feeds_config_path, encoding="utf-8") as f:
        feeds_config = yaml.safe_load(f)

    for entry in feeds_config.get("feeds", []):
        feed = Feed.from_dict(entry)
        db.upsert_feed(feed)

    return db


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(
        description="Initialize the surveillance monitor SQLite database.",
    )
    parser.add_argument(
        "--db",
        default=os.path.join(repo_root, "data", "monitor.db"),
        help="Path to the SQLite database file (default: data/monitor.db)",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(repo_root, "config", "feeds.yaml"),
        help="Path to feeds YAML config (default: config/feeds.yaml)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help=(
            "Drop the existing articles and feeds tables before re-creating "
            "the schema. Use this to purge stale demo data before re-seeding."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    if args.clean:
        print(
            f"[--clean] Wiping articles and feeds tables in {args.db} "
            "before reload."
        )
    db = init_database(
        db_path=args.db,
        feeds_config_path=args.config,
        clean=args.clean,
    )
    feeds = db.get_active_feeds()
    print(f"Database initialized. {len(feeds)} feeds loaded.")
    db.close()


if __name__ == "__main__":
    main()
