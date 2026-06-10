"""S1 de-risk spike — Mechanical Mates epoch, TIER 2 (Rack-Pinion + Cam-Follower).

Tier-1 (gear/screw) proved the SCALAR axis on the SYMMETRIC EntitiesToMate path.
Tier-2's risk is the ASYMMETRIC reference layout. The typelib dump (O1, run
before authoring) settled the property layout decisively:

  IRackPinionMateFeatureData: EntitiesToMate (indexed) + DiameterType:I4 +
    DiameterVal:R8 + Reverse:BOOL.
  ICamFollowerMateFeatureData: EntitiesToMate (indexed) + MateAlignment ONLY —
    NO separate Cam/Follower arrays. The W12 two-set model does NOT apply; both
    cam face(s) and follower go in the SAME EntitiesToMate array.

Two tactical constraints (per W0 directive):

  1. RACK-PINION SCALAR TOGGLE — DiameterType (swRackPinionMateDistanceOptions_e:
     swPinionPitchDiameter=0 / swRackTravelPerRevolution=1) gates how DiameterVal
     reads, exactly like the screw's RevolutionType. It is set BEFORE DiameterVal
     or the kernel reverts the scalar (the W46 screw clamp lesson).
  2. CAM TANGENCY — the cam fixture is a mathematically-perfect ELLIPSE extrude
     (no spline discontinuity), so a CreateMate failure indicts our COM
     marshaling, not the kernel's geometric solver.

GREEN (per leg):
  rack-pinion: enum-by-name; CreateMate clean (GetErrorCode2==(0,False)); the
    scalar (DiameterType + DiameterVal) PERSISTS through save/reopen at the set
    value (or a CHARACTERIZED transform we can invert, Tier-1 style).
  cam-follower: enum-by-name; CreateMate clean; the mate (MateCamFollower)
    PERSISTS through reopen with both EntitiesToMate selections intact. No scalar.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_tier2_rack_cam.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _find_assembly_template,
    _build_part_spec,
)
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_tier2_rack_cam.json"

# swRackPinionMateDistanceOptions_e (swconst.tlb v32, dumped).
_RP_PINION_PITCH_DIA = 0   # swPinionPitchDiameter
_RP_RACK_TRAVEL_PER_REV = 1  # swRackTravelPerRevolution

_RACKPINION_IFACE = ("IRackPinionMateFeatureData", "IRackPinionMateFeatureData2")
_CAMFOLLOWER_IFACE = ("ICamFollowerMateFeatureData", "ICamFollowerMateFeatureData2")


def _pinion_spec(name: str) -> dict[str, Any]:
    """Ø20 × 40 mm cylindrical pinion (reuse Tier-1 cylinder shape)."""
    return t1._cylinder_spec(name)


def _follower_spec(name: str) -> dict[str, Any]:
    """Ø10 × 30 mm small cylindrical follower."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_circle_on_plane", "name": "SK", "plane": "Front",
             "diameter": 10.0, "center": {"x": 0.0, "y": 0.0}},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 30.0},
        ],
    }


def _rack_spec(name: str) -> dict[str, Any]:
    """100 × 8 mm bar extruded 8 mm — long linear edges along the 100 mm axis."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "width": 100.0, "height": 8.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 8.0},
        ],
    }


def _cam_spec(name: str) -> dict[str, Any]:
    """Mathematically-perfect ELLIPSE (25 × 15 mm radii) extruded 10 mm — the
    lateral face is one continuous periodic surface (no spline discontinuity)."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_ellipse", "name": "SK", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "major_radius": 25.0, "minor_radius": 15.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }


