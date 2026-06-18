"""
Pktgen Agent Tools
Exposes all skill tools for use with LangChain ReAct agents.

Usage:
    from tools import create_tools

    # Read host/port from topology.yaml (default: 10.99.80.222:22022)
    # dry_run=True by default — compiles Lua but doesn't send to Pktgen
    tools = create_tools()

    # Live execution against a specific Pktgen instance
    tools = create_tools(pktgen_host="10.99.80.222", dry_run=False)

    # With LangChain agent
    from langchain.agents import create_react_agent
    agent = create_react_agent(llm, tools, prompt)
"""

import yaml
from pathlib import Path

from .execute import create_all_tools, create_skill_tool, execute_skill_dry_run, execute_skill_live, compile_skill_lua


def _load_topology_config():
    """Read pktgen host/port from topology.yaml."""
    topology_path = Path(__file__).resolve().parent.parent / "topology.yaml"
    with open(topology_path) as f:
        data = yaml.safe_load(f)
    pktgen_cfg = data.get("pktgen", {})
    return pktgen_cfg.get("host", "localhost"), pktgen_cfg.get("port", 22022)


# Pre-built tool list (dry_run by default — safe to use without pktgen)
ALL_TOOLS = create_all_tools(dry_run=True)


def create_tools(pktgen_host=None, pktgen_port=None, dry_run=True):
    """
    Create all skill tools.

    Args:
        pktgen_host: Pktgen host (default: from topology.yaml)
        pktgen_port: Pktgen TCP port (default: from topology.yaml)
        dry_run: If True, compile Lua without connecting to Pktgen (default: True)
    """
    if pktgen_host is None or pktgen_port is None:
        default_host, default_port = _load_topology_config()
        if pktgen_host is None:
            pktgen_host = default_host
        if pktgen_port is None:
            pktgen_port = default_port
    return create_all_tools(pktgen_host=pktgen_host, pktgen_port=pktgen_port, dry_run=dry_run)
