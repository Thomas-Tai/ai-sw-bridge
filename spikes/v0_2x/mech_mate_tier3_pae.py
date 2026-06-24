"""Tier-3 PRODUCTION PAE — slot + hinge through create_mate.

Exercises the ACTUAL production handler assembly.handlers.create_mate (not the
de-risk spike's inline COM) with the new W48 vocab — the slot's symmetric a/b +
Constraint, and the hinge's compound concentric_faces/coincident_faces dispatch
through _create_hinge_mate (role-keyed SetEntitiesToMate) + the new
``planar_normal`` resolver entity_ref — then save -> reopen and verify EFFECT:

  slot:  {type:"slot", a:{is_cylinder}, b:{is_cylinder}, constraint:"centered"}
         -> reopened MateSlot, Constraint==1 (swSlotMateConstraintOption_Centered).
  hinge: {type:"hinge", concentric_faces:[{is_cylinder}x2],
         coincident_faces:[{planar_normal:[0,0,1]},{planar_normal:[0,0,-1]}]}
         -> reopened MateHinge persists (GetErrorCode2 clean, MateAlignment read).

Fixtures use the production builder (the slotted plate via cut_extrude_two_
direction, two cylinders for the hinge). Reuses the Tier-1/2/3 spike helpers.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_tier3_pae.py
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
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_tier2_rack_cam as t2  # noqa: E402
import mech_mate_tier3_slot_hinge as t3  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_tier3_pae.json"


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


def _slot_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "slot", "ok": False}
    plate = t3._build("slotplate", t3._slot_plate_spec("slotplate"))
    pin = t3._build("pin", t3._pin_spec("pin"))
    if "error" in plate or "error" in pin:
        r["error"] = plate.get("error") or pin.get("error")
        return r
    ctx = _place(
        sw, mod, [("plate", plate["path"], [0, 0, 0]), ("pin", pin["path"], [0, 0, 40])]
    )
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    spec = {
        "type": "slot",
        "a": {"component": "plate", "face_ref": {"is_cylinder": True}},
        "b": {"component": "pin", "face_ref": {"is_cylinder": True}},
        "constraint": "centered",
    }
    mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
    r["create_mate_error"] = err
    if mate is None:
        r["error"] = f"create_mate None: {err}"
        return r
    r["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()
    asm_path = str(Path(t1._results_tmp(), f"slot_pae_{os.getpid()}.SLDASM"))
    if int(typed(ctx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)) != 0:
        r["error"] = "SAVE_FAILED"
        return r
    rb = t2._read_back(
        sw, mod, asm_path, "ISlotMateFeatureData", ("Constraint", "MateAlignment")
    )
    r["persist"] = rb
    vals = rb.get("read_back", {})
    r["ok"] = "Slot" in rb.get("mate_feature_type", "") and vals.get("Constraint") == 1
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _hinge_leg(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "hinge", "ok": False}
    a = t1._build_shaft("hingeA")
    b = t1._build_shaft("hingeB")
    if "error" in a or "error" in b:
        r["error"] = a.get("error") or b.get("error")
        return r
    ctx = _place(sw, mod, [("a", a["path"], [0, 0, 0]), ("b", b["path"], [0, 0, 40])])
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    spec = {
        "type": "hinge",
        "concentric_faces": [
            {"component": "a", "face_ref": {"is_cylinder": True}},
            {"component": "b", "face_ref": {"is_cylinder": True}},
        ],
        "coincident_faces": [
            {"component": "a", "face_ref": {"planar_normal": [0, 0, 1]}},
            {"component": "b", "face_ref": {"planar_normal": [0, 0, -1]}},
        ],
    }
    mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
    r["create_mate_error"] = err
    if mate is None:
        r["error"] = f"create_mate None: {err}"
        return r
    ifeat = typed(mate, "IFeature", module=mod)
    r["feature_type"] = ifeat.GetTypeName2()
    ec = ifeat.GetErrorCode2()
    r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
    asm_path = str(Path(t1._results_tmp(), f"hinge_pae_{os.getpid()}.SLDASM"))
    if int(typed(ctx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)) != 0:
        r["error"] = "SAVE_FAILED"
        return r
    rb = t2._read_back(
        sw,
        mod,
        asm_path,
        "IHingeMateFeatureData",
        ("Angle", "MaxVal", "MinVal", "MateAlignment"),
    )
    r["persist"] = rb
    r["ok"] = "Hinge" in rb.get("mate_feature_type", "") and "read_back" in rb
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_tier3_pae", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["legs"]["slot"] = _slot_leg(sw, mod)
        print(f"[t3pae] slot -> {result['legs']['slot'].get('verdict')}")
        result["legs"]["hinge"] = _hinge_leg(sw, mod)
        print(f"[t3pae] hinge -> {result['legs']['hinge'].get('verdict')}")
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
