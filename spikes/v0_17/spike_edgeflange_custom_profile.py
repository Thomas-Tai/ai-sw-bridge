"""Spike v0.17 — Wave-7: Edge-flange with custom profile sketch.

TYPELIB-FIRST signature (sldworks.tlb, IFeatureManager.InsertSheetMetalEdgeFlange2):
  #  Name                 VT Type   Enum
  1  FlangeEdges          VARIANT   (edge entity/entities)
  2  SketchFeats          VARIANT   (sketch feature/entity)
  3  BooleanOptions       I4        swInsertEdgeFlangeOptions_e
  4  FlangeAngle          R8        (radians)
  5  FlangeRadius         R8        (meters)
  6  BendPosition         I4        swFlangePositionTypes_e
  7  FlangeOffsetDist     R8        (meters)
  8  ReliefType           I4        swSheetMetalReliefTypes_e
  9  FlangeReliefRatio    R8        (0-1)
  10 FlangeReliefWidth    R8        (meters)
  11 FlangeReliefDepth    R8        (meters)
  12 FlangeSharpType      I4        (no enum found; 0 = default)
  13 CustomBendAllowance  USERDEFINED(IDispatch) VARIANT(VT_DISPATCH,None)

swconst.tlb verified:
  swInsertEdgeFlangeUseDefaultRadius  = 1
  swInsertEdgeFlangeUseDefaultRelief  = 128
  swFlangePositionTypeMaterialInside  = 1
  swSheetMetalReliefTear              = 2

Strategy:
  1. Build base flange (proven CD(34) pipeline, Wave-4).
  2. Capture longest linear boundary edge (persist round-trip).
  3. Build normal-to-edge ref plane + profile sketch on it (Wave-6 recipe).
  4. Call InsertSheetMetalEdgeFlange2 with the REAL sketch as SketchFeats.
  5. Delta-verify: len(GetFeatures(True)) +1, GetTypeName2 = flange type.

Usage:
    python spikes/v0_17/spike_edgeflange_custom_profile.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parents[1] / "v0_16"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.selection._edge_ref import DurableEdgeRef
from ai_sw_bridge.selection.live import resolve_edge_ref, select_entity

from spike_earlybind_persist import connect_running_sw, ensure_sw_module
from spike_sheetmetal_v2 import (
    SW_FM_BASEFLANGE,
    SW_DEFAULT_TEMPLATE_PART,
    _build_profile,
    _build_base_flange,
    _capture,
    _find_bendable_edges,
    _materialized,
    _title,
    _try_close,
    _type_name,
)

RESULTS_DIR = Path(__file__).resolve().parent / "_results"

# Typelib-verified enum values (swconst.tlb)
OPT_USE_DEFAULT_RADIUS = 1
OPT_USE_DEFAULT_RELIEF = 128
BOOLEAN_OPTIONS = OPT_USE_DEFAULT_RADIUS | OPT_USE_DEFAULT_RELIEF  # 129

POS_MATERIAL_INSIDE = 1      # swFlangePositionTypeMaterialInside
RELIEF_TEAR = 2              # swSheetMetalReliefTear
RELIEF_NONE = 4              # swSheetMetalReliefNone

FLANGE_ANGLE = math.pi / 2.0  # 90 degrees
FLANGE_RADIUS = 0.002          # 2mm
OFFSET_DIST = 0.0              # no offset
RELIEF_RATIO = 0.5
RELIEF_WIDTH = 0.0
RELIEF_DEPTH = 0.0
SHARP_TYPE = 0                 # default (no enum found)

FLANGE_HEIGHT = 0.010          # 10mm profile sketch height


def _feature_count(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(True)
    return len(feats) if feats else 0


def _feature_types(doc: Any, mod: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _rank_linear_edges(edges: list, mod: Any) -> list[dict]:
    ranked: list[dict] = []
    for ei, e in enumerate(edges):
        info: dict[str, Any] = {"index": ei, "edge": e, "is_line": False, "length": 0.0}
        try:
            ie = typed_qi(e, "IEdge", module=mod)
            cv = typed_qi(ie.GetCurve(), "ICurve", module=mod)
            info["is_line"] = bool(cv.IsLine())
            ep = cv.GetEndParams()
            info["length"] = float(cv.GetLength(ep[1], ep[2]))
        except Exception:
            pass
        ranked.append(info)
    linear = sorted(
        (r for r in ranked if r["is_line"]),
        key=lambda r: r["length"], reverse=True,
    )
    return linear or sorted(ranked, key=lambda r: r["length"], reverse=True)


def _capture_edge_ref(doc: Any, edge: Any, mod: Any) -> dict:
    from ai_sw_bridge.com.earlybind import read_persist_reference
    pid = read_persist_reference(doc, edge)
    if pid is None:
        raise RuntimeError("no persist_id for edge")
    ie = typed(edge, "IEdge", module=mod)
    ic = typed(ie.GetCurve(), "ICurve", module=mod)
    p = ic.GetEndParams()
    ev_s = ic.Evaluate(p[1])
    ev_e = ic.Evaluate(p[2])
    ev_m = ic.Evaluate((p[1] + p[2]) / 2.0)
    ref = DurableEdgeRef(
        persist_id=pid,
        start=(ev_s[0], ev_s[1], ev_s[2]),
        end=(ev_e[0], ev_e[1], ev_e[2]),
        length=float(ic.GetLength(p[1], p[2])),
        midpoint=(ev_m[0], ev_m[1], ev_m[2]),
    )
    return ref.to_dict()


def _build_normal_plane_and_sketch(
    doc: Any, edge: Any, mod: Any,
) -> dict[str, Any]:
    """Build a normal-to-edge ref plane + profile sketch (Wave-6 proven recipe).

    Returns dict with plane_name, sketch_name, and diagnostics.
    """
    out: dict[str, Any] = {}

    from ai_sw_bridge.com.earlybind import read_persist_reference
    ext = typed_extension(doc, module=mod)

    # Capture persist_id BEFORE any rebuild (edge is live now)
    edge_pid_bytes = read_persist_reference(doc, edge)
    if edge_pid_bytes is None:
        out["error"] = "no persist_id for edge"
        return out

    # Persist round-trip edge
    edge_obj = ext.GetObjectByPersistReference3(edge_pid_bytes)
    live_edge = edge_obj[0] if isinstance(edge_obj, tuple) else edge_obj

    # Get start vertex
    iedge = typed(live_edge, "IEdge", module=mod)
    vertex = iedge.GetStartVertex()
    if vertex is None:
        out["error"] = "no start vertex"
        return out

    # Rebuild before selections (proven: rebuild invalidates stale proxies)
    doc.ForceRebuild3(False)

    # Re-resolve edge using saved persist_id bytes AND re-derive vertex
    edge_obj2 = ext.GetObjectByPersistReference3(edge_pid_bytes)
    live_edge2 = edge_obj2[0] if isinstance(edge_obj2, tuple) else edge_obj2
    if live_edge2 is None or isinstance(live_edge2, int):
        out["error"] = "edge re-resolve failed after rebuild"
        return out
    iedge2 = typed(live_edge2, "IEdge", module=mod)
    vertex = iedge2.GetStartVertex()
    if vertex is None:
        out["error"] = "vertex not found after rebuild"
        return out

    # Select vertex (Coincident, mark=0) then edge (Perpendicular, mark=1)
    doc.ClearSelection2(True)
    if not select_entity(vertex, mark=0):
        out["error"] = "vertex select failed"
        return out
    if not select_entity(live_edge2, append=True, mark=1):
        out["error"] = "edge select failed"
        return out

    # InsertRefPlane: Coincident=4, Perpendicular=2
    n_before = _feature_count(doc)
    fm = doc.FeatureManager
    fm.InsertRefPlane(4, 0, 2, 0, 0, 0)
    doc.ForceRebuild3(False)
    n_after = _feature_count(doc)
    out["plane_delta"] = n_after - n_before

    if n_after <= n_before:
        out["error"] = "plane did not materialize"
        return out

    # Find the new plane name
    feats = _feature_types(doc, mod)
    plane_name = None
    for f in feats:
        if f["type"] == "RefPlane" and f["name"].startswith("Plane"):
            plane_name = f["name"]
    out["plane_name"] = plane_name

    if not plane_name:
        out["error"] = "plane name not found"
        return out

    # Open sketch on the plane and draw profile (vertical line = flange height)
    doc.ClearSelection2(True)
    sel = doc.SelectByID(plane_name, "DATUMPLANE", 0, 0, 0)
    out["select_plane"] = bool(sel)

    n_before_sk = _feature_count(doc)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    # Draw a vertical line from origin upward = flange wall height
    sk.CreateLine(0, 0, 0, 0, FLANGE_HEIGHT, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    n_after_sk = _feature_count(doc)
    out["sketch_delta"] = n_after_sk - n_before_sk

    # Find the new sketch name
    feats2 = _feature_types(doc, mod)
    sketch_name = None
    for f in feats2:
        if f["type"] == "ProfileFeature" and f["name"].startswith("Sketch"):
            # Last sketch is the profile
            sketch_name = f["name"]
    # Also check for 3DSketch or Sketch (not ProfileFeature)
    if not sketch_name:
        for f in feats2:
            if "Sketch" in f["name"] and f["name"] != "Sketch1":
                sketch_name = f["name"]
    out["sketch_name"] = sketch_name

    return out


def _call_edge_flange(
    doc: Any, fm: Any, edge: Any, sketch_feature: Any, mod: Any,
    mark: int,
) -> dict[str, Any]:
    """InsertSheetMetalEdgeFlange2 with typelib-verified args + real sketch.

    Key finding: both FlangeEdges and SketchFeats MUST be passed as
    VARIANT(VT_ARRAY | VT_DISPATCH, (obj,)) SAFEARRAYs — single dispatch
    objects or bare tuples are silently ignored by the COM server.
    """
    vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
    edge_arr = w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (edge,))
    sketch_arr = w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (sketch_feature,))

    doc.ClearSelection2(True)
    try:
        ient = typed(edge, "IEntity")
        sel_ok = bool(ient.Select2(False, mark))
    except Exception:
        sel_ok = False

    n_before = _feature_count(doc)
    try:
        ret = fm.InsertSheetMetalEdgeFlange2(
            edge_arr,       # 1  FlangeEdges (VARIANT SAFEARRAY)
            sketch_arr,     # 2  SketchFeats (VARIANT SAFEARRAY)
            BOOLEAN_OPTIONS,# 3  BooleanOptions = 129
            FLANGE_ANGLE,   # 4  FlangeAngle = pi/2
            FLANGE_RADIUS,  # 5  FlangeRadius = 2mm
            POS_MATERIAL_INSIDE,  # 6  BendPosition = 1
            OFFSET_DIST,    # 7  FlangeOffsetDist = 0
            RELIEF_TEAR,    # 8  ReliefType = 2
            RELIEF_RATIO,   # 9  FlangeReliefRatio = 0.5
            RELIEF_WIDTH,   # 10 FlangeReliefWidth = 0
            RELIEF_DEPTH,   # 11 FlangeReliefDepth = 0
            SHARP_TYPE,     # 12 FlangeSharpType = 0
            vt_disp,        # 13 CustomBendAllowance = VARIANT(None)
        )
        err = None
    except Exception as e:
        ret = None
        err = f"{type(e).__name__}: {str(e)[:300]}"

    n_after = _feature_count(doc)
    delta = n_after - n_before

    return {
        "select": sel_ok,
        "mark": mark,
        "delta": delta,
        "materialized": delta > 0,
        "return_type": type(ret).__name__ if ret is not None else "None",
        "error": err,
    }


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "edgeflange_custom_profile_W7",
        "ts": time.time(),
    }
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    result["typelib_signature"] = {
        "method": "InsertSheetMetalEdgeFlange2",
        "arg_count": 13,
        "args": [
            {"pos": 1, "name": "FlangeEdges", "vt": "VARIANT(12)"},
            {"pos": 2, "name": "SketchFeats", "vt": "VARIANT(12)"},
            {"pos": 3, "name": "BooleanOptions", "vt": "I4(3)"},
            {"pos": 4, "name": "FlangeAngle", "vt": "R8(5)"},
            {"pos": 5, "name": "FlangeRadius", "vt": "R8(5)"},
            {"pos": 6, "name": "BendPosition", "vt": "I4(3)"},
            {"pos": 7, "name": "FlangeOffsetDist", "vt": "R8(5)"},
            {"pos": 8, "name": "ReliefType", "vt": "I4(3)"},
            {"pos": 9, "name": "FlangeReliefRatio", "vt": "R8(5)"},
            {"pos": 10, "name": "FlangeReliefWidth", "vt": "R8(5)"},
            {"pos": 11, "name": "FlangeReliefDepth", "vt": "R8(5)"},
            {"pos": 12, "name": "FlangeSharpType", "vt": "I4(3)"},
            {"pos": 13, "name": "CustomBendAllowance", "vt": "USERDEFINED(IDispatch)"},
        ],
    }
    result["named_arg_vector"] = {
        "BooleanOptions": {"value": BOOLEAN_OPTIONS, "name": "UseDefaultRadius|UseDefaultRelief"},
        "FlangeAngle": {"value": FLANGE_ANGLE, "name": "pi/2 (90 deg)"},
        "FlangeRadius": {"value": FLANGE_RADIUS, "name": "2mm"},
        "BendPosition": {"value": POS_MATERIAL_INSIDE, "name": "MaterialInside"},
        "ReliefType": {"value": RELIEF_TEAR, "name": "Tear"},
        "FlangeSharpType": {"value": SHARP_TYPE, "name": "default (no enum)"},
        "CustomBendAllowance": {"value": "VARIANT(VT_DISPATCH,None)", "name": "null"},
    }

    sw = connect_running_sw()
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument None"}

    try:
        fm = doc.FeatureManager

        # Step 1: Sheet-metal base flange
        print("[w7] building profile + base flange...")
        prof = _build_profile(doc)
        result["profile"] = prof
        if not prof.get("built"):
            return {**result, "overall": "FAIL", "reason": "profile sketch failed"}

        base = _build_base_flange(doc, fm, mod)
        result["base_flange"] = {k: v for k, v in base.items() if not k.startswith("_")}
        if base.get("overall") != "PASS":
            return {**result, "overall": "FAIL", "reason": "base flange failed"}

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        # Step 2: Capture longest linear edge
        print("[w7] finding edges...")
        edges = _find_bendable_edges(doc, mod)
        result["edge_count"] = len(edges)
        if not edges:
            return {**result, "overall": "FAIL", "reason": "no edges"}

        ranked = _rank_linear_edges(edges, mod)
        best_edge = ranked[0]["edge"]
        best_len = ranked[0]["length"]
        result["best_edge_mm"] = round(best_len * 1000, 2)

        # Step 2b: Capture edge persist_id for re-resolution after sketch build
        from ai_sw_bridge.com.earlybind import read_persist_reference
        edge_pid_bytes = read_persist_reference(doc, best_edge)

        # Step 3: Normal-to-edge plane + profile sketch
        print("[w7] building normal-to-edge plane + profile sketch...")
        plane_sk = _build_normal_plane_and_sketch(doc, best_edge, mod)
        result["plane_and_sketch"] = plane_sk

        if plane_sk.get("error"):
            return {**result, "overall": "FAIL", "reason": plane_sk["error"]}

        sketch_name = plane_sk.get("sketch_name")
        if not sketch_name:
            return {**result, "overall": "FAIL", "reason": "profile sketch name not found"}

        print("[w7] plane=%s sketch=%s" % (plane_sk.get("plane_name"), sketch_name))

        # Get the sketch feature as a dispatch for InsertSheetMetalEdgeFlange2
        doc.ClearSelection2(True)
        sel_sketch = doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
        # Get the selected sketch feature object
        sel_mgr = doc.SelectionManager
        sketch_feat = None
        try:
            sketch_feat = sel_mgr.GetSelectedObject6(1, -1)
        except Exception:
            pass

        # If GetSelectedObject6 fails, get it from the feature tree
        if sketch_feat is None:
            feat = doc.FeatureByName(sketch_name) if hasattr(doc, "FeatureByName") else None
            if feat is not None:
                sketch_feat = feat

        # Try FeatureManager approach
        if sketch_feat is None:
            feats = doc.FeatureManager.GetFeatures(True)
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    if ifeat.Name == sketch_name:
                        sketch_feat = f
                        break
                except Exception:
                    continue

        if sketch_feat is None:
            return {**result, "overall": "FAIL", "reason": "could not get sketch feature dispatch"}

        result["sketch_feature_type"] = type(sketch_feat).__name__

        # Step 3b: Re-resolve edge (stale after plane+sketch construction)
        if edge_pid_bytes is not None:
            ext = typed_extension(doc, module=mod)
            edge_obj = ext.GetObjectByPersistReference3(edge_pid_bytes)
            fresh_edge = edge_obj[0] if isinstance(edge_obj, tuple) else edge_obj
            if fresh_edge is not None and not isinstance(fresh_edge, int):
                print("[w7] edge re-resolved via persist_id")
            else:
                fresh_edge = best_edge
                print("[w7] edge re-resolve failed, using original")
        else:
            fresh_edge = best_edge

        # Step 4: Call InsertSheetMetalEdgeFlange2 with the REAL sketch
        print("[w7] calling InsertSheetMetalEdgeFlange2 with sketch...")
        attempts: list[dict[str, Any]] = []
        overall = "WALL"

        for mark in [0, 1]:
            a = _call_edge_flange(doc, fm, fresh_edge, sketch_feat, mod, mark)
            attempts.append(a)
            print("  mark=%d delta=%d mat=%s err=%s" % (
                mark, a["delta"], a["materialized"], a.get("error")))
            if a["materialized"]:
                overall = "GREEN"
                break

        # If both marks fail, try with ReliefType variations
        if overall != "GREEN":
            for relief in [RELIEF_NONE, RELIEF_TEAR]:
                for mark in [0, 1]:
                    vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
                    doc.ClearSelection2(True)
                    try:
                        ient = typed(fresh_edge, "IEntity")
                        ient.Select2(False, mark)
                    except Exception:
                        pass
                    n_before = _feature_count(doc)
                    try:
                        ret = fm.InsertSheetMetalEdgeFlange2(
                            fresh_edge, sketch_feat, BOOLEAN_OPTIONS,
                            FLANGE_ANGLE, FLANGE_RADIUS,
                            POS_MATERIAL_INSIDE, OFFSET_DIST,
                            relief, RELIEF_RATIO, RELIEF_WIDTH, RELIEF_DEPTH,
                            SHARP_TYPE, vt_disp,
                        )
                        err = None
                    except Exception as e:
                        ret = None
                        err = f"{type(e).__name__}: {str(e)[:200]}"
                    n_after = _feature_count(doc)
                    delta = n_after - n_before
                    a2 = {
                        "variant": f"relief={relief}",
                        "mark": mark,
                        "delta": delta,
                        "materialized": delta > 0,
                        "error": err,
                    }
                    attempts.append(a2)
                    if delta > 0:
                        overall = "GREEN"
                        break
                if overall == "GREEN":
                    break

        # Try with BendPosition variations
        if overall != "GREEN":
            for pos in [2, 3, 4]:  # MaterialOutside, BendOutside, BendCenterLine
                vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
                doc.ClearSelection2(True)
                try:
                    ient = typed(fresh_edge, "IEntity")
                    ient.Select2(False, 0)
                except Exception:
                    pass
                n_before = _feature_count(doc)
                try:
                    ret = fm.InsertSheetMetalEdgeFlange2(
                        fresh_edge, sketch_feat, BOOLEAN_OPTIONS,
                        FLANGE_ANGLE, FLANGE_RADIUS,
                        pos, OFFSET_DIST,
                        RELIEF_TEAR, RELIEF_RATIO, RELIEF_WIDTH, RELIEF_DEPTH,
                        SHARP_TYPE, vt_disp,
                    )
                    err = None
                except Exception as e:
                    ret = None
                    err = f"{type(e).__name__}: {str(e)[:200]}"
                n_after = _feature_count(doc)
                delta = n_after - n_before
                a3 = {
                    "variant": f"pos={pos}",
                    "mark": 0,
                    "delta": delta,
                    "materialized": delta > 0,
                    "error": err,
                }
                attempts.append(a3)
                if delta > 0:
                    overall = "GREEN"
                    break

        result["attempts"] = attempts
        result["attempt_count"] = len(attempts)
        result["overall"] = overall

        if overall == "GREEN":
            winner = next(a for a in attempts if a.get("materialized"))
            result["winner"] = winner
            feats = _feature_types(doc, mod)
            result["features_after"] = feats
            # Find the flange feature
            for f in feats:
                if "Flange" in f.get("type", "") or "flange" in f.get("name", "").lower():
                    if f["type"] != "SMBaseFlange":
                        result["flange_feature"] = f
                        break
            result["interpretation"] = (
                "Edge flange materialized with custom profile sketch. "
                "Ship as 14th kind."
            )
        else:
            result["features_after"] = _feature_types(doc, mod)
            err_hist: dict[str, int] = {}
            for a in attempts:
                key = (a.get("error") or a.get("return_type") or "?")[:80]
                err_hist[key] = err_hist.get(key, 0) + 1
            result["error_histogram"] = err_hist
            result["interpretation"] = (
                "WALL: %d attempts with real profile sketch — all delta=0. "
                "Custom-profile edge flange does not materialize out-of-process."
                % len(attempts)
            )

    finally:
        _try_close(sw, doc)

    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "edgeflange_custom_profile_W7.json"
    out.write_text(payload, encoding="utf-8")
    print("wrote %s" % out)
    print("overall: %s (%d attempts)" % (result.get("overall"), result.get("attempt_count", 0)))
    return {"GREEN": 0, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
