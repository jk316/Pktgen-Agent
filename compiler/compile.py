"""
Pktgen Skill Compiler
Reads a skill YAML + user params → resolves topology/params → emits Lua code.

Input:  skill_name="udp_flood", params={rate: 80, pktSize: 512}
Output: Complete Lua script string ready for pktgen execution.

Grounded in:
  - dsl/schema.yaml    (API whitelist, enums, key validation)
  - dsl/mapping.yaml   (step→Lua compilation rules)
  - dsl/skills/*.yaml  (skill templates)
  - topology.yaml      (physical port mapping)
  - knowledge/         (reference — used for cross-checking)
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths relative to this file
BASE_DIR = Path(__file__).resolve().parent.parent
DSL_DIR = BASE_DIR / "dsl"
SKILLS_DIR = DSL_DIR / "skills"
SCHEMA_PATH = DSL_DIR / "schema.yaml"
TOPOLOGY_PATH = BASE_DIR / "topology.yaml"


class CompileError(Exception):
    """Raised when compilation fails due to validation or resolution errors."""
    pass


class SkillCompiler:
    """
    Compiles a skill file + user parameters → executable Lua code.

    Usage:
        compiler = SkillCompiler()
        lua = compiler.compile("udp_flood", {"rate": 80, "pktSize": 512})
    """

    def __init__(self, topology_path: Optional[Path] = None):
        self.topology_path = topology_path or TOPOLOGY_PATH
        self._topology = None
        self._schema = None
        self._valid_apis = None

    @property
    def topology(self) -> Dict:
        if self._topology is None:
            with open(self.topology_path) as f:
                self._topology = yaml.safe_load(f)
        return self._topology

    @property
    def schema(self) -> Dict:
        if self._schema is None:
            with open(SCHEMA_PATH) as f:
                self._schema = yaml.safe_load(f)
        return self._schema

    @property
    def valid_apis(self) -> set:
        """Flattened set of all valid API function names from schema.yaml."""
        if self._valid_apis is None:
            apis = set()
            for category, funcs in self.schema.get("valid_apis", {}).items():
                for func in funcs:
                    apis.add(func)
            # Add utility functions
            apis.add("printf")
            apis.add("prints")
            self._valid_apis = apis
        return self._valid_apis

    def load_skill(self, skill_name: str) -> Dict:
        """Load a skill YAML file by name."""
        skill_path = SKILLS_DIR / f"{skill_name}.yaml"
        if not skill_path.exists():
            raise CompileError(f"Skill not found: {skill_name} (expected at {skill_path})")
        with open(skill_path) as f:
            data = yaml.safe_load(f)
        return data.get("skill", data)

    def validate_api(self, api_name: str) -> None:
        """Check that an API function exists in the schema whitelist."""
        if api_name not in self.valid_apis and not api_name.startswith("$"):
            raise CompileError(f"Unknown API function: '{api_name}'. Not found in dsl/schema.yaml valid_apis.")

    def validate_set_key(self, key: str) -> None:
        """Check that a pktgen.set() key is valid."""
        valid_keys = [k["key"] for k in self.schema.get("valid_set_keys", [])]
        if key not in valid_keys:
            raise CompileError(f"Unknown pktgen.set() key: '{key}'. Valid keys: {valid_keys}")

    def resolve_topology(self, value: str) -> str:
        """Replace $topology.<name> with physical portlist."""
        pattern = r"\$topology\.(\w+)"
        def replacer(match):
            name = match.group(1)
            if name not in self.topology:
                raise CompileError(f"Undefined topology reference: '{name}'. Available: {list(self.topology.keys())}")
            return self.topology[name]["portlist"]
        return re.sub(pattern, replacer, value)

    def resolve_params(self, value: str, user_params: Dict, skill_params: List[Dict]) -> str:
        """Replace $params.<name> with user-supplied value or default."""
        pattern = r"\$params\.(\w+)"
        def replacer(match):
            name = match.group(1)
            if name in user_params:
                return self._to_lua_literal(user_params[name])
            # Look up default from skill params definition
            for p in skill_params:
                if p.get("name") == name:
                    if "default" in p:
                        return self._to_lua_literal(p["default"])
                    raise CompileError(
                        f"Parameter '{name}' is required but not provided. "
                        f"Available params: {[p['name'] for p in skill_params]}"
                    )
            raise CompileError(f"Undefined parameter reference: '{name}'")
        return re.sub(pattern, replacer, value)

    def resolve_special(self, value: str, skill: Dict, user_params: Dict) -> str:
        """Resolve special references like $seq_index, $sequence_count, $range_api."""
        # $seq_index — handled at compile time by the caller for each sequence entry
        # $sequence_count — resolved to the number of sequence entries
        if "$sequence_count" in value:
            seq_param = user_params.get("sequences", [])
            count = len(seq_param)
            value = value.replace("$sequence_count", str(count))
        return value

    def _to_lua_literal(self, value: Any) -> str:
        """Convert a Python value to its Lua literal representation."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            # If already quoted, return as-is; otherwise quote
            if value.startswith('"') and value.endswith('"'):
                return value
            # If it's a topology/param ref, don't quote
            if value.startswith("$"):
                return value
            return f'"{value}"'
        elif isinstance(value, (int, float)):
            return str(value)
        elif value is None:
            return "nil"
        else:
            return f'"{value}"'

    def compile_step(self, step: Dict, user_params: Dict, skill: Dict) -> List[str]:
        """Compile a single DSL step into one or more Lua lines."""
        lines = []

        # Skip steps marked as skip or without an API (comment-only steps)
        if step.get("skip") or not step.get("api"):
            return lines

        # Skip steps with unmet conditions
        if "condition" in step and step["condition"]:
            condition = self.resolve_topology(step["condition"])
            condition = self.resolve_params(condition, user_params, skill.get("params", []))
            # Emit the if-statement wrapper
            lines.append(f"if ( {condition} ) then")

        api = step.get("api", "")
        args = step.get("args", [])
        assign_to = step.get("assign_to", None)
        table_data = step.get("table_data", None)
        table_name = step.get("table_name", "tbl")
        comment = step.get("comment", "")

        # Resolve API (e.g., $range_api → pktgen.range.dst_ip)
        api = self.resolve_params(api, user_params, skill.get("params", []))
        api = self.resolve_topology(api)

        # Validate API exists (skip for special refs resolved at runtime)
        if not api.startswith("$") and api not in ("printf", "prints"):
            self.validate_api(api)

        # Resolve args
        resolved_args = []
        for arg in args:
            arg_str = str(arg)
            arg_str = self.resolve_topology(arg_str)
            arg_str = self.resolve_params(arg_str, user_params, skill.get("params", []))
            arg_str = self.resolve_special(arg_str, skill, user_params)
            resolved_args.append(arg_str)

        # Validate pktgen.set() keys
        if api == "pktgen.set" and len(resolved_args) >= 2:
            key = resolved_args[1].strip('"')
            self.validate_set_key(key)

        # ── Emit Lua based on step type ──

        # seqTable call — emit table literal first
        if api == "pktgen.seqTable" and table_data:
            lines.append(f"local {table_name} = {{")
            td = table_data
            # If table_data is a string ref like "$params.sequences[$seq_index]", just emit a placeholder
            if isinstance(td, str) and td.startswith("$"):
                lines.append(f"  -- table data from {td}")
            elif isinstance(td, dict):
                for k, v in td.items():
                    lines.append(f'    ["{k}"] = {self._to_lua_literal(v)},')
            lines.append("};")
            lines.append(f"pktgen.seqTable({', '.join(resolved_args[:2])}, {table_name});")
            return self._indent(lines, step)

        # Assignment call: local var = api(...)
        if assign_to:
            lines.append(f"local {assign_to} = {api}({', '.join(resolved_args)});")
            return self._indent(lines, step)

        # No-args call
        if not resolved_args:
            lines.append(f"{api}();")
            return self._indent(lines, step)

        # Direct call
        lines.append(f"{api}({', '.join(resolved_args)});")

        return self._indent(lines, step)

    def _indent(self, lines: List[str], step: Dict) -> List[str]:
        """Apply indentation if inside a condition block."""
        if "condition" in step:
            return [f"    {l}" for l in lines] + ["end"]
        return lines

    def compile_phase(self, steps: List[Dict], user_params: Dict, skill: Dict, phase_name: str) -> List[str]:
        """Compile a list of steps (setup/plan/teardown)."""
        lua_lines = []
        if not steps:
            return lua_lines

        lua_lines.append(f"-- [{phase_name}]")
        for step in steps:
            # Handle repeat
            if "repeat" in step:
                repeat_cfg = step.pop("repeat", {})
                count = repeat_cfg.get("count", 1)
                interval = repeat_cfg.get("interval_ms", 0)

                # Resolve count if it's a param ref
                count_str = str(count)
                count_str = self.resolve_params(count_str, user_params, skill.get("params", []))
                try:
                    count = int(count_str)
                except ValueError:
                    count = 1

                lua_lines.append(f"for i = 1, {count} do")
                inner = self.compile_step(step, user_params, skill)
                lua_lines.extend([f"    {l}" for l in inner])
                if interval:
                    interval_str = self.resolve_params(str(interval), user_params, skill.get("params", []))
                    lua_lines.append(f"    pktgen.delay({interval_str});")
                lua_lines.append("end")
            else:
                lua_lines.extend(self.compile_step(step, user_params, skill))

        return lua_lines

    def compile(self, skill_name: str, user_params: Optional[Dict] = None) -> str:
        """
        Compile a skill into executable Lua code.

        Args:
            skill_name: Name of the skill (matches filename without .yaml)
            user_params: User-supplied parameter values

        Returns:
            Complete Lua script string
        """
        if user_params is None:
            user_params = {}

        skill = self.load_skill(skill_name)
        skill_params = skill.get("params", [])

        # ── Phase 1: Validate user params against skill schema ──
        for p in skill_params:
            pname = p["name"]
            if p.get("required", False) and pname not in user_params:
                raise CompileError(f"Required parameter '{pname}' not provided for skill '{skill_name}'")

            if pname in user_params:
                val = user_params[pname]
                ptype = p.get("type", "string")
                constraints = p.get("constraints", {})

                # Type check
                if ptype == "integer" and not isinstance(val, int):
                    raise CompileError(f"Parameter '{pname}' must be integer, got {type(val).__name__}")
                if ptype == "float" and not isinstance(val, (int, float)):
                    raise CompileError(f"Parameter '{pname}' must be number, got {type(val).__name__}")

                # Range check
                if "min" in constraints and val < constraints["min"]:
                    raise CompileError(f"Parameter '{pname}'={val} below minimum {constraints['min']}")
                if "max" in constraints and val > constraints["max"]:
                    raise CompileError(f"Parameter '{pname}'={val} above maximum {constraints['max']}")

                # Enum check
                if "enum" in constraints and val not in constraints["enum"]:
                    raise CompileError(
                        f"Parameter '{pname}'='{val}' not in valid values: {constraints['enum']}"
                    )

        # ── Phase 2: Emit Lua ──
        lua = []
        # Prologue
        lua.append('package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"')
        lua.append("")
        lua.append('require "Pktgen"')
        lua.append("")

        # Setup
        lua.extend(self.compile_phase(
            skill.get("setup", []), user_params, skill, "setup"
        ))
        if skill.get("setup"):
            lua.append("")

        # Plan
        lua.extend(self.compile_phase(
            skill.get("plan", []), user_params, skill, "plan"
        ))
        if skill.get("plan"):
            lua.append("")

        # Teardown
        lua.extend(self.compile_phase(
            skill.get("teardown", []), user_params, skill, "teardown"
        ))

        return "\n".join(lua) + "\n"


# ── Convenience function ──

def compile_skill(skill_name: str, params: Optional[Dict] = None) -> str:
    """Compile a skill to Lua. Raises CompileError on validation failure."""
    compiler = SkillCompiler()
    return compiler.compile(skill_name, params)
