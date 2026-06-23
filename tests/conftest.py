"""
Shared pytest fixtures for Pktgen Agent unit tests.

Redirects compiler filesystem paths to test fixtures so tests never
touch the real dsl/skills/ or topology.yaml on disk.
"""

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
    paths (SCHEMA_PATH, SKILLS_DIR, TOPOLOGY_PATH, BASE_DIR) there.

    Returns the tmp_path so tests can inspect staged files if needed.
    """
    staged = _stage_fixtures(tmp_path)

    import compiler.compile as cc

    monkeypatch.setattr(cc, "SCHEMA_PATH", staged / "dsl" / "schema.yaml")
    monkeypatch.setattr(cc, "SKILLS_DIR", staged / "dsl" / "skills")
    monkeypatch.setattr(cc, "TOPOLOGY_PATH", staged / "topology.yaml")
    monkeypatch.setattr(cc, "BASE_DIR", staged)

    # tools/execute.py has its own SKILLS_DIR (not imported from compiler.compile)
    try:
        import tools.execute as te
        monkeypatch.setattr(te, "SKILLS_DIR", staged / "dsl" / "skills")
        monkeypatch.setattr(te, "BASE_DIR", staged)
    except ImportError:
        pass

    return staged


@pytest.fixture
def compiler(test_data_dir: Path):
    """
    Return a fresh SkillCompiler that reads from test fixtures.

    Depends on test_data_dir to set up path redirection first.
    """
    from compiler.compile import SkillCompiler

    return SkillCompiler()


@pytest.fixture
def mock_socket():
    """
    Patch socket.socket globally.  Returns the MagicMock instance
    so tests can inspect sendall / recv / connect calls.
    """
    mock_sock = MagicMock()
    mock_sock.sendall = MagicMock()
    # Default: return one data chunk then simulate timeout to exit the read loop
    mock_sock.recv = MagicMock(side_effect=[b"pktgen> ", socket.timeout()])
    mock_sock.settimeout = MagicMock()
    mock_sock.close = MagicMock()
    mock_sock.connect = MagicMock()

    with patch("socket.socket", return_value=mock_sock):
        yield mock_sock


@pytest.fixture
def no_langchain(monkeypatch):
    """Simulate langchain not installed."""
    monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", False)


@pytest.fixture
def with_langchain(monkeypatch):
    """Ensure langchain IS marked as available for this test."""
    monkeypatch.setattr("tools.execute.HAS_LANGCHAIN", True)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "langchain: tests requiring langchain-core + pydantic"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip langchain tests when pydantic/langchain is not installed."""
    try:
        from pydantic import BaseModel  # noqa: F401
        from langchain_core.tools import StructuredTool  # noqa: F401
        _has_langchain = True
    except ImportError:
        _has_langchain = False

    if not _has_langchain:
        skip_lc = pytest.mark.skip(reason="langchain-core + pydantic not installed")
        for item in items:
            if "langchain" in item.keywords:
                item.add_marker(skip_lc)
