"""Screw-mate pitch CALIBRATION v2 — concentric-precondition diagnostic strike.

v1 proved the screw pitch clamps to the 1 mm kernel default at CreateMate time
(T0=set, T1=T2=0.001 for every input) via BOTH the pre-create setter AND
ModifyDefinition. Root-cause hypothesis: a screw mate is a COUPLED kinematic
constraint; with no primary axis established the solver falls to a degenerate
1 mm default. Our v1 fixture placed the two shafts with NO concentric mate
aligning their axes.

v2 adds the missing physical precondition and re-runs the exact same matrix:

  1. Place two Ø20 shafts.
  2. PRECONDITION: a CONCENTRIC mate aligning the two cylindrical faces' axes
     (CreateMateData(swMateCONCENTRIC) -> EntitiesToMate -> CreateMate).
  3. Screw mate over the SAME two faces; read RevolutionVal at T0/T1/T2 for
     pitch in {0.002, 0.004, 0.010}.

BRANCHING (per W0 directive):
  * T2 == input for all pitches -> the wall was GEOMETRIC, not COM. Screw ships.
  * T2 clamps to 0.001 regardless -> genuine out-of-process COM limitation; the
    solver refuses parameterization even with a constrained axis. Freeze screw,
    document in DEFERRED.md, ship gear alone.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_screw_calibration_v2.py
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

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_screw_calibration as cal  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_screw_calibration_v2.json"

_SCREW_IFACE = "IScrewMateFeatureData"
_SCREW_DISTANCE_PER_REV = 1
_PITCHES = (0.002, 0.004, 0.010)


def _entities_variant(f1: Any, f2: Any) -> Any:
    return w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (f1, f2))


def _add_concentric(
    typed_asm: Any, mod: Any, conc_enum: int, f1: Any, f2: Any
) -> dict[str, Any]:
    """Add a concentric mate over the two cyl faces (establishes the axis)."""
    out: dict[str, Any] = {}
    cmd = typed_asm.CreateMateData(conc_enum)
    if cmd is None:
        out["error"] = "concentric CreateMateData -> None"
        return out
    # EntitiesToMate lives on the DERIVED per-type interface, not base
    # IMateFeatureData (mirrors handlers.MATE_TYPE_INTERFACES["concentric"]).
    cti = typed_qi(cmd, "IConcentricMateFeatureData", module=mod)
    cti.EntitiesToMate = _entities_variant(f1, f2)
    cmate = typed_asm.CreateMate(cmd)
    ok = cmate is not None and not isinstance(cmate, int)
    out["created"] = ok
    if ok:
        try:
            ifeat = typed(cmate, "IFeature", module=mod)
            out["feature_type"] = ifeat.GetTypeName2()
            ec = ifeat.GetErrorCode2()
            out["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        except Exception as exc:  # noqa: BLE001
            out["probe_error"] = f"{exc!r}"
    else:
        out["error"] = "concentric CreateMate -> None/int"
    return out


def _matrix_leg_concentric(
    sw: Any, mod: Any, screw_enum: int, conc_enum: int, pitch: float
) -> dict[str, Any]:
    r: dict[str, Any] = {"pitch_set": pitch}
    ctx = cal._place_two_shafts(sw, mod, f"screwcc_{int(pitch * 1e6)}")
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    asm = ctx["asm"]
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    f1, f2 = ctx["f1"], ctx["f2"]

    # --- PRECONDITION: concentric mate establishes the rotation/translation axis ---
    r["concentric"] = _add_concentric(typed_asm, mod, conc_enum, f1, f2)
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    if not r["concentric"].get("created"):
        r["error"] = "concentric precondition failed"
        return r

    # --- screw mate over the SAME two (now-coaxial) faces ---
    smd = typed_asm.CreateMateData(screw_enum)
    if smd is None:
        r["error"] = "screw CreateMateData -> None"
        return r
    sti = typed_qi(smd, _SCREW_IFACE, module=mod)
    sti.EntitiesToMate = _entities_variant(f1, f2)
    sti.RevolutionType = _SCREW_DISTANCE_PER_REV
    sti.RevolutionVal = pitch
    try:
        r["T0_post_set"] = sti.RevolutionVal
    except Exception as exc:  # noqa: BLE001
        r["T0_post_set"] = f"read failed: {exc!r}"
    smate = typed_asm.CreateMate(smd)
    if smate is None or isinstance(smate, int):
        try:
            mfd = typed_qi(smd, "IMateFeatureData", module=mod)
            r["screw_error_status"] = mfd.ErrorStatus
        except Exception:  # noqa: BLE001
            pass
        r["error"] = "CREATEMATE_NONE"
        return r
    ifeat = typed(smate, "IFeature", module=mod)
    try:
        ec = ifeat.GetErrorCode2()
        r["screw_error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
    except Exception:  # noqa: BLE001
        pass
    try:
        defn1 = ifeat.GetDefinition()
        ti1 = typed_qi(defn1, _SCREW_IFACE, module=mod)
        r["T1_post_solve"] = ti1.RevolutionVal
    except Exception as exc:  # noqa: BLE001
        r["T1_post_solve"] = f"read failed: {exc!r}"
    asm_path = str(
        Path(t1._results_tmp(), f"screwcc_{int(pitch*1e6)}_{os.getpid()}.SLDASM")
    )
    save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
    if int(save_ok) != 0:
        r["error"] = f"SAVE_FAILED({save_ok})"
        return r
    r["T2_post_reopen"] = cal._read_screw_val_after_reopen(sw, mod, asm_path)
    return r


def main() -> int:
    result: dict[str, Any] = {
        "spike_id": "mech_mate_screw_calibration_v2",
        "precondition": "concentric_mate_first",
        "matrix": [],
    }
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        screw_enum = t1._resolve_mate_enum("swMateSCREW")
        conc_enum = t1._resolve_mate_enum("swMateCONCENTRIC")
        result["screw_enum"] = screw_enum
        result["concentric_enum"] = conc_enum
        if screw_enum is None or conc_enum is None:
            result["fatal"] = "screw or concentric enum absent from typelib"
            _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            print(json.dumps(result, indent=2, default=str))
            return 0
        for pitch in _PITCHES:
            row = _matrix_leg_concentric(sw, mod, screw_enum, conc_enum, pitch)
            result["matrix"].append(row)
            print(
                f"[cc] pitch={pitch} conc={row.get('concentric', {}).get('created')} "
                f"T0={row.get('T0_post_set')} T1={row.get('T1_post_solve')} "
                f"T2={row.get('T2_post_reopen')} err={row.get('error')}"
            )
        result["verdict"] = cal._verdict(result["matrix"])
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
