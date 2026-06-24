"""W49 PRODUCTION PAE — Motion Audit through motion_audit.motion_sweep.

Exercises the ACTUAL production capability (assembly built by production
builder/handlers, swept by production motion_sweep) and verifies the EFFECT:

  DISTANCE leg — two 40mm cubes on a distance-mate driver. Sweep 0..50mm; the
    interference VOLUME must track 1600*(40-d) (collision at small distance,
    clear by 40mm), the clearance must open up once clear, and the driver value
    must be RESTORED at the end (net non-destructive).
  ANGLE leg — cube on a coincident pivot + an angle-mate driver. Sweep 0..90deg;
    the production pipeline must drive + observe + restore cleanly for a
    ROTATIONAL driver (the rotation itself is proven exact in
    kinematic_angle_confirm).

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/motion_audit_pae.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _find_assembly_template,
    _build_part_spec,
)
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402
from ai_sw_bridge.motion_audit import motion_sweep  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "motion_audit_pae.json"


def _cube_spec(name: str) -> dict[str, Any]:
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
    save_as = str(Path(t1._results_tmp(), f"ma_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(_cube_spec(name), save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _name2(comp: Any, mod: Any) -> str | None:
    try:
        ic = typed(comp, "IComponent2", module=mod)
        nm = ic.Name2
        return nm() if callable(nm) else str(nm)
    except Exception:  # noqa: BLE001
        return None


def _assemble(
    sw: Any, mod: Any, pa: dict, pb: dict, xyz_b: list[float]
) -> dict[str, Any]:
    asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    comps = [
        {"id": "a", "part": pa["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": pb["path"], "transform": {"xyz_mm": xyz_b}},
    ]
    placed, err = place_components(sw, asm, comps, mod=mod)
    if err is not None:
        return {"error": f"PLACE_FAILED:{err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return {"asm": asm, "placed": placed}


def _distance_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "distance", "ok": False}
    a, b = _build("distA"), _build("distB")
    if "error" in a or "error" in b:
        r["error"] = a.get("error") or b.get("error")
        return r
    ctx = _assemble(sw, mod, a, b, [60, 0, 0])
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    spec = {
        "type": "distance",
        "alignment": "aligned",
        "value_mm": 30.0,
        "a": {"component": "a", "face_ref": {"planar_normal": [-1, 0, 0]}},
        "b": {"component": "b", "face_ref": {"planar_normal": [-1, 0, 0]}},
    }
    mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
    if mate is None:
        r["error"] = f"driver mate failed: {err}"
        return r
    typed(mate, "IFeature", module=mod).Name = "DriveDist"
    pair = (_name2(ctx["placed"]["a"], mod), _name2(ctx["placed"]["b"], mod))
    sweep = motion_sweep(
        ctx["asm"],
        mate_name="DriveDist",
        kind="distance",
        start=0.0,
        stop=50.0,
        steps=6,
        clearance_pair=pair,
        mod=mod,
    )
    r["sweep"] = sweep
    prof = sweep.get("profile", [])
    summ = sweep.get("summary", {})
    vols = {p["position"]: p["interference_volume_mm3"] for p in prof}
    r["ok"] = (
        sweep.get("ok") is True
        and sweep.get("restored") is True
        and summ.get("collision_free") is False
        and summ.get("first_collision_position") == 0.0
        and abs((vols.get(0.0) or 0) - 64000.0) < 50.0
        and abs((vols.get(20.0) or 0) - 32000.0) < 50.0
        and (vols.get(40.0) or 0) < 50.0
        and [40.0, 50.0] in summ.get("clear_ranges", [])
    )
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _angle_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "angle", "ok": False}
    a, b = _build("angA"), _build("angB")
    if "error" in a or "error" in b:
        r["error"] = a.get("error") or b.get("error")
        return r
    ctx = _assemble(sw, mod, a, b, [0, 0, 60])
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    coin = {
        "type": "coincident",
        "alignment": "closest",
        "a": {"component": "a", "face_ref": {"planar_normal": [0, 0, 1]}},
        "b": {"component": "b", "face_ref": {"planar_normal": [0, 0, -1]}},
    }
    m1, e1 = create_mate(ctx["asm"], ctx["placed"], coin, mod=mod)
    if m1 is None:
        r["error"] = f"coincident failed: {e1}"
        return r
    ang = {
        "type": "angle",
        "value_deg": 0.0,
        "a": {"component": "a", "face_ref": {"planar_normal": [1, 0, 0]}},
        "b": {"component": "b", "face_ref": {"planar_normal": [1, 0, 0]}},
    }
    m2, e2 = create_mate(ctx["asm"], ctx["placed"], ang, mod=mod)
    if m2 is None:
        r["error"] = f"angle mate failed: {e2}"
        return r
    typed(m2, "IFeature", module=mod).Name = "DriveAngle"
    sweep = motion_sweep(
        ctx["asm"],
        mate_name="DriveAngle",
        kind="angle",
        start=0.0,
        stop=90.0,
        steps=4,
        mod=mod,
    )
    r["sweep"] = sweep
    prof = sweep.get("profile", [])
    r["ok"] = (
        sweep.get("ok") is True
        and sweep.get("restored") is True
        and len(prof) == 4
        and all(not p["drive_route"].startswith("FAIL") for p in prof)
    )
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "motion_audit_pae", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["legs"]["distance"] = _distance_leg(sw, mod)
        print(f"[ma] distance -> {result['legs']['distance'].get('verdict')}")
        result["legs"]["angle"] = _angle_leg(sw, mod)
        print(f"[ma] angle -> {result['legs']['angle'].get('verdict')}")
        result["overall"] = (
            "PASS"
            if all(result["legs"][k].get("ok") for k in result["legs"])
            else "FAIL"
        )
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"
        result["overall"] = "FAIL"
    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
