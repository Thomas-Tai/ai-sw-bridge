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

import sys
from typing import Any

from .runtime import ServerRuntime


def create_server(runtime: ServerRuntime) -> Any:
    """Create and configure the FastMCP server.

    Registers every tool from the §6 inventory:

    * Observation (10 tools): sw_active_doc, sw_feature_errors,
      sw_equations, sw_bbox, sw_volume, sw_screenshot, sw_measure,
      sw_mate_errors, sw_custom_props, sw_enabled_addins.
    * Build (1 tool): sw_build.
    * API doc (5 tools): sw_apidoc_search, sw_apidoc_detail,
      sw_apidoc_members, sw_apidoc_examples, sw_apidoc_enum.
    * History (4 tools): sw_history_part, sw_history_since,
      sw_history_diff, sw_checkpoint_info.
    * Reconnect (1 tool): sw_reconnect.

    Total: 21 tools.

    Tools NOT registered in v0.13 (per §6.5): sw_mutate_apply,
    sw_codegen, sw_probe, sw_checkpoint_genkey/rekey/migrate.

    Args:
        runtime: A constructed (but not yet started) ServerRuntime.

    Returns:
        A FastMCP server instance ready for ``mcp.run(transport="stdio")``.
    """
    raise NotImplementedError("W5.4-impl pending")


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
    raise NotImplementedError("W5.4-impl pending")


if __name__ == "__main__":
    sys.exit(main())
