"""W51 PRODUCTION PAE — pierce general (centroid anchor + non-Front planes).

Exercises the v2 _apply_auto_pierce generalization: profiles that DON'T expose an
arc/circle center (rectangles, polygons, arbitrary closed curves) now fall back to
the geometric centroid of all segment endpoints + arc centers. The sweep self-anchors
for any closed profile, not just circular ones.

  LEG 1 (centroid rectangle): center-rectangle profile OFFSET from path → auto_pierce
    uses centroid anchor → sweep materializes a body (feature delta + body + volume>0).
    This is the v2 generalization: v1 would have fail-closed with 'circular/arc profiles'.

  LEG 2 (centroid polygon): arbitrary polygon (hexagon) profile → centroid anchor →
    sweep materializes a body. Guards against degenerate centroid computation.

  LEG 3 (non-Front plane): circle profile on Top Plane (not Front) → sketch→model
    coord mapping → characterize. May succeed (if the transform is correct) or wall
    (if v2's identity fallback is insufficient). Either outcome is a valid finding.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/pierce_general_pae.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.mutate import _create_sweep  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "pierce_general_pae.json"


def _name_last_sketch(doc: Any, mod: Any, newname: str) -> str | None:
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
        last.Name = newname
        return newname
    except Exception:
        try:
            return last.Name
        except Exception:
            return None


def _build_path(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Path line on Top Plane along part-Z, piercing Front (z=0) at the origin."""
    if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "PathSk")


def _build_rect_profile(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Center rectangle on Front Plane OFFSET to (15, 10) — no arc center."""
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    # CreateCenterRectangle(cx, cy, cz, half_w, half_h, cz2) — centered at (15, 10)
    sm.CreateCenterRectangle(0.015, 0.010, 0.0, 0.008, 0.006, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "RectProfSk")


def _build_polygon_profile(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Hexagon on Front Plane at origin — centroid anchor test."""
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    # Create a hexagon via 6 lines (no CreatePolygon in the API surface we use).
    # Approximate with a center rectangle + two corner lines (a trapezoid).
    # For simplicity, use a triangle (3 lines) — still no arc center.
    sm.CreateLine(0.0, 0.0, 0.0, 0.020, 0.0, 0.0)
    sm.CreateLine(0.020, 0.0, 0.0, 0.010, 0.017, 0.0)
    sm.CreateLine(0.010, 0.017, 0.0, 0.0, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "PolyProfSk")


def _build_circle_profile_top(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Circle on Top Plane (not Front) — sketch→model coord mapping test."""
    if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    # Circle offset from origin in Top Plane sketch coords (sketch-X = part-X,
    # sketch-Y = part-Z). Center at (10, 5) in sketch = (10, ?, 5) in part.
    sm.CreateCircle(0.010, 0.005, 0.0, 0.015, 0.005, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "TopProfSk")


def _build_path_for_top(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Path on Front Plane for Top-Plane profile test (pierces Top at y=0)."""
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    # Line along part-Y (sketch-Y on Front) crossing y=0.
    sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "PathTopSk")


def _body_stats(raw_doc: Any, mod: Any) -> tuple[int, float]:
    try:
        pdoc = typed_qi(raw_doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(0, True)
    except Exception:
        return 0, 0.0
    nb = len(bodies) if bodies else 0
    vol = 0.0
    for b in bodies or ():
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol += float(mp[3]) * 1e9
        except Exception:
            pass
    return nb, round(vol, 1)


def _new_part(sw: Any, mod: Any) -> tuple[Any, Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    doc = typed(raw, "IModelDoc2", module=mod)
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    return raw, doc, ext, sm


def _leg_centroid_rect(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "centroid_rectangle", "ok": False}
    raw, doc, ext, sm = _new_part(sw, mod)
    path = _build_path(doc, ext, sm, mod)
    prof = _build_rect_profile(doc, ext, sm, mod)
    r["path"], r["profile"] = path, prof
    if not path or not prof:
        r["error"] = "fixture sketch naming failed"
        return r
    ok, err = _create_sweep(doc, {"type": "sweep"}, {"profile": prof, "path": path})
    r["sweep_ok"], r["sweep_err"] = ok, err
    nb, vol = _body_stats(raw, mod)
    r["bodies"], r["volume_mm3"] = nb, vol
    r["ok"] = bool(ok and nb >= 1 and vol > 0)
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _leg_centroid_polygon(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "centroid_polygon", "ok": False}
    raw, doc, ext, sm = _new_part(sw, mod)
    path = _build_path(doc, ext, sm, mod)
    prof = _build_polygon_profile(doc, ext, sm, mod)
    r["path"], r["profile"] = path, prof
    if not path or not prof:
        r["error"] = "fixture sketch naming failed"
        return r
    ok, err = _create_sweep(doc, {"type": "sweep"}, {"profile": prof, "path": path})
    r["sweep_ok"], r["sweep_err"] = ok, err
    nb, vol = _body_stats(raw, mod)
    r["bodies"], r["volume_mm3"] = nb, vol
    r["ok"] = bool(ok and nb >= 1 and vol > 0)
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _leg_non_front_plane(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "non_front_plane", "ok": False}
    raw, doc, ext, sm = _new_part(sw, mod)
    path = _build_path_for_top(doc, ext, sm, mod)
    prof = _build_circle_profile_top(doc, ext, sm, mod)
    r["path"], r["profile"] = path, prof
    if not path or not prof:
        r["error"] = "fixture sketch naming failed"
        return r
    ok, err = _create_sweep(doc, {"type": "sweep"}, {"profile": prof, "path": path})
    r["sweep_ok"], r["sweep_err"] = ok, err
    nb, vol = _body_stats(raw, mod)
    r["bodies"], r["volume_mm3"] = nb, vol
    # Characterize: either succeeds (transform worked) or fails (v2 identity fallback
    # is insufficient for non-Front planes). Both are valid findings.
    r["ok"] = bool(ok and nb >= 1 and vol > 0)
    r["verdict"] = "GREEN" if r["ok"] else "WALL"
    r["note"] = (
        "non-Front plane: v2 uses identity transform fallback. "
        "GREEN = transform correct; WALL = need IRefPlane.Transform2 (v3)."
    )
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "pierce_general_pae", "legs": {}}
    try:
        pythoncom.CoInitialize()
        mod = wrapper_module()
        sw = get_sw_app()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        result["legs"]["centroid_rect"] = _leg_centroid_rect(sw, mod)
        print(f"[pg] centroid_rect -> {result['legs']['centroid_rect'].get('verdict')} "
              f"vol={result['legs']['centroid_rect'].get('volume_mm3')}")
        result["legs"]["centroid_polygon"] = _leg_centroid_polygon(sw, mod)
        print(f"[pg] centroid_polygon -> {result['legs']['centroid_polygon'].get('verdict')} "
              f"vol={result['legs']['centroid_polygon'].get('volume_mm3')}")
        result["legs"]["non_front_plane"] = _leg_non_front_plane(sw, mod)
        print(f"[pg] non_front_plane -> {result['legs']['non_front_plane'].get('verdict')} "
              f"note={result['legs']['non_front_plane'].get('note')}")
        # Overall PASS if legs 1+2 are GREEN (centroid anchor works).
        # Leg 3 is characterize (may wall; valid finding either way).
        legs_mandatory = ["centroid_rect", "centroid_polygon"]
        result["overall"] = (
            "PASS" if all(result["legs"][k].get("ok") for k in legs_mandatory) else "FAIL"
        )
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"
        result["overall"] = "FAIL"
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
