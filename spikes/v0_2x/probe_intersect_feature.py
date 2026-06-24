"""MEASURE-FIRST probe — the Intersect feature (boundary-law verification).

Hypothesis (W69 boundary law): Intersect is a boolean body-op (computes the
mutual regions of overlapping bodies/surfaces), the same family as combine/split
which all wall ret=None out-of-process. PREDICT: a kernel-side refusal. This
probe forces the kernel to answer explicitly so we codify HOW it refuses (or, if
the law is violated, ship it).

DLL recon (docs/sw_api_full.md, IFeatureManager @ build 32.1.0.123):
  * The Intersect feature is a Pre->Post workflow (NOT a single Insert):
      PreIntersect(CapPlanar) -> Object
      PreIntersect2(CapPlanar, RegionType:swRegionType_e) -> Object   (regions)
      PostIntersect(IntersectionsToExclude, Merge, Consume) -> Feature
  * IIntersectFeatureData exists (edit-only, post-creation).
  * swRegionType_e: Margins=0, Sheet=1.

Witness chain (the kernel's refusal mode, captured explicitly):
  1. select both overlapping solid bodies (IBody2.Select — whole-body select).
  2. PreIntersect2(False, 0): does it RETURN a regions array OOP, or None?
  3. PostIntersect(None, False, False): Feature or None? new bodies? dVol?
Any None / silent no-op (feat returned but dVol==0 and dBody==0) = the wall.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_intersect_feature.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "probe_intersect_feature.json"
out: dict[str, Any] = {"probe": "intersect_feature"}

_SW_SOLID = 0


def _extrude(doc: Any, sketch: str, depth_m: float, *, merge: bool) -> None:
    fx._select_feature(doc, sketch)
    doc.FeatureManager.FeatureExtrusion2(
        True, False, False, 0, 0, depth_m, 0.0, False, False, False, False,
        0, 0, False, False, False, False, merge, True, True, 0, 0, False)
    doc.ClearSelection2(True)


def _build_overlapping(sw: Any) -> Any:
    """Two overlapping solid bodies (merge=False) sharing a 20^3 mm region."""
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


def _solid_count(doc: Any) -> int:
    try:
        b = doc.GetBodies2(_SW_SOLID, False)
        return len(b) if b else 0
    except Exception:
        return -1


def _total_volume_mm3(doc: Any, mod: Any) -> float | None:
    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty
        mp = mp() if callable(mp) else mp
        return float(mp.Volume) * 1e9
    except Exception:
        return None


def _region_count(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (list, tuple)):
        return len(obj)
    return "non_null_scalar"


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        doc = _build_overlapping(sw)
        out["solid_bodies"] = _solid_count(doc)
        out["vol_before_mm3"] = _total_volume_mm3(doc, mod)

        bodies = list(doc.GetBodies2(_SW_SOLID, False) or ())
        if len(bodies) < 2:
            out["error"] = "fixture did not produce 2 solid bodies"
            return _finish()

        # Whole-body select (IBody2.Select(Append, Mark) — the proven recipe).
        try:
            doc.ClearSelection2(True)
            tb0 = typed(bodies[0], "IBody2", module=mod)
            tb1 = typed(bodies[1], "IBody2", module=mod)
            s0 = tb0.Select(False, 0)
            s1 = tb1.Select(True, 0)
            out["body_select"] = {"b0": bool(s0), "b1": bool(s1)}
            try:
                out["selected_count"] = int(doc.GetSelectedObjectCount2(-1))
            except Exception as e:  # noqa: BLE001
                out["selected_count_exc"] = repr(e)
        except Exception as e:  # noqa: BLE001
            out["body_select_exc"] = repr(e)

        # Typed IFeatureManager for the Pre/Post Intersect workflow.
        fm = typed(doc.FeatureManager, "IFeatureManager", module=mod)

        # --- PreIntersect2 (the regions-compute witness) ---
        regions = None
        for label, call in (
            ("PreIntersect2(False,0)", lambda: fm.PreIntersect2(False, 0)),
            ("PreIntersect(False)", lambda: fm.PreIntersect(False)),
        ):
            try:
                # re-select before each attempt (PreIntersect may clear it)
                doc.ClearSelection2(True)
                tb0.Select(False, 0)
                tb1.Select(True, 0)
                r = call()
                out[f"pre::{label}"] = {"region_count": _region_count(r),
                                        "type": type(r).__name__}
                if r is not None and regions is None:
                    regions = r
            except Exception as e:  # noqa: BLE001
                out[f"pre::{label}"] = {"exc": repr(e)}

        # --- PostIntersect (the materialize witness) ---
        body_before = _solid_count(doc)
        if regions is not None:
            for label, excl in (
                ("excl=None", None),
                ("excl=VARIANT_empty", VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [])),
            ):
                try:
                    feat = fm.PostIntersect(excl, False, False)  # Merge=F, Consume=F
                    tn = None
                    if feat is not None:
                        try:
                            gt = feat.GetTypeName2
                            tn = gt() if callable(gt) else gt
                        except Exception:
                            tn = "<type?>"
                    out[f"post::{label}"] = {
                        "feat": feat is not None, "type_name": tn,
                        "solid_after": _solid_count(doc),
                        "d_bodies": _solid_count(doc) - body_before,
                    }
                    break  # one PostIntersect attempt is enough
                except Exception as e:  # noqa: BLE001
                    out[f"post::{label}"] = {"exc": repr(e)}
        else:
            out["post"] = "SKIPPED — PreIntersect returned None (regions wall)"

        doc.ForceRebuild3(False)
        out["solid_after_mm3_total"] = _total_volume_mm3(doc, mod)
        out["solid_after_count"] = _solid_count(doc)
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


def _finish() -> int:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
