"""S1 DE-RISK — Dynamic Kinematic Verification epoch (W49).

Static interference detection is SHIPPED (W27, observe_interference). The new
epoch's open question is the DRIVE: can we parametrically move a mate-constrained
component through its degree of freedom OUT-OF-PROCESS and watch interference
respond — i.e. collision-IN-MOTION, not just a frozen snapshot?

This spike de-risks that single unknown. It composes PROVEN parts:
  * a 1-DOF slider fixture — two 40mm cubes, one fixed, one positioned ONLY by a
    DISTANCE mate (the driver). The distance value IS the kinematic coordinate.
  * the W27 interference reader, run at each swept position.

LEG 1 — PARAMETRIC SWEEP (the likely-GREEN path). Drive the distance mate's value
  across 0..50mm; at each step rebuild + read interference. VERIFY-THE-EFFECT: the
  interference VOLUME must track the kinematic overlap — for two coincident-faced
  40-cubes that is 1600*(40-d) mm^3 (64000 at d=0, 0 at d>=40), monotonic. A
  responding volume proves the drive+detect loop; a frozen volume = the value
  setter no-ops (a wall, like the W46 screw pitch).
  Two drive routes are tried and the working one recorded (O1: characterize, don't
  guess): (1) the mate DIMENSION via IModelDoc2.Parameter, (2) GetDefinition ->
  IDistanceMateFeatureData.Distance -> ModifyDefinition.

LEG 2 — DRAG PROBE (characterize the interactive route). Dump IAssemblyDoc members
  matching Drag/Move/Motion from the typelib and best-effort probe a drag — to see
  whether the interactive kinematic-drag API is reachable headless or a wall.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/kinematic_motion_derisk.py
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _find_assembly_template,
    _build_part_spec,
)
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402
from ai_sw_bridge.observe_interference import read_interference  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "kinematic_motion_derisk.json"

_SWEEP_MM = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]


def _cube_spec(name: str) -> dict[str, Any]:
    """A 40mm cube centered on the origin in X/Y (CenterRectangle on Front,
    extruded 40mm) — symmetric so two of them fully overlap at distance 0."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "center": {"x": 0.0, "y": 0.0},
                "width": 40.0,
                "height": 40.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 40.0},
        ],
    }


