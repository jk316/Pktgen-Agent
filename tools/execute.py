"""
Pktgen Skill Tool Factory
Reads dsl/skills/*.yaml and creates LangChain StructuredTool instances.
Each tool compiles the skill → sends Lua via socket → returns result.

Usage:
    from tools.execute import create_all_tools, execute_skill

    tools = create_all_tools(pktgen_host="192.168.1.100", pktgen_port=22022)
    # tools is a list of langchain_core.tools.BaseTool
"""

from __future__ import annotations

import os
import sys
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from pydantic import BaseModel

# Ensure compiler is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compiler.compile import SkillCompiler, CompileError
from pktgen_client import PktgenClient, execute_lua

# ── LangChain imports (optional — tools work standalone too) ──
try:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field, create_model
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "dsl" / "skills"

PYTHON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "enum": str,
    "mac_address": str,
    "ip_address": str,
    "portlist": str,
    "table": list,
}

# ── Inline execution (no socket) ──

compiler = SkillCompiler()


def compile_skill_lua(skill_name: str, params: Dict[str, Any]) -> str:
    """Compile a skill to Lua. Raises CompileError on validation failure."""
    return compiler.compile(skill_name, params)


def execute_skill_dry_run(skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compile skill and return Lua without executing against live Pktgen.
    Useful for testing and offline code generation.
    """
    lua_code = compiler.compile(skill_name, params)
    return {
        "success": True,
        "skill": skill_name,
        "params": params,
        "lua_code": lua_code,
        "mode": "dry_run",
    }


def execute_skill_live(
    skill_name: str,
    params: Dict[str, Any],
    host: str = "localhost",
    port: int = 22022,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Compile skill and execute against a running Pktgen instance via TCP socket.

    Returns:
        Dict with keys: success, skill, params, lua_code, response, mode
    """
    lua_code = compiler.compile(skill_name, params)
    try:
        response = execute_lua(host=host, port=port, lua_code=lua_code, timeout=timeout)
        return {
            "success": True,
            "skill": skill_name,
            "params": params,
            "lua_code": lua_code,
            "response": response,
            "mode": "live",
        }
    except ConnectionError as e:
        return {
            "success": False,
            "skill": skill_name,
            "error": f"Connection failed: {e}",
            "lua_code": lua_code,
            "mode": "live",
        }
    except Exception as e:
        return {
            "success": False,
            "skill": skill_name,
            "error": str(e),
            "lua_code": lua_code,
            "mode": "live",
        }


# ── Tool Factory ──

def _load_skill_meta(skill_name: str) -> Dict:
    """Load a skill YAML and extract metadata for tool creation."""
    skill_path = SKILLS_DIR / f"{skill_name}.yaml"
    with open(skill_path) as f:
        data = yaml.safe_load(f)
    return data.get("skill", data)


def _build_pydantic_model(skill_name: str, params_def: List[Dict]) -> Type[BaseModel]:
    """Dynamically create a Pydantic model from skill params definition."""
    if not HAS_LANGCHAIN:
        return None

    fields = {}
    for p in params_def:
        pname = p["name"]
        ptype_str = p.get("type", "string")
        ptype = PYTHON_TYPE_MAP.get(ptype_str, str)
        description = p.get("description", "")
        required = p.get("required", False)
        default = p.get("default", None)

        if required:
            fields[pname] = (ptype, Field(description=description))
        else:
            fields[pname] = (ptype, Field(default=default, description=description))

    model_name = f"{skill_name}_Input".replace("_", " ").title().replace(" ", "")
    return create_model(model_name, **fields)


def create_skill_tool(
    skill_name: str,
    pktgen_host: str = "localhost",
    pktgen_port: int = 22022,
    dry_run: bool = False,
):
    """
    Create a LangChain StructuredTool for a given skill.

    Args:
        skill_name: Skill name (matches filename without .yaml)
        pktgen_host: Pktgen hostname for live execution
        pktgen_port: Pktgen TCP port
        dry_run: If True, only compile Lua without executing

    Returns:
        langchain_core.tools.StructuredTool, or None if langchain not installed
    """
    meta = _load_skill_meta(skill_name)
    params_def = meta.get("params", [])
    description = meta.get("description", f"Execute {skill_name}")

    # Append parameter docs to description
    param_docs = "\n\nParameters:"
    for p in params_def:
        req = " (required)" if p.get("required") else ""
        default = f" [default: {p['default']}]" if "default" in p else ""
        param_docs += f"\n  - {p['name']}: {p.get('type','string')}{req}{default} — {p.get('description','')}"
    full_description = description + param_docs

    if not HAS_LANGCHAIN:
        # Return a plain callable without langchain dependency
        def tool_func(**kwargs):
            if dry_run:
                return execute_skill_dry_run(skill_name, kwargs)
            return execute_skill_live(skill_name, kwargs, host=pktgen_host, port=pktgen_port)
        tool_func.__name__ = skill_name
        tool_func.__doc__ = full_description
        return tool_func

    # Build Pydantic args schema dynamically
    ArgsModel = _build_pydantic_model(skill_name, params_def)

    def executor(**kwargs):
        if dry_run:
            return execute_skill_dry_run(skill_name, kwargs)
        return execute_skill_live(skill_name, kwargs, host=pktgen_host, port=pktgen_port)

    executor.__name__ = skill_name

    return StructuredTool.from_function(
        func=executor,
        name=skill_name,
        description=full_description,
        args_schema=ArgsModel,
    )


def create_all_tools(
    pktgen_host: str = "localhost",
    pktgen_port: int = 22022,
    dry_run: bool = False,
) -> List:
    """
    Create LangChain tools for all skills found in dsl/skills/.

    Args:
        pktgen_host: Pktgen hostname
        pktgen_port: Pktgen TCP port
        dry_run: If True, generate Lua without connecting to Pktgen

    Returns:
        List of callables (or StructuredTools if langchain is installed)
    """
    tools = []
    for skill_file in sorted(SKILLS_DIR.glob("*.yaml")):
        skill_name = skill_file.stem
        tool = create_skill_tool(
            skill_name,
            pktgen_host=pktgen_host,
            pktgen_port=pktgen_port,
            dry_run=dry_run,
        )
        tools.append(tool)
    return tools
