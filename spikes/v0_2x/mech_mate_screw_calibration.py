"""Screw-mate pitch CALIBRATION — disambiguate the 0.002->0.001 round-trip ghost.

The Tier-1 re-PAE proved the screw mate creates+solves+persists, but the pitch
read back as HALF the set value (0.002 set -> 0.001 reopened). A solve-only gate
would have shipped a pipeline where every LLM-authored lead screw binds at half
the requested pitch. This spike maximizes the signal from one seat run to pin the
root cause, per W0's directive:

  3x3 MATRIX — pitch in {0.002, 0.004, 0.010} x checkpoint:
    T0 (post-set)   : read RevolutionVal right after assigning it to the
                      pre-CreateMate IScrewMateFeatureData.
    T1 (post-solve) : read RevolutionVal off the CREATED mate's GetDefinition,
                      before any save.
    T2 (post-reopen): read RevolutionVal after save -> CloseAllDocuments -> reopen.

  BRANCHING LOGIC:
    * T2 scales cleanly (0.001, 0.002, 0.005)  -> factor-of-2 UNIT TRANSFORM.
      Fix = production handler multiplies pitch_m by 2 before setting.
    * T2 collapses to 0.001 for every input    -> setter IGNORED, kernel default
      (1 mm) surfaces. Pre-create MateData is walled for this property.

  PLUS an inline MODIFYDEFINITION PROBE (Option 2) for pitch=0.004: create the
  mate, then set RevolutionType+RevolutionVal on GetDefinition() and push it back
  via IFeature.ModifyDefinition, save->reopen, re-read. Resolves the default-clamp
  branch WITHOUT a second seat run.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_screw_calibration.py
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
# Reuse the Tier-1 spike's proven helpers (build/place/cyl-face/enum-resolve).
sys.path.insert(0, str(_HERE.parent))

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_screw_calibration.json"

_SCREW_ENUM = "swMateSCREW"
_SCREW_IFACE = "IScrewMateFeatureData"
_SCREW_DISTANCE_PER_REV = 1
_PITCHES = (0.002, 0.004, 0.010)


def _place_two_shafts(sw: Any, mod: Any, leg: str) -> dict[str, Any]:
    """Build + place two shafts; return {asm, c1_face, c2_face} or {error}."""
    s1 = t1._build_shaft(f"{leg}_a")
    s2 = t1._build_shaft(f"{leg}_b")
    if "error" in s1 or "error" in s2:
        return {"error": s1.get("error") or s2.get("error")}
    asm_template = _find_assembly_template()
    if asm_template is None:
        return {"error": "NO_ASM_TEMPLATE"}
    asm = sw.NewDocument(asm_template, 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    components = [
        {"id": "a", "part": s1["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": s2["path"], "transform": {"xyz_mm": [50, 0, 0]}},
    ]
    placed, place_err = place_components(sw, asm, components, mod=mod)
    if place_err is not None:
        return {"error": f"PLACE_FAILED: {place_err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    f1 = t1._first_cyl_face(placed.get("a"), mod)
    f2 = t1._first_cyl_face(placed.get("b"), mod)
    if f1 is None or f2 is None:
        return {"error": "NO_CYL_FACE"}
    return {"asm": asm, "f1": f1, "f2": f2}


def _read_screw_val_after_reopen(sw: Any, mod: Any, asm_path: str) -> Any:
    """Reopen the saved assembly and return the screw mate's RevolutionVal."""
    try:
        typed_sw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)
        reopened = typed_sw.OpenDoc6(asm_path, 2, 0, "", 0, 0)
        rdoc = reopened[0] if isinstance(reopened, tuple) else reopened
        if rdoc is None:
            return "reopen returned None"
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        for f in rdoc.FeatureManager.GetFeatures(False) or ():
            tf = typed(f, "IFeature", module=mod)
            try:
                if "Mate" not in tf.GetTypeName2():
                    continue
                defn = tf.GetDefinition()
                if defn is None:
                    continue
                ti = typed_qi(defn, _SCREW_IFACE, module=mod)
                return ti.RevolutionVal
            except Exception:  # noqa: BLE001
                continue
        return "no screw mate found on reopen"
    except Exception as exc:  # noqa: BLE001
        return f"reopen raised: {exc!r}"


def _matrix_leg(sw: Any, mod: Any, enum_val: int, pitch: float) -> dict[str, Any]:
    """One pitch: build/place/mate and read RevolutionVal at T0, T1, T2."""
    r: dict[str, Any] = {"pitch_set": pitch}
    ctx = _place_two_shafts(sw, mod, f"screwcal_{int(pitch * 1e6)}")
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    asm = ctx["asm"]
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    md = typed_asm.CreateMateData(enum_val)
    ti = typed_qi(md, _SCREW_IFACE, module=mod)
    ti.EntitiesToMate = w32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (ctx["f1"], ctx["f2"])
    )
    ti.RevolutionType = _SCREW_DISTANCE_PER_REV
    ti.RevolutionVal = pitch
    # T0 — post-set, pre-create.
    try:
        r["T0_post_set"] = ti.RevolutionVal
    except Exception as exc:  # noqa: BLE001
        r["T0_post_set"] = f"read failed: {exc!r}"
    mate = typed_asm.CreateMate(md)
    if mate is None or isinstance(mate, int):
        r["error"] = "CREATEMATE_NONE"
        return r
    ifeat = typed(mate, "IFeature", module=mod)
    # T1 — post-solve, pre-save (off the created mate's definition).
    try:
        defn1 = ifeat.GetDefinition()
        ti1 = typed_qi(defn1, _SCREW_IFACE, module=mod)
        r["T1_post_solve"] = ti1.RevolutionVal
    except Exception as exc:  # noqa: BLE001
        r["T1_post_solve"] = f"read failed: {exc!r}"
    # Save + reopen for T2.
    asm_path = str(Path(t1._results_tmp(), f"screwcal_{int(pitch*1e6)}_{os.getpid()}.SLDASM"))
    save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
    if int(save_ok) != 0:
        r["error"] = f"SAVE_FAILED({save_ok})"
        return r
    r["T2_post_reopen"] = _read_screw_val_after_reopen(sw, mod, asm_path)
    return r


