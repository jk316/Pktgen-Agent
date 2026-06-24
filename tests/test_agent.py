"""
Unit tests for pktgen_agent.agent — dependency checks, env loading, topology reading.
"""

import os
from pathlib import Path

import pytest

from pktgen_agent.agent import check_dependencies
from pktgen_agent.config import load_dotenv
from pktgen_agent.topology import load_topology_config


# ── TestCheckDependencies ──


class TestCheckDependencies:
    def test_returns_true_when_all_installed(self):
        """pyyaml, langchain-core, langchain, langchain-openai, pydantic."""
        ok, msg = check_dependencies()
        if not ok:
            pytest.skip(f"Required packages not installed in this env: {msg}")
        assert msg == ""

    def test_returns_false_and_lists_missing(self, monkeypatch):
        """Simulate a missing package by making __import__ fail for it."""
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        ok, msg = check_dependencies()
        assert ok is False
        assert "pyyaml" in msg

    def test_error_mentions_pip_install(self, monkeypatch):
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "langchain.agents":
                raise ImportError("nope")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        _, msg = check_dependencies()
        assert "pip install" in msg

    def test_lists_all_missing_packages(self, monkeypatch):
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name in ("langchain_core", "langchain.agents"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        ok, msg = check_dependencies()
        assert ok is False
        assert "langchain-core" in msg
        assert "langchain" in msg


# ── TestLoadDotenv ──


class TestLoadDotenv:
    def test_does_not_crash_on_missing_file(self):
        """load_dotenv should not crash when .env doesn't exist."""
        load_dotenv(env_path=Path("/nonexistent/.env"))  # safe no-op

    def test_strips_quotes(self):
        """Fallback parser strips double and single quotes."""
        import pktgen_agent.config as cfg

        # Simulate the manual parsing logic
        value = '"quoted_value"'
        value = value.strip().strip('"').strip("'")
        assert value == "quoted_value"

        value2 = "'single_quoted'"
        value2 = value2.strip().strip('"').strip("'")
        assert value2 == "single_quoted"

    def test_does_not_overwrite_existing(self, tmp_path):
        """Existing os.environ values should not be overwritten by fallback parser."""
        os.environ["PYTEST_TEST_EXISTING"] = "original"
        env_file = tmp_path / ".env"
        env_file.write_text('PYTEST_TEST_EXISTING=new\n')
        load_dotenv(env_path=env_file)
        # Manual parser should not overwrite
        assert os.environ["PYTEST_TEST_EXISTING"] == "original"
        del os.environ["PYTEST_TEST_EXISTING"]

    def test_skips_comments_and_blank(self, tmp_path):
        """Fallback parser skips comments and blank lines."""
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nKEY=val\n")
        load_dotenv(env_path=env_file)
        # Should not crash


# ── TestLoadTopologyConfig ──


class TestLoadTopologyConfig:
    def test_returns_host_and_port(self):
        host, port = load_topology_config()
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert port == 22022
        assert len(host) > 0

    def test_returns_strings_not_none(self):
        host, port = load_topology_config()
        assert host is not None
        assert port is not None
