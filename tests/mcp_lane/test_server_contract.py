"""Test contract for ai_sw_bridge.mcp.server (W5.4).

Cross-reference: ``docs/mcp_server_design.md`` §11 — each test maps
1:1 to a row there. The contract is the load-bearing artifact for
the design: it pins behavior so the impl can't drift.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# §11.1 Runtime smoke (no SW needed)
# ---------------------------------------------------------------------------


class TestRuntime:
    def test_create_runtime_returns_executor_and_adapter(self) -> None:
        from ai_sw_bridge.mcp.runtime import ServerRuntime

        runtime = ServerRuntime.create(adapter_type="mock")
        assert runtime.executor is not None
        assert runtime.adapter is not None
        assert not runtime.executor.is_alive  # NOT started by .create()

    def test_runtime_shutdown_stops_executor(self) -> None:
        from ai_sw_bridge.mcp.runtime import ServerRuntime

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()
        runtime.shutdown()
        assert not runtime.executor.is_alive

    def test_runtime_reconnect_resets_dead_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After executor flips is_sw_dead, reconnect() yields a fresh executor."""
        from ai_sw_bridge.mcp.runtime import ServerRuntime

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()

        # Simulate SW death (W5.6 wires the real flag; we patch).
        monkeypatch.setattr(runtime.executor, "_sw_app_is_dead", True, raising=False)

        runtime.reconnect()
        assert runtime.executor.is_alive
        assert getattr(runtime.executor, "_sw_app_is_dead", False) is False


# ---------------------------------------------------------------------------
# §11.2 Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """Inventory + safety-decorator audit on the registered tool set."""

    EXPECTED_TOOLS = frozenset(
        {
            # Observation (17)
            "sw_active_doc",
            "sw_feature_errors",
            "sw_equations",
            "sw_bbox",
            "sw_volume",
            "sw_screenshot",
            "sw_measure",
            "sw_mate_errors",
            "sw_custom_props",
            "sw_enabled_addins",
            # W27 — interference
            "sw_interference",
            # W30 — perception axis
            "sw_bounding_box",
            "sw_measure_selection",
            # W5 E1 — inertia
            "sw_inertia",
            # W35 — clearance
            "sw_clearance",
            # W45 — DFM probes
            "sw_undercut_faces",
            "sw_min_wall_thickness",
            # Build (1)
            "sw_build",
            # API doc (5)
            "sw_apidoc_search",
            "sw_apidoc_detail",
            "sw_apidoc_members",
            "sw_apidoc_examples",
            "sw_apidoc_enum",
            # History (4)
            "sw_history_part",
            "sw_history_since",
            "sw_history_diff",
            "sw_checkpoint_info",
            # Reconnect (1)
            "sw_reconnect",
        }
    )

    EXCLUDED_TOOLS = frozenset(
        {
            # Mutate stays CLI-only — requires human approval per call.
            # If any of these ever get wrapped with @server.tool, the MCP
            # client gains write access without the per-call HITL gate.
            "sw_propose_local_change",
            "sw_dry_run",
            "sw_commit",
            "sw_undo_last_commit",
            # Credential operations stay CLI-only.
            "sw_checkpoint_genkey",
            "sw_checkpoint_rekey",
            "sw_checkpoint_migrate",
            # Codegen + probe — not request/response shaped.
            "sw_codegen",
            "sw_probe",
        }
    )

    def _registered_tool_names(self) -> set[str]:
        # ai_sw_bridge.mcp.server imports the optional `mcp` SDK at module
        # load. The `test` CI job installs `[dev]` (not `[mcp]`); skip
        # these tool-registration tests there. runtime + tools (used by
        # TestRuntime and TestComToolWrapping) don't need the SDK so they
        # still run on a `[dev]`-only install.
        pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.server import create_server

        runtime = ServerRuntime.create(adapter_type="mock")
        mcp = create_server(runtime)
        # _Server.iter_tools() yields the internal Tool records (with
        # .fn). The inherited async list_tools() is reserved for the
        # JSON-RPC wire protocol.
        return {t.name for t in mcp.iter_tools()}

    def test_tool_inventory_matches_design(self) -> None:
        names = self._registered_tool_names()
        assert names == self.EXPECTED_TOOLS

    def test_excluded_tools_not_registered(self) -> None:
        names = self._registered_tool_names()
        for excluded in self.EXCLUDED_TOOLS:
            assert excluded not in names, (
                f"{excluded!r} must NOT be exposed via MCP " "(design doc §6.5)"
            )

    def test_all_com_tools_have_decorator(self) -> None:
        """Every tool that touches the adapter MUST be @com_tool-wrapped."""
        # See note on _registered_tool_names: server.py needs the `mcp` SDK.
        pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

        from ai_sw_bridge.mcp.tools import is_com_tool

        # Tools that exercise SOLIDWORKS COM (per the design's §6.1, §6.2).
        # apidoc + history + checkpoint_info touch SQLite, not COM — exempt.
        com_tool_names = frozenset(
            {
                "sw_active_doc",
                "sw_feature_errors",
                "sw_equations",
                "sw_bbox",
                "sw_volume",
                "sw_screenshot",
                "sw_measure",
                "sw_mate_errors",
                "sw_custom_props",
                "sw_enabled_addins",
                "sw_build",
            }
        )

        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.server import create_server

        runtime = ServerRuntime.create(adapter_type="mock")
        mcp = create_server(runtime)

        # FastMCP stores the wrapped callable on the tool record;
        # iter_tools() is _Server's sync accessor for the contract test.
        for tool in mcp.iter_tools():
            if tool.name not in com_tool_names:
                continue
            assert is_com_tool(tool.fn), (
                f"{tool.name!r} is COM-touching but missing @com_tool — "
                "see docs/mcp_server_design.md §10"
            )


