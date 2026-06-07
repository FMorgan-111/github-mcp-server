"""Tests for HTTP transport mode."""
import json
import socket
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest


def _find_free_port() -> int:
    """Find a free port to bind to."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _initialize_session(base_url: str) -> str | None:
    """Initialize an MCP session and return the session ID (or None if none)."""
    init_payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    with httpx.Client(timeout=5.0) as client:
        r = client.post(
            f"{base_url}/mcp",
            json=init_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert r.status_code == 200, f"Initialize failed: {r.status_code} {r.text}"
    session_id = r.headers.get("mcp-session-id")
    return session_id


class TestHTTPTransport:
    """Integration tests for the HTTP transport mode."""

    @pytest.fixture
    def http_server(self):
        """Start the MCP server in HTTP mode on a random port."""
        port = _find_free_port()
        env = {**__import__("os").environ, "GITHUB_TOKEN": "test-token"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.main", "--transport", "http", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        base_url = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10
        started = False
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=2.0) as client:
                    r = client.get(f"{base_url}/health")
                    if r.status_code == 200:
                        started = True
                        break
            except (httpx.ConnectError, httpx.ReadError, OSError):
                pass
            time.sleep(0.2)

        if not started:
            proc.terminate()
            proc.wait()
            stderr_out = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"Server failed to start within 10s. stderr: {stderr_out}")

        yield base_url, proc

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def test_health_endpoint(self, http_server):
        """Verify the health endpoint returns {'status': 'ok'}."""
        base_url, _ = http_server
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{base_url}/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_tools_list_via_jsonrpc(self, http_server):
        """Send a tools/list JSON-RPC request and verify the response."""
        base_url, _ = http_server
        session_id = _initialize_session(base_url)

        request_payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        with httpx.Client(timeout=5.0) as client:
            r = client.post(f"{base_url}/mcp", json=request_payload, headers=headers)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "result" in data, f"Expected result in response: {data}"
        tools = data["result"].get("tools", [])
        assert len(tools) > 0, "Expected at least one tool in tools/list response"

    def test_missing_method_returns_error(self, http_server):
        """Send a non-existent method and verify an error response."""
        base_url, _ = http_server
        session_id = _initialize_session(base_url)

        request_payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "nonexistent/method",
            "params": {},
        }
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        with httpx.Client(timeout=5.0) as client:
            r = client.post(f"{base_url}/mcp", json=request_payload, headers=headers)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "error" in data, f"Expected error for unknown method: {data}"
        # MCP may return -32601 (method not found) or -32602 (invalid params)
        assert data["error"]["code"] in (-32601, -32602), (
            f"Expected error code -32601 or -32602: {data}"
        )
