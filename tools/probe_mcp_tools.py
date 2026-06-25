"""One-shot probe: run every registered MCP tool against MockAdapter + the
committed RAG index, dump each result (and its structural shape) to
``tests/mcp_lane/fixtures/<name>.json``.

Run this once from the repo root:

    python tools/probe_mcp_tools.py

It is not part of the test suite; it is the source-of-truth generator for
the snapshot fixtures. Re-run it whenever the tool output shape changes on
purpose, then review the diff before committing the new snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge.mcp.runtime import ServerRuntime
from ai_sw_bridge.mcp.server import create_server


FIXTURES_ROOT = (
    Path(__file__).resolve().parent.parent / "tests" / "mcp_lane" / "fixtures"
)


def _shape(value):
    """Structural skeleton of *value* — type tags for leaves, key-shapes for dicts.

    Leaves become ``"$str"`` / ``"$int"`` / ``"$float"`` / ``"$bool"`` /
    ``"$none"`` markers. Dicts recurse. Lists keep their length and use the
    first element as a template (homogeneous-list assumption, which holds
    for every tool payload in this surface).
    """
    if value is None:
        return "$none"
    if isinstance(value, bool):
        return "$bool"
    if isinstance(value, int):
        return "$int"
    if isinstance(value, float):
        return "$float"
    if isinstance(value, str):
        return "$str"
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if not value:
            return {"__list__": True, "len": 0, "item": None}
        return {"__list__": True, "len": "*", "item": _shape(value[0])}
    return f"$type:{type(value).__name__}"


def _call(tool, args: dict):
    """Call tool.fn with *args* and return (value, error_string | None)."""
    try:
        return tool.fn(**args), None
    except Exception as exc:  # noqa: BLE001 — snapshot whatever the tool raises
        return None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)

    FIXTURES_ROOT.mkdir(parents=True, exist_ok=True)

    # Argument map per tool. Empty dict => tool is arg-less.
    args_by_tool: dict[str, dict] = {
        # Observation (arg-less)
        "sw_active_doc": {},
        "sw_feature_errors": {},
        "sw_equations": {},
        "sw_bbox": {},
        "sw_volume": {},
        "sw_mate_errors": {},
        "sw_custom_props": {},
        "sw_enabled_addins": {},
        "sw_undercut_faces": {},
        "sw_min_wall_thickness": {},
        # W71/W77 observe additions — no active doc => the no_active_doc branch.
        "sw_feature_statistics": {},
        "sw_analyze_stackup": {
            "components": ["base-1", "top-1"],
            "check_endpoints": True,
        },
        # Batch-plan — point at a path that doesn't exist so the open-doc
        # failure manifest is captured (deterministic, live-seat-independent;
        # mirrors sw_build's nonexistent-spec branch).
        "sw_batch_plan": {
            "file_path": "/nonexistent/part.sldprt",
            "proposals": [{"feature": {"type": "fillet"}, "target": {"edge": "Edge1"}}],
        },
        # Observation (with args)
        "sw_screenshot": {"width": 320, "height": 240, "fit_view": False},
        "sw_measure": {},
        # Build — point at a path that doesn't exist so the validator
        # branch fires before any COM write.
        "sw_build": {"spec_path": "/nonexistent/spec.json"},
        # API doc — enum lookup always returns the corpus_missing branch.
        "sw_apidoc_enum": {"enum_name": "swDocumentSaveTypes_e"},
        "sw_apidoc_search": {"query": "bounding box", "k": 2},
        "sw_apidoc_detail": {"retrieval_key": "does-not-exist"},
        "sw_apidoc_members": {},
        "sw_apidoc_examples": {"limit": 2},
        # Design-memory — the index is a gitignored per-operator artifact, absent
        # in CI, so this captures the deterministic index-not-found branch.
        "sw_retrieve_design_memory": {"query": "bracket linear pattern", "k": 2},
        # Session-health — read-only; no ledger + no seat in CI = the healthy/
        # empty branch (shape-only assertion tolerates a live seat locally).
        "sw_session_health": {},
        # History — no part DB present, so these hit the empty/error branch.
        "sw_history_part": {"part_name": "NonexistentPart"},
        "sw_history_since": {
            "part_name": "NonexistentPart",
            "since_ts": "2024-01-01T00:00:00",
        },
        "sw_history_diff": {
            "part_name": "NonexistentPart",
            "id_a": 1,
            "id_b": 2,
        },
        "sw_checkpoint_info": {"part_name": "NonexistentPart"},
        # Reconnect — safe on mock adapter.
        "sw_reconnect": {},
    }

    tools = {t.name: t for t in mcp.iter_tools()}
    missing = set(args_by_tool) - set(tools)
    if missing:
        raise SystemExit(f"tools not registered: {sorted(missing)}")

    for name, args in sorted(args_by_tool.items()):
        value, err = _call(tools[name], args)
        payload = {
            "tool": name,
            "args": args,
            "result": value,
            "result_shape": _shape(value),
            "error": err,
        }
        out_path = FIXTURES_ROOT / f"{name}.json"
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out_path.name}: err={err!r}")

    runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
