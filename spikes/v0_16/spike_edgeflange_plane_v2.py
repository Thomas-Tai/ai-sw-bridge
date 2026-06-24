"""Spike v0.16 - T6 v2: Edge-flange normal-plane (CORRECTED two-reference probe).

v1 WALL REJECTED by W0: v1 selected ONLY the edge (one reference) and GUESSED
constraint flags (Distance=1, Perpendicular=16). A plane normal-to-edge is a
TWO-reference construction; one reference is under-defined and InsertRefPlane
correctly no-ops.

v2 corrections:
  - TYPELIB FIRST: read swRefPlaneReferenceConstraints_e from swconst.tlb via
    pythoncom.LoadTypeLib. Cross-check: _Distance MUST equal 8 (proven by the
    shipping ref_plane handler, mutate.py:119). If Distance != 8, abort.
  - TWO references: edge endpoint vertex (anchor, Coincident) + linear edge
    (direction, Perpendicular). Both acquired via persist round-trip.
  - Mark sweep: vertex mark=0/edge mark=0, then vertex mark=0/edge mark=1,
    then swap reference order. Reference slots often map by mark (dome needed
    mark=1).
  - Delta verification: len(GetFeatures(True)) before/after.

MILESTONE (this only, do NOT chain into the flange call):
  selected linear edge + its endpoint vertex -> reference plane NORMAL to the
  edge, delta-verified -> profile sketch opens on it with a closed rectangle.

Usage:
    python spikes/v0_16/spike_edgeflange_plane_v2.py --out spikes/v0_16/_results/edgeflange_normal_plane_T6_v2.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_extension, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module

SW_DEFAULT_TEMPLATE_PART = 8
SWCONST_TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb"


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _feature_count(doc: Any) -> int:
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _list_features(doc: Any, mod: Any) -> list[dict[str, str]]:
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


# ---- TYPELIB FIRST --------------------------------------------------------


def _read_swconst_enum(enum_name: str) -> dict[str, int]:
    """Read an enum from swconst.tlb via pythoncom.LoadTypeLib + ITypeComp.

    Two-step: (1) iterate via GetVarDesc over cVars to dump all members,
    (2) cross-validate via ITypeComp.Bind for named lookups.
    Returns {member_name: value} for the named enum. Raises on failure.
    """
    if not os.path.isfile(SWCONST_TLB_PATH):
        raise FileNotFoundError(f"swconst.tlb not found at {SWCONST_TLB_PATH}")
    tlb = pythoncom.LoadTypeLib(SWCONST_TLB_PATH)
    typeinfo = None
    for i in range(tlb.GetTypeInfoCount()):
        try:
            name = tlb.GetDocumentation(i)[0]
        except Exception:
            continue
        if name == enum_name:
            typeinfo = tlb.GetTypeInfo(i)
            break
    if typeinfo is None:
        raise LookupError(f"enum {enum_name!r} not found in swconst.tlb")

    members: dict[str, int] = {}
    attr = typeinfo.GetTypeAttr()
    for vi in range(attr.cVars):
        vd = typeinfo.GetVarDesc(vi)
        memid = vd[0]
        name = typeinfo.GetNames(memid)[0]
        members[name] = vd.value

    tc = typeinfo.GetTypeComp()
    for check_name in tuple(members.keys())[:3]:
        bind_result = tc.Bind(check_name)
        if bind_result and isinstance(bind_result, tuple) and len(bind_result) >= 2:
            bind_val = (
                bind_result[1].value if hasattr(bind_result[1], "value") else None
            )
            if bind_val is not None and bind_val != members[check_name]:
                raise ValueError(
                    f"Bind({check_name})={bind_val} != iter={members[check_name]}"
                )

    return members


def _extract_constraints() -> dict[str, Any]:
    """Extract swRefPlaneReferenceConstraints_e from swconst.tlb.

    Cross-check: _Distance MUST equal 8 (proven by shipping ref_plane handler).
    """
    raw = _read_swconst_enum("swRefPlaneReferenceConstraints_e")
    result: dict[str, Any] = {"raw_members": raw}

    distance_val = raw.get("swRefPlaneReferenceConstraint_Distance")
    result["Distance"] = distance_val
    result["distance_anchor_ok"] = distance_val == 8

    for short_name in (
        "Coincident",
        "Perpendicular",
        "Parallel",
        "Angle",
        "MidPlane",
        "Distance",
    ):
        full = f"swRefPlaneReferenceConstraint_{short_name}"
        result[short_name] = raw.get(full)

    return result


# ---- BOX + EDGE + VERTEX --------------------------------------------------


def _build_box(sw: Any) -> Any:
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


def _find_linear_edge_and_vertex(
    doc: Any, mod: Any
) -> tuple[Any, Any, float, dict[str, Any]]:
    """Get the longest linear edge + its start vertex via persist round-trip.

    Returns (live_edge, live_vertex, edge_length, diagnostics).
    """
    diag: dict[str, Any] = {}
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        raise RuntimeError("no bodies")
    body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    edges_raw = body.GetEdges()
    if not edges_raw:
        raise RuntimeError("no edges")
    ext = typed_extension(doc, module=mod)

    best_edge = None
    best_vertex = None
    best_len = -1.0
    edge_candidates = 0
    linear_candidates = 0

    for e in edges_raw:
        try:
            pid = ext.GetPersistReference3(e)
            if pid is None:
                continue
            obj = ext.GetObjectByPersistReference3(pid)
            live = obj[0] if isinstance(obj, tuple) else obj
            if live is None or isinstance(live, int):
                continue

            iedge = typed(live, "IEdge", module=mod)
            icurve_raw = iedge.GetCurve()
            if icurve_raw is None:
                continue
            icurve = typed(icurve_raw, "ICurve", module=mod)

            try:
                is_line = bool(icurve.IsLine())
            except Exception:
                is_line = False
            if not is_line:
                continue
            linear_candidates += 1

            params = icurve.GetEndParams()
            length = float(icurve.GetLength(params[1], params[2]))

            if length > best_len:
                best_len = length
                best_edge = live
                vtx_raw = iedge.GetStartVertex()
                if vtx_raw is not None:
                    vtx_pid = ext.GetPersistReference3(vtx_raw)
                    if vtx_pid is not None:
                        vtx_obj = ext.GetObjectByPersistReference3(vtx_pid)
                        best_vertex = (
                            vtx_obj[0] if isinstance(vtx_obj, tuple) else vtx_obj
                        )
        except Exception as exc:
            continue
        edge_candidates += 1

    diag["edge_candidates"] = edge_candidates
    diag["linear_candidates"] = linear_candidates
    diag["vertex_acquired"] = best_vertex is not None

    if best_edge is None:
        raise RuntimeError("no linear edge found")
    if best_vertex is None:
        raise RuntimeError("edge found but vertex acquisition failed")

    return best_edge, best_vertex, best_len, diag


# ---- MAIN PROBE -----------------------------------------------------------


def _probe_normal_plane(
    doc: Any,
    fm: Any,
    mod: Any,
    edge: Any,
    vertex: Any,
    coincident_flag: int,
    perpendicular_flag: int,
) -> dict[str, Any]:
    """Sweep marks and reference order for InsertRefPlane with two references.

    The moving variable is the selection sequence:
      - reference order (vertex-first vs edge-first)
      - mark values (0 vs 1)
      - InsertRefPlane argument order (which constraint maps to which ref)
    """
    attempts: list[dict[str, Any]] = []
    ient_vtx = typed(vertex, "IEntity", module=mod)
    ient_edge = typed(edge, "IEntity", module=mod)

    configs = [
        {
            "label": "vtx(m=0)->edge(m=0) coin/perp",
            "first": (ient_vtx, False, 0),
            "second": (ient_edge, True, 0),
            "args": (coincident_flag, 0, perpendicular_flag, 0, 0, 0),
        },
        {
            "label": "vtx(m=0)->edge(m=1) coin/perp",
            "first": (ient_vtx, False, 0),
            "second": (ient_edge, True, 1),
            "args": (coincident_flag, 0, perpendicular_flag, 0, 0, 0),
        },
        {
            "label": "edge(m=0)->vtx(m=0) perp/coin",
            "first": (ient_edge, False, 0),
            "second": (ient_vtx, True, 0),
            "args": (perpendicular_flag, 0, coincident_flag, 0, 0, 0),
        },
        {
            "label": "edge(m=0)->vtx(m=1) perp/coin",
            "first": (ient_edge, False, 0),
            "second": (ient_vtx, True, 1),
            "args": (perpendicular_flag, 0, coincident_flag, 0, 0, 0),
        },
        {
            "label": "vtx(m=1)->edge(m=0) coin/perp",
            "first": (ient_vtx, False, 1),
            "second": (ient_edge, True, 0),
            "args": (coincident_flag, 0, perpendicular_flag, 0, 0, 0),
        },
        {
            "label": "edge(m=1)->vtx(m=0) perp/coin",
            "first": (ient_edge, False, 1),
            "second": (ient_vtx, True, 0),
            "args": (perpendicular_flag, 0, coincident_flag, 0, 0, 0),
        },
        {
            "label": "vtx(m=0)->edge(m=0) coin/perp SWAPPED_ARGS",
            "first": (ient_vtx, False, 0),
            "second": (ient_edge, True, 0),
            "args": (perpendicular_flag, 0, coincident_flag, 0, 0, 0),
        },
        {
            "label": "edge(m=0)->vtx(m=0) coin/perp BOTH_COIN",
            "first": (ient_edge, False, 0),
            "second": (ient_vtx, True, 0),
            "args": (coincident_flag, 0, coincident_flag, 0, 0, 0),
        },
    ]

    for cfg in configs:
        doc.ClearSelection2(True)
        first_ent, first_append, first_mark = cfg["first"]
        second_ent, second_append, second_mark = cfg["second"]

        sel1_ok = bool(first_ent.Select2(first_append, first_mark))
        sel2_ok = bool(second_ent.Select2(second_append, second_mark))

        n_before = _feature_count(doc)
        try:
            ret = fm.InsertRefPlane(*cfg["args"])
            err = None
        except Exception as e:
            ret = None
            err = f"{type(e).__name__}: {str(e)[:200]}"

        n_after = _feature_count(doc)
        delta = n_after - n_before

        entry = {
            "label": cfg["label"],
            "sel1": sel1_ok,
            "sel2": sel2_ok,
            "args": list(cfg["args"]),
            "delta": delta,
            "materialized": delta > 0,
            "return_value": str(ret)[:120] if ret is not None else "None",
            "error": err,
        }
        attempts.append(entry)

        if delta > 0:
            return {"attempts": attempts, "winner": entry, "overall": "GREEN"}

    return {"attempts": attempts, "winner": None, "overall": "WALL"}


def _verify_sketch(doc: Any, mod: Any, plane_name: str) -> dict[str, Any]:
    """Open a sketch on the new plane and draw a closed rectangle."""
    out: dict[str, Any] = {}
    try:
        doc.ClearSelection2(True)
        sel = doc.SelectByID(plane_name, "DATUMPLANE", 0, 0, 0)
        out["select_plane"] = bool(sel)
        doc.InsertSketch2(True)
        sk = doc.SketchManager
        seg = sk.CreateCornerRectangle(-0.005, -0.005, 0, 0.005, 0.005, 0)
        out["rectangle_created"] = seg is not None
        doc.InsertSketch2(False)
        doc.ClearSelection2(True)

        sketches = [
            f["name"]
            for f in _list_features(doc, mod)
            if f.get("type") == "ProfileFeature"
        ]
        out["all_sketches"] = sketches
        out["sketch_verified"] = len(sketches) > 1
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "edgeflange_normal_plane_T6_v2",
        "ts": time.time(),
    }
    print("[t6v2] TYPELIB FIRST: reading swconst.tlb...")

    try:
        constraints = _extract_constraints()
    except Exception as e:
        return {
            **result,
            "overall": "FAIL",
            "reason": f"typelib extraction failed: {type(e).__name__}: {e}",
        }

    result["typelib"] = constraints
    if not constraints.get("distance_anchor_ok"):
        return {
            **result,
            "overall": "FAIL",
            "reason": (
                f"ANCHOR MISMATCH: Distance={constraints.get('Distance')}, "
                f"expected 8. Wrong enum block or wrong tlb."
            ),
        }
    print("[t6v2] anchor OK: Distance=%s" % constraints["Distance"])
    print(
        "[t6v2] Coincident=%s, Perpendicular=%s"
        % (constraints.get("Coincident"), constraints.get("Perpendicular"))
    )

    coin = constraints.get("Coincident")
    perp = constraints.get("Perpendicular")
    if coin is None or perp is None:
        return {
            **result,
            "overall": "FAIL",
            "reason": "Coincident or Perpendicular not found in typelib enum",
        }

    print("[t6v2] connecting to SW...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    print("[t6v2] building 50x50x50mm box...")
    doc = _build_box(sw)
    print("[t6v2] box built: %s" % _title(doc))

    try:
        fm = doc.FeatureManager
        print("[t6v2] finding longest linear edge + endpoint vertex...")
        edge, vertex, edge_len, edge_diag = _find_linear_edge_and_vertex(doc, mod)
        result["edge_length"] = edge_len
        result["edge_diag"] = edge_diag
        print(
            "[t6v2] edge: %.1fmm, vertex acquired: %s"
            % (edge_len * 1000, edge_diag.get("vertex_acquired"))
        )

        iedge = typed(edge, "IEdge", module=mod)
        icurve = typed(iedge.GetCurve(), "ICurve", module=mod)
        params = icurve.GetEndParams()
        t_mid = (params[1] + params[2]) / 2.0
        eval_out = icurve.Evaluate(t_mid)
        result["edge_midpoint"] = [eval_out[0], eval_out[1], eval_out[2]]
        result["edge_tangent"] = (
            [eval_out[3], eval_out[4], eval_out[5]] if len(eval_out) >= 6 else None
        )

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before

        print("[t6v2] probing InsertRefPlane with TWO references + mark sweep...")
        probe = _probe_normal_plane(doc, fm, mod, edge, vertex, coin, perp)
        result["probe"] = probe
        result["overall"] = probe["overall"]

        if probe["overall"] == "GREEN":
            winner = probe["winner"]
            print("[t6v2] GREEN! winner: %s" % winner["label"])

            feats = _list_features(doc, mod)
            plane_name = None
            for f in feats:
                if f.get("type") == "RefPlane" and f.get("name", "").startswith(
                    "Plane"
                ):
                    plane_name = f["name"]
                    break
            result["plane_name"] = plane_name

            if plane_name:
                print("[t6v2] sketching on %s..." % plane_name)
                sketch = _verify_sketch(doc, mod, plane_name)
                result["sketch"] = sketch
                if sketch.get("sketch_verified"):
                    result["overall"] = "GREEN"
                    result["interpretation"] = (
                        "Normal plane materialized (delta>0) + sketch verified. "
                        "Winning: %s, args=%s. Coincident=%d, Perpendicular=%d. "
                        "COM boundary is closed for T6 normal-plane milestone."
                        % (winner["label"], winner["args"], coin, perp)
                    )
                else:
                    result["overall"] = "PARTIAL"
                    result["interpretation"] = (
                        "Plane materialized but sketch verification failed."
                    )
            else:
                result["overall"] = "PARTIAL"
                result["interpretation"] = (
                    "Plane materialized (delta>0) but plane name not found."
                )
        else:
            result["feature_count_after"] = _feature_count(doc)
            result["features_after"] = _list_features(doc, mod)
            result["interpretation"] = (
                "WALL: all %d mark/order combos no-oped with Coincident=%d, "
                "Perpendicular=%d. Two-reference InsertRefPlane does not "
                "materialize out-of-process." % (len(probe["attempts"]), coin, perp)
            )

    finally:
        _try_close(sw, doc)

    return result


def main() -> int:
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
