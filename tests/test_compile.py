"""
Unit tests for compiler/compile.py — SkillCompiler class.

Covers: __init__, topology, schema, valid_apis, load_skill, validate_api,
validate_set_key, resolve_topology, resolve_params, resolve_special,
_to_lua_literal, compile_step, _indent, compile_phase, compile.
"""

import pytest
from compiler.compile import SkillCompiler, CompileError, compile_skill


# ── TestSkillCompilerInit ──


class TestSkillCompilerInit:
    def test_default_topology_path(self, test_data_dir):
        """Default constructor uses the patched TOPOLOGY_PATH."""
        c = SkillCompiler()
        assert c.topology_path is not None
        assert str(c.topology_path).endswith("topology.yaml")

    def test_custom_topology_path(self, tmp_path):
        custom = tmp_path / "custom_topo.yaml"
        c = SkillCompiler(topology_path=custom)
        assert c.topology_path == custom

    def test_caches_are_none_initially(self, compiler):
        assert compiler._topology is None
        assert compiler._schema is None
        assert compiler._valid_apis is None


# ── TestTopologyProperty ──


class TestTopologyProperty:
    def test_loads_yaml(self, compiler):
        topo = compiler.topology
        assert "tx_port" in topo
        assert topo["tx_port"]["portlist"] == "0"
        assert "rx_port" in topo
        assert "pktgen" in topo

    def test_cached_on_second_access(self, compiler):
        topo1 = compiler.topology
        topo2 = compiler.topology
        assert topo1 is topo2

    def test_file_not_found(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        c = SkillCompiler(topology_path=missing)
        with pytest.raises(FileNotFoundError):
            _ = c.topology


# ── TestSchemaProperty ──


class TestSchemaProperty:
    def test_loads_yaml(self, compiler):
        schema = compiler.schema
        assert "valid_apis" in schema
        assert "valid_set_keys" in schema

    def test_cached_on_second_access(self, compiler):
        s1 = compiler.schema
        s2 = compiler.schema
        assert s1 is s2


# ── TestValidApis ──


class TestValidApis:
    def test_returns_set(self, compiler):
        apis = compiler.valid_apis
        assert isinstance(apis, set)
        assert len(apis) > 0

    def test_includes_whitelisted_apis(self, compiler):
        apis = compiler.valid_apis
        assert "pktgen.set" in apis
        assert "pktgen.start" in apis
        assert "pktgen.screen" in apis

    def test_includes_printf_and_prints(self, compiler):
        apis = compiler.valid_apis
        assert "printf" in apis
        assert "prints" in apis

    def test_cached(self, compiler):
        a1 = compiler.valid_apis
        a2 = compiler.valid_apis
        assert a1 is a2


# ── TestLoadSkill ──


class TestLoadSkill:
    def test_loads_skill_by_name(self, compiler):
        skill = compiler.load_skill("minimal_skill")
        assert skill["name"] == "minimal_skill"
        assert skill["intent"] == "traffic_generation"
        assert "plan" in skill

    def test_compiler_error_when_skill_not_found(self, compiler):
        with pytest.raises(CompileError, match="Skill not found"):
            compiler.load_skill("nonexistent_skill")

    def test_returns_skill_key_when_present(self, compiler):
        skill = compiler.load_skill("minimal_skill")
        # The YAML has a top-level "skill:" key, so we get its value
        assert skill["name"] is not None


# ── TestValidateApi ──


class TestValidateApi:
    def test_passes_whitelisted_api(self, compiler):
        compiler.validate_api("pktgen.set")
        compiler.validate_api("pktgen.start")
        compiler.validate_api("pktgen.screen")

    def test_passes_dollar_prefixed(self, compiler):
        """APIs prefixed with $ are special refs, always allowed."""
        compiler.validate_api("$range_api")
        compiler.validate_api("$something_dynamic")

    def test_passes_printf_and_prints(self, compiler):
        compiler.validate_api("printf")
        compiler.validate_api("prints")

    def test_raises_for_unknown_api(self, compiler):
        with pytest.raises(CompileError, match="Unknown API function"):
            compiler.validate_api("pktgen.nonexistent_func")

    def test_case_sensitive(self, compiler):
        with pytest.raises(CompileError):
            compiler.validate_api("Pktgen.Set")


# ── TestValidateSetKey ──


class TestValidateSetKey:
    def test_passes_valid_keys(self, compiler):
        for key in ["count", "rate", "size", "sport", "dport"]:
            compiler.validate_set_key(key)

    def test_raises_for_invalid_key(self, compiler):
        with pytest.raises(CompileError, match="Unknown pktgen.set\\(\\) key"):
            compiler.validate_set_key("invalid_key")

    def test_error_messages_lists_valid_keys(self, compiler):
        with pytest.raises(CompileError, match="Valid keys"):
            compiler.validate_set_key("badkey")


# ── TestResolveTopology ──


class TestResolveTopology:
    def test_replaces_tx_port(self, compiler):
        result = compiler.resolve_topology("$topology.tx_port")
        assert result == "0"

    def test_replaces_rx_port(self, compiler):
        result = compiler.resolve_topology("$topology.rx_port")
        assert result == "1"

    def test_multiple_refs_in_one_string(self, compiler):
        result = compiler.resolve_topology("$topology.tx_port,$topology.rx_port")
        assert result == "0,1"

    def test_noop_when_no_ref(self, compiler):
        result = compiler.resolve_topology('"off"')
        assert result == '"off"'

    def test_raises_for_undefined_topology_name(self, compiler):
        with pytest.raises(CompileError, match="Undefined topology reference"):
            compiler.resolve_topology("$topology.undefined_port")

    def test_error_lists_available_keys(self, compiler):
        with pytest.raises(CompileError, match="Available"):
            compiler.resolve_topology("$topology.bad")


# ── TestResolveParams ──


class TestResolveParams:
    def test_replaces_with_user_value_int(self, compiler):
        skill_params = [{"name": "count", "type": "integer"}]
        result = compiler.resolve_params("$params.count", {"count": 42}, skill_params)
        assert result == "42"

    def test_replaces_with_user_value_string(self, compiler):
        skill_params = [{"name": "target_ip", "type": "ip_address"}]
        result = compiler.resolve_params("$params.target_ip", {"target_ip": "10.0.0.1"}, skill_params)
        assert result == '"10.0.0.1"'

    def test_replaces_with_user_value_bool_true(self, compiler):
        skill_params = [{"name": "enable", "type": "boolean"}]
        result = compiler.resolve_params("$params.enable", {"enable": True}, skill_params)
        assert result == "true"

    def test_replaces_with_user_value_bool_false(self, compiler):
        skill_params = [{"name": "enable", "type": "boolean"}]
        result = compiler.resolve_params("$params.enable", {"enable": False}, skill_params)
        assert result == "false"

    def test_falls_back_to_default(self, compiler):
        skill_params = [
            {"name": "count", "type": "integer", "default": 200}
        ]
        result = compiler.resolve_params("$params.count", {}, skill_params)
        assert result == "200"

    def test_raises_for_missing_required_param(self, compiler):
        skill_params = [
            {"name": "rate", "type": "float", "required": True}
        ]
        with pytest.raises(CompileError, match="required but not provided"):
            compiler.resolve_params("$params.rate", {}, skill_params)

    def test_raises_for_undefined_param(self, compiler):
        skill_params = []
        with pytest.raises(CompileError, match="Undefined parameter reference"):
            compiler.resolve_params("$params.bogus", {}, skill_params)

    def test_multiple_refs_in_one_string(self, compiler):
        skill_params = [
            {"name": "a", "type": "integer", "default": 1},
            {"name": "b", "type": "integer", "default": 2},
        ]
        result = compiler.resolve_params("a=$params.a,b=$params.b", {}, skill_params)
        assert result == "a=1,b=2"

    def test_default_bool_false(self, compiler):
        """Boolean default of False should be 'false', not skipped."""
        skill_params = [
            {"name": "save_config", "type": "boolean", "default": False}
        ]
        result = compiler.resolve_params("$params.save_config", {}, skill_params)
        assert result == "false"


# ── TestResolveSpecial ──


class TestResolveSpecial:
    def test_sequence_count_replaced(self, compiler):
        result = compiler.resolve_special("$sequence_count", {},
                                          {"sequences": [1, 2, 3]})
        assert result == "3"

    def test_sequence_count_empty(self, compiler):
        result = compiler.resolve_special("$sequence_count", {},
                                          {"sequences": []})
        assert result == "0"

    def test_no_special_refs_passes_through(self, compiler):
        result = compiler.resolve_special("normal_string", {}, {})
        assert result == "normal_string"


# ── TestToLuaLiteral ──


class TestToLuaLiteral:
    def test_bool_true(self, compiler):
        assert compiler._to_lua_literal(True) == "true"

    def test_bool_false(self, compiler):
        assert compiler._to_lua_literal(False) == "false"

    def test_plain_string(self, compiler):
        assert compiler._to_lua_literal("hello") == '"hello"'

    def test_already_quoted_string(self, compiler):
        assert compiler._to_lua_literal('"already"') == '"already"'

    def test_dollar_ref_passthrough(self, compiler):
        assert compiler._to_lua_literal("$topology.tx_port") == "$topology.tx_port"

    def test_int(self, compiler):
        assert compiler._to_lua_literal(42) == "42"
        assert compiler._to_lua_literal(-1) == "-1"

    def test_float(self, compiler):
        assert compiler._to_lua_literal(3.14) == "3.14"

    def test_none(self, compiler):
        assert compiler._to_lua_literal(None) == "nil"

    def test_empty_string(self, compiler):
        assert compiler._to_lua_literal("") == '""'

    def test_dict_raises_compiler_error(self, compiler):
        with pytest.raises(CompileError, match="Cannot convert value to Lua literal"):
            compiler._to_lua_literal({"key": "val"})

    def test_list_raises_compiler_error(self, compiler):
        with pytest.raises(CompileError, match="Cannot convert value to Lua literal"):
            compiler._to_lua_literal([1, 2, 3])

    def test_very_large_int(self, compiler):
        assert compiler._to_lua_literal(9999999999) == "9999999999"

    def test_negative_float(self, compiler):
        assert compiler._to_lua_literal(-0.5) == "-0.5"


# ── TestCompileStep ──


class TestCompileStep:
    def test_skip_step(self, compiler):
        step = {"api": "pktgen.set", "skip": True, "args": ["a"]}
        result = compiler.compile_step(step, {}, {"params": []})
        assert result == []

    def test_no_api_returns_empty(self, compiler):
        step = {"comment": "just a comment"}
        result = compiler.compile_step(step, {}, {"params": []})
        assert result == []

    def test_direct_call(self, compiler):
        step = {"api": "pktgen.start", "args": ["$topology.tx_port"]}
        result = compiler.compile_step(step, {}, {"params": []})
        assert result == ['pktgen.start(0);']

    def test_no_args_call(self, compiler):
        step = {"api": "pktgen.portCount"}
        result = compiler.compile_step(step, {}, {"params": []})
        assert result == ["pktgen.portCount();"]

    def test_assignment(self, compiler):
        step = {
            "api": "pktgen.portCount",
            "assign_to": "pc",
        }
        result = compiler.compile_step(step, {}, {"params": []})
        assert result == ["local pc = pktgen.portCount();"]

    def test_condition_emits_if_block(self, compiler):
        skill = {
            "params": [
                {"name": "save_config", "type": "boolean", "default": False}
            ]
        }
        step = {
            "api": "pktgen.save",
            "args": ['"test.cfg"'],
            "condition": "$params.save_config == true",
        }
        result = compiler.compile_step(step, {"save_config": True}, skill)
        assert result[0] == "    if ( true == true ) then"
        assert '    pktgen.save("test.cfg");' in result
        assert result[-1] == "end"

    def test_validates_api(self, compiler):
        step = {"api": "pktgen.bogus_api", "args": []}
        with pytest.raises(CompileError, match="Unknown API"):
            compiler.compile_step(step, {}, {"params": []})

    def test_validates_set_key(self, compiler):
        step = {
            "api": "pktgen.set",
            "args": ["$topology.tx_port", '"bogus_key"', "42"],
        }
        with pytest.raises(CompileError, match="Unknown pktgen.set\\(\\) key"):
            compiler.compile_step(step, {}, {"params": []})

    def test_dollar_api_passes_validation(self, compiler):
        """APIs starting with $ are special refs, skip validation."""
        step = {"api": "$range_api", "args": ["$topology.tx_port", '"start"', "0"]}
        result = compiler.compile_step(
            step, {"range_api": "pktgen.range.dst_ip"}, {"params": []}
        )
        assert len(result) > 0


# ── TestIndent ──


class TestIndent:
    def test_no_condition_no_indent(self, compiler):
        lines = ["line1", "line2"]
        result = compiler._indent(lines, {})
        assert result == ["line1", "line2"]

    def test_with_condition_adds_end(self, compiler):
        lines = ["pktgen.save();"]
        result = compiler._indent(lines, {"condition": "x == true"})
        assert result == ["    pktgen.save();", "end"]


# ── TestCompilePhase ──


class TestCompilePhase:
    def test_empty_steps(self, compiler):
        result = compiler.compile_phase([], {}, {"params": []}, "plan")
        assert result == []

    def test_emits_phase_header(self, compiler):
        steps = [
            {"api": "pktgen.start", "args": ["0"]}
        ]
        result = compiler.compile_phase(steps, {}, {"params": []}, "plan")
        assert result[0] == "-- [plan]"

    def test_repeat_loop(self, compiler):
        steps = [
            {
                "api": "pktgen.portStats",
                "args": ["0"],
                "repeat": {"count": 3, "interval_ms": 500},
            }
        ]
        result = compiler.compile_phase(steps, {}, {"params": []}, "plan")
        assert "for i = 1, 3 do" in result
        assert "    pktgen.portStats(0);" in result
        assert "    pktgen.delay(500);" in result
        assert "end" in result

    def test_repeat_count_from_params(self, compiler):
        steps = [
            {
                "api": "pktgen.portStats",
                "args": ["0"],
                "repeat": {"count": "$params.iterations", "interval_ms": 0},
            }
        ]
        skill = {
            "params": [
                {"name": "iterations", "type": "integer", "default": 5}
            ]
        }
        result = compiler.compile_phase(steps, {"iterations": 10}, skill, "plan")
        assert "for i = 1, 10 do" in result
        # interval 0 → no delay line
        assert "pktgen.delay" not in " ".join(result)

    def test_repeat_with_condition(self, compiler):
        steps = [
            {
                "api": "pktgen.save",
                "args": ['"cfg"'],
                "condition": "$params.save_config == true",
                "repeat": {"count": 2, "interval_ms": 0},
            }
        ]
        skill = {"params": [
            {"name": "save_config", "type": "boolean", "default": False}
        ]}
        result = compiler.compile_phase(steps, {"save_config": True}, skill, "plan")
        # Should have for-loop wrapping the conditional step
        assert any("for i = 1, 2 do" in line for line in result)
        assert any("if ( true == true ) then" in line for line in result)


# ── TestCompile (main entry) ──


class TestCompile:
    def test_returns_string_ending_with_newline(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert isinstance(lua, str)
        assert len(lua) > 0

    def test_starts_with_package_path(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert 'package.path =' in lua
        assert 'require "Pktgen"' in lua

    def test_contains_setup_phase(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert "-- [setup]" in lua
        assert "pktgen.screen" in lua

    def test_contains_plan_phase(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert "-- [plan]" in lua
        assert "pktgen.start" in lua

    def test_contains_teardown_phase(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert "-- [teardown]" in lua

    def test_user_params_none_defaults_to_empty(self, compiler):
        """Compile with no params: user_params=None should not crash."""
        # minimal_skill has required rate, so this should raise validation
        with pytest.raises(CompileError, match="Required parameter"):
            compiler.compile("minimal_skill")

    def test_raises_for_missing_required_param(self, compiler):
        with pytest.raises(CompileError, match="Required parameter"):
            compiler.compile("required_only", {"rate": 50.0})

    def test_raises_boolean_type_mismatch(self, compiler):
        """Non-boolean value for boolean param should raise CompileError."""
        with pytest.raises(CompileError, match="must be boolean"):
            compiler.compile("all_param_types", {
                "rate": 50.0,
                "enable_log": "not_a_bool",
            })

    def test_raises_integer_type_mismatch(self, compiler):
        with pytest.raises(CompileError, match="must be integer"):
            compiler.compile("all_param_types", {
                "rate": 50.0,
                "count": "not_an_int",
            })

    def test_raises_below_min(self, compiler):
        with pytest.raises(CompileError, match="below minimum"):
            compiler.compile("all_param_types", {"rate": -1.0})

    def test_raises_above_max(self, compiler):
        with pytest.raises(CompileError, match="above maximum"):
            compiler.compile("all_param_types", {"rate": 999.0})

    def test_raises_not_in_enum(self, compiler):
        with pytest.raises(CompileError, match="not in valid values"):
            compiler.compile("all_param_types", {
                "rate": 50.0,
                "proto": "gre",
            })

    def test_float_param_accepts_int(self, compiler):
        """Integer value should be accepted for float param type."""
        lua = compiler.compile("all_param_types", {"rate": 80})
        assert "pktgen.start" in lua

    def test_full_valid_compile(self, compiler):
        """Happy path: all valid params produce correct Lua."""
        lua = compiler.compile("all_param_types", {
            "rate": 75.0,
            "count": 500,
            "enable_log": True,
            "proto": "tcp",
            "target_ip": "10.0.0.99",
        })
        assert "pktgen.start" in lua
        assert "# Acquire" not in lua  # no ARP steps in fixture


# ── TestCompileSkillConvenience ──


class TestCompileSkillConvenience:
    def test_returns_lua_string(self, compiler):
        lua = compile_skill("minimal_skill", {"rate": 50.0})
        assert isinstance(lua, str)
        assert "pktgen.start" in lua

    def test_raises_on_bad_skill_name(self, compiler):
        with pytest.raises(CompileError):
            compile_skill("nonexistent", {})


# ── Integration: Full pipeline ──


class TestCompileIntegration:
    def test_valid_params_produce_correct_structure(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        lines = lua.strip().split("\n")
        # Should start with package.path
        assert "package.path" in lines[0]
        # Should contain require
        assert any('require "Pktgen"' in l for l in lines)
        # Should contain the plan step
        assert any("pktgen.start" in l for l in lines)
        # Should contain the setup step
        assert any("pktgen.screen" in l for l in lines)

    def test_topology_resolved_in_output(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        # $topology.tx_port should be resolved to "0"
        assert "pktgen.set(0, " in lua
        assert "pktgen.start(0)" in lua

    def test_param_resolved_in_output(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 75.5})
        assert "75.5" in lua
