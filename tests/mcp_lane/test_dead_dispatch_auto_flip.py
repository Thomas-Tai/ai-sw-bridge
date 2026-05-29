"""Regression: ``@com_tool`` flips ``is_sw_dead`` on dead-dispatch payload.

Wave 5 Phase 2.5 audit (2026-05-28) found that pywin32 surfaces SW
process death as ``AttributeError('SldWorks.Application.<member>')``,
NOT the catalogued death HRESULTs that ``ComExecutor._worker``'s trap
matches. ``observe.*`` / ``mutate.*`` catch the AttributeError into a
string ``result['error']`` and return a well-formed payload, so the
exception never reaches the worker's HRESULT trap and ``is_sw_dead``
stays False — the user sees the same dispatch-failed message on every
subsequent call.

The v0.13.0 fix: ``@com_tool`` inspects the returned payload for the
dead-dispatch pattern and calls ``executor.mark_sw_dead()`` so the
next call short-circuits with the reconnect hint.

This test exercises the post-hoc detection without needing live SW —
it monkey-patches a tool body to return the dead-dispatch shape and
asserts the flag flips.
"""

from __future__ import annotations

import pytest


def test_com_tool_marks_executor_dead_on_dispatch_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool returning the dead-dispatch error pattern flips is_sw_dead."""
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    from ai_sw_bridge.mcp.tools import com_tool
    import ai_sw_bridge.mcp.runtime as rt_module

    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.executor.start()
    monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

    @com_tool
    def fake_dead_tool() -> dict:
        return {
            "ok": False,
            "doc_path": None,
            "error": (
                "dispatch failed: " "AttributeError('SldWorks.Application.ActiveDoc')"
            ),
        }

    try:
        assert runtime.executor.is_sw_dead is False, "precondition: not dead"

        result = fake_dead_tool()
        assert result["ok"] is False
        assert (
            runtime.executor.is_sw_dead is True
        ), "@com_tool did not flip is_sw_dead on dead-dispatch payload"
    finally:
        runtime.shutdown()


def test_com_tool_does_not_flip_on_non_sw_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool returning a NON-SW AttributeError (e.g. Extension API miss)
    must NOT flip is_sw_dead. This is the false-positive guard."""
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    from ai_sw_bridge.mcp.tools import com_tool
    import ai_sw_bridge.mcp.runtime as rt_module

    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.executor.start()
    monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

    @com_tool
    def fake_api_miss_tool() -> dict:
        # The ``<unknown>.GetCustomInfoNames3`` pattern from Phase 2.5 —
        # an API miss on Extension, NOT a death signal.
        return {
            "ok": False,
            "properties": {},
            "count": 0,
            "error": (
                "GetCustomInfoNames3 failed: "
                "AttributeError('<unknown>.GetCustomInfoNames3')"
            ),
        }

    try:
        fake_api_miss_tool()
        assert runtime.executor.is_sw_dead is False, (
            "@com_tool flipped is_sw_dead on a non-death AttributeError — "
            "false positive on a legitimate API miss"
        )
    finally:
        runtime.shutdown()


def test_com_tool_short_circuits_after_dead_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a dead-dispatch payload flips the flag, the very next
    @com_tool call short-circuits with the reconnect-required hint
    instead of invoking the underlying body."""
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    from ai_sw_bridge.mcp.tools import com_tool
    import ai_sw_bridge.mcp.runtime as rt_module

    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.executor.start()
    monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

    call_count = {"n": 0}

    @com_tool
    def dead_tool() -> dict:
        call_count["n"] += 1
        return {
            "ok": False,
            "error": "dispatch failed: AttributeError('SldWorks.Application.X')",
        }

    @com_tool
    def follow_up_tool() -> dict:
        call_count["n"] += 1
        return {"ok": True}  # would succeed if reached

    try:
        dead_tool()
        assert call_count["n"] == 1
        assert runtime.executor.is_sw_dead is True

        with pytest.raises(RuntimeError, match="sw_reconnect"):
            follow_up_tool()
        # follow_up_tool's body must NOT have run — the pre-check
        # short-circuited.
        assert call_count["n"] == 1, (
            f"follow_up_tool body ran ({call_count['n']} calls) "
            "after is_sw_dead was True"
        )
    finally:
        runtime.shutdown()
