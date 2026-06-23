"""
Unit tests for pktgen_client.py — PktgenClient class and execute_lua helper.

Socket operations are fully mocked via the mock_socket fixture.
"""

import socket

import pytest
from pktgen_client import PktgenClient, execute_lua, _load_topology_config


# ── TestLoadTopologyConfig ──


class TestLoadTopologyConfig:
    def test_returns_host_and_port(self, monkeypatch):
        """Should read host/port from the real topology.yaml in project root."""
        host, port = _load_topology_config()
        assert isinstance(host, str)
        assert isinstance(port, int)
        # The real topology.yaml has 10.99.80.222:22022
        assert port == 22022


# ── TestPktgenClientInit ──


class TestPktgenClientInit:
    def test_defaults_from_topology(self, monkeypatch):
        """When no args, reads from topology.yaml."""
        def fake_config():
            return ("fakehost", 9999)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        assert c.host == "fakehost"
        assert c.port == 9999

    def test_explicit_host_overrides(self, monkeypatch):
        def fake_config():
            return ("fakehost", 9999)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient(host="override")
        assert c.host == "override"
        assert c.port == 9999

    def test_explicit_port_overrides(self, monkeypatch):
        def fake_config():
            return ("fakehost", 9999)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient(port=7777)
        assert c.host == "fakehost"
        assert c.port == 7777

    def test_both_explicit(self, monkeypatch):
        def fake_config():
            return ("fakehost", 9999)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient(host="a", port=1)
        assert c.host == "a"
        assert c.port == 1

    def test_stores_timeout(self, monkeypatch):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient(timeout=5.0)
        assert c.timeout == 5.0

    def test_default_timeout(self, monkeypatch):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        assert c.timeout == 10.0

    def test_sock_is_none_initially(self, monkeypatch):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        assert c._sock is None


# ── TestConnect ──


class TestConnect:
    def test_creates_tcp_socket(self, monkeypatch, mock_socket):
        def fake_config():
            return ("testhost", 9999)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        mock_socket.settimeout.assert_called_once_with(10.0)
        mock_socket.connect.assert_called_once_with(("testhost", 9999))

    def test_sock_is_set_after_connect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        assert c._sock is mock_socket


# ── TestDisconnect ──


class TestDisconnect:
    def test_closes_socket(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        c.disconnect()
        mock_socket.close.assert_called_once()

    def test_sets_sock_to_none_after_disconnect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        c.disconnect()
        assert c._sock is None

    def test_idempotent_disconnect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        c.disconnect()
        c.disconnect()  # should not raise
        assert c._sock is None

    def test_disconnect_before_connect_no_error(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.disconnect()  # should not raise


# ── TestIsConnected ──


class TestIsConnected:
    def test_false_before_connect(self, monkeypatch):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        assert not c.is_connected()

    def test_true_after_connect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        assert c.is_connected()


# ── TestSendLua ──


class TestSendLua:
    def test_raises_when_not_connected(self, monkeypatch):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        with pytest.raises(ConnectionError, match="ot connected"):
            c.send_lua("print(1)")

    def test_appends_newline(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        c.send_lua("print(1)")
        sent = mock_socket.sendall.call_args[0][0]
        assert sent.endswith(b"\n")

    def test_no_double_newline(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        c.send_lua("print(1)\n")
        sent = mock_socket.sendall.call_args[0][0]
        assert sent == b"print(1)\n"

    def test_no_response_when_read_response_false(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        c = PktgenClient()
        c.connect()
        resp = c.send_lua("cmd", read_response=False)
        assert resp == ""
        mock_socket.recv.assert_not_called()

    def test_returns_decoded_response(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        mock_socket.recv.side_effect = [b"pktgen> ", socket.timeout()]
        c = PktgenClient()
        c.connect()
        resp = c.send_lua("cmd")
        assert resp == "pktgen> "

    def test_concatenates_multiple_chunks(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        mock_socket.recv.side_effect = [b"chunk1", b"chunk2", socket.timeout()]
        c = PktgenClient()
        c.connect()
        resp = c.send_lua("cmd")
        assert resp == "chunk1chunk2"

    def test_handles_timeout_gracefully(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        mock_socket.recv.side_effect = [b"some_data", socket.timeout()]
        c = PktgenClient()
        c.connect()
        resp = c.send_lua("cmd")
        assert resp == "some_data"


# ── TestExecute ──


class TestExecute:
    def test_delegates_to_send_lua(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        mock_socket.recv.side_effect = [b"ok", socket.timeout()]
        c = PktgenClient()
        c.connect()
        resp = c.execute("test()")
        assert resp == "ok"


# ── TestContextManager ──


class TestContextManager:
    def test_connect_and_disconnect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        with PktgenClient() as c:
            assert c.is_connected()
            mock_socket.connect.assert_called_once()
        mock_socket.close.assert_called_once()

    def test_returns_false_does_not_suppress_exceptions(self, monkeypatch, mock_socket):
        """__exit__ returns False so exceptions propagate."""
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        class TestError(Exception):
            pass
        with pytest.raises(TestError):
            with PktgenClient() as c:
                raise TestError("boom")

    def test_disconnect_called_even_on_exception(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr("pktgen_client._load_topology_config", fake_config)
        class TestError(Exception):
            pass
        with pytest.raises(TestError):
            with PktgenClient() as c:
                raise TestError("boom")
        mock_socket.close.assert_called_once()


# ── TestExecuteLua ──


class TestExecuteLua:
    def test_one_shot_connect_execute_disconnect(self, monkeypatch, mock_socket):
        def fake_config():
            return ("h", 1)
        monkeypatch.setattr(
            "pktgen_client._load_topology_config", fake_config
        )
        mock_socket.recv.side_effect = [b"result", socket.timeout()]
        resp = execute_lua("print(1)", host="override", port=1234)
        assert resp == "result"
        mock_socket.close.assert_called_once()
