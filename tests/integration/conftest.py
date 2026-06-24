"""
Integration test fixtures.

Unlike the root conftest.py (which monkeypatches compiler paths to test fixtures),
this conftest uses the REAL dsl/skills/ and topology.yaml so integration tests
validate the actual compile→execute pipeline.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from pktgen_agent.client import PktgenClient
from pktgen_agent.compiler import SkillCompiler

# ── Pktgen availability detection ──

_TOPOLOGY_PATH = Path(__file__).resolve().parent.parent.parent / "topology.yaml"


def _get_pktgen_host_port() -> tuple[str, int]:
    """Read host/port from the real topology.yaml."""
    with open(_TOPOLOGY_PATH) as f:
        data = yaml.safe_load(f)
    cfg = data.get("pktgen", {})
    return cfg.get("host", "localhost"), cfg.get("port", 22022)


def _is_pktgen_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check whether Pktgen is reachable at the given host:port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def pktgen_host_port() -> tuple[str, int]:
    """Pktgen host and port from topology.yaml."""
    return _get_pktgen_host_port()


@pytest.fixture(scope="session")
def pktgen_available(pktgen_host_port: tuple[str, int]) -> bool:
    """Session-scoped check: is Pktgen reachable?

    All integration tests depend on this fixture so they auto-skip when
    Pktgen is not running.
    """
    host, port = pktgen_host_port
    if not _is_pktgen_reachable(host, port):
        pytest.skip(f"Pktgen not reachable at {host}:{port}")
    return True


@pytest.fixture
def client(pktgen_available, pktgen_host_port):
    """Connected PktgenClient, auto-disconnects after test."""
    host, port = pktgen_host_port
    c = PktgenClient(host=host, port=port, timeout=10.0)
    c.connect()
    yield c
    c.disconnect()


@pytest.fixture
def compiler():
    """SkillCompiler reading from real dsl/skills/ and topology.yaml."""
    return SkillCompiler()


# ── Helpers for safe Lua snippets (won't disrupt running traffic) ──


def send_hello(client: PktgenClient) -> str:
    """Send a minimal harmless Lua snippet to verify connectivity."""
    return client.execute('printf("hello from pktgen integration test\\n")\n')
