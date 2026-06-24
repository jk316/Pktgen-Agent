"""
Unit tests for pktgen_agent.agent_prompt — system prompt and tool catalogue.
"""

import pytest
from pktgen_agent.agent_prompt import (
    _build_tool_summaries,
    get_tool_catalog,
    SYSTEM_PROMPT,
)


class TestBuildToolSummaries:
    def test_returns_non_empty_string(self):
        result = _build_tool_summaries()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_markdown_table(self):
        result = _build_tool_summaries()
        assert "| Tool |" in result
        assert "|------|" in result

    def test_has_at_least_one_skill_row(self):
        result = _build_tool_summaries()
        lines = result.strip().split("\n")
        # Header + separator + at least 1 skill row
        assert len(lines) >= 3

    def test_contains_known_skill_names(self):
        result = _build_tool_summaries()
        assert "udp_flood" in result
        assert "tcp_flood" in result

    def test_rows_sorted_by_name(self):
        result = _build_tool_summaries()
        lines = [
            l
            for l in result.strip().split("\n")
            if l.startswith("|") and "Tool" not in l and "---" not in l
        ]
        names = [l.split("|")[1].strip() for l in lines]
        assert names == sorted(names)

    def test_cached_on_second_call(self, monkeypatch):
        """Second call returns cached result without re-reading disk."""
        # Clear cache for this test
        monkeypatch.setattr(
            "pktgen_agent.agent_prompt._tool_table_cache", None
        )
        result1 = _build_tool_summaries()
        result2 = _build_tool_summaries()
        assert result1 == result2  # Same content
        assert result1 is result2  # Same object (cached)


class TestGetToolCatalog:
    def test_returns_same_as_build_tool_summaries(self):
        assert get_tool_catalog() == _build_tool_summaries()


class TestSystemPrompt:
    def test_is_non_empty_string(self):
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0

    def test_contains_pktgen_identity(self):
        assert "Pktgen Traffic Generator Controller" in SYSTEM_PROMPT

    def test_does_not_embed_tool_table_at_load_time(self):
        """V1.0: SYSTEM_PROMPT is a plain string — tool table is lazy-loaded."""
        # Tool table is NOT embedded inline (was an import-time I/O anti-pattern)
        assert "| Tool |" not in SYSTEM_PROMPT

    def test_contains_usage_rules(self):
        assert "Important Rules" in SYSTEM_PROMPT
        assert "Always stop before switching" in SYSTEM_PROMPT

    def test_contains_example_interactions(self):
        assert "Example Interactions" in SYSTEM_PROMPT
        assert "Send UDP traffic" in SYSTEM_PROMPT

    def test_contains_response_format(self):
        assert "Response Format" in SYSTEM_PROMPT
