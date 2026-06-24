"""sw_batch_plan MCP tool — seat PAE (live validation, ZERO disk mutation).

Drives the REAL registered ``sw_batch_plan`` tool through the REAL ServerRuntime
+ ComExecutor on the live seat (the full MCP path minus the stdio JSON-RPC framing,
which the existing mcp_lane wire tests cover). Proves the §6.5 contract on the
kernel:

  A facade_seam : create_server registers sw_batch_plan (it's in iter_tools).
  B validates   : a 3-feature batch [ref_plane, scale, com_point] dry-runs through
                  the executor → ok=True, dry_run=True, doc_saved=False,
                  committed_count=3 (every B-rep validated on the live kernel).
  C disk_untouched : the .sldprt on disk is DEFINITIVELY not modified — file mtime
                  is unchanged AND a reopen shows the feature count unchanged.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_mcp_batch_plan_pae.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_OUT = _RESULTS / "mcp_batch_plan_pae.json"
results: dict[str, Any] = {"pae": "mcp_batch_plan", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _RESULTS.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block_to_disk(sw: Any, path: Path) -> None:
    _close_all(sw)
    doc = fx.build_block(sw)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    doc.SaveAs3(str(path), 0, 0)
    _close_all(sw)


def _reopen_node_count(sw: Any, path: Path) -> int:
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(str(path), 1, 1, "", errs, warns)
    n = verify.feature_node_count(doc)
    _close_all(sw)
    return n


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    _RESULTS.mkdir(parents=True, exist_ok=True)

    # Fixture on the main thread: build, save, close (no doc left open).
    sw = w32.Dispatch("SldWorks.Application")
    path = _RESULTS / "mcp_batch_plan_pae.sldprt"
    _build_block_to_disk(sw, path)
    nodes_before = _reopen_node_count(sw, path)
    mtime_before = path.stat().st_mtime_ns

    from ai_sw_bridge.mcp.runtime import ServerRuntime
    from ai_sw_bridge.mcp.server import create_server

    runtime = ServerRuntime.create(adapter_type="pywin32")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        tool = next((t for t in mcp.iter_tools() if t.name == "sw_batch_plan"), None)
        gate(
            "facade_seam",
            tool is not None,
            f"sw_batch_plan registered={tool is not None}",
        )
        if tool is None:
            return _finish()

        proposals = [
            {
                "feature": {"type": "ref_plane", "distance_mm": 25.0},
                "target": {"plane": "Front Plane"},
            },
            {"feature": {"type": "scale", "scale_factor": 1.5}, "target": {}},
            {"feature": {"type": "com_point"}, "target": {}},
        ]
        # Drives @com_tool → ComExecutor STA thread → engine dry_run on the kernel.
        r = tool.fn(str(path), proposals)
        results["manifest"] = r
        ok_b = (
            r.get("ok") is True
            and r.get("dry_run") is True
            and r.get("doc_saved") is False
            and r.get("committed_count") == 3
            and r.get("mcp_mode") == "plan_only_dry_run"
            and r.get("committed_to_disk") is False
        )
        gate(
            "validates",
            bool(ok_b),
            f"ok={r.get('ok')} dry_run={r.get('dry_run')} saved={r.get('doc_saved')} "
            f"committed={r.get('committed_count')} kinds={[c.get('kind') for c in r.get('committed', [])]} "
            f"err={r.get('error')}",
        )
    finally:
        try:
            runtime.shutdown()
        except Exception:
            pass

    # Disk-untouched witness (after the executor released the doc).
    mtime_after = path.stat().st_mtime_ns
    nodes_after = _reopen_node_count(sw, path)
    gate(
        "disk_untouched",
        mtime_after == mtime_before and nodes_after == nodes_before,
        f"mtime_unchanged={mtime_after == mtime_before} "
        f"nodes {nodes_before}->{nodes_after} (must be equal — dry-run persists nothing)",
    )

    _close_all(sw)
    pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
