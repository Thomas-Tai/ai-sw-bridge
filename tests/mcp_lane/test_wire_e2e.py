"""Wire-level end-to-end tests for the MCP server (W5.4 design §11.5,
implemented in W5.5 follow-up S2).

These three tests were stubbed with ``pytest.skip`` in the original
contract test (``test_server_contract.py`` §11.5) because Wave 5 was
blocked on an in-memory MCP transport. The ``mcp`` SDK ships
``mcp.shared.memory.create_client_server_memory_streams``, which we
use directly here — the higher-level
``create_connected_server_and_client_session`` helper trips an anyio
cancel-scope bug under pytest-asyncio's fixture teardown (the server
task group is entered on the fixture's task and exited on the test
task), so we wire the streams by hand inside a single task group that
owns both server and client for the test's duration.

Kept separate from the §11.1–§11.4 contract tests because they
exercise the asyncio transport; failure modes are different (hangs,
timeouts, capability negotiation errors) and should not pollute the
pure-Python contract test run.

Note on MockAdapter and ``observe.sw_*``: the observation functions
(``observe.sw_get_bbox`` et al.) call ``sw_com.get_sw_app`` directly,
NOT through the adapter wired into ``ServerRuntime``. On a Windows
machine with SOLIDWORKS running, the observation path reaches the
live SW process regardless of ``adapter_type``. The wire tests assert
on structural shape, not on specific values, so they pass whether the
observation hits MockAdapter (no SW running) or live COM (SW running).
"""

from __future__ import annotations

import json

import pytest

# Skip cleanly when the optional `mcp` SDK is absent (onboarding CI job
# installs without the `[mcp]` extra). anyio is a transitive dep of mcp
# so a single importorskip("mcp") gates both. Without this, the imports
# below would crash pytest *collection* before marker filtering.
pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from ai_sw_bridge.mcp.runtime import ServerRuntime
from ai_sw_bridge.mcp.server import create_server


# ---------------------------------------------------------------------------
# §11.5 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_handshake() -> None:
    """MCP ``initialize`` → server declares the ``tools`` capability."""
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: mcp._mcp_server.run(
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(
                        read_stream=client_read,
                        write_stream=client_write,
                    ) as session:
                        await session.initialize()
                        caps = session.get_server_capabilities()
                        assert caps is not None, "server returned no capabilities"
                        assert caps.tools is not None, (
                            "server did not declare the `tools` capability — "
                            "the agent cannot call tools/list or tools/call "
                            "without it"
                        )
                finally:
                    tg.cancel_scope.cancel()
    finally:
        runtime.shutdown()


@pytest.mark.asyncio
async def test_list_tools_matches_inventory() -> None:
    """``tools/list`` returns the design-doc §6 inventory (23 tools)."""
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: mcp._mcp_server.run(
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(
                        read_stream=client_read,
                        write_stream=client_write,
                    ) as session:
                        await session.initialize()
                        response = await session.list_tools()
                        actual = {t.name for t in response.tools}
                        from tests.mcp_lane.test_server_contract import (
                            TestToolRegistration,
                        )

                        expected = TestToolRegistration.EXPECTED_TOOLS
                        assert actual == expected, (
                            f"tools/list inventory drift — "
                            f"extra={sorted(actual - expected)}, "
                            f"missing={sorted(expected - actual)}"
                        )
                finally:
                    tg.cancel_scope.cancel()
    finally:
        runtime.shutdown()


@pytest.mark.asyncio
async def test_call_sw_bbox_against_mock() -> None:
    """``tools/call sw_bbox`` over the wire returns a well-formed bbox dict.

    Wire payload is FastMCP's standard ``TextContent`` envelope:
    ``content = [TextContent(type="text", text=<json-string>)]``. We
    parse the text back to a dict and check structural shape: the
    key set matches the documented bbox schema, ``ok`` is a bool,
    ``error`` is either ``null`` (doc present) or a non-empty string
    (no doc / wrong doc type). We intentionally do NOT pin specific
    field values — see module docstring for the MockAdapter-vs-live-
    COM caveat.
    """
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: mcp._mcp_server.run(
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(
                        read_stream=client_read,
                        write_stream=client_write,
                    ) as session:
                        await session.initialize()
                        result = await session.call_tool("sw_bbox", arguments={})

                        assert result.content, "sw_bbox returned empty content list"
                        text_block = result.content[0]
                        assert getattr(text_block, "type", None) == "text", (
                            f"expected a text content block, got "
                            f"{type(text_block).__name__}"
                        )
                        payload = json.loads(text_block.text)

                        expected_keys = {
                            "ok",
                            "doc_path",
                            "x_min_mm",
                            "x_max_mm",
                            "x_span_mm",
                            "y_min_mm",
                            "y_max_mm",
                            "y_span_mm",
                            "z_min_mm",
                            "z_max_mm",
                            "z_span_mm",
                            "x_min_m",
                            "x_max_m",
                            "y_min_m",
                            "y_max_m",
                            "z_min_m",
                            "z_max_m",
                            "error",
                        }
                        assert set(payload) == expected_keys, (
                            f"bbox key-set drift — "
                            f"extra={sorted(set(payload) - expected_keys)}, "
                            f"missing={sorted(expected_keys - set(payload))}"
                        )
                        assert isinstance(payload["ok"], bool)
                        assert payload["error"] is None or isinstance(
                            payload["error"], str
                        )
                        # JSON-RPC did not flag this as a tool error.
                        assert getattr(result, "isError", False) is False
                finally:
                    tg.cancel_scope.cancel()
    finally:
        runtime.shutdown()
