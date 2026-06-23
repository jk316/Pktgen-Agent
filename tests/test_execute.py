"""
Unit tests for tools/execute.py — tool factory + execution functions.

Tests cover both langchain and no-langchain code paths.
"""

import os
import sys

import pytest

# Ensure project root is on path so tools/execute can import compiler + pktgen_client
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.execute import (
    compile_skill_lua,
    execute_skill_dry_run,
    execute_skill_live,
    _load_skill_meta,
    _build_pydantic_model,
    create_skill_tool,
    create_all_tools,
    HAS_LANGCHAIN,
    PYTHON_TYPE_MAP,
)
from compiler.compile import CompileError


# ── TestCompileSkillLua ──


@pytest.mark.usefixtures("test_data_dir")
class TestCompileSkillLua:
    def test_returns_lua_string(self):
        """Uses real skills from project — they exist on disk."""
        lua = compile_skill_lua("minimal_skill", {"rate": 50.0})
        assert isinstance(lua, str)
        assert len(lua) > 0
        assert "pktgen.start" in lua

    def test_raises_for_unknown_skill(self, monkeypatch):
        with pytest.raises(CompileError):
            compile_skill_lua("nonexistent_skill_xyz", {})


# ── TestExecuteSkillDryRun ──


@pytest.mark.usefixtures("test_data_dir")
class TestExecuteSkillDryRun:
    def test_returns_dict_with_expected_keys(self, monkeypatch):
        result = execute_skill_dry_run("minimal_skill", {"rate": 50.0})
        assert result["success"] is True
        assert result["skill"] == "minimal_skill"
        assert result["mode"] == "dry_run"
        assert "lua_code" in result
        assert "pktgen.start" in result["lua_code"]

    def test_raises_on_bad_skill(self):
        """execute_skill_dry_run does NOT catch CompileError — it propagates."""
        with pytest.raises(CompileError):
            execute_skill_dry_run("nonexistent_xyz", {})


# ── TestLoadSkillMeta ──


@pytest.mark.usefixtures("test_data_dir")
class TestLoadSkillMeta:
    def test_loads_skill_metadata(self, monkeypatch):
        meta = _load_skill_meta("minimal_skill")
        assert "name" in meta
        assert meta["name"] == "minimal_skill"

    def test_file_not_found(self, monkeypatch):
        with pytest.raises(FileNotFoundError):
            _load_skill_meta("nonexistent_xyz")


# ── TestBuildPydanticModel ──


@pytest.mark.langchain
class TestBuildPydanticModel:
    def test_returns_model_with_fields(self, monkeypatch):
        monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", True)
        params = [
            {"name": "rate", "type": "float", "required": True},
            {"name": "count", "type": "integer", "default": 100},
            {"name": "enable", "type": "boolean", "default": False},
        ]
        Model = _build_pydantic_model("test_skill", params)
        assert Model is not None
        # Check field types
        assert Model.model_fields["rate"].annotation is float
        assert Model.model_fields["count"].annotation is int
        assert Model.model_fields["enable"].annotation is bool

    def test_required_field_has_no_default(self, monkeypatch):
        monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", True)
        params = [{"name": "rate", "type": "float", "required": True}]
        Model = _build_pydantic_model("test", params)
        assert Model.model_fields["rate"].is_required()

    def test_returns_none_when_langchain_not_installed(self, no_langchain):
        result = _build_pydantic_model("test", [])
        assert result is None

    def test_empty_params_returns_model(self, monkeypatch):
        monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", True)
        Model = _build_pydantic_model("empty", [])
        assert Model is not None
        assert len(Model.model_fields) == 0

    def test_model_name_formatting(self, monkeypatch):
        monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", True)
        Model = _build_pydantic_model("safe_stop_and_reset", [])
        assert Model.__name__ == "SafeStopAndResetInput"


# ── TestCreateSkillTool ──


@pytest.mark.usefixtures("test_data_dir")
class TestCreateSkillTool:
    def test_returns_callable(self, no_langchain, monkeypatch):
        """Without langchain, returns a plain callable."""
        tool = create_skill_tool("minimal_skill", dry_run=True)
        assert callable(tool)

    def test_plain_callable_has_name_and_doc(self, no_langchain, monkeypatch):
        tool = create_skill_tool("minimal_skill", dry_run=True)
        assert hasattr(tool, "__name__")
        assert hasattr(tool, "__doc__")
        assert tool.__name__ == "minimal_skill"

    def test_plain_callable_dry_run_executes(self, no_langchain, monkeypatch):
        tool = create_skill_tool("minimal_skill", dry_run=True)
        result = tool(rate=50.0)
        assert result["success"] is True
        assert result["mode"] == "dry_run"

    @pytest.mark.langchain
    def test_returns_structured_tool_with_langchain(self, with_langchain, monkeypatch):
        tool = create_skill_tool("minimal_skill", dry_run=True)
        # Should have args_schema (Pydantic model)
        assert hasattr(tool, "args_schema")


# ── TestCreateAllTools ──


@pytest.mark.usefixtures("test_data_dir")
class TestCreateAllTools:
    def test_returns_list(self, monkeypatch):
        tools = create_all_tools(dry_run=True)
        assert isinstance(tools, list)
        # At least the 9 real skills should be present
        assert len(tools) >= 1

    def test_all_tools_are_callable(self, monkeypatch):
        tools = create_all_tools(dry_run=True)
        for tool in tools:
            assert callable(tool)


# ── TestPYTHON_TYPE_MAP ──


class TestPythonTypeMap:
    def test_maps_known_types(self):
        assert PYTHON_TYPE_MAP["string"] is str
        assert PYTHON_TYPE_MAP["integer"] is int
        assert PYTHON_TYPE_MAP["float"] is float
        assert PYTHON_TYPE_MAP["boolean"] is bool
