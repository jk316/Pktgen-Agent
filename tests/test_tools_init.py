"""
Unit tests for pktgen_agent.tools — public create_tools API.

No more eager ALL_TOOLS constant or duplicated _load_topology_config.
"""

import pytest

from pktgen_agent.tools import create_tools


class TestCreateTools:
    def test_returns_list_of_invokable_tools(self):
        tools = create_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 1
        for t in tools:
            # V1.0 BaseTool objects may be Pydantic models (not plain callables)
            assert hasattr(t, "invoke") or callable(t)

    def test_defaults_to_dry_run(self):
        """create_tools() should use dry_run=True by default."""
        tools = create_tools()
        # Execute a tool and verify dry_run mode
        for t in tools:
            name = getattr(t, "name", getattr(t, "__name__", ""))
            if "minimal" in name:
                result = t(rate=50.0)
                assert result["mode"] == "dry_run"
                break

    def test_explicit_dry_run_false(self):
        """Tools created with dry_run=False exist (won't actually connect)."""
        tools = create_tools(dry_run=False)
        assert len(tools) >= 1

    def test_all_tools_have_name(self):
        """All tools should have a name attribute for LangChain."""
        tools = create_tools()
        for tool in tools:
            # V1.0 @tool decorator sets .name
            name = getattr(tool, "name", getattr(tool, "__name__", ""))
            assert name, f"Tool {tool} has no name"
