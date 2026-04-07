"""Tests for scripts/run_ingestion.py — CLI entry point for live ingestion."""

import os
import shutil
import signal
import threading
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with config files."""
    src_config = os.path.join(REPO_ROOT, "config")
    dst_config = tmp_path / "config"
    shutil.copytree(src_config, dst_config)
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def env_file(tmp_path):
    """Create a .env file with both API keys."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-test-key-openai-12345\n"
        "ANTHROPIC_API_KEY=sk-ant-test-key-anthropic-12345\n"
    )
    return str(env_path)


# ------------------------------------------------------------------ #
#  parse_args tests                                                    #
# ------------------------------------------------------------------ #


class TestParseArgs:
    """Verify CLI argument parsing."""

    def test_defaults(self):
        """Default values: once=False, interval=1800, log_level=INFO."""
        from scripts.run_ingestion import parse_args

        args = parse_args([])
        assert args.once is False
        assert args.interval == 1800
        assert args.log_level == "INFO"

    def test_once_flag(self):
        """--once sets once=True."""
        from scripts.run_ingestion import parse_args

        args = parse_args(["--once"])
        assert args.once is True

    def test_custom_interval(self):
        """--interval sets the interval in seconds."""
        from scripts.run_ingestion import parse_args

        args = parse_args(["--interval", "600"])
        assert args.interval == 600

    def test_log_level_debug(self):
        """--log-level DEBUG sets log_level to DEBUG."""
        from scripts.run_ingestion import parse_args

        args = parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_interval_minimum_enforced(self):
        """Interval below 60 seconds is rejected."""
        from scripts.run_ingestion import parse_args

        with pytest.raises(SystemExit):
            parse_args(["--interval", "10"])

    def test_interval_negative_rejected(self):
        """Negative interval is rejected."""
        from scripts.run_ingestion import parse_args

        with pytest.raises(SystemExit):
            parse_args(["--interval", "-5"])

    def test_once_with_short_interval_allowed(self):
        """--once skips interval minimum validation."""
        from scripts.run_ingestion import parse_args

        args = parse_args(["--once", "--interval", "1"])
        assert args.once is True
        assert args.interval == 1


# ------------------------------------------------------------------ #
#  load_api_keys tests                                                 #
# ------------------------------------------------------------------ #


class TestLoadApiKeys:
    """Verify API key loading from environment."""

    def test_success(self, env_file, monkeypatch):
        """Returns both keys when present in .env file."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from scripts.run_ingestion import load_api_keys

        openai_key, anthropic_key = load_api_keys(env_path=env_file)
        assert openai_key == "sk-test-key-openai-12345"
        assert anthropic_key == "sk-ant-test-key-anthropic-12345"

    def test_missing_openai_key(self, tmp_path, monkeypatch):
        """Exits with code 1 when OPENAI_API_KEY is missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        env_path.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
        from scripts.run_ingestion import load_api_keys

        with pytest.raises(SystemExit) as exc_info:
            load_api_keys(env_path=str(env_path))
        assert exc_info.value.code == 1

    def test_missing_anthropic_key(self, tmp_path, monkeypatch):
        """Exits with code 1 when ANTHROPIC_API_KEY is missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        env_path.write_text("OPENAI_API_KEY=sk-test\n")
        from scripts.run_ingestion import load_api_keys

        with pytest.raises(SystemExit) as exc_info:
            load_api_keys(env_path=str(env_path))
        assert exc_info.value.code == 1

    def test_both_missing(self, tmp_path, monkeypatch):
        """Exits with code 1 when both keys are missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        env_path.write_text("")
        from scripts.run_ingestion import load_api_keys

        with pytest.raises(SystemExit) as exc_info:
            load_api_keys(env_path=str(env_path))
        assert exc_info.value.code == 1

    def test_whitespace_only_key(self, tmp_path, monkeypatch):
        """Whitespace-only key is treated as missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        env_path.write_text(
            "OPENAI_API_KEY=   \nANTHROPIC_API_KEY=sk-ant-test\n"
        )
        from scripts.run_ingestion import load_api_keys

        with pytest.raises(SystemExit) as exc_info:
            load_api_keys(env_path=str(env_path))
        assert exc_info.value.code == 1


# ------------------------------------------------------------------ #
#  build_components tests                                              #
# ------------------------------------------------------------------ #


class TestBuildComponents:
    """Verify component wiring."""

    def test_returns_db_and_worker(self, temp_project):
        """build_components returns (Database, IngestionWorker)."""
        from scripts.run_ingestion import build_components
        from src.database import Database
        from src.ingestion import IngestionWorker

        db_path = str(temp_project / "data" / "monitor.db")
        config_path = str(temp_project / "config" / "feeds.yaml")

        db, worker = build_components(
            openai_key="sk-test-openai-12345",
            anthropic_key="sk-ant-test-anthropic-12345",
            db_path=db_path,
            feeds_config_path=config_path,
        )
        try:
            assert isinstance(db, Database)
            assert isinstance(worker, IngestionWorker)
        finally:
            db.close()

    def test_db_has_feeds_loaded(self, temp_project):
        """Database has feeds loaded from config after build."""
        from scripts.run_ingestion import build_components

        db_path = str(temp_project / "data" / "monitor.db")
        config_path = str(temp_project / "config" / "feeds.yaml")

        db, _worker = build_components(
            openai_key="sk-test-openai-12345",
            anthropic_key="sk-ant-test-anthropic-12345",
            db_path=db_path,
            feeds_config_path=config_path,
        )
        try:
            feeds = db.get_active_feeds()
            assert len(feeds) > 50  # config has 61 feeds
        finally:
            db.close()


# ------------------------------------------------------------------ #
#  run_loop tests                                                      #
# ------------------------------------------------------------------ #


class TestRunLoop:
    """Verify ingestion loop behavior."""

    def test_once_mode_calls_run_once_exactly_once(self):
        """In --once mode, worker.run_once() is called exactly once."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()

        run_loop(
            worker=mock_worker,
            interval=1800,
            once=True,
            shutdown_event=shutdown_event,
        )
        mock_worker.run_once.assert_called_once()

    def test_continuous_stops_on_shutdown_event(self):
        """In continuous mode, loop stops when shutdown event is set."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()

        # Set shutdown event after first run_once call
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                shutdown_event.set()

        mock_worker.run_once.side_effect = side_effect

        run_loop(
            worker=mock_worker,
            interval=1,  # low interval; run_loop doesn't enforce minimum
            once=False,
            shutdown_event=shutdown_event,
        )
        assert mock_worker.run_once.call_count == 2

    def test_once_mode_ignores_shutdown_event(self):
        """In --once mode, shutdown event state doesn't matter."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()
        shutdown_event.set()  # pre-set

        run_loop(
            worker=mock_worker,
            interval=1800,
            once=True,
            shutdown_event=shutdown_event,
        )
        mock_worker.run_once.assert_called_once()

    def test_continuous_shutdown_after_first_pass(self):
        """Shutdown set during first pass exits after that pass."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()

        # Set shutdown after first call
        mock_worker.run_once.side_effect = lambda: shutdown_event.set()

        run_loop(
            worker=mock_worker,
            interval=1,
            once=False,
            shutdown_event=shutdown_event,
        )
        mock_worker.run_once.assert_called_once()

    def test_continuous_pre_set_shutdown_zero_passes(self):
        """If shutdown is already set, loop runs zero passes."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()
        shutdown_event.set()  # pre-set before entering loop

        run_loop(
            worker=mock_worker,
            interval=1,
            once=False,
            shutdown_event=shutdown_event,
        )
        mock_worker.run_once.assert_not_called()

    def test_continuous_first_pass_failure_retries(self):
        """First-pass failure in continuous mode is caught; loop continues."""
        from scripts.run_ingestion import run_loop

        mock_worker = MagicMock()
        shutdown_event = threading.Event()

        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Feed fetch failed")
            # Second call succeeds, then shut down
            shutdown_event.set()

        mock_worker.run_once.side_effect = side_effect

        run_loop(
            worker=mock_worker,
            interval=1,
            once=False,
            shutdown_event=shutdown_event,
        )
        assert mock_worker.run_once.call_count == 2


