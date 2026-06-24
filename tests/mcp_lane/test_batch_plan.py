"""Contract test — the ``sw_batch_plan`` MCP tool (the §6.5 write-PLANNING surface).

``sw_batch_plan`` must:
  1. be COM-touching and @com_tool-wrapped (runs on the ComExecutor STA thread);
  2. HARD-WIRE ``dry_run=True`` into the batch engine — the MCP surface can never
     persist (the document is never saved to disk regardless of outcome);
  3. return the recovery manifest annotated with the read-only / human-gate
     contract (``mcp_mode``, ``committed_to_disk=False``, ``next_step``).

These run SDK-free: a tiny fake ``mcp`` captures the registered tool function so
the test exercises the real tool body + the @com_tool wrapper through a real
ServerRuntime, with the batch ENGINE patched to capture the kwargs it receives.
"""

from __future__ import annotations

from ai_sw_bridge.mcp import _tool_batch
from ai_sw_bridge.mcp.tools import is_com_tool


class _FakeMcp:
    """Captures functions registered via ``@mcp.tool()`` without the SDK."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _register_and_get():
    fake = _FakeMcp()
    _tool_batch.register(fake)
    return fake.tools["sw_batch_plan"]


def test_tool_is_registered_and_com_wrapped():
    fn = _register_and_get()
    assert is_com_tool(fn), "sw_batch_plan must be @com_tool-wrapped (COM-touching)"


def test_tool_forces_dry_run_and_annotates(monkeypatch):
    """The tool invokes the engine with dry_run=True and stamps the HITL contract."""
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    import ai_sw_bridge.mcp.runtime as rt_module

    captured: dict = {}

    def fake_engine(doc_path, proposals, strict=False, dry_run=False):
        captured["doc_path"] = doc_path
        captured["proposals"] = proposals
        captured["strict"] = strict
        captured["dry_run"] = dry_run
        # a minimal would-commit manifest
        return {
            "ok": True, "doc_path": doc_path, "dry_run": dry_run,
            "doc_saved": False, "committed_count": 2, "committed": [],
            "fault": None, "skipped": [], "error": None,
        }

    monkeypatch.setattr(_tool_batch, "_sw_batch_feature_add_impl", fake_engine)

    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.executor.start()
    monkeypatch.setattr(rt_module, "_current_runtime", runtime, raising=False)

    proposals = [
        {"feature": {"type": "ref_plane"}, "target": {"plane": "Front Plane"}},
        {"feature": {"type": "com_point"}, "target": {"x": 0}},
    ]
    try:
        fn = _register_and_get()
        result = fn("C:/part.sldprt", proposals)
    finally:
        runtime.shutdown()

    # the engine was driven in PLAN-ONLY mode
    assert captured["dry_run"] is True
    assert captured["strict"] is False
    assert captured["doc_path"] == "C:/part.sldprt"
    assert captured["proposals"] == proposals

    # the payload carries the read-only / human-gate contract
    assert result["dry_run"] is True and result["doc_saved"] is False
    assert result["mcp_mode"] == "plan_only_dry_run"
    assert result["committed_to_disk"] is False
    assert "human" in result["next_step"].lower()


def test_returns_dict_shape():
    """Return annotation must be a dict shape (MCP wire-format contract)."""
    import inspect

    fn = _register_and_get()
    # unwrap @com_tool to read the underlying signature
    inner = getattr(fn, "__wrapped__", fn)
    ann = inspect.signature(inner).return_annotation
    assert ann in (dict, "dict[str, Any]")
