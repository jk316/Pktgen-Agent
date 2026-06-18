"""
Pktgen TCP Socket Client
Connects to a running Pktgen instance via TCP port 22022 (0x5606).
Sends Lua code and returns the response.

Reference: knowledge/socket.html
  - telnet localhost 22022
  - socat -d -d READLINE TCP4:localhost:22022
  - socat - TCP4:localhost:22022 < test/hello-world.lua
"""

import socket
import time
import logging

logger = logging.getLogger(__name__)

PKTGEN_DEFAULT_HOST = "localhost"
PKTGEN_DEFAULT_PORT = 22022  # 0x5606
DEFAULT_TIMEOUT = 10.0
BUFFER_SIZE = 65536


class PktgenClient:
    """TCP client for communicating with a running Pktgen instance."""

    def __init__(self, host=PKTGEN_DEFAULT_HOST, port=PKTGEN_DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None

    def connect(self):
        """Establish TCP connection to Pktgen."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))
        logger.info(f"Connected to Pktgen at {self.host}:{self.port}")

    def disconnect(self):
        """Close TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            logger.info("Disconnected from Pktgen")

    def is_connected(self):
        return self._sock is not None

    def send_lua(self, lua_code: str, read_response=True) -> str:
        """
        Send Lua code to Pktgen and optionally read the response.

        Args:
            lua_code: Complete Lua script to execute
            read_response: Whether to wait for and return the response

        Returns:
            Response string from Pktgen (empty string if read_response is False)
        """
        if not self._sock:
            raise ConnectionError("Not connected to Pktgen. Call connect() first.")

        # Pktgen expects complete Lua statements terminated by newline
        if not lua_code.endswith("\n"):
            lua_code += "\n"

        self._sock.sendall(lua_code.encode("utf-8"))

        if not read_response:
            return ""

        # Read response with a brief delay to allow Pktgen to process
        response_parts = []
        try:
            while True:
                data = self._sock.recv(BUFFER_SIZE)
                if not data:
                    break
                response_parts.append(data.decode("utf-8", errors="replace"))
        except socket.timeout:
            pass  # Expected — Pktgen doesn't close after each command

        return "".join(response_parts)

    def execute(self, lua_code: str) -> str:
        """High-level: send Lua code and return response."""
        return self.send_lua(lua_code, read_response=True)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


def execute_lua(host: str, port: int, lua_code: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """
    Convenience function: connect, execute Lua, disconnect.

    Args:
        host: Pktgen hostname or IP
        port: Pktgen TCP port (default 22022)
        lua_code: Lua code to execute
        timeout: Socket timeout in seconds

    Returns:
        Response from Pktgen
    """
    with PktgenClient(host=host, port=port, timeout=timeout) as client:
        return client.execute(lua_code)