def _build(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    save_as = str(Path(t1._results_tmp(), f"t2_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(spec, save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _first_cyl_face(comp: Any, mod: Any) -> Any | None:
    return t1._first_cyl_face(comp, mod)


def _body_of(comp: Any) -> Any | None:
    try:
        bodies = comp.GetBodies(0)
        if not bodies:
            return None
        return bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    except Exception:  # noqa: BLE001
        return None


def _first_linear_edge(comp: Any, mod: Any) -> Any | None:
    body = _body_of(comp)
    if body is None:
        return None
    try:
        edges = body.GetEdges() or ()
    except Exception:  # noqa: BLE001
        return None
    for e in edges:
        try:
            ie = typed(e, "IEdge", module=mod)
            curve = ie.GetCurve()
            ic = typed(curve, "ICurve", module=mod)
            if bool(ic.IsLine()):
                return e
        except Exception:  # noqa: BLE001
            continue
    return None


def _first_nonplanar_face(comp: Any, mod: Any) -> Any | None:
    """The cam profile = the lateral (non-planar, non-cylindrical) face of the
    elliptical extrude. Skip the two flat elliptical caps."""
    body = _body_of(comp)
    if body is None:
        return None
    try:
        faces = body.GetFaces() or ()
    except Exception:  # noqa: BLE001
        return None
    for f in faces:
        try:
            iface = typed(f, "IFace2", module=mod)
            surf = typed(iface.GetSurface(), "ISurface", module=mod)
            if not bool(surf.IsPlane()):
                return f
        except Exception:  # noqa: BLE001
            continue
    return None


def _entities(a: Any, b: Any) -> Any:
    return w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (a, b))


def _set_entities(ti: Any, ents: list[Any]) -> str:
    """Set the mate entities. Symmetric mates (gear/cam) take a settable array
    property; the asymmetric rack-pinion exposes only the indexed PROPPUT, which
    makepy surfaces as the method SetEntitiesToMate(index, entity). Try the array
    form first, fall back to per-index."""
    try:
        ti.EntitiesToMate = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(ents)
        )
        return "property_array"
    except AttributeError:
        for i, e in enumerate(ents):
            ti.SetEntitiesToMate(i, e)
        return "SetEntitiesToMate_indexed"


def _place_pair(sw: Any, mod: Any, p1: dict, p2: dict) -> dict[str, Any]:
    asm_template = _find_assembly_template()
    if asm_template is None:
        return {"error": "NO_ASM_TEMPLATE"}
    asm = sw.NewDocument(asm_template, 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    components = [
        {"id": "a", "part": p1["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": p2["path"], "transform": {"xyz_mm": [60, 0, 0]}},
    ]
    placed, err = place_components(sw, asm, components, mod=mod)
    if err is not None:
        return {"error": f"PLACE_FAILED: {err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return {"asm": asm, "a": placed.get("a"), "b": placed.get("b")}


def _qi_first(mate_data: Any, candidates: tuple[str, ...], mod: Any) -> tuple[str, Any] | None:
    for cand in candidates:
        try:
            ti = typed_qi(mate_data, cand, module=mod)
            if ti is not None:
                return cand, ti
        except Exception:  # noqa: BLE001
            continue
    return None


def _read_back(sw: Any, mod: Any, asm_path: str, iface_name: str,
               props: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        typed_sw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)
        reopened = typed_sw.OpenDoc6(asm_path, 2, 0, "", 0, 0)
        rdoc = reopened[0] if isinstance(reopened, tuple) else reopened
        if rdoc is None:
            return {"error": "reopen None"}
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        for f in rdoc.FeatureManager.GetFeatures(False) or ():
            tf = typed(f, "IFeature", module=mod)
            try:
                tname = tf.GetTypeName2()
                if "Mate" not in tname:
                    continue
                defn = tf.GetDefinition()
                if defn is None:
                    continue
                ti = typed_qi(defn, iface_name, module=mod)
                vals = {}
                for p in props:
                    try:
                        vals[p] = getattr(ti, p)
                    except Exception as exc:  # noqa: BLE001
                        vals[p] = f"read failed: {exc!r}"
                out["mate_feature_type"] = tname
                out["read_back"] = vals
                return out
            except Exception:  # noqa: BLE001
                continue
        out["error"] = "no mate feature with readable definition on reopen"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"readback raised: {exc!r}"
    return out


def _leg_rack_pinion(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "rack_pinion", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum("swMateRACKPINION")
    r["enum_resolved"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    rack = _build("rack", _rack_spec("rack"))
    pinion = _build("pinion", _pinion_spec("pinion"))
    if "error" in rack or "error" in pinion:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = rack.get("error") or pinion.get("error")
        return r
    ctx = _place_pair(sw, mod, rack, pinion)
    if "error" in ctx:
        r["status"] = ctx["error"]
        return r
    asm = ctx["asm"]
    rack_edge = _first_linear_edge(ctx["a"], mod)
    pinion_face = _first_cyl_face(ctx["b"], mod)
    r["entities_found"] = {"rack_linear_edge": rack_edge is not None,
                           "pinion_cyl_face": pinion_face is not None}
    if rack_edge is None or pinion_face is None:
        r["status"] = "ENTITY_RESOLUTION_FAILED"
        return r
    try:
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            r["status"] = "CREATEMATEDATA_NONE"
            return r
        bound = _qi_first(md, _RACKPINION_IFACE, mod)
        if bound is None:
            r["status"] = "NO_TYPED_IFACE"
            return r
        iface_name, ti = bound
        r["typed_iface"] = iface_name
        r["iface_members"] = [n for n in dir(ti) if not n.startswith("_")]
        # Rack first (swRackPinionMateEntityType_Rack=0), pinion second (=1).
        r["entities_set_via"] = _set_entities(ti, [rack_edge, pinion_face])
        # TOGGLE BEFORE SCALAR (screw lesson): DiameterType then DiameterVal.
        ti.DiameterType = _RP_PINION_PITCH_DIA
        ti.DiameterVal = 0.020  # 20 mm pinion pitch diameter
        r["scalars_set"] = {"DiameterType": _RP_PINION_PITCH_DIA, "DiameterVal": 0.020}
        # Echo immediately (T0) to see if the setter holds pre-create.
        try:
            r["T0_post_set"] = {"DiameterType": ti.DiameterType, "DiameterVal": ti.DiameterVal}
        except Exception:  # noqa: BLE001
            pass
        mate = typed_asm.CreateMate(md)
        if mate is None or isinstance(mate, int):
            try:
                mfd = typed_qi(md, "IMateFeatureData", module=mod)
                r["error_status"] = mfd.ErrorStatus
            except Exception:  # noqa: BLE001
                pass
            r["status"] = "CREATEMATE_NONE"
            return r
        ifeat = typed(mate, "IFeature", module=mod)
        r["feature_type"] = ifeat.GetTypeName2()
        ec = ifeat.GetErrorCode2()
        r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        asm_path = str(Path(t1._results_tmp(), f"rp_asm_{os.getpid()}.SLDASM"))
        save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        if int(save_ok) != 0:
            r["status"] = "SAVE_FAILED"
            return r
        rb = _read_back(sw, mod, asm_path, iface_name, ("DiameterType", "DiameterVal"))
        r["persist"] = rb
        if "read_back" in rb:
            vals = rb["read_back"]
            holds = (
                isinstance(vals.get("DiameterVal"), (int, float))
                and abs(vals["DiameterVal"] - 0.020) < 1e-6
                and vals.get("DiameterType") == _RP_PINION_PITCH_DIA
            )
            r["status"] = "SOLVED_PERSISTED" if holds else "SOLVED_SCALAR_TRANSFORMED"
        else:
            r["status"] = "SOLVED_READBACK_UNVERIFIED"
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return r


def _newest_sketch_name(doc: Any, mod: Any) -> str | None:
    try:
        raw = doc.GetFeatureCount
        count = raw(True) if callable(raw) else int(raw)
    except Exception:  # noqa: BLE001
        return None
    for i in range(count):
        try:
            feat = doc.FeatureByPositionReverse(i)
        except Exception:  # noqa: BLE001
            break
        if feat is None:
            break
        try:
            tf = typed(feat, "IFeature", module=mod)
            tn = tf.GetTypeName2()
        except Exception:  # noqa: BLE001
            continue
        if tn in {"ProfileFeature", "Sketch"}:
            try:
                return tf.Name
            except Exception:  # noqa: BLE001
                pass
    return None


def _build_cam_handrolled(sw: Any, mod: Any, name: str) -> dict[str, Any]:
    """Hand-roll a mathematically-perfect elliptical cam, bypassing the broken
    declarative sketch_ellipse->extrude path. ISketchManager.CreateEllipse (the
    exact call the builder uses) + FeatureExtrusion2 (23-arg, mirrors
    builder._call_feature_extrusion verbatim: blind, depth 10mm)."""
    try:
        template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
        raw_doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if raw_doc is None:
            return {"error": "NewDocument(part) None"}
        # Type-wrap as IModelDoc2 so SelectByID/ClearSelection2/etc. resolve
        # (raw NewDocument dispatch doesn't expose them out-of-process).
        doc = typed(raw_doc, "IModelDoc2", module=mod)
        if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
            return {"error": "could not select Front plane"}
        # Type-wrap the SketchManager — raw dispatch methods silently no-op
        # out-of-process (the Tier-1 cyl-face lesson).
        sm = typed(doc.SketchManager, "ISketchManager", module=mod)
        sm.InsertSketch(True)
        major, minor = 0.025, 0.015  # 25 x 15 mm radii
        sm.CreateEllipse(0.0, 0.0, 0.0, major, 0.0, 0.0, 0.0, minor, 0.0)
        sm.InsertSketch(True)  # close — the new sketch remains selected
        # Extrude the just-closed (still-selected) sketch directly; no name
        # lookup (GetFeatureCount arity differs on the typed proxy).
        fm = typed(doc.FeatureManager, "IFeatureManager", module=mod)
        args = (
            True, False, False, 0, 0, 0.010, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False, True, True, True, 0, 0.0, False,
        )
        feat = fm.FeatureExtrusion2(*args)
        if feat is None:
            return {"error": "FeatureExtrusion2 returned None (cam)"}
        doc.ForceRebuild3(False)
        # Verify a real body materialized before saving.
        pdoc = typed(raw_doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(0, True)
        if not bodies:
            return {"error": "cam extrude produced no body"}
        save_as = str(Path(t1._results_tmp(), f"t2_{name}_{os.getpid()}.SLDPRT"))
        err = doc.SaveAs3(save_as, 0, 0)
        if (int(err) if err is not None else 0) != 0:
            return {"error": f"cam SaveAs3 returned {err}"}
        return {"path": save_as}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"cam handroll raised: {exc!r}"}


def _leg_cam_follower(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "cam_follower", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum("swMateCAMFOLLOWER")
    r["enum_resolved"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    cam = _build_cam_handrolled(sw, mod, "cam")
    follower = _build("follower", _follower_spec("follower"))
    if "error" in cam or "error" in follower:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = cam.get("error") or follower.get("error")
        return r
    ctx = _place_pair(sw, mod, cam, follower)
    if "error" in ctx:
        r["status"] = ctx["error"]
        return r
    asm = ctx["asm"]
    cam_face = _first_nonplanar_face(ctx["a"], mod)
    follower_face = _first_cyl_face(ctx["b"], mod)
    r["entities_found"] = {"cam_nonplanar_face": cam_face is not None,
                           "follower_cyl_face": follower_face is not None}
    if cam_face is None or follower_face is None:
        r["status"] = "ENTITY_RESOLUTION_FAILED"
        return r
    try:
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            r["status"] = "CREATEMATEDATA_NONE"
            return r
        bound = _qi_first(md, _CAMFOLLOWER_IFACE, mod)
        if bound is None:
            r["status"] = "NO_TYPED_IFACE"
            return r
        iface_name, ti = bound
        r["typed_iface"] = iface_name
        r["iface_members"] = [n for n in dir(ti) if not n.startswith("_")]
        # Cam face first, follower second.
        r["entities_set_via"] = _set_entities(ti, [cam_face, follower_face])
        mate = typed_asm.CreateMate(md)
        if mate is None or isinstance(mate, int):
            try:
                mfd = typed_qi(md, "IMateFeatureData", module=mod)
                r["error_status"] = mfd.ErrorStatus
            except Exception:  # noqa: BLE001
                pass
            r["status"] = "CREATEMATE_NONE"
            return r
        ifeat = typed(mate, "IFeature", module=mod)
        r["feature_type"] = ifeat.GetTypeName2()
        ec = ifeat.GetErrorCode2()
        r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        asm_path = str(Path(t1._results_tmp(), f"cf_asm_{os.getpid()}.SLDASM"))
        save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        if int(save_ok) != 0:
            r["status"] = "SAVE_FAILED"
            return r
        # No scalar — GREEN = the mate persists with its MateAlignment readable.
        rb = _read_back(sw, mod, asm_path, iface_name, ("MateAlignment",))
        r["persist"] = rb
        r["status"] = "SOLVED_PERSISTED" if "read_back" in rb else "SOLVED_READBACK_UNVERIFIED"
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_tier2_rack_cam", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["legs"]["rack_pinion"] = _leg_rack_pinion(sw, mod)
        print(f"[t2] rack_pinion -> {result['legs']['rack_pinion'].get('status')}")
        result["legs"]["cam_follower"] = _leg_cam_follower(sw, mod)
        print(f"[t2] cam_follower -> {result['legs']['cam_follower'].get('status')}")
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"
    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
