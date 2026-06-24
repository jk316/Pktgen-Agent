"""
Unit tests for pktgen_agent.compiler.compile — SkillCompiler class.

Covers: __init__, topology, schema, valid_apis, load_skill, validate_api,
validate_set_key, resolve_topology, resolve_params, resolve_special,
_to_lua_literal, compile_step, _indent, compile_phase, compile.
"""

import pytest
from pktgen_agent.compiler.compile import SkillCompiler, CompileError, compile_skill


# ── TestSkillCompilerInit ──


class TestSkillCompilerInit:
    def test_default_init(self, test_data_dir):
        """Default constructor works with patched paths."""
        c = SkillCompiler()
        assert c._topology_path is not None
        assert str(c._topology_path).endswith("topology.yaml")

    def test_custom_topology_path(self, tmp_path):
        custom = tmp_path / "custom_topo.yaml"
        c = SkillCompiler(topology_path=custom)
        assert c._topology_path == custom

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
        c = SkillCompiler(topology_path=tmp_path / "nonexistent.yaml")
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


# ── TestValidApisProperty ──


class TestValidApisProperty:
    def test_includes_pktgen_start(self, compiler):
        apis = compiler.valid_apis
        assert "pktgen.start" in apis
        assert "pktgen.stop" in apis
        assert "pktgen.set" in apis

    def test_includes_utility_functions(self, compiler):
        apis = compiler.valid_apis
        assert "printf" in apis
        assert "prints" in apis


# ── TestLoadSkill ──


class TestLoadSkill:
    def test_loads_minimal_skill(self, compiler):
        skill = compiler.load_skill("minimal_skill")
        assert skill["name"] == "minimal_skill"
        assert "params" in skill
        assert "plan" in skill

    def test_raises_for_missing_skill(self, compiler):
        with pytest.raises(CompileError) as e:
            compiler.load_skill("nonexistent_skill")
        assert "nonexistent_skill" in str(e.value)


# ── TestValidateApi ──


class TestValidateApi:
    def test_valid_api_passes(self, compiler):
        compiler.validate_api("pktgen.start")  # no raise

    def test_invalid_api_raises(self, compiler):
        with pytest.raises(CompileError, match="Unknown API"):
            compiler.validate_api("pktgen.fake_api")

    def test_ref_prefix_bypasses_validation(self, compiler):
        # $range_api references are resolved at runtime, skip validation
        compiler.validate_api("$range_api")  # no raise


# ── TestValidateSetKey ──


class TestValidateSetKey:
    def test_valid_key_passes(self, compiler):
        compiler.validate_set_key("count")  # no raise

    def test_valid_key_rate(self, compiler):
        compiler.validate_set_key("rate")  # no raise

    def test_invalid_key_raises(self, compiler):
        with pytest.raises(CompileError, match="Unknown pktgen.set"):
            compiler.validate_set_key("nonexistent_key")


# ── TestResolveTopology ──


class TestResolveTopology:
    def test_resolves_tx_port(self, compiler):
        result = compiler.resolve_topology("$topology.tx_port")
        assert result == "0"

    def test_resolves_rx_port(self, compiler):
        result = compiler.resolve_topology("$topology.rx_port")
        assert result == "1"

    def test_raises_for_undefined(self, compiler):
        with pytest.raises(CompileError, match="Undefined topology"):
            compiler.resolve_topology("$topology.undefined")

    def test_no_dollar_unchanged(self, compiler):
        result = compiler.resolve_topology("pktgen.start")
        assert result == "pktgen.start"


# ── TestResolveParams ──


class TestResolveParams:
    def test_resolves_user_value(self, compiler):
        user = {"rate": 80}
        result = compiler.resolve_params("$params.rate", user, [])
        assert result == "80"

    def test_resolves_string_value(self, compiler):
        user = {"dst_ip": "10.0.0.1"}
        result = compiler.resolve_params("$params.dst_ip", user, [])
        assert result == '"10.0.0.1"'

    def test_uses_default(self, compiler):
        skill_params = [{"name": "rate", "default": 50.0}]
        result = compiler.resolve_params("$params.rate", {}, skill_params)
        assert result == "50.0"

    def test_raises_for_missing_required(self, compiler):
        skill_params = [{"name": "rate"}]
        with pytest.raises(CompileError, match="required"):
            compiler.resolve_params("$params.rate", {}, skill_params)

    def test_raises_for_undefined(self, compiler):
        with pytest.raises(CompileError, match="Undefined parameter"):
            compiler.resolve_params("$params.undefined", {}, [])


# ── TestResolveSpecial ──


class TestResolveSpecial:
    def test_resolves_sequence_count(self, compiler):
        user = {"sequences": [{}, {}, {}]}
        result = compiler.resolve_special("$sequence_count", {}, user)
        assert "3" in result

    def test_sequence_count_zero(self, compiler):
        user = {"sequences": []}
        result = compiler.resolve_special("$sequence_count", {}, user)
        assert "0" in result


# ── TestToLuaLiteral ──


