"""
Integration tests for the compile→execute pipeline.

Validates that skills compile into valid Lua that Pktgen accepts and executes
without errors.  Uses the real dsl/skills/*.yaml and topology.yaml.
"""

from __future__ import annotations

import pytest

from pktgen_agent.compiler import SkillCompiler
from pktgen_agent.client import PktgenClient

pytestmark = pytest.mark.integration


# ── Helper ──

def assert_no_pktgen_error(response: str) -> None:
    """Fail if the Pktgen response contains error indicators."""
    # Pktgen prints "!! ERROR" or "error:" on failure
    lower = response.lower()
    if "!! error" in lower or "error:" in lower:
        # Still allow printf of error words
        lines = [l for l in lower.splitlines()
                 if "!! error" in l or ("error:" in l and "printf" not in l)]
        if lines:
            pytest.fail(f"Pktgen returned error:\n{response}")


class TestCompileAndExecute:
    """Compile a skill YAML → Lua → execute on Pktgen."""

    def test_safe_stop_and_reset(self, client, compiler):
        """safe_stop_and_reset should always succeed (idempotent)."""
        lua = compiler.compile("safe_stop_and_reset", {})
        response = client.execute(lua)
        assert_no_pktgen_error(response)

    def test_stats_monitoring(self, client, compiler):
        """stats_monitoring should return port statistics."""
        lua = compiler.compile("stats_monitoring", {"rate": 100})
        response = client.execute(lua)
        assert_no_pktgen_error(response)

    def test_udp_flood_compile_execute(self, client, compiler):
        """Compile and execute udp_flood — start traffic then immediately stop."""
        # Start UDP flood
        lua = compiler.compile("udp_flood", {"rate": 50, "pktSize": 512})
        response = client.execute(lua)
        assert_no_pktgen_error(response)

        # Stop immediately
        stop_lua = compiler.compile("safe_stop_and_reset", {})
        client.execute(stop_lua)

    def test_tcp_flood_compile_execute(self, client, compiler):
        """Compile and execute tcp_flood with TCP flags."""
        lua = compiler.compile("tcp_flood", {"rate": 30, "pktSize": 1024})
        response = client.execute(lua)
        assert_no_pktgen_error(response)

        # Cleanup
        client.execute(compiler.compile("safe_stop_and_reset", {}))


class TestSequentialWorkflow:
    """Multi-skill workflows simulating real agent usage patterns."""

    def test_stop_flood_stats_stop(self, client, compiler):
        """Full cycle: stop → start UDP → check stats → stop."""
        # 1. Ensure clean state
        client.execute(compiler.compile("safe_stop_and_reset", {}))

        # 2. Start UDP traffic
        lua = compiler.compile("udp_flood", {"rate": 60, "pktSize": 512})
        response = client.execute(lua)
        assert_no_pktgen_error(response)

        # 3. Check stats
        stats_lua = compiler.compile("stats_monitoring", {"rate": 100})
        stats_response = client.execute(stats_lua)
        assert_no_pktgen_error(stats_response)

        # 4. Stop
        client.execute(compiler.compile("safe_stop_and_reset", {}))

    def test_switch_traffic_type(self, client, compiler):
        """Stop UDP → start TCP — verify Pktgen handles traffic type switching."""
        # Start UDP
        client.execute(compiler.compile("safe_stop_and_reset", {}))
        client.execute(compiler.compile("udp_flood", {"rate": 40}))

        # Stop and switch to TCP
        client.execute(compiler.compile("safe_stop_and_reset", {}))
        tcp_lua = compiler.compile("tcp_flood", {"rate": 40, "tcp_flags": "syn"})
        response = client.execute(tcp_lua)
        assert_no_pktgen_error(response)

        # Cleanup
        client.execute(compiler.compile("safe_stop_and_reset", {}))

    def test_icmp_and_arp_skills(self, client, compiler):
        """Verify ICMP and ARP flood skills compile and execute cleanly."""
        for skill_name, params in [
            ("icmp_flood", {"rate": 30}),
            ("arp_flood", {"rate": 30, "arp_type": "request"}),
        ]:
            lua = compiler.compile(skill_name, params)
            response = client.execute(lua)
            assert_no_pktgen_error(response)
            # Stop between each
            client.execute(compiler.compile("safe_stop_and_reset", {}))


class TestCompiledLuaValidity:
    """Verify skill compilation produces syntactically valid Lua."""

    @pytest.mark.parametrize("skill_name,params", [
        ("udp_flood", {"rate": 80, "pktSize": 512}),
        ("tcp_flood", {"rate": 80, "tcp_flags": "syn"}),
        ("icmp_flood", {"rate": 80}),
        ("arp_flood", {"rate": 80, "arp_type": "request"}),
        ("safe_stop_and_reset", {}),
        ("stats_monitoring", {"rate": 100}),
        ("pcap_replay", {"pcap_file": "test.pcap", "rate": 100}),
        ("range_based_scan", {
            "scan_field": "dst_ip",
            "start": "192.168.1.1",
            "min": "192.168.1.1",
            "max": "192.168.1.10",
            "inc": "0.0.0.1",
            "rate": 10,
        }),
        ("packet_sequence_generation", {
            "rate": 50,
            "sequences": [{
                "eth_dst_addr": "00:11:22:33:44:55",
                "eth_src_addr": "66:77:88:99:aa:bb",
                "ip_dst_addr": "10.0.0.2",
                "ip_src_addr": "10.0.0.1",
                "sport": 1234,
                "dport": 5678,
                "ethType": "IPv4",
                "ipProto": "UDP",
                "vlanid": 0,
                "pktSize": 512,
            }],
        }),
    ])
    def test_skill_compiles_to_executable_lua(
        self, client, compiler, skill_name, params
    ):
        """Every skill in the DSL compiles to Lua that Pktgen can parse."""
        lua = compiler.compile(skill_name, params)

        # Basic Lua structure checks
        assert 'require "Pktgen"' in lua, f"{skill_name}: missing require"
        assert lua.endswith("\n"), f"{skill_name}: should end with newline"

        # Execute — Pktgen should at least parse it without error
        response = client.execute(lua)
        assert_no_pktgen_error(response)

        # Always stop after traffic-generating skills
        if skill_name != "safe_stop_and_reset":
            client.execute(compiler.compile("safe_stop_and_reset", {}))


class TestCompileValidation:
    """Validation should fail BEFORE sending to Pktgen."""

    def test_invalid_rate_rejected(self, compiler):
        """Rate=999 should fail validation, not reach Pktgen."""
        with pytest.raises(Exception) as exc_info:
            compiler.compile("udp_flood", {"rate": 999})
        assert "rate" in str(exc_info.value).lower() or "999" in str(exc_info.value)

    def test_invalid_scan_field_rejected(self, compiler):
        """Invalid scan_field should fail enum validation."""
        with pytest.raises(Exception) as exc_info:
            compiler.compile("range_based_scan", {
                "scan_field": "nonexistent_field",
                "start": "192.168.1.1",
                "min": "192.168.1.1",
                "max": "192.168.1.10",
                "inc": "0.0.0.1",
                "rate": 10,
            })
        assert "scan_field" in str(exc_info.value).lower()
