"""Regression: ``ServerRuntime.reconnect()`` clears the sw_com dispatch cache.

Wave 5 Phase 2.5 audit (2026-05-28) found that the MCP ``sw_reconnect``
tool succeeded logically (executor restarted, adapter re-dispatched)
but subsequent observe.* calls still surfaced the dead-handle
``AttributeError`` because ``sw_com._CACHED_SW_APP`` is a module-level
global that survived reconnect.

The fix in ``ServerRuntime.reconnect()`` calls
``sw_com.release_sw_app()`` so the next ``get_sw_app()`` re-dispatches
against whatever SW process is alive now.

This test verifies the call site without needing a live SW process —
it monkeypatches ``release_sw_app`` and asserts the patch was invoked.
"""

from __future__ import annotations

import pytest


def test_reconnect_clears_sw_com_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """ServerRuntime.reconnect() must call sw_com.release_sw_app()."""
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    import ai_sw_bridge.sw_com as sw_com

    called: list[bool] = []

    def fake_release():
        called.append(True)

    monkeypatch.setattr(sw_com, "release_sw_app", fake_release)

    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.executor.start()
    try:
        runtime.reconnect()
    finally:
        runtime.shutdown()

    assert called, (
        "ServerRuntime.reconnect() did not call sw_com.release_sw_app() — "
        "observe.* will reuse the stale dispatch cache after reconnect"
    )
