"""body_interference observe lane — seat PAE.

Drives the production facade ``client.observe.body_interference()`` against the
exact two fixtures from probe_body_interference:

  A facade_seam   : SolidWorksClient().observe exposes body_interference.
  B overlapping   : 2 solid bodies sharing a 20^3 mm region -> 1 interfering
                    pair, total_interference_volume_mm3 ~= 8000.0, clean=False,
                    mutation_guard_ok=True (read-only proof on the live seat).
  C disjoint      : 2 separated bodies -> clean=True, 0 interfering pairs,
                    mutation_guard_ok=True.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_body_interference_pae.py
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

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "body_interference_pae.json"
results: dict[str, Any] = {"pae": "body_interference", "gates": {}}


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


def _extrude(doc: Any, sketch: str, depth_m: float, *, merge: bool) -> None:
    fx._select_feature(doc, sketch)
    doc.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        0,
        0,
        depth_m,
        0.0,
        False,
        False,
        False,
        False,
        0,
        0,
        False,
        False,
        False,
        False,
        merge,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)


def _build_multibody(sw: Any, *, overlap: bool) -> Any:
    doc = sw.NewDocument(fx.PART_TEMPLATE, 0, 0, 0)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch1", 0.020, merge=True)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    if overlap:
        doc.SketchManager.CreateCornerRectangle(0.000, -0.005, 0.0, 0.040, 0.025, 0.0)
    else:
        doc.SketchManager.CreateCornerRectangle(0.100, -0.015, 0.0, 0.140, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch2", 0.020, merge=False)
    doc.ForceRebuild3(False)
    return doc


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all(sw)
    client = SolidWorksClient()
    try:
        gate(
            "facade_seam",
            hasattr(client.observe, "body_interference"),
            f"present={hasattr(client.observe, 'body_interference')}",
        )

        # B: overlapping
        _close_all(sw)
        _build_multibody(sw, overlap=True)
        rb = client.observe.body_interference()
        results["overlapping"] = rb
        vol = rb.get("total_interference_volume_mm3")
        ok_b = (
            rb.get("ok")
            and rb.get("interfering_pair_count") == 1
            and rb.get("clean") is False
            and rb.get("mutation_guard_ok") is True
            and vol is not None
            and abs(vol - 8000.0) < 1.0
        )
        gate(
            "overlapping",
            bool(ok_b),
            f"ok={rb.get('ok')} pairs={rb.get('interfering_pair_count')} "
            f"clean={rb.get('clean')} vol_mm3={vol} "
            f"edges={(rb.get('pairs') or [{}])[0].get('intersection_edge_count')} "
            f"mutation_guard_ok={rb.get('mutation_guard_ok')} err={rb.get('error')}",
        )

        # C: disjoint
        _close_all(sw)
        _build_multibody(sw, overlap=False)
        rc = client.observe.body_interference()
        results["disjoint"] = rc
        ok_c = (
            rc.get("ok")
            and rc.get("clean") is True
            and rc.get("interfering_pair_count") == 0
            and rc.get("mutation_guard_ok") is True
        )
        gate(
            "disjoint",
            bool(ok_c),
            f"ok={rc.get('ok')} pairs={rc.get('interfering_pair_count')} "
            f"clean={rc.get('clean')} mutation_guard_ok={rc.get('mutation_guard_ok')} "
            f"err={rc.get('error')}",
        )
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
