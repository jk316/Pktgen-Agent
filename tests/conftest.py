"""
Shared pytest fixtures for Pktgen Agent unit tests.

Redirects compiler filesystem paths to test fixtures so tests never
touch the real dsl/skills/ or topology.yaml on disk.

Updated for pktgen_agent package structure (LangChain V1.0 migration).
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Path helpers ──

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _stage_fixtures(tmp_path: Path) -> Path:
    """Copy fixture YAML files into tmp_path and return it."""
    # topology
    shutil.copy(FIXTURES_DIR / "topology.yaml", tmp_path / "topology.yaml")

    # dsl/schema.yaml
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES_DIR / "schema.yaml", dsl_dir / "schema.yaml")

    # dsl/skills/
    skills_dir = dsl_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for skill_file in (FIXTURES_DIR / "skills").glob("*.yaml"):
        shutil.copy(skill_file, skills_dir / skill_file.name)

    return tmp_path


# ── Fixtures ──


@pytest.fixture
def test_data_dir(tmp_path: Path, monkeypatch) -> Path:
    """
    Stage test fixtures in a temp directory and redirect all compiler
    paths (SCHEMA_PATH, SKILLS_DIR, TOPOLOGY_PATH) there.

    Also patches the module-level compiler instance in tools/execute.py
    so it reads from test fixtures instead of real disk.
    """
    staged = _stage_fixtures(tmp_path)

    import pktgen_agent.compiler.compile as cc
    import pktgen_agent.tools.execute as te
    from pktgen_agent.compiler.compile import SkillCompiler

    monkeypatch.setattr(cc, "_SCHEMA_PATH", staged / "dsl" / "schema.yaml")
    monkeypatch.setattr(cc, "_SKILLS_DIR", staged / "dsl" / "skills")
    monkeypatch.setattr(cc, "_TOPOLOGY_PATH", staged / "topology.yaml")

    monkeypatch.setattr(te, "_SKILLS_DIR", staged / "dsl" / "skills")
    monkeypatch.setattr(te, "_PROJECT_ROOT", staged)

    # Replace the module-level compiler instance so it uses the patched paths
    monkeypatch.setattr(
        te, "compiler",
        SkillCompiler(
            topology_path=staged / "topology.yaml",
            schema_path=staged / "dsl" / "schema.yaml",
            skills_dir=staged / "dsl" / "skills",
        )
    )

    return staged


@pytest.fixture
def compiler(test_data_dir: Path):
    """Return a fresh SkillCompiler that reads from test fixtures."""
    from pktgen_agent.compiler.compile import SkillCompiler

    return SkillCompiler()


@pytest.fixture
def mock_socket():
    """Patch socket.socket globally. Returns the MagicMock instance."""
    mock_sock = MagicMock()
    mock_sock.sendall = MagicMock()
    mock_sock.recv = MagicMock(
        side_effect=[b"pktgen> ", socket.timeout()]
    )
    mock_sock.settimeout = MagicMock()
    mock_sock.close = MagicMock()
    mock_sock.connect = MagicMock()

    with patch("socket.socket", return_value=mock_sock):
        yield mock_sock


@pytest.fixture
def no_langchain(monkeypatch):
    """Simulate langchain not installed."""
    monkeypatch.setattr("pktgen_agent.tools.execute.HAS_LANGCHAIN", False)


@pytest.fixture
def with_langchain(monkeypatch):
    """Ensure langchain IS marked as available for this test."""
    monkeypatch.setattr("pktgen_agent.tools.execute.HAS_LANGCHAIN", True)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "langchain: tests requiring langchain-core + pydantic"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip langchain tests when pydantic/langchain is not installed."""
    try:
        from pydantic import BaseModel  # noqa: F401
        from langchain.tools import tool  # noqa: F401
        _has_langchain = True
    except ImportError:
        _has_langchain = False

    if not _has_langchain:
        skip_lc = pytest.mark.skip(
            reason="langchain-core + pydantic not installed"
        )
        for item in items:
            if "langchain" in item.keywords:
                item.add_marker(skip_lc)
