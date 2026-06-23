#!/usr/bin/env python3
"""
Pktgen ReAct Agent — LangChain ReAct agent for Pktgen traffic generation.

Usage:
    # Dry-run (default): compile skills to Lua without connecting to Pktgen
    python agent.py

    # Live mode: connect to a running Pktgen instance
    python agent.py --live

    # Custom host
    python agent.py --live --host 192.168.1.100
"""

import argparse
import os
import sys
from pathlib import Path


def _load_dotenv():
    """Load environment variables from .env file, if it exists."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # Fallback: parse .env manually
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value


def _load_topology_config():
    """Read pktgen host/port from topology.yaml."""
    import yaml
    topology_path = Path(__file__).resolve().parent / "topology.yaml"
    with open(topology_path) as f:
        data = yaml.safe_load(f)
    cfg = data.get("pktgen", {})
    return cfg.get("host", "localhost"), cfg.get("port", 22022)


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    for pkg, import_name in [
        ("pyyaml", "yaml"),
        ("langchain-core", "langchain_core"),
        ("langchain", "langchain"),
        ("langchain-openai", "langchain_openai"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        return False, f"Missing packages: {', '.join(missing)}\n  pip install {' '.join(missing)}"
    return True, ""


def create_agent(llm, tools, verbose=True):
    """Create a LangChain ReAct agent with the Pktgen system prompt."""
    from agent_prompt import SYSTEM_PROMPT
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain_core.prompts import PromptTemplate

    # create_react_agent injects {agent_scratchpad} as a STRING via
    # format_log_to_str(), so we must use PromptTemplate (string template),
    # NOT ChatPromptTemplate — its MessagesPlaceholder expects List[BaseMessage]
    # and raises "agent_scratchpad should be a list of base messages, got str".
    # {tools} and {tool_names} are also injected by the framework.
    template = SYSTEM_PROMPT + """

You have access to the following tools. Each tool name is followed by its
parameter schema in JSON.

{tools}

Valid tool names: {tool_names}

Use the following ReAct format strictly:

Question: the input request you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action as a VALID JSON object
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original request

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

    prompt = PromptTemplate.from_template(template)
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=15,
    )


def get_llm(model: str):
    """Create a DeepSeek LLM instance (OpenAI-compatible API)."""
    from langchain_openai import ChatOpenAI

    _load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found in environment or .env file.")
        print("  Add to .env: DEEPSEEK_API_KEY=sk-...")
        sys.exit(1)

    return ChatOpenAI(
        model=model,
        temperature=0,
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Pktgen ReAct Agent — control a DPDK packet generator with natural language.",
    )
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="Execute against a running Pktgen instance (default: dry-run)"
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Pktgen hostname or IP (default: from topology.yaml)"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Pktgen TCP port (default: from topology.yaml)"
    )
    parser.add_argument(
        "--model", type=str, default="deepseek-v4-flash",
        help="DeepSeek model name (default: deepseek-v4-flash)"
    )
    args = parser.parse_args()

    # ── Dependency check ──
    ok, msg = check_dependencies()
    if not ok:
        print(msg, file=sys.stderr)
        sys.exit(1)

    # ── Resolve host/port ──
    default_host, default_port = _load_topology_config()
    host = args.host or default_host
    port = args.port or default_port
    dry_run = not args.live

    # ── Import after dependency check ──
    from tools import create_tools

    # ── Create tools ──
    mode_str = "DRY-RUN" if dry_run else f"LIVE → {host}:{port}"
    print(f"Pktgen Agent — {mode_str}")
    print(f"Model: {args.model}")
    print(f"Loading tools...")

    tools = create_tools(pktgen_host=host, pktgen_port=port, dry_run=dry_run)
    print(f"Tools loaded: {len(tools)} skills\n")

    # ── Create agent ──
    llm = get_llm(args.model)
    executor = create_agent(llm, tools)

    # ── Interactive loop ──
    print("Enter a traffic generation request, or Ctrl+C / 'quit' to exit.\n")
    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not cmd:
            continue
        if cmd.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        try:
            result = executor.invoke({"input": cmd})
            print(f"\n{result['output']}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
