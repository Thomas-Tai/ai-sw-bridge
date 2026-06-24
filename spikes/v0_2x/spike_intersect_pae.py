"""intersect feature-add lane — seat PAE (the boundary-law refinement, proven).

Drives the production handler ``features.intersect.create_intersect`` against the
exact two-box overlapping fixture from probe_intersect_feature, with INDEPENDENT
(zero-trust) before/after measurement via the verify substrate — NOT trusting the
handler's own note:

  A facade_seam : create_intersect imports; SPIKE_STATUS is a known sentinel.
  B no_merge    : 2 overlapping solid bodies (24000 mm³ each, 20³=8000 overlap) ->
                  create_intersect({}, {}) materializes a Sculpt feature, solid
                  bodies 2 -> 3, total volume 48000 -> 40000 (ΔVol = -8000, the
                  de-double-counted overlap). ok=True.
  C merge_obs   : same fixture with merge=True — OBSERVED (logged, not hard-gated:
                  merge geometry was not part of the probe-proven contract).

The MassProperty null defect (probe used doc-level Extension.CreateMassProperty)
is resolved by reading PER-BODY via verify.solid_volume_mm3 (IBody2.GetMass
Properties[3]).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_intersect_pae.py
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
from ai_sw_bridge.features import verify  # noqa: E402
from ai_sw_bridge.features import intersect as ix  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "intersect_pae.json"
results: dict[str, Any] = {"pae": "intersect", "gates": {}}

_OVERLAP_MM3 = 8000.0  # 20×20×20 shared region


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
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
        True, False, False, 0, 0, depth_m, 0.0, False, False, False, False,
        0, 0, False, False, False, False, merge, True, True, 0, 0, False)
    doc.ClearSelection2(True)


def _build_overlapping(sw: Any) -> Any:
    """Two overlapping solid bodies (merge=False) sharing a 20³ mm region."""
    doc = sw.NewDocument(fx.PART_TEMPLATE, 0, 0, 0)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch1", 0.020, merge=True)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(0.000, -0.005, 0.0, 0.040, 0.025, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _extrude(doc, "Sketch2", 0.020, merge=False)
    doc.ForceRebuild3(False)
    return doc


def _measure(doc: Any) -> tuple[int, float]:
    """INDEPENDENT (zero-trust) solid-body count + per-body total volume mm³."""
    return verify.solid_body_count(doc), verify.solid_volume_mm3(doc)


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all(sw)
    try:
        gate("facade_seam",
             callable(ix.create_intersect)
             and ix.SPIKE_STATUS in {"GREEN", "UNFIRED", "UNRUN", "DEFERRED", "WALLED", "DORMANT"},
             f"SPIKE_STATUS={ix.SPIKE_STATUS}")

        # B: no-merge — the probe-proven 2→3 / ΔVol=-8000 contract.
        _close_all(sw)
        doc = _build_overlapping(sw)
        cb, vb = _measure(doc)
        ok, note = ix.create_intersect(doc, {}, {})
        ca, va = _measure(doc)
        d_vol = va - vb
        results["no_merge"] = {
            "ok": ok, "note": note,
            "count_before": cb, "count_after": ca,
            "vol_before": vb, "vol_after": va, "d_vol": d_vol,
        }
        gate("no_merge",
             bool(ok) and cb == 2 and ca == 3
             and abs(d_vol - (-_OVERLAP_MM3)) < 1.0,
             f"ok={ok} bodies {cb}→{ca} vol {vb:.1f}→{va:.1f} "
             f"ΔVol={d_vol:+.1f} (expect -8000) note={note!r}")

        # C: merge — OBSERVED only (not part of the proven contract).
        _close_all(sw)
        doc2 = _build_overlapping(sw)
        cb2, vb2 = _measure(doc2)
        ok2, note2 = ix.create_intersect(doc2, {"merge": True}, {})
        ca2, va2 = _measure(doc2)
        results["merge_obs"] = {
            "ok": ok2, "note": note2,
            "count_before": cb2, "count_after": ca2,
            "vol_before": vb2, "vol_after": va2, "d_vol": va2 - vb2,
        }
        print(f"  [OBS ] merge: ok={ok2} bodies {cb2}→{ca2} "
              f"vol {vb2:.1f}→{va2:.1f} note={note2!r}")
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