class TestToLuaLiteral:
    def test_bool_true(self, compiler):
        assert compiler._to_lua_literal(True) == "true"

    def test_bool_false(self, compiler):
        assert compiler._to_lua_literal(False) == "false"

    def test_int(self, compiler):
        assert compiler._to_lua_literal(42) == "42"

    def test_float(self, compiler):
        assert compiler._to_lua_literal(3.14) == "3.14"

    def test_string(self, compiler):
        assert compiler._to_lua_literal("hello") == '"hello"'

    def test_none(self, compiler):
        assert compiler._to_lua_literal(None) == "nil"

    def test_dollar_ref_unchanged(self, compiler):
        assert compiler._to_lua_literal("$params.foo") == "$params.foo"

    def test_escapes_embedded_quotes(self, compiler):
        result = compiler._to_lua_literal('he said "hi"')
        assert result == '"he said \\"hi\\""'

    def test_escapes_backslashes(self, compiler):
        result = compiler._to_lua_literal("C:\\path\\to")
        assert result == '"C:\\\\path\\\\to"'

    def test_raises_for_dict(self, compiler):
        with pytest.raises(CompileError, match="Cannot convert"):
            compiler._to_lua_literal({"key": "value"})


# ── TestCompileStep ──


class TestCompileStep:
    def test_skips_step_with_skip_true(self, compiler):
        step = {"skip": True, "api": "pktgen.start"}
        lines = compiler.compile_step(step, {}, {"params": []})
        assert lines == []

    def test_skips_step_without_api(self, compiler):
        step = {"comment": "documentation only"}
        lines = compiler.compile_step(step, {}, {"params": []})
        assert lines == []

    def test_direct_call(self, compiler):
        step = {"api": "pktgen.start", "args": ["$topology.tx_port"]}
        lines = compiler.compile_step(step, {}, {"params": []})
        assert len(lines) == 1
        assert "pktgen.start(0)" in "".join(lines)

    def test_no_args_call(self, compiler):
        step = {"api": "pktgen.screen", "args": ["off"]}
        lines = compiler.compile_step(step, {}, {"params": []})
        assert "off" in "".join(lines)

    def test_assignment(self, compiler):
        step = {"api": "pktgen.range.dst_ip", "args": ["$topology.tx_port", "start", "$params.start"], "assign_to": "result"}
        user = {"start": "10.0.0.1"}
        lines = compiler.compile_step(step, user, {"params": [{"name": "start"}]})
        assert "local result = " in "".join(lines)


# ── TestIndent ──


class TestIndent:
    def test_no_condition_no_indent(self, compiler):
        lines = ["line1;", "line2;"]
        result = compiler._indent(lines, {})
        assert result == lines

    def test_with_condition_adds_end(self, compiler):
        lines = ["line1;"]
        step = {"condition": "true"}
        result = compiler._indent(lines, step)
        assert result[0].startswith("    ")
        assert "end" in result


# ── TestCompilePhase ──


class TestCompilePhase:
    def test_empty_steps(self, compiler):
        lines = compiler.compile_phase([], {}, {"params": []}, "setup")
        assert lines == []

    def test_adds_phase_comment(self, compiler):
        steps = [{"api": "pktgen.start", "args": ["$topology.tx_port"]}]
        lines = compiler.compile_phase(steps, {}, {"params": []}, "setup")
        assert "-- [setup]" in lines

    def test_handles_repeat(self, compiler):
        steps = [{"api": "pktgen.start", "args": ["$topology.tx_port"], "repeat": {"count": 3}}]
        lines = compiler.compile_phase(steps, {}, {"params": []}, "plan")
        assert "for i = 1, 3 do" in lines
        assert "end" in lines

    def test_repeat_does_not_mutate_step(self, compiler):
        """Regression test: step.pop() was silently removing repeat config."""
        step = {"api": "pktgen.start", "args": ["$topology.tx_port"], "repeat": {"count": 5}}
        steps = [step]
        compiler.compile_phase(steps, {}, {"params": []}, "plan")
        # After compilation, the step dict should still have its 'repeat' key
        assert "repeat" in step
        assert step["repeat"]["count"] == 5


# ── TestCompile ──


class TestCompile:
    def test_compiles_minimal_skill(self, compiler):
        lua = compiler.compile("minimal_skill", {"rate": 50.0})
        assert "package.path" in lua
        assert 'require "Pktgen"' in lua
        assert "-- [plan]" in lua

    def test_raises_for_missing_required(self, compiler):
        with pytest.raises(CompileError, match="Required parameter"):
            compiler.compile("required_only", {})

    def test_validates_type_boolean(self, compiler):
        with pytest.raises(CompileError, match="boolean"):
            compiler.compile("all_param_types", {"rate": 50.0, "enable_log": "not_a_bool"})

    def test_validates_type_integer(self, compiler):
        with pytest.raises(CompileError, match="integer"):
            compiler.compile("all_param_types", {"rate": 50.0, "count": 3.14})

    def test_validates_range(self, compiler):
        with pytest.raises(CompileError, match="below minimum"):
            compiler.compile("all_param_types", {"rate": 50.0, "count": 0})

    def test_validates_range_max(self, compiler):
        with pytest.raises(CompileError, match="above maximum"):
            compiler.compile("all_param_types", {"rate": 50.0, "count": 99999})

    def test_validates_enum(self, compiler):
        with pytest.raises(CompileError, match="not in valid values"):
            compiler.compile("all_param_types", {"rate": 50.0, "proto": "invalid_option"})

    def test_allows_valid_params(self, compiler):
        lua = compiler.compile("all_param_types", {
            "enable_log": True,
            "count": 50,
            "rate": 50.0,
            "proto": "tcp",
        })
        assert 'require "Pktgen"' in lua


# ── TestCompileSkillConvenience ──


@pytest.mark.usefixtures("test_data_dir")
class TestCompileSkillConvenience:
    def test_returns_lua_string(self):
        lua = compile_skill("minimal_skill", {"rate": 50.0})
        assert isinstance(lua, str)
        assert len(lua) > 0

    def test_raises_for_bad_skill(self):
        with pytest.raises(CompileError):
            compile_skill("nonexistent", {})