# ------------------------------------------------------------------ #
#  Signal handler tests                                                #
# ------------------------------------------------------------------ #


class TestSignalHandler:
    """Verify signal handling sets shutdown event."""

    def test_handler_sets_event(self):
        """Signal handler function sets the shutdown event."""
        from scripts.run_ingestion import make_signal_handler

        shutdown_event = threading.Event()
        handler = make_signal_handler(shutdown_event)
        assert not shutdown_event.is_set()

        handler(signal.SIGINT, None)
        assert shutdown_event.is_set()

    def test_handler_is_idempotent(self):
        """Calling handler multiple times is safe."""
        from scripts.run_ingestion import make_signal_handler

        shutdown_event = threading.Event()
        handler = make_signal_handler(shutdown_event)

        handler(signal.SIGINT, None)
        handler(signal.SIGTERM, None)
        assert shutdown_event.is_set()


# ------------------------------------------------------------------ #
#  main() integration tests                                            #
# ------------------------------------------------------------------ #


class TestMain:
    """Verify main() orchestration."""

    def test_once_mode_end_to_end(self, temp_project, monkeypatch):
        """main(["--once"]) initializes components and calls run_once."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-12345")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-anthropic-12345")

        mock_worker = MagicMock()
        mock_db = MagicMock()

        with patch(
            "scripts.run_ingestion.build_components",
            return_value=(mock_db, mock_worker),
        ):
            from scripts.run_ingestion import main

            main(["--once"])

        mock_worker.run_once.assert_called_once()
        mock_db.close.assert_called_once()

    def test_missing_keys_exits(self, tmp_path, monkeypatch):
        """main() exits with code 1 when API keys are missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Point repo_root at a temp dir with no .env to isolate from real .env
        empty_env = tmp_path / ".env"
        empty_env.write_text("")

        from scripts.run_ingestion import load_api_keys

        with patch(
            "scripts.run_ingestion.load_api_keys",
            side_effect=lambda **kw: load_api_keys(env_path=str(empty_env)),
        ):
            from scripts.run_ingestion import main

            with pytest.raises(SystemExit) as exc_info:
                main(["--once"])
        assert exc_info.value.code == 1

    def test_db_closed_on_worker_exception(self, monkeypatch):
        """Database is closed even if worker raises."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-12345")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-anthropic-12345")

        mock_worker = MagicMock()
        mock_worker.run_once.side_effect = RuntimeError("Feed fetch failed")
        mock_db = MagicMock()

        with patch(
            "scripts.run_ingestion.build_components",
            return_value=(mock_db, mock_worker),
        ):
            from scripts.run_ingestion import main

            with pytest.raises(RuntimeError, match="Feed fetch failed"):
                main(["--once"])

        mock_db.close.assert_called_once()
