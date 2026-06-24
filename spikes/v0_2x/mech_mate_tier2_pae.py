"""Tier-2 PRODUCTION PAE — rack-pinion + cam-follower through create_mate.

Exercises the ACTUAL production handler assembly.handlers.create_mate (not inline
COM) with the new W47 entity_ref vocabulary (linear_edge / non_planar) + the
asymmetric SetEntitiesToMate path, then save -> reopen and verify the EFFECT:

  rack-pinion: spec {type:"rackpinion", a:{linear_edge}, b:{is_cylinder},
    pitch_diameter_mm:20} -> reopened DiameterType==0 (swPinionPitchDiameter) and
    DiameterVal==0.020 (faithful round-trip).
  cam-follower: spec {type:"camfollower", a:{non_planar}, b:{is_cylinder}} ->
    reopened MateCamTangent persists (MateAlignment readable). No scalar.

The cam fixture is still the hand-rolled ellipse (the declarative
sketch_ellipse->extrude fix is in flight); rack/pinion/follower use the
production builder. Reuses the Tier-2 de-risk spike's helpers verbatim.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_tier2_pae.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_tier2_rack_cam as t2  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_tier2_pae.json"


def _place(sw: Any, mod: Any, specs: list[tuple[str, str, list[float]]]) -> Any:
    asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    components = [
        {"id": cid, "part": path, "transform": {"xyz_mm": xyz}}
        for cid, path, xyz in specs
    ]
    placed, err = place_components(sw, asm, components, mod=mod)
    if err is not None:
        return {"error": f"PLACE_FAILED: {err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return {"asm": asm, "placed": placed}


def _rack_pinion_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "rackpinion", "ok": False}
    rack = t2._build("rack", t2._rack_spec("rack"))
    pinion = t2._build("pinion", t2._pinion_spec("pinion"))
    if "error" in rack or "error" in pinion:
        r["error"] = rack.get("error") or pinion.get("error")
        return r
    ctx = _place(
        sw,
        mod,
        [("rack", rack["path"], [0, 0, 0]), ("pinion", pinion["path"], [60, 0, 0])],
    )
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    spec = {
        "type": "rackpinion",
        "a": {"component": "rack", "face_ref": {"linear_edge": True}},
        "b": {"component": "pinion", "face_ref": {"is_cylinder": True}},
        "pitch_diameter_mm": 20.0,
    }
    mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
    r["create_mate_error"] = err
    if mate is None:
        r["error"] = f"create_mate None: {err}"
        return r
    r["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()
    asm_path = str(Path(t1._results_tmp(), f"rp_pae_{os.getpid()}.SLDASM"))
    if int(typed(ctx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)) != 0:
        r["error"] = "SAVE_FAILED"
        return r
    rb = t2._read_back(
        sw, mod, asm_path, "IRackPinionMateFeatureData", ("DiameterType", "DiameterVal")
    )
    r["persist"] = rb
    vals = rb.get("read_back", {})
    r["ok"] = (
        vals.get("DiameterType") == 0
        and isinstance(vals.get("DiameterVal"), (int, float))
        and abs(vals["DiameterVal"] - 0.020) < 1e-6
    )
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _cam_follower_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "camfollower", "ok": False}
    cam = t2._build_cam_handrolled(sw, mod, "cam")
    follower = t2._build("follower", t2._follower_spec("follower"))
    if "error" in cam or "error" in follower:
        r["error"] = cam.get("error") or follower.get("error")
        return r
    ctx = _place(
        sw,
        mod,
        [("cam", cam["path"], [0, 0, 0]), ("follower", follower["path"], [60, 0, 0])],
    )
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    spec = {
        "type": "camfollower",
        "a": {"component": "cam", "face_ref": {"non_planar": True}},
        "b": {"component": "follower", "face_ref": {"is_cylinder": True}},
    }
    mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
    r["create_mate_error"] = err
    if mate is None:
        r["error"] = f"create_mate None: {err}"
        return r
    r["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()
    asm_path = str(Path(t1._results_tmp(), f"cf_pae_{os.getpid()}.SLDASM"))
    if int(typed(ctx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)) != 0:
        r["error"] = "SAVE_FAILED"
        return r
    rb = t2._read_back(
        sw, mod, asm_path, "ICamFollowerMateFeatureData", ("MateAlignment",)
    )
    r["persist"] = rb
    r["ok"] = "read_back" in rb and "Cam" in rb.get("mate_feature_type", "")
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_tier2_pae", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["legs"]["rackpinion"] = _rack_pinion_leg(sw, mod)
        print(f"[t2pae] rackpinion -> {result['legs']['rackpinion'].get('verdict')}")
        result["legs"]["camfollower"] = _cam_follower_leg(sw, mod)
        print(f"[t2pae] camfollower -> {result['legs']['camfollower'].get('verdict')}")
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
