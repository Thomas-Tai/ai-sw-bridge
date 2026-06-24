"""Diagnostic — characterize the InsertSheetMetalHem mode-B wall.

Tries multiple approaches to get past the silent None return:
1. Dynamic dispatch (bypass makepy entirely)
2. Valid CustomBendAllowance object (not null)
3. Edge enumeration — try all non-bend edges
4. IModelDoc2 8-arg legacy version
5. pythoncom.Missing for PCBA

Prereq: SOLIDWORKS running. Sheet Metal add-in enabled.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module
from spike_earlybind_persist import connect_running_sw, ensure_sw_module

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_BASEFLANGE = 34
IFACE_BASEFLANGE = "IBaseFlangeFeatureData"
SW_BODY_SOLID = 0

PROF_W_M = 0.060
PROF_H_M = 0.040
THICKNESS_M = 0.002
BEND_RADIUS_M = 0.002

SW_HEM_TYPE_CLOSED = 1
SW_HEM_POSITION_OUTSIDE = 1
HEM_LENGTH_M = 0.010
HEM_MITER_GAP_M = 0.001

MEMID_HEM_V1 = 91
HEM_V1_ARGTYPES_VT13 = (
    (3, 1),
    (3, 1),
    (11, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (5, 1),
    (13, 1),
)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:300],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (tuple, list)) else [v]


def _count_faces(doc: Any) -> int:
    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    total = 0
    for b in _as_list(bodies):
        try:
            faces = b.GetFaces()
            total += len(_as_list(faces))
        except Exception:
            pass
    return total


def _build_base_flange(doc: Any, fm: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0, PROF_W_M / 2, PROF_H_M / 2, 0.0
        )
        sk.InsertSketch(True)
    except Exception as e:
        out["sketch_error"] = str(e)

    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
    out["create_definition"] = def_rec
    if data is None:
        return out
    qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
    out["typed_qi"] = qi_rec
    if wrapped is None:
        return out
    for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
        try:
            setattr(wrapped, name, val)
        except Exception:
            pass
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
    feat_rec["materialized"] = _materialized(feat)
    out["create_feature"] = feat_rec
    out["overall"] = "PASS" if _materialized(feat) else "FAIL"
    return out


def _find_edges_with_info(doc: Any, mod: Any) -> list[dict]:
    """Find all edges with their names and types for diagnostic."""
    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    body_list = _as_list(bodies)
    if not body_list:
        return []
    body = body_list[0]
    rec, edges_raw = _capture(lambda: body.GetEdges())
    edge_list = _as_list(edges_raw)
    result = []
    for i, e in enumerate(edge_list):
        info = {"index": i}
        try:
            info["name"] = getattr(e, "Name", None) or f"edge_{i}"
        except Exception:
            info["name"] = f"edge_{i}"
        try:
            info["id"] = e.GetId() if hasattr(e, "GetId") else None
        except Exception:
            pass
        result.append(info)
    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()

    sw = connect_running_sw()

    # --- Approach 1: Dynamic dispatch ---
    result["approach_1_dynamic"] = _try_dynamic_dispatch(sw, mod)

    # Restart for clean state
    _close_all(sw)

    # --- Approach 2: Valid PCBA + edge enumeration ---
    result["approach_2_pcba_edges"] = _try_pcba_and_edges(sw, mod)

    _close_all(sw)
    return result


def _try_dynamic_dispatch(sw: Any, mod: Any) -> dict[str, Any]:
    """Use pure dynamic dispatch — no makepy wrapping at all."""
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"error": "NewDocument None"}

    try:
        try:
            doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
            sk = doc.SketchManager
            sk.InsertSketch(True)
            sk.CreateCornerRectangle(
                -PROF_W_M / 2, -PROF_H_M / 2, 0.0, PROF_W_M / 2, PROF_H_M / 2, 0.0
            )
            sk.InsertSketch(True)
        except Exception as e:
            return {"error": f"sketch: {e}"}

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
        if data is None:
            return {"error": "CD(34) None"}
        qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
        if wrapped is None:
            return {"error": "QI None"}
        for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
            try:
                setattr(wrapped, name, val)
            except Exception:
                pass
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        if not _materialized(feat):
            return {"error": "base flange None"}

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        # Get edges
        rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
        body_list = _as_list(bodies)
        if not body_list:
            return {"error": "no bodies"}
        body = body_list[0]
        rec, edges_raw = _capture(lambda: body.GetEdges())
        edge_list = _as_list(edges_raw)
        if not edge_list:
            return {"error": "no edges"}

        # Try dynamic dispatch call on first edge
        edge = edge_list[0]
        try:
            ext = typed_extension(doc, module=mod)
            pid = ext.GetPersistReference3(edge)
            if pid:
                obj_result = ext.GetObjectByPersistReference3(pid)
                edge = obj_result[0] if isinstance(obj_result, tuple) else obj_result
        except Exception:
            pass

        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        try:
            edge.Select2(False, 0)
        except Exception:
            pass

        # Dynamic dispatch InsertSheetMetalHem
        args = (
            SW_HEM_TYPE_CLOSED,
            SW_HEM_POSITION_OUTSIDE,
            False,
            HEM_LENGTH_M,
            0.0,
            0.0,
            0.0,
            HEM_MITER_GAP_M,
            None,
        )
        rec_dyn, feat_dyn = _capture(lambda: fm.InsertSheetMetalHem(*args))
        out["dynamic_dispatch"] = rec_dyn
        out["dynamic_dispatch_materialized"] = _materialized(feat_dyn)

        if not _materialized(feat_dyn):
            # Try with pythoncom.Missing instead of None
            args_missing = (
                SW_HEM_TYPE_CLOSED,
                SW_HEM_POSITION_OUTSIDE,
                False,
                HEM_LENGTH_M,
                0.0,
                0.0,
                0.0,
                HEM_MITER_GAP_M,
                pythoncom.Missing,
            )
            rec_miss, feat_miss = _capture(
                lambda: fm.InsertSheetMetalHem(*args_missing)
            )
            out["pythoncom_missing"] = rec_miss
            out["pythoncom_missing_materialized"] = _materialized(feat_miss)

        out["faces"] = _count_faces(doc)

    finally:
        _close_all(sw)

    return out


def _try_pcba_and_edges(sw: Any, mod: Any) -> dict[str, Any]:
    """Try with valid PCBA object + multiple edges."""
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"error": "NewDocument None"}

    try:
        try:
            doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
            sk = doc.SketchManager
            sk.InsertSketch(True)
            sk.CreateCornerRectangle(
                -PROF_W_M / 2, -PROF_H_M / 2, 0.0, PROF_W_M / 2, PROF_H_M / 2, 0.0
            )
            sk.InsertSketch(True)
        except Exception as e:
            return {"error": f"sketch: {e}"}

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
        if data is None:
            return {"error": "CD(34) None"}
        qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
        if wrapped is None:
            return {"error": "QI None"}
        for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
            try:
                setattr(wrapped, name, val)
            except Exception:
                pass
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        if not _materialized(feat):
            return {"error": "base flange None"}

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        # Enumerate edges
        edges_info = _find_edges_with_info(doc, mod)
        out["edges_found"] = len(edges_info)
        out["edge_info"] = edges_info[:4]

        # Try raw invoke on multiple edges
        rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
        body_list = _as_list(bodies)
        if not body_list:
            return {"error": "no bodies"}
        body = body_list[0]
        rec, edges_raw = _capture(lambda: body.GetEdges())
        edge_list = _as_list(edges_raw)

        attempts = []
        for i, edge in enumerate(edge_list[:4]):
            try:
                doc.ClearSelection2(True)
            except Exception:
                pass
            try:
                ext = typed_extension(doc, module=mod)
                pid = ext.GetPersistReference3(edge)
                if pid:
                    obj_result = ext.GetObjectByPersistReference3(pid)
                    edge = (
                        obj_result[0] if isinstance(obj_result, tuple) else obj_result
                    )
                edge.Select2(False, 0)
            except Exception as e:
                attempts.append({"edge": i, "select_error": str(e)})
                continue

            args = (
                SW_HEM_TYPE_CLOSED,
                SW_HEM_POSITION_OUTSIDE,
                False,
                HEM_LENGTH_M,
                0.0,
                0.0,
                0.0,
                HEM_MITER_GAP_M,
                None,
            )

            rec_raw, feat_raw = _capture(
                lambda: fm._oleobj_.InvokeTypes(
                    MEMID_HEM_V1, 0, 1, (9, 0), HEM_V1_ARGTYPES_VT13, *args
                )
            )

            attempt = {
                "edge": i,
                "name": edges_info[i]["name"] if i < len(edges_info) else f"edge_{i}",
                "status": rec_raw["status"],
                "type": rec_raw.get("type"),
                "materialized": _materialized(feat_raw),
            }
            if _materialized(feat_raw):
                attempt["feature_name"] = getattr(feat_raw, "Name", None)
                doc.ForceRebuild3(False)
                attempt["faces_after"] = _count_faces(doc)
                attempts.append(attempt)
                out["edge_attempts"] = attempts
                out["overall"] = "PASS"
                return out
            attempts.append(attempt)

        out["edge_attempts"] = attempts
        out["overall"] = "FAIL"

    finally:
        _close_all(sw)

    return out


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    out_path = Path(__file__).parent / "_results" / "hem_diag_wall.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    sys.stderr.write(f"wrote {out_path}\n")
    sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
