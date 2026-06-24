# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Pktgen Agent — an AI agent controller for [Pktgen-DPDK](https://pktgen.github.io/Pktgen-DPDK/) (a DPDK-based packet generator). Translates natural language traffic-generation requests into executable Lua scripts via a Skill DSL compiler, then sends them to a running Pktgen instance over TCP (port 22022). Uses LangChain V1.0 `create_agent` (LangGraph-backed) with native tool calling.

## Commands

```bash
# Run the agent (dry-run by default — compiles Lua without connecting to Pktgen)
python -m pktgen_agent.agent
# or: python agent.py

# Live mode (connects to Pktgen at topology.yaml host:port)
python -m pktgen_agent.agent --live

# Custom host and model
python -m pktgen_agent.agent --live --host 192.168.1.100 --model deepseek-v4-flash

# Debug logging
python -m pktgen_agent.agent --live --verbose

# Run all tests (requires -p no:asyncio due to pytest-asyncio compatibility)
python -m pytest tests/ -p no:asyncio

# Run a single test file
python -m pytest tests/test_compile.py -p no:asyncio -v

# Run tests with coverage
python -m pytest tests/ -p no:asyncio --cov=pktgen_agent --cov-report=term-missing

# Run only unit tests (skip langchain-dependent tests)
python -m pytest tests/ -p no:asyncio -m "not langchain"
```

## Architecture

```
User Request → LangChain V1.0 Agent (LangGraph StateGraph)
                 ├─ System prompt (pktgen_agent/agent_prompt.py)
                 ├─ Tool: e.g. udp_flood(rate=80) (pktgen_agent/tools/)
                 │    ├─ SkillCompiler validates params against dsl/schema.yaml
                 │    ├─ Compiles dsl/skills/<name>.yaml → Lua code
                 │    └─ PktgenClient sends Lua over TCP → returns response
                 └─ Knowledge base (knowledge/*.yaml) grounds the DSL
```

**Four-layer stack:**

| Layer | Location | Role |
|-------|----------|------|
| Knowledge Base | `knowledge/` | Machine-readable Pktgen docs (API ref, CLI commands, examples) — the ground truth |
| DSL | `dsl/` | Skill YAML templates (`skills/`), API schema whitelist (`schema.yaml`), compilation rules (`mapping.yaml`) |
| Compiler | `pktgen_agent/compiler/` | Validates user params, resolves `$topology`/`$params` refs, emits Lua |
| Tools | `pktgen_agent/tools/` | LangChain `@tool` factory — one tool per skill, auto-generated from YAML |

**Package structure (`pktgen_agent/`):**

| Module | Purpose |
|--------|---------|
| `agent.py` | Entry point, `create_pktgen_agent()`, `get_model()`, REPL loop |
| `agent_prompt.py` | System prompt + lazy-loaded tool catalogue |
| `client.py` | `PktgenClient` (TCP socket to Pktgen), `PktgenConnectionError` |
| `compiler/compile.py` | `SkillCompiler` — validates params, resolves topology/params, emits Lua |
| `tools/execute.py` | `create_skill_tool()`, `create_all_tools()` — generates LangChain tools from YAML |
| `config.py` | `load_dotenv()`, `require_env()`, `setup_logging()` |
| `topology.py` | `load_topology_config()` — single source of truth for `topology.yaml` |

`agent.py` at the project root is a thin wrapper: `from pktgen_agent.agent import main`.

The public API is exported from `pktgen_agent.__init__`.

## Skill DSL

Every skill YAML in `dsl/skills/` follows a three-phase structure:

```yaml
skill:
  name: "udp_flood"
  intent: "traffic_generation"
  params: [{name, type, required, default, constraints: {min, max, enum}}]
  setup:    # Initialization (screen off, set MACs/IPs, configure ARP)
  plan:     # Main execution — at least one step required
  teardown: # Cleanup (stop, reset, screen on)
```

Steps reference topology via `$topology.tx_port` (resolved to physical portlist) and user params via `$params.rate` (with default fallback). Conditions (`$params.save_config == true`) and repeat loops are supported.

9 skills available: `udp_flood`, `tcp_flood`, `icmp_flood`, `arp_flood`, `range_based_scan`, `packet_sequence_generation`, `pcap_replay`, `stats_monitoring`, `safe_stop_and_reset`.

## Adding a new skill

1. Create `dsl/skills/<name>.yaml` following the schema in `dsl/schema.yaml`
2. Every `api` value must exist in the whitelist (`dsl/schema.yaml` → `valid_apis`)
3. Validate: `from pktgen_agent import compile_skill; lua = compile_skill("name", {...})`
4. The new skill is auto-discovered by `create_all_tools()` — no registration needed

## Key patterns

- **Compiler validates then emits.** `SkillCompiler.compile()` has two phases: (1) type/range/enum/bool validation against skill params, then (2) Lua code generation. Failures raise `CompileError`.
- **Topology separation.** Skills reference ports by logical name (`$topology.tx_port`); physical portlists live only in `topology.yaml`. This keeps skills hardware-agnostic.
- **Dry-run by default.** `create_tools()` defaults to `dry_run=True` — compiles Lua without connecting to Pktgen. Pass `dry_run=False` for live execution.
- **Range scan field routing.** `range_based_scan` uses `$range_api` which resolves at compile time: `scan_field="dst_ip"` → `pktgen.range.dst_ip`. See `dsl/skills/range_based_scan.yaml` constraints for the mapping.
- **PktgenClient is a context manager.** Use `with PktgenClient(host=...) as client:` for safe connect/disconnect.
- **Lazy loading.** Tool catalog and topology config are cached after first read — no disk I/O at import time.
- **Tool execution returns JSON.** Each tool returns a JSON string with `success`, `skill`, `params`, `lua_code`, and optionally `response`/`error`.

## Requirements

- Python ≥3.10 (pyproject.toml requires 3.10+, code uses 3.12 features)
- Dependencies: `pyyaml`, `langchain`, `langchain-openai`, `pydantic`
- Dev dependencies: `pytest`, `pytest-cov`, `python-dotenv`
- Environment: `DEEPSEEK_API_KEY` in `.env` or environment (Uses DeepSeek's OpenAI-compatible API at `https://api.deepseek.com`)

## Testing

121 tests in `tests/`, organized by module (`test_compile.py`, `test_execute.py`, `test_agent.py`, `test_pktgen_client.py`, `test_agent_prompt.py`, `test_tools_init.py`).

`tests/conftest.py` redirects all compiler filesystem paths to `tests/fixtures/` via `monkeypatch` — tests never touch real `dsl/skills/` or `topology.yaml`. A `test_data_dir` fixture stages fixture YAML into a temp directory and patches the compiler module constants + tools module-level `compiler` instance.

Fixture files live in `tests/fixtures/`:
- `topology.yaml` — minimal test topology
- `schema.yaml` — test API whitelist
- `skills/udp_flood.yaml` — single test skill used by all compiler/execute tests

Markers: `@pytest.mark.langchain` for tests needing `langchain-core` + `pydantic` (auto-skipped if not installed).
