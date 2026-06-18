"""
Pktgen Agent Tools
Exposes all skill tools for use with LangChain ReAct agents.

Usage:
    from tools import ALL_TOOLS, create_tools

    # Default: localhost, dry_run (no live pktgen needed)
    tools = create_tools()

    # Live execution against a pktgen instance
    tools = create_tools(pktgen_host="192.168.1.100", dry_run=False)

    # With LangChain agent
    from langchain.agents import create_react_agent
    agent = create_react_agent(llm, tools, prompt)
"""

from .execute import create_all_tools, create_skill_tool, execute_skill_dry_run, execute_skill_live, compile_skill_lua

# Pre-built tool list (dry_run by default — safe to use without pktgen)
ALL_TOOLS = create_all_tools(dry_run=True)


def create_tools(pktgen_host="localhost", pktgen_port=22022, dry_run=True):
    """Convenience: create tools with specified config."""
    return create_all_tools(host=pktgen_host, port=pktgen_port, dry_run=dry_run)
