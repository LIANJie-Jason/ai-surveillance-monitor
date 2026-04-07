#!/usr/bin/env python3
"""CLI entry point for live RSS ingestion.

Wires up Database, LLMClient, Classifier, Summarizer, and IngestionWorker,
then runs ingestion in single-pass or continuous mode.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

# Ensure repo root is on sys.path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from scripts.init_db import init_database
from src.classifier import Classifier
from src.database import Database
from src.ingestion import IngestionWorker
from src.llm_client import LLMClient
from src.summarizer import Summarizer

logger = logging.getLogger(__name__)

_MIN_INTERVAL = 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:] if None).

    Returns:
        Namespace with: once (bool), interval (int), log_level (str).
    """
    parser = argparse.ArgumentParser(
        description="Run the AI Surveillance News Monitor ingestion worker.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run a single ingestion pass and exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Seconds between ingestion passes (default: 1800). Minimum: 60.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    args = parser.parse_args(argv)

    if not args.once and args.interval < _MIN_INTERVAL:
        parser.error(
            f"--interval must be at least {_MIN_INTERVAL} seconds, got {args.interval}"
        )

    return args


def load_api_keys(env_path: str | None = None) -> tuple[str, str]:
    """Load and validate API keys from environment.

    Args:
        env_path: Optional path to .env file. If None, python-dotenv
                  searches from cwd upward.

    Returns:
        (openai_key, anthropic_key) — both guaranteed non-empty strings.

    Raises:
        SystemExit: If either key is missing or empty (exit code 1).
    """
    if env_path is not None:
        load_dotenv(env_path)
    else:
        load_dotenv()

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    missing: list[str] = []
    if not openai_key:
        missing.append("OPENAI_API_KEY")
    if not anthropic_key:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(
            f"ERROR: Missing required API key(s): {', '.join(missing)}.\n"
            "Set them in .env or as environment variables.",
            file=sys.stderr,
        )
        sys.exit(1)

    return (openai_key, anthropic_key)


def build_components(
    openai_key: str,
    anthropic_key: str,
    db_path: str,
    feeds_config_path: str,
) -> tuple[Database, IngestionWorker]:
    """Initialize all pipeline components.

    Returns:
        (database, worker) — caller is responsible for calling db.close().
    """
    db = init_database(db_path=db_path, feeds_config_path=feeds_config_path)
    llm_client = LLMClient(openai_key=openai_key, anthropic_key=anthropic_key)
    classifier = Classifier(llm_client=llm_client)
    summarizer = Summarizer(llm_client=llm_client)
    worker = IngestionWorker(db=db, classifier=classifier, summarizer=summarizer)
    return (db, worker)


def run_loop(
    worker: IngestionWorker,
    interval: int,
    once: bool,
    shutdown_event: threading.Event,
) -> None:
    """Execute ingestion passes.

    Args:
        worker: Fully initialized IngestionWorker.
        interval: Seconds between passes (ignored if once=True).
        once: If True, run a single pass and return.
        shutdown_event: Set by signal handlers to break the sleep loop.
    """
    if once:
        logger.info("Starting single ingestion pass...")
        worker.run_once()
        logger.info("Ingestion pass complete.")
        return

    while not shutdown_event.is_set():
        try:
            logger.info("Starting ingestion pass...")
            worker.run_once()
            logger.info("Ingestion pass complete.")
        except Exception:
            logger.exception("Ingestion pass failed; will retry at next interval.")
        shutdown_event.wait(interval)


def make_signal_handler(
    shutdown_event: threading.Event,
) -> Callable[[int, object | None], None]:
    """Create a signal handler that sets the shutdown event.

    Returns:
        A signal handler function with signature (signum, frame) -> None.
    """

    def handler(signum: int, frame: object | None) -> None:
        logger.info("Shutdown signal received (signal %d), stopping...", signum)
        shutdown_event.set()

    return handler


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(repo_root, ".env")
    openai_key, anthropic_key = load_api_keys(env_path=env_path)
    db_path = os.path.join(repo_root, "data", "monitor.db")
    feeds_config_path = os.path.join(repo_root, "config", "feeds.yaml")

    db, worker = build_components(
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        db_path=db_path,
        feeds_config_path=feeds_config_path,
    )

    shutdown_event = threading.Event()
    handler = make_signal_handler(shutdown_event)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    try:
        run_loop(
            worker=worker,
            interval=args.interval,
            once=args.once,
            shutdown_event=shutdown_event,
        )
    finally:
        db.close()
        logger.info("Ingestion stopped. Database closed.")


if __name__ == "__main__":
    main()
