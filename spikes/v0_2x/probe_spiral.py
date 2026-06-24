"""MEASURE-FIRST probe — spiral via IModelDoc2.InsertHelix (swHelixDefinedBy_e).

Spiral is the curve-sibling of the SHIPPED helix lane (W62): the SAME 10-arg
InsertHelix call, with the 5th arg (DefinedBy, swHelixDefinedBy_e) flipped from
0 (pitch+revolution helix) to 3 (swHelixDefinedBySpiral — a FLAT planar spiral).
Closed-form curve → boundary law predicts it materializes.

Witness: on a base circle sketch, InsertHelix(DefinedBy=3, pitch, revolutions)
materializes a 'Helix'-type node (spiral is a Helix feature in SW) carrying real
arc length, surviving the COM boundary. Primary probe DefinedBy=3; if it no-ops,
sweep {1,2,3} to locate the spiral mode empirically (don't trust the enum blind).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_spiral.py
"""
from __future__ import annotations

import json
import math
import os
import shutil
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
import win32com.client.dynamic as w32dyn  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

_WORK = _HERE.parent / "_results" / "probe_spiral_work"
_OUT = _HERE.parent / "_results" / "probe_spiral.json"
out: dict[str, Any] = {}


def _node_types(doc: Any) -> list[str]:
    names = []
    for f in (doc.FeatureManager.GetFeatures(False) or []):
        for attr in ("GetTypeName2", "GetTypeName"):
            try:
                v = getattr(f, attr)
                names.append(str(v() if callable(v) else v))
                break
            except Exception:
                continue
    return names


def _count_helix(doc: Any) -> int:
    return sum(1 for n in _node_types(doc) if n.lower() == "helix")


def _build_circle_seed(sw: Any, radius_m: float) -> tuple[Any, Any, str] | None:
    """New part, circle on Front Plane (start radius), named sketch. Returns
    (typed_doc, raw_latebound_doc, sketch_name) — both proxies wrap the same
    underlying document (shared selection set)."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return None
    doc = typed(raw, "IModelDoc2", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, radius_m, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    # name the last sketch
    last = None
    for f in doc.FeatureManager.GetFeatures(True) or []:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                last = tf
        except Exception:
            continue
    if last is None:
        return None
    try:
        last.Name = "SpiralBase"
    except Exception:
        pass
    doc.ForceRebuild3(False)
    return doc, raw, "SpiralBase"


def _try_spiral(sw: Any, defined_by: int, *, const_pitch: bool = True,
                reverse: bool = False, clockwise: bool = False,
                pitch_m: float = 0.010, revolutions: float = 3.0,
                height_m: float | None = None, start_angle: float = 0.0,
                diameter: float = 0.0, start_radius_m: float = 0.005) -> dict[str, Any]:
    """Fresh seed, fire InsertHelix on a GENUINELY late-bound doc
    (dynamic.Dispatch). Selection (VARIANT callout) + InsertHelix both go
    through the late-bound proxy — the typed Extension rejects the
    VARIANT(VT_DISPATCH,None) callout (ref_axis binding-inverse trap)."""
    import traceback
    if height_m is None:
        height_m = pitch_m * revolutions
    r: dict[str, Any] = {"defined_by": defined_by, "args": {
        "const_pitch": const_pitch, "reverse": reverse, "clockwise": clockwise,
        "pitch_m": pitch_m, "rev": revolutions, "height_m": height_m,
        "start_angle": start_angle, "diameter": diameter}}
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    seed = _build_circle_seed(sw, start_radius_m)
    if seed is None:
        r["error"] = "seed build failed"
        return r
    doc, raw, sketch = seed
    ldoc = w32dyn.Dispatch(raw)  # genuine late-bound (makepy NewDocument = typed)
    before = _count_helix(doc)
    try:
        ldoc.ClearSelection2(True)
        null_callout = VARIANT(pythoncom.VT_DISPATCH, None)
        sel = ldoc.Extension.SelectByID2(sketch, "SKETCH", 0, 0, 0, False, 0, null_callout, 0)
        r["select_ok"] = bool(sel)
        if not sel:
            r["error"] = "sketch select failed"
            return r
        ldoc.InsertHelix(
            const_pitch, reverse, False, clockwise, defined_by,
            pitch_m, revolutions, height_m, start_angle, diameter,
        )
        ldoc.ForceRebuild3(False)
    except Exception as e:  # noqa: BLE001
        r["insert_exc"] = repr(e)
        r["tb"] = traceback.format_exc()[-300:]
        return r
    after = _count_helix(doc)
    r["helix_before"], r["helix_after"] = before, after
    r["materialized"] = after > before
    return r


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        # db=3 = spiral (only one of 0..5 that no-ops). Focused arg sweep to
        # find the recipe that materializes it.
        variants = {
            "A_diameter_explicit": dict(diameter=0.010),
            "B_const_pitch_false": dict(const_pitch=False),
            "C_height_zero": dict(height_m=0.0),
            "D_reverse": dict(reverse=True),
            "E_small_pitch_more_rev": dict(pitch_m=0.002, revolutions=5.0),
            "F_diam_and_constpitch_false": dict(diameter=0.010, const_pitch=False),
            "G_startangle": dict(start_angle=math.radians(0.0), diameter=0.010, height_m=0.0),
        }
        out["spiral_db3_variants"] = {}
        for name, kw in variants.items():
            res = _try_spiral(sw, 3, **kw)
            out["spiral_db3_variants"][name] = {
                "materialized": res.get("materialized"),
                "helix_after": res.get("helix_after"),
                "insert_exc": res.get("insert_exc"),
                "args": res.get("args"),
            }
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
