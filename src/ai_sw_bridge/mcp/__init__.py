"""MCP server lane (W5.4).

Stdio MCP server that exposes the bridge's existing tool surface
(observe, build, apidoc, history, checkpoint info) over the Model
Context Protocol so shell-less clients (Claude Desktop, Cursor) can
drive SOLIDWORKS via the same primitives as the CLIs.

Design lives in ``docs/mcp_server_design.md``. This package is the
implementation; the CLIs in ``ai_sw_bridge.cli`` are peer entry
points, not consumers of this lane.

Optional install: ``pip install ai-sw-bridge[mcp]``.
"""

from __future__ import annotations

__all__ = [
    "ServerRuntime",
    "com_tool",
    "create_server",
    "main",
]


def __getattr__(name: str):
    # Defer imports so importing ``ai_sw_bridge`` doesn't pull ``mcp``
    # transitively. The optional extra (``ai-sw-bridge[mcp]``) installs
    # ``mcp``; users without the extra still get a clean ImportError
    # only when they actually invoke the server.
    if name == "create_server":
        from .server import create_server

        return create_server
    if name == "main":
        from .server import main

        return main
    if name == "ServerRuntime":
        from .runtime import ServerRuntime

        return ServerRuntime
    if name == "com_tool":
        from .tools import com_tool

        return com_tool
    raise AttributeError(f"module 'ai_sw_bridge.mcp' has no attribute {name!r}")
