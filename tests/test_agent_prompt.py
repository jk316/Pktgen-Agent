"""
Unit tests for agent_prompt.py — system prompt construction and tool table generation.
"""

import pytest
from agent_prompt import _build_tool_table, get_skill_summaries, SYSTEM_PROMPT


class TestBuildToolTable:
    def test_returns_non_empty_string(self):
        result = _build_tool_table()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_markdown_table(self):
        result = _build_tool_table()
        assert "| Tool |" in result
        assert "|------|" in result

    def test_has_at_least_one_skill_row(self):
        result = _build_tool_table()
        lines = result.strip().split("\n")
        # Header + separator + at least 1 skill row
        assert len(lines) >= 3

    def test_contains_known_skill_names(self):
        result = _build_tool_table()
        assert "udp_flood" in result
        assert "tcp_flood" in result

    def test_rows_sorted_by_name(self):
        result = _build_tool_table()
        lines = [l for l in result.strip().split("\n") if l.startswith("|") and "Tool" not in l and "---" not in l]
        names = [l.split("|")[1].strip() for l in lines]
        assert names == sorted(names)


class TestGetSkillSummaries:
    def test_returns_same_as_build_tool_table(self):
        assert get_skill_summaries() == _build_tool_table()


class TestSystemPrompt:
    def test_is_non_empty_string(self):
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0

    def test_contains_pktgen_identity(self):
        assert "Pktgen Traffic Generator Controller" in SYSTEM_PROMPT

    def test_contains_tool_table(self):
        """The SYSTEM_PROMPT embeds the tool table at module load."""
        assert "| Tool |" in SYSTEM_PROMPT
        assert "udp_flood" in SYSTEM_PROMPT

    def test_contains_usage_rules(self):
        assert "Important Rules" in SYSTEM_PROMPT
        assert "Always stop before switching" in SYSTEM_PROMPT

    def test_contains_example_interactions(self):
        assert "Example Interactions" in SYSTEM_PROMPT
        assert "Send UDP traffic" in SYSTEM_PROMPT

    def test_contains_react_format_instructions(self):
        # SYSTEM_PROMPT itself is used as base for the full ReAct template
        assert "Response Format" in SYSTEM_PROMPT
