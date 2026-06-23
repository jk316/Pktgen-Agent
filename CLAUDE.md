# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Pktgen Agent — an AI agent controller for [Pktgen-DPDK](https://pktgen.github.io/Pktgen-DPDK/) (a DPDK-based packet generator). It translates natural language traffic-generation requests into executable Lua scripts via a Skill DSL compiler, then sends them to a running Pktgen instance over TCP (port 22022). Designed to work with LangChain ReAct agents.

## Architecture

```
User Request → ReAct Agent (LangChain)
                 ├─ System prompt (agent_prompt.py)
                 ├─ Tool: e.g. udp_flood(rate=80) (tools/)
                 │    ├─ SkillCompiler validates params against dsl/schema.yaml
                 │    ├─ Compiles dsl/skills/<name>.yaml → Lua code
                 │    └─ PktgenClient sends Lua over TCP → returns response
                 └─ Knowledge base (knowledge/*.yaml) grounds the DSL
```

**Four-layer stack:**

| Layer | Directory | Role |
|-------|-----------|------|
| Knowledge Base | `knowledge/` | Machine-readable Pktgen docs (API ref, CLI commands, examples) — the ground truth |
| DSL | `dsl/` | Skill YAML templates (`skills/`), API schema whitelist (`schema.yaml`), compilation rules (`mapping.yaml`) |
| Compiler | `compiler/` | Validates user params, resolves `$topology`/`$params` refs, emits Lua |
| Tools | `tools/` | LangChain `StructuredTool` factory — one tool per skill, auto-generated from YAML |

**Key files:**
- `pktgen_client.py` — TCP client to Pktgen (port 22022). Reads default host/port from `topology.yaml`.
- `agent_prompt.py` — ReAct agent system prompt with tool catalog and usage rules.
- `topology.yaml` — Maps logical port names (`tx_port`, `rx_port`) to physical portlists. Edit for your hardware.

## Skill DSL structure

Every skill YAML in `dsl/skills/` follows a three-phase structure:

```yaml
skill:
  name: "udp_flood"
  intent: "traffic_generation"  # traffic_generation | packet_crafting | traffic_scanning | monitoring | control
  params: [{name, type, required, default, constraints: {min, max, enum}}]
  setup:    # Initialization (screen off, set MACs/IPs, configure ARP)
  plan:     # Main execution — at least one step required
  teardown: # Cleanup (stop, reset, screen on)
```

Steps reference topology via `$topology.tx_port` (resolved to physical portlist) and user params via `$params.rate` (with default fallback). Conditions (`$params.save_config == true`) and repeat loops are supported.

## Adding a new skill

1. Create `dsl/skills/<name>.yaml` following the schema in `dsl/schema.yaml`
2. Every `api` value must exist in the whitelist (`dsl/schema.yaml` → `valid_apis`)
3. Validate: run the compiler — `from compiler.compile import SkillCompiler; c = SkillCompiler(); lua = c.compile("name", {...})`
4. The new skill is auto-discovered by `tools.execute.create_all_tools()` — no registration needed

## Requirements

- Python 3.12+
- `pyyaml` (for YAML parsing)
- `langchain-core` + `pydantic` (optional — only needed for LangChain `StructuredTool` integration; see `HAS_LANGCHAIN` flag in `tools/execute.py`)

No build system, no test suite currently. No `requirements.txt`. Modules import each other via `sys.path.insert` in `tools/execute.py`.

## Key patterns

- **Compiler validates then emits.** `SkillCompiler.compile()` has two phases: (1) type/range/enum validation against skill params, then (2) Lua code generation. Validation failures raise `CompileError`.
- **Topology separation.** Skills reference ports by logical name (`$topology.tx_port`); physical portlists live only in `topology.yaml`. This keeps skills hardware-agnostic.
- **Dry-run by default.** `tools` creates tools with `dry_run=True` — they compile Lua without connecting to Pktgen. Pass `dry_run=False` for live execution.
- **Range scan field routing.** `range_based_scan` uses `$range_api` which resolves at compile time: `scan_field="dst_ip"` → `pktgen.range.dst_ip`, etc. (see `dsl/skills/range_based_scan.yaml` constraints for the mapping).
- **PktgenClient is a context manager.** Use `with PktgenClient() as client:` for safe connect/disconnect.
