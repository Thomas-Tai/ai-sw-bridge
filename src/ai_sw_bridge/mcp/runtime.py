"""ServerRuntime — single point of state for the MCP server (W5.4).

Design: ``docs/mcp_server_design.md`` §9. The runtime holds the
``ComExecutor`` (W5.1) + a ``SolidWorksAdapter`` instance (W5.2) +
arbitrary config. Tools access it via the module-level ``runtime``
reference set in :func:`create_server` (see ``server.py``).

The runtime is created at process startup and lives until the MCP
client disconnects. Reconnect (after SW death) tears down the dead
executor and starts a fresh one without re-creating the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..com.adapter import SolidWorksAdapter
from ..com.executor import ComExecutor


@dataclass
class ServerRuntime:
    """Single point of state for the MCP server.

    Attributes:
        executor: The STA-threaded ComExecutor. Started in
            :func:`server.main`; tools submit work via
            :meth:`ComExecutor.run` indirectly through ``@com_tool``.
        adapter: The SolidWorksAdapter (PyWin32 on Windows, Mock
            elsewhere — auto-selected by AdapterFactory).
        config: Free-form config passed to tools. v0.13 uses this for
            the read-only/strict-addins toggle and the checkpoint root.
    """

    executor: ComExecutor
    adapter: SolidWorksAdapter
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, adapter_type: str | None = None) -> "ServerRuntime":
        """Create a runtime. Does NOT start the executor.

        ``main()`` is responsible for the start/stop lifecycle so the
        order is deterministic at server entry: create runtime → start
        executor → register tools → mcp.run() → stop executor.

        Args:
            adapter_type: ``"pywin32"``, ``"mock"``, or ``None`` for
                platform auto-selection.
        """
        raise NotImplementedError("W5.4-impl pending")

    def reconnect(self) -> None:
        """Tear down the dead executor + adapter, start fresh.

        Called by the ``sw_reconnect`` MCP tool when
        ``executor.is_sw_dead`` is True (W5.6 wires that flag).

        Post-condition: ``self.executor.is_alive`` is True and a fresh
        STA apartment is held. The adapter is reconnected.
        """
        raise NotImplementedError("W5.4-impl pending")

    def shutdown(self) -> None:
        """Final cleanup. Called from ``main()``'s finally block.

        Idempotent. Safe to call when the executor is already stopped.
        """
        raise NotImplementedError("W5.4-impl pending")
