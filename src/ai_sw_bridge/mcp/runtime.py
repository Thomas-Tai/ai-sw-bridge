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

import logging
from dataclasses import dataclass, field
from typing import Any

from ..com.adapter import SolidWorksAdapter
from ..com.executor import ComExecutor
from ..com.factory import AdapterFactory

logger = logging.getLogger(__name__)


# Module-level runtime reference. Set by ``server.create_server()`` and
# read lazily by ``@com_tool`` (which runs at request time, not import
# time). Using a module-level slot keeps the decorator free of global
# state while still allowing tools to locate the executor without every
# caller threading it through.
_current_runtime: "ServerRuntime | None" = None


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
        adapter = AdapterFactory.create_adapter(adapter_type)
        executor = ComExecutor(name="SolidWorks-MCP-COM")
        return cls(executor=executor, adapter=adapter, config={})

    def reconnect(self) -> None:
        """Tear down the dead executor + adapter, start fresh.

        Called by the ``sw_reconnect`` MCP tool when
        ``executor.is_sw_dead`` is True (W5.6 wires that flag).

        Post-condition: ``self.executor.is_alive`` is True, the
        ``sw_com`` module-level dispatch cache is cleared, and a fresh
        STA apartment is held. The adapter is reconnected.
        """
        logger.info("ServerRuntime: reconnecting after SW death")

        # Drop the module-level sw_com._CACHED_SW_APP. observe.* and
        # mutate.* call sw_com.get_sw_app() directly (the W5.2 adapter
        # is not in their call path), so without this the next tool
        # call reuses the stale dispatch handle and surfaces the same
        # AttributeError that signalled death in the first place.
        # Found by Wave 5 Phase 2.5 audit (2026-05-28).
        try:
            from ..sw_com import release_sw_app

            release_sw_app()
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug("release_sw_app during reconnect raised: %r", exc)

        # Adapter: it may hold a stale IDispatch. A fresh connect
        # re-Dispatches SldWorks.Application on whatever SW is running now.
        try:
            self.adapter.disconnect()
        except Exception as exc:  # noqa: BLE001 — best-effort teardown
            logger.debug("adapter.disconnect during reconnect raised: %r", exc)
        try:
            self.adapter.connect()
        except Exception as exc:
            # Fresh adapter failed to connect — propagate so the MCP
            # client gets a typed error rather than a silent hang.
            raise ConnectionError(
                f"reconnect failed: adapter.connect() raised: {exc}"
            ) from exc

        # Executor: ComExecutor.reconnect() resets the dead flag, replaces
        # the queue, and starts a fresh STA worker.
        self.executor.reconnect()
        logger.info("ServerRuntime: reconnect complete; executor.is_alive=True")

    def shutdown(self) -> None:
        """Final cleanup. Called from ``main()``'s finally block.

        Idempotent. Safe to call when the executor is already stopped.
        """
        logger.info("ServerRuntime: shutting down")
        # Stop the executor first — the worker may still be running COM
        # calls through the adapter; cutting the worker before the
        # adapter means no further COM traffic after this point.
        try:
            self.executor.stop()
        except Exception as exc:  # noqa: BLE001 — shutdown is best-effort
            logger.debug("executor.stop during shutdown raised: %r", exc)
        try:
            self.adapter.disconnect()
        except Exception as exc:  # noqa: BLE001 — shutdown is best-effort
            logger.debug("adapter.disconnect during shutdown raised: %r", exc)
