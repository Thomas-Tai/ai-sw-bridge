"""Reconnect MCP tool (W5.4, §8.4).

Single tool ``sw_reconnect`` — tears down the dead executor + adapter
and starts fresh after SW process death. Triggered by the MCP client
when an earlier tool call surfaces the reconnect hint from
``ComExecutor.is_sw_dead``.

Not COM-touching itself (it delegates to
:meth:`ai_sw_bridge.mcp.runtime.ServerRuntime.reconnect`, which
orchestrates the executor restart), so it does NOT use ``@com_tool``.
The contract test exempts it from the decorator audit.
"""

from __future__ import annotations

from typing import Any


def register(mcp: Any) -> None:
    """Register the ``sw_reconnect`` tool against *mcp*."""

    @mcp.tool()
    def sw_reconnect() -> dict[str, Any]:
        """Re-acquire SldWorks.Application on a fresh STA thread.

        Call this after any tool returns a reconnect hint (triggered
        by the SW process dying — see ``ComExecutor.is_sw_dead`` and
        ``docs/com_failure_modes.md`` row M-01). The previous worker
        thread is joined, the adapter re-Dispatches, and a new STA
        worker is started.

        .. warning::

           The new SW process has no knowledge of any partially-built
           state from a prior ``sw_build`` call. Verify the model
           after reconnect.
        """
        from . import runtime as _rt_module

        rt = _rt_module._current_runtime
        if rt is None:
            return {
                "ok": False,
                "error": "ServerRuntime not wired",
                "hint": "Server startup incomplete; restart the MCP server.",
            }
        try:
            rt.reconnect()
        except ConnectionError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "executor_alive": rt.executor.is_alive,
            "hint": (
                "Fresh STA worker is up. Call sw_active_doc or "
                "sw_bbox to confirm the new SW session responds."
            ),
        }
