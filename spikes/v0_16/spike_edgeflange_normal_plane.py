"""Spike v0.16 - T6: Edge-flange normal-plane milestone.

Three bounded steps:
1. Identify a topological edge (linear edge of a box).
2. Construct a reference plane normal to that edge at a chosen point.
3. Open a valid profile sketch on that plane.

InsertRefPlane constraint flags: Distance=1, Coincident=2, Angle=4,
Parallel=8, Perpendicular=16, MidPlane=128. Materialization via
len(GetFeatures(True)) delta.
"""

from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module

SW_DEFAULT_TEMPLATE_PART = 8
SW_REFPLANE_PERPENDICULAR = 16
SW_REFPLANE_COINCIDENT = 2
SW_REFPLANE_ANGLE = 4
SW_REFPLANE_PARALLEL = 8
SW_REFPLANE_DISTANCE = 1


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw, doc):
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _feature_count(doc):
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _list_features(doc):
    out = []
    mod = wrapper_module()
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


def _build_box(sw):
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.05,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _find_linear_edge(doc, mod):
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        raise RuntimeError("no bodies")
    body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    edges = body.GetEdges()
    if not edges:
        raise RuntimeError("no edges")
    ext = typed_extension(doc, module=mod)
    best_edge, best_len = None, -1.0
    for e in edges:
        try:
            pid = ext.GetPersistReference3(e)
            if pid is None:
                continue
            obj = ext.GetObjectByPersistReference3(pid)
            live = obj[0] if isinstance(obj, tuple) else obj
            iedge = typed(live, "IEdge", module=mod)
            icurve = iedge.GetCurve()
            if icurve is None:
                continue
            icurve = typed(icurve, "ICurve", module=mod)
            try:
                is_line = icurve.IsLine()
            except Exception:
                is_line = None
            if not is_line:
                continue
            try:
                params = icurve.GetEndParams()
                length = icurve.GetLength(params[1], params[2])
            except Exception:
                length = 0.0
            if length > best_len:
                best_len = length
                best_edge = live
        except Exception:
            continue
    if best_edge is None:
        raise RuntimeError("no linear edge")
    return best_edge, best_len


def run():
    result = {"spike": "edgeflange_normal_plane_T6", "ts": time.time()}
    print("[t6] connecting...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    sw = connect_running_sw()
    print("[t6] building 50x50x50mm box...")
    doc = _build_box(sw)
    print("[t6] box built: %s" % _title(doc))

    try:
        fm = doc.FeatureManager
        print("[t6] finding longest linear edge...")
        edge, edge_len = _find_linear_edge(doc, mod)
        result["edge_length"] = edge_len
        print("[t6] edge found: length=%.4fm" % edge_len)

        iedge = typed(edge, "IEdge", module=mod)
        icurve_raw = iedge.GetCurve()
        icurve = typed(icurve_raw, "ICurve", module=mod)
        params = icurve.GetEndParams()
        t_mid = (params[1] + params[2]) / 2.0
        eval_out = icurve.Evaluate(t_mid)
        point = (eval_out[0], eval_out[1], eval_out[2])
        tangent = (
            (eval_out[3], eval_out[4], eval_out[5]) if len(eval_out) >= 6 else None
        )
        result["edge_midpoint"] = list(point)
        result["edge_tangent"] = list(tangent) if tangent else None
        print("[t6] midpoint: %s" % str(point))
        print("[t6] tangent: %s" % str(tangent))

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before

        constraint_probes = [
            ("perp_only", SW_REFPLANE_PERPENDICULAR, 0, 0, 0),
            (
                "perp_coincident",
                SW_REFPLANE_PERPENDICULAR,
                0,
                SW_REFPLANE_COINCIDENT,
                0,
            ),
            ("perp_angle", SW_REFPLANE_PERPENDICULAR, 0, SW_REFPLANE_ANGLE, 90.0),
        ]

        probes = []
        green = None

        for probe_name, c1, d1, c2, d2 in constraint_probes:
            doc.ClearSelection2(True)
            try:
                ient_edge = typed(edge, "IEntity", module=mod)
                edge_sel = ient_edge.Select2(False, 0)
            except Exception as e:
                edge_sel = False
                print("    edge sel err: %s" % e)

            if not edge_sel:
                probes.append({"probe": probe_name, "error": "edge selection failed"})
                continue

            n_before_call = _feature_count(doc)
            try:
                ref = fm.InsertRefPlane(c1, d1, c2, d2, 0, 0)
                err = None
            except Exception as e:
                ref = None
                err = "%s: %s" % (type(e).__name__, str(e)[:200])

            n_after_call = _feature_count(doc)
            delta = n_after_call - n_before_call
            mat = delta > 0

            entry = {
                "probe": probe_name,
                "constraints": [c1, c2],
                "distances": [d1, d2],
                "delta": delta,
                "materialized": mat,
                "return_value": str(ref)[:120] if ref else "None",
                "error": err,
            }
            if mat:
                for feat_info in _list_features(doc):
                    if feat_info.get("type") == "RefPlane" and feat_info.get(
                        "name", ""
                    ).startswith("Plane"):
                        entry["plane_name"] = feat_info["name"]
                        break
            probes.append(entry)
            print(
                "  [%s] c1=%d c2=%d delta=%d mat=%s err=%s"
                % (probe_name, c1, c2, delta, mat, err)
            )

            if mat and green is None:
                green = entry

        result["probes"] = probes

        if green and green.get("plane_name"):
            plane_name = green["plane_name"]
            print("[t6] sketching on plane: %s" % plane_name)
            try:
                doc.ClearSelection2(True)
                doc.SelectByID(plane_name, "DATUMPLANE", 0, 0, 0)
                doc.InsertSketch2(True)
                sk = doc.SketchManager
                sk.CreateCornerRectangle(-0.005, -0.005, 0, 0.005, 0.005, 0)
                doc.InsertSketch2(False)
                doc.ClearSelection2(True)
                sketches = [
                    feat_info["name"]
                    for feat_info in _list_features(doc)
                    if feat_info.get("type") == "ProfileFeature"
                ]
                result["sketches"] = sketches
                result["sketch_verified"] = len(sketches) > 1
                if result["sketch_verified"]:
                    result["overall"] = "GREEN"
                    result["recipe"] = {
                        "constraints": green["constraints"],
                        "plane_name": plane_name,
                        "edge_midpoint": list(point),
                        "edge_tangent": list(tangent) if tangent else None,
                    }
                    result["interpretation"] = (
                        "Normal plane materialized (c1=%d, c2=%d) + sketch verified. "
                        "W0 scopes the edge-flange follow-on."
                        % (green["constraints"][0], green["constraints"][1])
                    )
                else:
                    result["overall"] = "PARTIAL"
                    result["interpretation"] = (
                        "Plane materialized but sketch not verified."
                    )
            except Exception as e:
                result["sketch_error"] = str(e)[:200]
                result["overall"] = "PARTIAL"
                result["interpretation"] = "Plane materialized but sketch failed."
        elif green:
            result["overall"] = "PARTIAL"
            result["interpretation"] = "Plane materialized but name not captured."
        else:
            result["overall"] = "WALL"
            result["interpretation"] = (
                "No constraint combo materialized a normal plane across %d probes."
                % len(probes)
            )

        result["feature_count_after"] = _feature_count(doc)
        result["features_after"] = _list_features(doc)

    finally:
        _try_close(sw, doc)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        print(payload)
    return {"GREEN": 0, "PARTIAL": 2, "WALL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
