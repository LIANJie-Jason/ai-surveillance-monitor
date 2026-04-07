#!/usr/bin/env python3
"""Batch-verify every feed in config/feeds.yaml against its live URL.

For each feed this script performs an HTTP GET (mirroring the ingestion
worker's ``allow_redirects=False`` so results reflect real ingestion
behaviour), parses the body with ``feedparser``, and classifies the result:

    OK                — HTTP 200, valid RSS/Atom, ≥1 entry
    OK_EMPTY          — HTTP 200, valid RSS/Atom, zero entries
    REDIRECT          — HTTP 3xx (ingestion would skip; fix URL in config)
    HTTP_ERROR        — HTTP 4xx/5xx
    NETWORK_ERROR     — timeout, DNS failure, connection refused, TLS error
    BOZO_NO_ENTRIES   — body parsed but feedparser flagged bozo and no entries
    BOZO_HAS_ENTRIES  — body parsed with bozo warning but entries are present

Exit code 0 iff every *active* feed returns OK, OK_EMPTY, or BOZO_HAS_ENTRIES.
Otherwise exit code 1. Feeds with ``active: false`` are skipped by default;
use ``--include-inactive`` to check them too (they will affect the exit code).

See H14 in docs/BUGLOG.md for context.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

# Ensure repo root on path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feedparser  # noqa: E402  (after sys.path manipulation)
import requests  # noqa: E402
import yaml  # noqa: E402

_USER_AGENT = "AI-Surveillance-Monitor/1.0 (+research; RSS reader)"
_REQUEST_TIMEOUT = (5, 10)  # (connect_timeout, read_timeout)
_MAX_WORKERS = 8

# Statuses that count as "working" from the ingestion worker's point of view.
_HEALTHY_STATUSES = frozenset({"OK", "OK_EMPTY", "BOZO_HAS_ENTRIES"})


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of verifying a single feed URL."""

    name: str
    url: str
    status: str
    detail: str
    entry_count: int = 0
    redirect_target: Optional[str] = None


def verify_feed(
    name: str,
    url: str,
    session: Optional[requests.Session] = None,
    timeout: int = _REQUEST_TIMEOUT,
) -> VerifyResult:
    """Fetch a single feed and classify the result.

    The session is optional so tests can inject a mock; in production we
    share one session across the thread pool for connection reuse.
    """
    get = (session or requests).get
    try:
        response = get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        return VerifyResult(name, url, "NETWORK_ERROR", f"timeout: {exc}")
    except requests.ConnectionError as exc:
        return VerifyResult(
            name, url, "NETWORK_ERROR", f"connection: {type(exc).__name__}"
        )
    except requests.RequestException as exc:
        return VerifyResult(
            name, url, "NETWORK_ERROR", f"{type(exc).__name__}: {exc}"
        )

    if 300 <= response.status_code < 400:
        target = response.headers.get("Location", "<no Location header>")
        return VerifyResult(
            name, url, "REDIRECT",
            f"HTTP {response.status_code} → {target}",
            redirect_target=target,
        )
    if response.status_code != 200:
        return VerifyResult(
            name, url, "HTTP_ERROR", f"HTTP {response.status_code}"
        )

    parsed = feedparser.parse(response.content)
    entry_count = len(parsed.entries)
    bozo = bool(getattr(parsed, "bozo", False))
    bozo_exc = type(
        getattr(parsed, "bozo_exception", None)
    ).__name__ if bozo else ""
    # feedparser sets .version to a non-empty string ("rss20", "atom10", ...)
    # for valid feeds and leaves it empty for non-feed content (HTML error
    # pages, JSON responses, etc.).
    feed_version = getattr(parsed, "version", "") or ""

    if bozo and entry_count == 0:
        return VerifyResult(
            name, url, "BOZO_NO_ENTRIES",
            f"feedparser bozo={bozo_exc}; no entries",
        )
    if bozo and entry_count > 0:
        return VerifyResult(
            name, url, "BOZO_HAS_ENTRIES",
            f"feedparser bozo={bozo_exc}; {entry_count} entries usable",
            entry_count=entry_count,
        )
    if entry_count == 0 and not feed_version:
        # Non-bozo zero-entry responses with no feed version are almost
        # certainly not RSS/Atom at all (HTML error page, JSON, empty body).
        return VerifyResult(
            name, url, "BOZO_NO_ENTRIES",
            "response is not RSS/Atom (feedparser.version empty, 0 entries)",
        )
    if entry_count == 0:
        return VerifyResult(name, url, "OK_EMPTY", "valid feed, zero entries")
    return VerifyResult(
        name, url, "OK", f"{entry_count} entries", entry_count=entry_count,
    )


def verify_all(
    feeds_config_path: str,
    max_workers: int = _MAX_WORKERS,
    session: Optional[requests.Session] = None,
    include_inactive: bool = False,
) -> list[VerifyResult]:
    """Verify every feed in the config concurrently.

    By default feeds with ``active: false`` are skipped — they were
    intentionally disabled (see H14 notes in config/feeds.yaml) and failing
    them would cause the script to exit nonzero even though the state is
    correct. Pass ``include_inactive=True`` to check them anyway.
    """
    with open(feeds_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    all_feeds = config.get("feeds", [])
    feeds = [
        f for f in all_feeds
        if include_inactive or f.get("active", True)
    ]

    results: list[VerifyResult] = []
    if not feeds:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                verify_feed, entry["name"], entry["url"], session=session,
            ): entry
            for entry in feeds
        }
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by original order in the config for stable output
    order = {entry["url"]: i for i, entry in enumerate(feeds)}
    results.sort(key=lambda r: order.get(r.url, 10**6))
    return results


def summarize(results: list[VerifyResult]) -> dict[str, int]:
    """Return {status: count} for a set of verify results."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def print_report(results: list[VerifyResult]) -> None:
    """Print a human-readable report grouped by status."""
    counts = summarize(results)
    total = len(results)
    healthy = sum(counts.get(s, 0) for s in _HEALTHY_STATUSES)
    print(f"\nVerified {total} feeds — {healthy} healthy, {total - healthy} broken\n")
    print("Status breakdown:")
    for status, count in sorted(counts.items()):
        marker = "OK " if status in _HEALTHY_STATUSES else "BAD"
        print(f"  [{marker}] {status:<18} {count}")

    broken = [r for r in results if r.status not in _HEALTHY_STATUSES]
    if broken:
        print("\nBroken feeds (need attention):")
        for r in broken:
            print(f"  - {r.name}")
            print(f"      url:    {r.url}")
            print(f"      status: {r.status}")
            print(f"      detail: {r.detail}")
            if r.redirect_target:
                print(f"      → try:  {r.redirect_target}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=os.path.join(repo_root, "config", "feeds.yaml"),
        help="Path to feeds YAML config (default: config/feeds.yaml)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=_MAX_WORKERS,
        help=f"Thread pool size (default: {_MAX_WORKERS})",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help=(
            "Also verify feeds marked active: false. By default these are "
            "skipped because they were intentionally disabled."
        ),
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()
    results = verify_all(
        args.config,
        max_workers=args.workers,
        include_inactive=args.include_inactive,
    )
    print_report(results)
    broken = [r for r in results if r.status not in _HEALTHY_STATUSES]
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