def _build(name: str) -> dict[str, Any]:
    save_as = str(Path(t1._results_tmp(), f"kin_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(_cube_spec(name), save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _drive_distance(
    asm_doc: Any, mate_feat: Any, mate_name: str, value_m: float, mod: Any
) -> str:
    """Set the distance mate's driving value to value_m, rebuild. Returns the
    route that took ('parameter' / 'modifydefinition') or 'FAIL:...'."""
    # Route 1: the mate DIMENSION (the classic parametric drive).
    try:
        dim = asm_doc.Parameter(f"D1@{mate_name}")
        if dim is not None:
            dim.SystemValue = value_m
            typed(asm_doc, "IModelDoc2", module=mod).EditRebuild3()
            return "parameter"
    except Exception:  # noqa: BLE001
        pass
    # Route 2: GetDefinition -> IDistanceMateFeatureData.Distance -> ModifyDefinition.
    try:
        ifeat = typed(mate_feat, "IFeature", module=mod)
        defn = ifeat.GetDefinition()
        ti = typed_qi(defn, "IDistanceMateFeatureData", module=mod)
        ti.Distance = value_m
        ifeat.ModifyDefinition(defn, asm_doc, None)
        typed(asm_doc, "IModelDoc2", module=mod).ForceRebuild3(False)
        return "modifydefinition"
    except Exception as exc:  # noqa: BLE001
        return f"FAIL:{exc!r}"


def _leg1_parametric_sweep(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "parametric_sweep", "status": "UNKNOWN"}
    a = _build("cubeA")
    b = _build("cubeB")
    if "error" in a or "error" in b:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = a.get("error") or b.get("error")
        return r
    asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
    if asm is None:
        r["status"] = "ASM_NEWDOC_NONE"
        return r
    components = [
        {"id": "a", "part": a["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": b["path"], "transform": {"xyz_mm": [60, 0, 0]}},
    ]
    placed, err = place_components(sw, asm, components, mod=mod)
    if err is not None:
        r["status"] = f"PLACE_FAILED:{err}"
        return r
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)

    # The driver: a distance mate between the two -X faces (signed planar_normal
    # so the SAME face is picked on both — the W48 resolver vocab). At distance d
    # the cubes overlap by (40-d) along X.
    spec = {
        "type": "distance",
        "alignment": "aligned",
        "value_mm": 30.0,
        "a": {"component": "a", "face_ref": {"planar_normal": [-1, 0, 0]}},
        "b": {"component": "b", "face_ref": {"planar_normal": [-1, 0, 0]}},
    }
    mate, mate_err = create_mate(asm, placed, spec, mod=mod)
    r["create_mate_error"] = mate_err
    if mate is None:
        r["status"] = f"DRIVER_MATE_FAILED:{mate_err}"
        return r
    try:
        typed(mate, "IFeature", module=mod).Name = "DriveDist"
    except Exception:  # noqa: BLE001
        pass

    sweep: list[dict[str, Any]] = []
    for d_mm in _SWEEP_MM:
        route = _drive_distance(asm, mate, "DriveDist", d_mm / 1000.0, mod)
        inter = read_interference(asm, mod)
        vol = 0.0
        for it in inter.get("interferences", []) or []:
            vol += float(it.get("interference_volume_mm3", 0.0) or 0.0)
        sweep.append(
            {
                "distance_mm": d_mm,
                "drive_route": route,
                "interference_count": inter.get("interference_count", 0),
                "interference_volume_mm3": round(vol, 1),
                "expected_overlap_mm3": round(1600.0 * max(0.0, 40.0 - d_mm), 1),
            }
        )
        print(
            f"[kin] d={d_mm:>4} via {route:<16} -> count={sweep[-1]['interference_count']} "
            f"vol={sweep[-1]['interference_volume_mm3']} (exp {sweep[-1]['expected_overlap_mm3']})"
        )
    r["sweep"] = sweep
    r["drive_routes_used"] = sorted({s["drive_route"] for s in sweep})

    # VERIFY-THE-EFFECT: volume must RESPOND to the driven position — high near
    # d=0, ~0 at d>=40, strictly decreasing. A frozen volume = the setter no-ops.
    vols = [s["interference_volume_mm3"] for s in sweep]
    v_at_0 = vols[0]
    v_at_40plus = vols[-2] + vols[-1]  # d=40 and d=50 both ~0
    responds = (
        v_at_0 > 20000.0  # real overlap at d=0
        and v_at_40plus < 1000.0  # cleared by d>=40
        and all(
            vols[i] >= vols[i + 1] - 50.0  # monotone non-increasing (eps)
            for i in range(len(vols) - 1)
        )
    )
    r["volume_responds_to_position"] = bool(responds)
    r["status"] = "GREEN" if responds else "FROZEN_NO_DRIVE"
    return r


def _leg2_drag_probe(sw: Any, mod: Any) -> dict[str, Any]:
    """O1 introspection: what motion/drive members does IAssemblyDoc expose, and
    is any interactive drag reachable headless? Characterize, do not bet."""
    r: dict[str, Any] = {"leg": "drag_probe", "status": "UNKNOWN"}
    try:
        import glob

        path = None
        for p in (r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",):
            if Path(p).exists():
                path = p
                break
        members: list[str] = []
        if path:
            tlb = pythoncom.LoadTypeLib(path)
            for i in range(tlb.GetTypeInfoCount()):
                try:
                    if tlb.GetDocumentation(i)[0] != "IAssemblyDoc":
                        continue
                except Exception:  # noqa: BLE001
                    continue
                ti = tlb.GetTypeInfo(i)
                ta = ti.GetTypeAttr()
                for fi in range(ta.cFuncs):
                    fd = ti.GetFuncDesc(fi)
                    nm = ti.GetNames(fd.memid)
                    if nm:
                        members.append(nm[0])
        hits = sorted(
            {
                m
                for m in members
                if any(k in m for k in ("Drag", "Move", "Motion", "GetDrag"))
            }
        )
        r["assembly_drive_members"] = hits
        r["status"] = "DUMPED"
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "kinematic_motion_derisk", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["legs"]["drag_probe"] = _leg2_drag_probe(sw, mod)
        print(
            f"[kin] drag_probe -> {result['legs']['drag_probe'].get('assembly_drive_members')}"
        )
        result["legs"]["parametric_sweep"] = _leg1_parametric_sweep(sw, mod)
        print(
            f"[kin] parametric_sweep -> {result['legs']['parametric_sweep'].get('status')}"
        )
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"
    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    leg1 = result.get("legs", {}).get("parametric_sweep", {})
    return 0 if leg1.get("status") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
