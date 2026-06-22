"""W75 Advanced Mates VANGUARD PROBE — symmetric + profile_center.

Cracks the IMateFeatureData parameter mapping for the two genuinely-unopened
advanced mate types (MATE_TYPES has neither; width/slot/gear/etc. already ship).

  symmetric (swMateSYMMETRIC=8) -> ISymmetricMateFeatureData
    props: EntitiesToMate (array of 2) + SymmetryPlane (1 plane/face) + MateAlignment
  profile_center (swMatePROFILECENTER=24) -> IProfileCenterMateFeatureData
    props: EntitiesToMate (array of 2 faces) + FlipDimension/LockRotation/
           OffsetDistance/MateAlignment

Pipeline (the shipped path): CreateMateData(enum) -> typed_qi(I<Type>...) ->
set props -> CreateMate -> IFeature.GetTypeName2 contains 'Mate'. Witness:
CreateMate returns a Feature AND the mate survives save->close->reopen.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_advanced_mates_probe.py
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
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _build_part_spec,
    _find_assembly_template,
)
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "advanced_mates_probe.json"

results: dict[str, Any] = {"probe": "w75_advanced_mates", "legs": {}}


def _cube(name: str, mm: float = 20.0) -> dict[str, Any]:
    return {
        "schema_version": 1, "name": name,
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "width": mm, "height": mm},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": mm},
        ],
    }


def _plate(name: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "name": name,
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "width": 40.0, "height": 30.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 5.0},
        ],
    }


def _build(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    save_as = str(Path(t1._results_tmp(), f"w75_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(spec, save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _body_of(comp: Any) -> Any | None:
    try:
        bodies = comp.GetBodies(0)
        if not bodies:
            return None
        return bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    except Exception:
        return None


def _planar_faces(comp: Any, mod: Any) -> list[tuple[Any, tuple]]:
    """Return [(face, plane_params)] for each PLANAR face of the comp's body.
    plane_params = (nx,ny,nz, px,py,pz)."""
    body = _body_of(comp)
    if body is None:
        return []
    out = []
    try:
        faces = body.GetFaces() or ()
    except Exception:
        return []
    for f in faces:
        try:
            iface = typed(f, "IFace2", module=mod)
            surf = typed(iface.GetSurface(), "ISurface", module=mod)
            isplane = surf.IsPlane
            isplane = isplane() if callable(isplane) else isplane
            if not isplane:
                continue
            pp = surf.PlaneParams
            pp = pp() if callable(pp) else pp
            out.append((f, tuple(pp)))
        except Exception:
            continue
    return out


def _face_normal_x(comp: Any, mod: Any) -> Any | None:
    """First planar face whose normal is ~±X (for symmetric about a YZ plane)."""
    for f, pp in _planar_faces(comp, mod):
        if abs(pp[0]) > 0.9:
            return f
    pf = _planar_faces(comp, mod)
    return pf[0][0] if pf else None


def _first_planar_face(comp: Any, mod: Any) -> Any | None:
    pf = _planar_faces(comp, mod)
    return pf[0][0] if pf else None


def _new_asm(sw: Any) -> Any | None:
    tmpl = _find_assembly_template()
    if tmpl is None:
        return None
    return sw.NewDocument(tmpl, 0, 0.1, 0.1)


def _place(sw: Any, mod: Any, comps: list[dict]) -> tuple[Any, dict, str | None]:
    asm = _new_asm(sw)
    if asm is None:
        return None, {}, "NO_ASM_TEMPLATE"
    placed, err = place_components(sw, asm, comps, mod=mod)
    if err is not None:
        return asm, {}, f"PLACE_FAILED: {err}"
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return asm, placed, None


def _save(asm: Any, mod: Any, path: str) -> bool:
    try:
        typed(asm, "IModelDoc2", module=mod).SaveAs3(path, 0, 0)
        return True
    except Exception:
        return False


def _reopen_mate_types(sw: Any, mod: Any, path: str) -> list[str]:
    """Reopen the assembly and return the type names of all Mate features."""
    out: list[str] = []
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)
        ro = tsw.OpenDoc6(path, 2, 0, "", 0, 0)
        rdoc = ro[0] if isinstance(ro, tuple) else ro
        if rdoc is None:
            return out
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        for f in rdoc.FeatureManager.GetFeatures(False) or ():
            try:
                tf = typed(f, "IFeature", module=mod)
                tname = tf.GetTypeName2()
                if "Mate" in tname:
                    out.append(tname)
            except Exception:
                continue
    except Exception:
        pass
    return out


def _leg_symmetric(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "symmetric", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum("swMateSYMMETRIC")
    r["enum"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    base = _build("sym_base", _cube("sym_base", 20.0))
    a = _build("sym_a", _cube("sym_a", 10.0))
    b = _build("sym_b", _cube("sym_b", 10.0))
    for x in (base, a, b):
        if "error" in x:
            r["status"] = "FIXTURE_FAILED"
            r["error"] = x["error"]
            return r
    comps = [
        {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "a", "part": a["path"], "transform": {"xyz_mm": [-50, 0, 0]}},
        {"id": "b", "part": b["path"], "transform": {"xyz_mm": [50, 30, 0]}},
    ]
    asm, placed, err = _place(sw, mod, comps)
    if err:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = err
        return r
    # CRACKED (W75): SymmetryPlane must be a reference DATUM PLANE (RefPlane
    # feature), NOT a component planar face (a face -> CreateMate None). The
    # assembly's "Right Plane" feature works passed directly.
    try:
        plane = asm.FeatureByName("Right Plane")
    except Exception:
        plane = None
    ea = _face_normal_x(placed["a"], mod)
    eb = _face_normal_x(placed["b"], mod)
    if not (plane and ea and eb):
        r["status"] = "ENTITY_FAILED"
        r["error"] = f"plane={plane!r} ea={ea!r} eb={eb!r}"
        return r
    try:
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            r["status"] = "CREATEMATEDATA_NONE"
            return r
        ti = typed_qi(md, "ISymmetricMateFeatureData", module=mod)
        ti.SymmetryPlane = plane
        ti.EntitiesToMate = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (ea, eb))
        try:
            ti.MateAlignment = 0  # closest/aligned default
        except Exception:
            pass
        mate = typed_asm.CreateMate(md)
    except Exception as exc:
        r["status"] = "FIRE_RAISED"
        r["error"] = f"{type(exc).__name__}: {exc}"
        return r
    if mate is None or isinstance(mate, int):
        try:
            es = typed_qi(md, "IMateFeatureData", module=mod).ErrorStatus
        except Exception:
            es = "?"
        r["status"] = "CREATEMATE_NONE"
        r["error"] = f"ErrorStatus={es}"
        return r
    try:
        r["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()
    except Exception:
        r["feature_type"] = "?"
    path = str(Path(t1._results_tmp(), f"w75_symmetric_{os.getpid()}.SLDASM"))
    r["saved"] = _save(asm, mod, path)
    r["reopen_mates"] = _reopen_mate_types(sw, mod, path) if r["saved"] else []
    r["status"] = "GREEN" if (r.get("feature_type", "").find("Mate") >= 0
                              and r["reopen_mates"]) else "PARTIAL"
    return r


def _leg_profile_center(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "profile_center", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum("swMatePROFILECENTER")
    r["enum"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    a = _build("pc_a", _plate("pc_a"))
    b = _build("pc_b", _plate("pc_b"))
    for x in (a, b):
        if "error" in x:
            r["status"] = "FIXTURE_FAILED"
            r["error"] = x["error"]
            return r
    comps = [
        {"id": "a", "part": a["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": b["path"], "transform": {"xyz_mm": [0, 0, 40]}},
    ]
    asm, placed, err = _place(sw, mod, comps)
    if err:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = err
        return r
    fa = _first_planar_face(placed["a"], mod)
    fb = _first_planar_face(placed["b"], mod)
    if not (fa and fb):
        r["status"] = "ENTITY_FAILED"
        r["error"] = f"fa={fa!r} fb={fb!r}"
        return r
    try:
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            r["status"] = "CREATEMATEDATA_NONE"
            return r
        ti = typed_qi(md, "IProfileCenterMateFeatureData", module=mod)
        ti.EntitiesToMate = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (fa, fb))
        for prop, val in (("LockRotation", False), ("FlipDimension", False),
                          ("OffsetDistance", 0.0)):
            try:
                setattr(ti, prop, val)
            except Exception:
                pass
        try:
            ti.MateAlignment = 0
        except Exception:
            pass
        mate = typed_asm.CreateMate(md)
    except Exception as exc:
        r["status"] = "FIRE_RAISED"
        r["error"] = f"{type(exc).__name__}: {exc}"
        return r
    if mate is None or isinstance(mate, int):
        try:
            es = typed_qi(md, "IMateFeatureData", module=mod).ErrorStatus
        except Exception:
            es = "?"
        r["status"] = "CREATEMATE_NONE"
        r["error"] = f"ErrorStatus={es}"
        return r
    try:
        r["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()
    except Exception:
        r["feature_type"] = "?"
    path = str(Path(t1._results_tmp(), f"w75_profilecenter_{os.getpid()}.SLDASM"))
    r["saved"] = _save(asm, mod, path)
    r["reopen_mates"] = _reopen_mate_types(sw, mod, path) if r["saved"] else []
    r["status"] = "GREEN" if (r.get("feature_type", "").find("Mate") >= 0
                              and r["reopen_mates"]) else "PARTIAL"
    return r


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        for leg_fn in (_leg_symmetric, _leg_profile_center):
            try:
                res = leg_fn(sw, mod)
            except Exception as exc:
                res = {"status": "UNEXPECTED", "error": f"{type(exc).__name__}: {exc}",
                       "tb": traceback.format_exc()}
            results["legs"][res.get("leg", leg_fn.__name__)] = res
            print(f"  [{res.get('status')}] {res.get('leg')}: "
                  f"feat={res.get('feature_type')} reopen={res.get('reopen_mates')} "
                  f"err={res.get('error')}")
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    verdict = "GREEN" if all(
        results["legs"].get(k, {}).get("status") == "GREEN"
        for k in ("symmetric", "profile_center")) else "PARTIAL"
    results["verdict"] = verdict
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {verdict}  (wrote {_OUT})")
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
