"""MCP server entry point (W5.4).

Stdio MCP server that exposes the bridge's observe / build / apidoc /
history / checkpoint-info surface to MCP clients (Claude Desktop,
Cursor). The tool surface inventory is in
``docs/mcp_server_design.md`` §6.

This module's ``main()`` is wired in ``pyproject.toml`` as
``ai-sw-mcp = "ai_sw_bridge.mcp.server:main"``. The MCP client (e.g.,
Claude Desktop) spawns this as a subprocess and communicates over
stdio per the MCP protocol.

Optional dependency: ``mcp >= 1.0.0`` (Anthropic's Python SDK).
Install with ``pip install ai-sw-bridge[mcp]``.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import runtime as _rt_module
from .runtime import ServerRuntime

logger = logging.getLogger(__name__)


class _Server(FastMCP):
    """FastMCP subclass that exposes ``iter_tools`` for test introspection.

    The MCP wire-format ``mcp.types.Tool`` objects (returned by
    ``FastMCP.list_tools`` over JSON-RPC) lack the wrapped callable
    (``.fn``), but the contract test needs to walk every tool and check
    for the ``@com_tool`` tag. The internal
    ``mcp.server.fastmcp.tools.base.Tool`` record carries ``.fn``.

    Earlier W5.4-impl overrode ``list_tools`` to return those records,
    but ``FastMCP.list_tools`` is ``async`` — overriding it sync broke
    the JSON-RPC ``tools/list`` and ``tools/call`` handlers, which
    ``await`` the call (caught by Wave 5 audit: see commit message).

    This subclass therefore exposes a **separate** sync ``iter_tools``
    accessor that tests and tooling can use to walk ``.fn``; the
    inherited async ``list_tools`` is left untouched so the wire
    protocol works.
    """

    def iter_tools(self) -> list[Any]:
        """Sync accessor for internal Tool records (with ``.fn``)."""
        return list(self._tool_manager.list_tools())


def create_server(runtime: ServerRuntime) -> Any:
    """Create and configure the FastMCP server.

    Registers every tool from the §6 inventory (the authoritative set is
    pinned in ``tests/mcp_lane/test_server_contract.py::EXPECTED_TOOLS``):

    * Observation (22 tools): sw_active_doc, sw_feature_errors,
      sw_equations, sw_bbox, sw_volume, sw_screenshot, sw_measure,
      sw_measure_selection, sw_mate_errors, sw_custom_props,
      sw_enabled_addins, sw_interference, sw_bounding_box, sw_inertia,
      sw_clearance, sw_draft_analysis, sw_current_selection,
      sw_undercut_faces, sw_min_wall_thickness, sw_feature_statistics,
      sw_analyze_stackup, sw_observe_mbd.
    * Build (1 tool): sw_build — validator-gated build pipeline.
    * Batch-plan (1 tool): sw_batch_plan — a READ-ONLY (dry-run)
      validation pass over a multi-feature batch; HARD-WIRED dry-run,
      never writes to disk (the §6.5 write-PLANNING surface).
    * Batch-execute (1 tool): sw_batch_execute — PLAN (dry-run) then
      elicit human approval IN-CHAT (MCP elicitation) then COMMIT. The
      ``ai-sw-batch`` CLI ``[y/N]`` gate moved into the agent surface;
      the human-in-the-loop is preserved, only the surface changes.
      Async (NOT @com_tool) — it awaits ctx.elicit between two STA COM
      phases; capability-gated, degrades to sw_batch_plan + CLI.
    * API doc (5 tools): sw_apidoc_search, sw_apidoc_detail,
      sw_apidoc_members, sw_apidoc_examples, sw_apidoc_enum.
    * Design-Memory (1 tool): sw_retrieve_design_memory — local,
      on-device semantic retrieval over the operator's design history.
    * History + checkpoint info (4 tools): sw_history_part,
      sw_history_since, sw_history_diff, sw_checkpoint_info.
    * Resilience + lifecycle (2 tools): sw_session_health (read-only),
      sw_reconnect.

    Total: 37 tools.

    Write-gate policy (§6.5). The four free-standing mutate operations
    (sw_propose_local_change, sw_dry_run, sw_commit,
    sw_undo_last_commit) stay CLI-only: each commits an irreversible
    write and the MCP surface deliberately does not re-expose them.
    The batch lane DOES reach disk over MCP, but only through a human
    in the loop: sw_batch_plan is hard-wired dry-run (it CANNOT commit),
    and sw_batch_execute commits ONLY after an explicit in-chat
    elicitation approval (capability-gated; degrades to the CLI when the
    client cannot elicit). So no MCP tool persists a mutation without a
    human approval in the loop — the approval surface is CLI [y/N] OR MCP
    elicitation, not autonomous. sw_codegen, sw_probe, and
    sw_checkpoint_genkey/rekey/migrate are also CLI-only.

    Args:
        runtime: A constructed (but not yet started) ServerRuntime.

    Returns:
        A FastMCP server instance ready for ``mcp.run(transport="stdio")``.
    """
    # Wire the module-level runtime reference that ``@com_tool`` reads
    # at request time. Tools import lazily, so this has to be set
    # BEFORE any tool module is imported below.
    _rt_module._current_runtime = runtime

    mcp = _Server(name="ai-sw-bridge", instructions=_SERVER_INSTRUCTIONS)

    # Importing each tool module triggers the ``@mcp.tool()`` decorators,
    # which register against the module-level ``mcp`` — so we pass the
    # server via a registration helper rather than relying on a global.
    from . import (
        _tool_apidoc,
        _tool_batch,
        _tool_batch_execute,
        _tool_build,
        _tool_design_memory,
        _tool_health,
        _tool_history,
        _tool_observe,
        _tool_reconnect,
    )

    _tool_observe.register(mcp)
    _tool_build.register(mcp)
    _tool_batch.register(mcp)
    _tool_batch_execute.register(mcp)
    _tool_apidoc.register(mcp)
    _tool_design_memory.register(mcp)
    _tool_health.register(mcp)
    _tool_history.register(mcp)
    _tool_reconnect.register(mcp)

    return mcp


_SERVER_INSTRUCTIONS = (
    "ai-sw-bridge MCP server. Read-only observation tools mirror the "
    "`ai-sw-observe` CLI; `sw_build` validates a spec then builds it only "
    "after you approve the plan via the in-chat elicitation prompt; "
    "`sw_batch_plan` validates a multi-feature batch without writing "
    "(hard-wired dry-run); `sw_batch_execute` commits a batch only after "
    "you approve the plan via the in-chat elicitation prompt; `sw_reconnect` "
    "re-acquires SldWorks.Application after the SW process dies "
    "(ComExecutor.is_sw_dead=True). The two write tools (`sw_build`, "
    "`sw_batch_execute`) never persist without your in-chat approval — COM "
    "writes are irreversible within a single SW session, so review the plan "
    "before approving."
)


def main() -> int:
    """Stdio entry point for ``ai-sw-mcp``.

    Lifecycle:

    1. Create a ServerRuntime (adapter + executor, not yet started).
    2. Start the executor (CoInitialize on the worker thread).
    3. Create the FastMCP server and register tools.
    4. ``mcp.run(transport="stdio")`` — blocks until the client disconnects.
    5. Stop the executor (CoUninitialize) in the finally block.
    6. Call ``runtime.shutdown()`` for any other cleanup.

    Returns:
        Process exit code. 0 on clean disconnect.
    """
    runtime = ServerRuntime.create()
    # adapter.connect() acquires SldWorks.Application on the current
    # thread. After the executor starts, all subsequent COM calls go
    # through the executor's STA worker, so the initial connect uses
    # a short-lived handle that the first @com_tool call replaces
    # with a worker-thread-resident dispatch.
    try:
        runtime.adapter.connect()
    except ConnectionError as exc:
        logger.error("adapter.connect() failed at startup: %s", exc)
        return 1
    try:
        runtime.executor.start()
    except RuntimeError as exc:
        # pywin32 missing, or CoInitialize failed.
        logger.error("executor.start() failed: %s", exc)
        try:
            runtime.adapter.disconnect()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
        return 1

    mcp = create_server(runtime)
    try:
        mcp.run(transport="stdio")
    finally:
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
