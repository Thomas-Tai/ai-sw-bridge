"""client.mutate.batch() — seat PAE (single-doc transaction across N features).

Proves the batch transaction holds one ``_open_doc_typed`` context open across
three DISTINCT COM materializations, and that the fail-fast manifest is honest on
the LIVE seat. The directive's illustrative ``ref_plane→sketch→boss_extrude`` is
adapted: ``sketch``/``boss_extrude`` are spec-builder (from-scratch) ops, NOT
feature_add registry kinds — the registry operates on EXISTING geometry. So the
three distinct materializations on a pre-built block are reference-light,
seat-proven registry kinds:

  A green_txn  : block on disk → batch[ref_plane, bounding_box, com_point] →
                 ok=True, committed_count=3, doc_saved=True; INDEPENDENT reopen
                 shows the feature tree grew by ≥3 nodes.
  B fail_fast  : batch[bounding_box(ok), ref_plane@"NoSuchPlane"(fail),
                 com_point(skipped)] → ok=False, committed_count=1, fault.index=1
                 (stage=apply, offending proposal echoed), skipped=[com_point],
                 doc_saved=True (the green was persisted — best-effort).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_batch_pae.py
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
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "batch_pae.json"
_RESULTS = _HERE.parent / "_results"
results: dict[str, Any] = {"pae": "mutate_batch", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block_to_disk(sw: Any, path: Path) -> int:
    """Build a 40×30×10 block, save it to *path*, close it, return its node count."""
    _close_all(sw)
    doc = fx.build_block(sw)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    saved = doc.SaveAs3(str(path), 0, 0)
    nodes = verify.feature_node_count(doc)
    print(f"    built block -> {path.name} (SaveAs3={saved}, nodes={nodes})")
    _close_all(sw)
    return nodes


def _reopen_node_count(sw: Any, path: Path) -> int:
    """Independently reopen *path* and count feature-tree nodes, then close."""
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(str(path), 1, 1, "", errs, warns)  # swDocPART=1, Silent=1
    n = verify.feature_node_count(doc)
    _close_all(sw)
    return n


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    client = SolidWorksClient()
    _RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        gate(
            "facade_seam",
            hasattr(client.mutate, "batch"),
            f"present={hasattr(client.mutate, 'batch')}",
        )

        # A: green transaction across 3 distinct materializations.
        path_a = _RESULTS / "batch_pae_green.sldprt"
        nodes_before = _build_block_to_disk(sw, path_a)
        # Three DISTINCT typed-path-robust kinds (none touch FeatureByName):
        # ref_plane (SelectByID2+_latebound), scale (IBody2.Select), com_point
        # (typed_qi IFeatureManager).
        green_props = [
            {
                "feature": {"type": "ref_plane", "distance_mm": 25.0},
                "target": {"plane": "Front Plane"},
            },
            {"feature": {"type": "scale", "scale_factor": 1.5}, "target": {}},
            {"feature": {"type": "com_point"}, "target": {}},
        ]
        ra = client.mutate.batch(str(path_a), green_props)
        results["green_txn"] = ra
        nodes_after = _reopen_node_count(sw, path_a)
        ok_a = (
            ra.get("ok") is True
            and ra.get("committed_count") == 3
            and ra.get("doc_saved") is True
            and ra.get("fault") is None
            and ra.get("skipped") == []
            and (nodes_after - nodes_before) >= 3
        )
        gate(
            "green_txn",
            bool(ok_a),
            f"ok={ra.get('ok')} committed={ra.get('committed_count')} "
            f"saved={ra.get('doc_saved')} kinds={[c.get('kind') for c in ra.get('committed', [])]} "
            f"nodes {nodes_before}->{nodes_after} (Δ≥3) err={ra.get('error')}",
        )

        # B: live fail-fast — middle proposal fails, greens persist, tail skipped.
        path_b = _RESULTS / "batch_pae_failfast.sldprt"
        _build_block_to_disk(sw, path_b)
        ff_props = [
            {
                "feature": {"type": "ref_plane", "distance_mm": 25.0},
                "target": {"plane": "Front Plane"},
            },  # green
            {
                "feature": {"type": "ref_plane", "distance_mm": 10.0},
                "target": {"plane": "NoSuchPlane"},
            },  # <- handler returns False
            {"feature": {"type": "com_point"}, "target": {}},  # skipped
        ]
        rb = client.mutate.batch(str(path_b), ff_props)
        results["fail_fast"] = rb
        fault = rb.get("fault") or {}
        ok_b = (
            rb.get("ok") is False
            and rb.get("committed_count") == 1
            and rb.get("attempted") == 2
            and rb.get("halted_at") == 1
            and fault.get("index") == 1
            and fault.get("stage") == "apply"
            and fault.get("kind") == "ref_plane"
            and fault.get("target") == ff_props[1]["target"]
            and [s.get("kind") for s in rb.get("skipped", [])] == ["com_point"]
            and rb.get("doc_saved") is True
        )
        gate(
            "fail_fast",
            bool(ok_b),
            f"ok={rb.get('ok')} committed={rb.get('committed_count')} "
            f"halted_at={rb.get('halted_at')} fault.kind={fault.get('kind')} "
            f"fault.stage={fault.get('stage')} skipped={[s.get('kind') for s in rb.get('skipped', [])]} "
            f"saved={rb.get('doc_saved')} err={rb.get('error')}",
        )
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
