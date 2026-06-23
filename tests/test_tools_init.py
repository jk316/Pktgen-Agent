"""
Unit tests for tools/__init__.py — public create_tools API and ALL_TOOLS constant.
"""

import os
import sys

import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools import create_tools, _load_topology_config, ALL_TOOLS


class TestLoadTopologyConfig:
    def test_returns_host_and_port(self):
        host, port = _load_topology_config()
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert port == 22022


class TestCreateTools:
    def test_returns_list_of_callables(self):
        tools = create_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 1
        for t in tools:
            assert callable(t)

    def test_defaults_to_dry_run_true(self, monkeypatch):
        """create_tools() should use dry_run=True by default."""
        tools = create_tools()
        # Execute a tool and verify dry_run mode
        for t in tools:
            if hasattr(t, "__name__") and "minimal" in t.__name__:
                result = t(rate=50.0)
                assert result["mode"] == "dry_run"
                break

    def test_explicit_dry_run_false(self):
        tools = create_tools(dry_run=False)
        # Tools created with dry_run=False exist (won't actually connect
        # since we're calling dry functions — just verify creation works)
        assert len(tools) >= 1


class TestAllToolsConstant:
    def test_is_list(self):
        assert isinstance(ALL_TOOLS, list)

    def test_all_are_callable(self):
        for tool in ALL_TOOLS:
            assert callable(tool)
