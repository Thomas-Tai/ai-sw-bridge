"""S1 confirm — ANGLE driver for the Motion Audit epoch (W49).

The distance driver is proven exact (kinematic_motion_derisk: interference volume
tracked 1600*(40-d) to the mm^3). This confirms the ROTATIONAL twin: driving an
ANGLE mate's value via IModelDoc2.Parameter (in RADIANS) + rebuild actually
ROTATES the mate-constrained component out-of-process — the driver the
hinge/gear/cam mates need.

Fixture: two 40mm cubes. A fixed; B sits on A via a COINCIDENT mate (top/bottom
faces, the planar pivot) and an ANGLE mate between their +X faces is the driver
(rotation about Z). Sweep the angle 0..90deg; at each step drive the angle
parameter, rebuild, and read B's IComponent2 Transform2 rotation.

VERIFY-THE-EFFECT: the component's extracted rotation about Z must TRACK the
driven angle (0->0, 30->30, 60->60, 90->90, monotone). A frozen rotation = the
angle setter no-ops.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/kinematic_angle_confirm.py
"""
from __future__ import annotations

import json
import math
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _find_assembly_template,
    _build_part_spec,
)
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "kinematic_angle_confirm.json"

_SWEEP_DEG = [0.0, 30.0, 60.0, 90.0]


def _cube_spec(name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "width": 40.0, "height": 40.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 40.0},
        ],
    }


def _build(name: str) -> dict[str, Any]:
    save_as = str(Path(t1._results_tmp(), f"kinang_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(_cube_spec(name), save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _comp_rot_z_deg(comp: Any, mod: Any) -> dict[str, Any]:
    """Extract candidate Z-rotation (deg) from a component's Transform2 array.

    SW IMathTransform.ArrayData = [r0..r8 rotation, tx,ty,tz, scale, 0,0,0].
    For a Z-rotation both atan2(arr[3],arr[0]) and atan2(arr[1],arr[0]) are
    reported (row- vs column-major); the CONFIRM only needs one to track."""
    try:
        ic = typed(comp, "IComponent2", module=mod)
        xform = ic.Transform2
        arr = xform.ArrayData
        arr = list(arr() if callable(arr) else arr)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{exc!r}"}
    if len(arr) < 4:
        return {"error": f"short array len={len(arr)}"}
    return {
        "rotZ_a_deg": round(math.degrees(math.atan2(arr[3], arr[0])), 3),
        "rotZ_b_deg": round(math.degrees(math.atan2(arr[1], arr[0])), 3),
        "r00": round(arr[0], 5),
    }


def _drive_angle(asm_doc: Any, mate_name: str, value_rad: float, mod: Any) -> str:
    try:
        dim = asm_doc.Parameter(f"D1@{mate_name}")
        if dim is not None:
            dim.SystemValue = value_rad
            typed(asm_doc, "IModelDoc2", module=mod).EditRebuild3()
            return "parameter"
    except Exception:  # noqa: BLE001
        pass
    return "FAIL"


def main() -> int:
    out: dict[str, Any] = {"spike_id": "kinematic_angle_confirm", "status": "UNKNOWN"}
    sw = None
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass

        a = _build("cubeA")
        b = _build("cubeB")
        if "error" in a or "error" in b:
            out["status"] = "FIXTURE_FAILED"
            out["error"] = a.get("error") or b.get("error")
            return _finish(out)
        asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
        if asm is None:
            out["status"] = "ASM_NEWDOC_NONE"
            return _finish(out)
        components = [
            {"id": "a", "part": a["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": b["path"], "transform": {"xyz_mm": [0, 0, 60]}},
        ]
        placed, err = place_components(sw, asm, components, mod=mod)
        if err is not None:
            out["status"] = f"PLACE_FAILED:{err}"
            return _finish(out)
        typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)

        # Pivot: B's bottom (-Z) coincident on A's top (+Z) → shared Z=40 plane.
        coin = {
            "type": "coincident", "alignment": "closest",
            "a": {"component": "a", "face_ref": {"planar_normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"planar_normal": [0, 0, -1]}},
        }
        m1, e1 = create_mate(asm, placed, coin, mod=mod)
        out["coincident_ok"] = m1 is not None
        if m1 is None:
            out["status"] = f"COINCIDENT_FAILED:{e1}"
            return _finish(out)

        # Driver: ANGLE between the two +X faces → rotation about Z.
        ang = {
            "type": "angle", "value_deg": 0.0,
            "a": {"component": "a", "face_ref": {"planar_normal": [1, 0, 0]}},
            "b": {"component": "b", "face_ref": {"planar_normal": [1, 0, 0]}},
        }
        m2, e2 = create_mate(asm, placed, ang, mod=mod)
        out["angle_mate_ok"] = m2 is not None
        out["angle_mate_error"] = e2
        if m2 is None:
            out["status"] = f"ANGLE_MATE_FAILED:{e2}"
            return _finish(out)
        try:
            typed(m2, "IFeature", module=mod).Name = "DriveAngle"
        except Exception:  # noqa: BLE001
            pass

        sweep: list[dict[str, Any]] = []
        for deg in _SWEEP_DEG:
            route = _drive_angle(asm, "DriveAngle", math.radians(deg), mod)
            rot = _comp_rot_z_deg(placed["b"], mod)
            sweep.append({"driven_deg": deg, "drive_route": route, **rot})
            print(f"[kinang] {deg:>4}deg via {route} -> rotZ_a={rot.get('rotZ_a_deg')} "
                  f"rotZ_b={rot.get('rotZ_b_deg')}")
        out["sweep"] = sweep

        # VERIFY: one of the two rotation candidates must track the driven angle
        # (monotone + magnitude within 5deg at each step vs the 0-step baseline).
        def _tracks(key: str) -> bool:
            base = sweep[0].get(key)
            if base is None or isinstance(base, str):
                return False
            deltas = []
            for s in sweep:
                v = s.get(key)
                if v is None or isinstance(v, str):
                    return False
                deltas.append(abs(v - base))
            # magnitude tracks driven angle within 5deg, strictly increasing
            ok_mag = all(abs(deltas[i] - sweep[i]["driven_deg"]) <= 5.0
                         for i in range(len(sweep)))
            ok_mono = all(deltas[i] <= deltas[i + 1] + 1.0 for i in range(len(deltas) - 1))
            return ok_mag and ok_mono

        tracks_a = _tracks("rotZ_a_deg")
        tracks_b = _tracks("rotZ_b_deg")
        out["rotation_tracks_driven_angle"] = bool(tracks_a or tracks_b)
        out["tracking_candidate"] = "rotZ_a_deg" if tracks_a else ("rotZ_b_deg" if tracks_b else None)
        out["status"] = "GREEN" if (tracks_a or tracks_b) else "FROZEN_NO_DRIVE"
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        out["status"] = "EXCEPTION"
        out["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        if sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:  # noqa: BLE001
                pass
    return _finish(out)


def _finish(out: dict) -> int:
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[kinang] verdict: {out.get('status')} -> {_OUT}")
    return 0 if out.get("status") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