def _modify_definition_probe(sw: Any, mod: Any, enum_val: int, pitch: float) -> dict[str, Any]:
    """Option-2 probe: set RevolutionVal via GetDefinition + ModifyDefinition
    AFTER CreateMate, then save->reopen and re-read. Resolves the default-clamp
    branch without a second seat run."""
    r: dict[str, Any] = {"probe": "ModifyDefinition", "pitch_set": pitch}
    ctx = _place_two_shafts(sw, mod, f"screwmod_{int(pitch * 1e6)}")
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    asm = ctx["asm"]
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    md = typed_asm.CreateMateData(enum_val)
    ti = typed_qi(md, _SCREW_IFACE, module=mod)
    ti.EntitiesToMate = w32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (ctx["f1"], ctx["f2"])
    )
    ti.RevolutionType = _SCREW_DISTANCE_PER_REV
    # Deliberately set a WRONG value pre-create, then fix it post-create via
    # ModifyDefinition — proves the post-create path is the authoritative one.
    ti.RevolutionVal = 0.001
    mate = typed_asm.CreateMate(md)
    if mate is None or isinstance(mate, int):
        r["error"] = "CREATEMATE_NONE"
        return r
    ifeat = typed(mate, "IFeature", module=mod)
    try:
        defn = ifeat.GetDefinition()
        ti2 = typed_qi(defn, _SCREW_IFACE, module=mod)
        ti2.RevolutionType = _SCREW_DISTANCE_PER_REV
        ti2.RevolutionVal = pitch
        amodel = typed(asm, "IModelDoc2", module=mod)
        # IFeature.ModifyDefinition(Data, TopDoc, Component) — assembly mate -> Component None.
        ok = ifeat.ModifyDefinition(defn, amodel, None)
        r["modify_returned"] = bool(ok) if not isinstance(ok, int) else ok
        amodel.ForceRebuild3(False)
        # Re-read post-modify, pre-save.
        defn_after = ifeat.GetDefinition()
        ti3 = typed_qi(defn_after, _SCREW_IFACE, module=mod)
        r["T1b_post_modify"] = ti3.RevolutionVal
    except Exception as exc:  # noqa: BLE001
        r["modify_error"] = f"{exc!r}"
        return r
    asm_path = str(Path(t1._results_tmp(), f"screwmod_{int(pitch*1e6)}_{os.getpid()}.SLDASM"))
    save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
    if int(save_ok) != 0:
        r["error"] = f"SAVE_FAILED({save_ok})"
        return r
    r["T2_post_reopen"] = _read_screw_val_after_reopen(sw, mod, asm_path)
    return r


def _verdict(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify the T2 column: clean scaling vs default-clamp."""
    rows = [m for m in matrix if isinstance(m.get("T2_post_reopen"), (int, float))]
    if len(rows) < 2:
        return {"class": "INCONCLUSIVE", "note": "fewer than 2 numeric T2 reads"}
    ratios = [round(m["T2_post_reopen"] / m["pitch_set"], 4) for m in rows]
    all_half = all(abs(r - 0.5) < 0.05 for r in ratios)
    all_one = all(abs(r - 1.0) < 0.05 for r in ratios)
    all_clamp = all(abs(m["T2_post_reopen"] - 0.001) < 1e-6 for m in rows)
    if all_one:
        return {"class": "CLEAN_ROUNDTRIP", "ratios": ratios,
                "note": "T2==set for all pitches; the Tier-1 0.002->0.001 was a fluke/diff cause"}
    if all_half:
        return {"class": "UNIT_TRANSFORM_X2", "ratios": ratios,
                "note": "T2==0.5*set for all pitches; handler must set pitch_m*2"}
    if all_clamp:
        return {"class": "DEFAULT_CLAMP_1MM", "ratios": ratios,
                "note": "T2==0.001 regardless of input; pre-create setter ignored -> use ModifyDefinition"}
    return {"class": "OTHER", "ratios": ratios, "note": "non-uniform; inspect per-row"}


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_screw_calibration", "matrix": []}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        enum_val = t1._resolve_mate_enum(_SCREW_ENUM)
        result["enum_resolved"] = enum_val
        if enum_val is None:
            result["fatal"] = "swMateSCREW absent from typelib"
            _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            print(json.dumps(result, indent=2, default=str))
            return 0
        for pitch in _PITCHES:
            row = _matrix_leg(sw, mod, enum_val, pitch)
            result["matrix"].append(row)
            print(f"[cal] pitch={pitch} -> T0={row.get('T0_post_set')} "
                  f"T1={row.get('T1_post_solve')} T2={row.get('T2_post_reopen')} "
                  f"err={row.get('error')}")
        result["verdict"] = _verdict(result["matrix"])
        # Inline Option-2 probe (default-clamp resolver) — run regardless to
        # maximize single-seat-run signal.
        result["modify_probe"] = _modify_definition_probe(sw, mod, enum_val, 0.004)
        print(f"[cal] modify_probe -> {json.dumps(result['modify_probe'], default=str)}")
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
