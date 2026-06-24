"""
Unit tests for pktgen_agent.client — PktgenClient class and execute_lua helper.

Socket operations are fully mocked via the mock_socket fixture.
"""

import socket

import pytest
from pktgen_agent.client import PktgenClient, PktgenConnectionError, execute_lua
from pktgen_agent.topology import load_topology_config


# ── TestLoadTopologyConfig ──


class TestLoadTopologyConfig:
    def test_returns_host_and_port(self):
        """Should read host/port from the real topology.yaml in project root."""
        host, port = load_topology_config()
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert port == 22022


# ── TestPktgenClientInit ──


class TestPktgenClientInit:
    def test_default_init(self):
        client = PktgenClient()
        assert client.host is not None
        assert client.port == 22022
        assert client.timeout == 10.0
        assert client._sock is None

    def test_explicit_host_port(self):
        client = PktgenClient(host="192.168.1.1", port=9999, timeout=5.0)
        assert client.host == "192.168.1.1"
        assert client.port == 9999
        assert client.timeout == 5.0

    def test_init_not_connected(self):
        client = PktgenClient()
        assert not client.is_connected()


# ── TestConnect ──


class TestConnect:
    def test_connect_success(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        assert client.is_connected()
        mock_socket.connect.assert_called_once_with(("10.0.0.1", 22022))

    def test_connect_failure(self, mock_socket):
        mock_socket.connect.side_effect = OSError("Connection refused")
        client = PktgenClient(host="10.0.0.1", port=22022)
        with pytest.raises(PktgenConnectionError, match="Failed to connect"):
            client.connect()
        assert not client.is_connected()


# ── TestDisconnect ──


class TestDisconnect:
    def test_disconnect_closes_socket(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        client.disconnect()
        mock_socket.close.assert_called_once()
        assert not client.is_connected()

    def test_disconnect_when_not_connected(self):
        client = PktgenClient()
        client.disconnect()  # no-op, no crash


# ── TestSendLua ──


class TestSendLua:
    def test_sends_utf8_encoded_lua(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        response = client.send_lua('print("hello")')
        assert isinstance(response, str)
        mock_socket.sendall.assert_called_once()
        # Verify UTF-8 encoding was used
        call_arg = mock_socket.sendall.call_args[0][0]
        assert isinstance(call_arg, bytes)

    def test_appends_newline(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        client.send_lua('print("hello")')
        call_arg = mock_socket.sendall.call_args[0][0]
        assert call_arg.endswith(b"\n")

    def test_read_response_false(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        response = client.send_lua("code", read_response=False)
        assert response == ""

    def test_not_connected_raises(self):
        client = PktgenClient(host="10.0.0.1", port=22022)
        with pytest.raises(PktgenConnectionError, match="Not connected"):
            client.send_lua("code")


# ── TestExecute ──


class TestExecute:
    def test_execute_is_send_lua_with_response(self, mock_socket):
        client = PktgenClient(host="10.0.0.1", port=22022)
        client.connect()
        response = client.execute("code")
        assert isinstance(response, str)
        assert "pktgen>" in response


# ── TestContextManager ──


class TestContextManager:
    def test_connect_and_disconnect(self, mock_socket):
        with PktgenClient(host="10.0.0.1", port=22022) as client:
            assert client.is_connected()
        assert not client.is_connected()
        mock_socket.close.assert_called_once()

    def test_does_not_suppress_exceptions(self, mock_socket):
        with pytest.raises(ValueError):
            with PktgenClient(host="10.0.0.1", port=22022):
                raise ValueError("test error")


# ── TestExecuteLuaConvenience ──


class TestExecuteLuaConvenience:
    def test_returns_response(self, mock_socket):
        response = execute_lua("code", host="10.0.0.1", port=22022)
        assert isinstance(response, str)
        assert "pktgen>" in response