# ---------------------------------------------------------------------------
# §11.3 @com_tool wrapping behavior
# ---------------------------------------------------------------------------


class TestComToolWrapping:
    def test_com_tool_runs_on_executor_thread(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The wrapped function runs on the executor's worker, not the caller."""
        import threading

        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.tools import com_tool

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()

        # Wire the module-level runtime reference the decorator reads.
        import ai_sw_bridge.mcp.runtime as rt_module

        monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

        caller_tid = threading.get_ident()
        captured: dict[str, int] = {}

        @com_tool
        def probe():
            captured["worker_tid"] = threading.get_ident()
            return "ok"

        try:
            result = probe()
        finally:
            runtime.shutdown()

        assert result == "ok"
        assert captured["worker_tid"] != caller_tid

    def test_com_tool_propagates_exceptions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.tools import com_tool

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()

        import ai_sw_bridge.mcp.runtime as rt_module

        monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

        @com_tool
        def boom():
            raise ValueError("from worker")

        try:
            with pytest.raises(ValueError, match="from worker"):
                boom()
        finally:
            runtime.shutdown()

    def test_com_tool_propagates_return_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.tools import com_tool

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()

        import ai_sw_bridge.mcp.runtime as rt_module

        monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

        @com_tool
        def echo():
            return {"ok": True, "value": 42}

        try:
            assert echo() == {"ok": True, "value": 42}
        finally:
            runtime.shutdown()

    def test_com_tool_handles_executor_dead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When executor is_sw_dead, the tool raises with a reconnect hint."""
        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.tools import com_tool

        runtime = ServerRuntime.create(adapter_type="mock")
        runtime.executor.start()

        import ai_sw_bridge.mcp.runtime as rt_module

        monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)
        monkeypatch.setattr(runtime.executor, "_sw_app_is_dead", True, raising=False)

        @com_tool
        def probe():
            return "should not reach"

        try:
            with pytest.raises(RuntimeError, match="reconnect"):
                probe()
        finally:
            runtime.shutdown()


# ---------------------------------------------------------------------------
# §11.4 Wire format
# ---------------------------------------------------------------------------


class TestWireFormat:
    def test_all_tool_returns_json_serializable(self) -> None:
        """Every registered tool's return type must be json.dumps-able.

        Catches accidental returns of tuples, sets, datetime objects,
        or anything else that breaks the MCP serialization layer.
        """
        # See note on _registered_tool_names: server.py needs the `mcp` SDK.
        pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

        import inspect

        from ai_sw_bridge.mcp.runtime import ServerRuntime
        from ai_sw_bridge.mcp.server import create_server

        runtime = ServerRuntime.create(adapter_type="mock")
        mcp = create_server(runtime)

        for tool in mcp.iter_tools():
            sig = inspect.signature(tool.fn)
            # Walk default values + annotations; if a tool returns a
            # well-typed dict, json.dumps round-trips. We can't actually
            # call the tool without SW for COM tools, so this is a
            # type-annotation check via the impl-provided helper.
            annotation = sig.return_annotation
            assert annotation in (dict, "dict[str, Any]", "dict[str, object]"), (
                f"{tool.name!r} return annotation must be a dict shape "
                f"(got {annotation!r})"
            )

    def test_validation_error_maps_to_invalid_params(self, tmp_path) -> None:
        """sw_build on a malformed spec → MCP error with -32602 (Invalid params)."""
        # The impl wraps ValidationError to mcp.ToolError(code=-32602).
        # Test exercises a real malformed spec against MockAdapter so
        # validator.validate() raises ValidationError before any COM.
        pytest.skip("Requires fully wired tool to fire — covered in §11.5")
