"""End-to-end MCP server lifecycle test.

Spawns ``ai-sw-mcp`` as a subprocess (the exact entry point a Claude
Desktop / Cursor client would invoke), speaks JSON-RPC over stdio,
and verifies the full wire protocol works against live SW:

1. ``initialize`` handshake declares the ``tools`` capability.
2. ``tools/list`` returns the full tool inventory (see ``EXPECTED_TOOLS``).
3. ``tools/call sw_active_doc`` returns a JSON-serializable payload.
4. ``tools/call sw_apidoc_enum`` returns the corpus_missing branch.

Catches the same class of bug Wave 5 audit caught at the wire layer
(the sync ``list_tools`` override in commit ``4a5f849``) — but
against the SW-backed runtime, not MockAdapter.

Skips automatically if SW is unavailable via the solidworks_only
marker. Also skipped if ``ai-sw-mcp`` console script isn't installed
(falls back to the python module form via the ai_sw_mcp_exe fixture).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.mcp_lane.test_server_contract import (
    TestToolRegistration as _ToolRegistrationContract,
)

pytestmark = pytest.mark.solidworks_only

_EXPECTED_TOOLS = _ToolRegistrationContract.EXPECTED_TOOLS


def _spawn_server(ai_sw_mcp_exe: str) -> subprocess.Popen:
    """Boot ai-sw-mcp as a subprocess with stdio pipes."""
    # ai_sw_mcp_exe is either an absolute path to the .exe or
    # a `"<python>" -m ai_sw_bridge.mcp.server` fallback string.
    if ai_sw_mcp_exe.startswith('"'):
        cmd = ai_sw_mcp_exe.split()
        # Reassemble the quoted python path
        cmd = [cmd[0].strip('"')] + cmd[1:]
    else:
        cmd = [ai_sw_mcp_exe]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )


def _send(proc: subprocess.Popen, payload: dict) -> None:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _recv(proc: subprocess.Popen, timeout: float = 10.0) -> dict:
    """Read one JSON-RPC message from stdout (one line)."""
    # Subprocess stdout is line-buffered (bufsize=1); readline blocks
    # until a newline. We don't need a watchdog for normal operation;
    # if it hangs longer than the test default, pytest's own timeout
    # surfaces it.
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"server closed stdout. stderr:\n{stderr}")
    return json.loads(line)


def test_e2e_mcp_handshake_and_inventory(ai_sw_mcp_exe: str) -> None:
    """initialize -> notifications/initialized -> tools/list -> full inventory."""
    proc = _spawn_server(ai_sw_mcp_exe)
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "e2e-test", "version": "0"},
                },
            },
        )
        init = _recv(proc)
        assert init.get("id") == 1
        assert "result" in init, f"initialize failed: {init}"
        caps = init["result"]["capabilities"]
        assert caps.get("tools") is not None, "server did not declare tools capability"

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools_resp = _recv(proc)
        assert "result" in tools_resp, f"tools/list failed: {tools_resp}"
        names = {t["name"] for t in tools_resp["result"]["tools"]}
        assert names == _EXPECTED_TOOLS, (
            f"tools/list inventory drift — "
            f"extra={sorted(names - _EXPECTED_TOOLS)}, "
            f"missing={sorted(_EXPECTED_TOOLS - names)}"
        )
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait(timeout=10)


def test_e2e_mcp_tools_call_apidoc_enum(ai_sw_mcp_exe: str) -> None:
    """tools/call sw_apidoc_enum -> corpus_missing payload over the wire.

    Chosen as the happy-path tool because it does not require SW (just
    the RAG index), so it's the cleanest wire-format check.
    """
    proc = _spawn_server(ai_sw_mcp_exe)
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "e2e-test", "version": "0"},
                },
            },
        )
        _recv(proc)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "sw_apidoc_enum",
                    "arguments": {"enum_name": "swDocumentSaveTypes_e"},
                },
            },
        )
        call_resp = _recv(proc)
        assert "result" in call_resp, f"tools/call failed: {call_resp}"
        # FastMCP returns content blocks; the structured tool result
        # appears in result.structuredContent OR result.content[0].text.
        structured = call_resp["result"].get("structuredContent")
        if structured is not None:
            payload = structured
        else:
            content = call_resp["result"].get("content", [])
            text_block = next((c for c in content if c.get("type") == "text"), None)
            assert (
                text_block is not None
            ), f"sw_apidoc_enum returned no text content: {call_resp}"
            payload = json.loads(text_block["text"])

        assert set(payload.keys()) == {"ok", "reason", "enum_name", "hint"}
        assert payload["ok"] is False
        assert payload["reason"] == "enum_corpus_missing"
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait(timeout=10)
