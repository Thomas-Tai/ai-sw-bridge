"""Gear-mate PRODUCTION PAE — verify the transposed-setter fix end-to-end.

Exercises the ACTUAL production handler ``assembly.handlers.create_mate`` (not
inline COM) with a gear ``ratio:{numerator:2, denominator:1}``, then save ->
close -> reopen and assert the PERSISTED ratio == the REQUESTED (2, 1).

This closes the loop on the W46 gear leg: mech_mate_gear_transform proved SW's
GearRatio setters are transposed and the handler now compensates by swapping the
assignment. This PAE proves that compensation survives the full production path
(face_ref resolution -> CreateMateData -> EntitiesToMate -> CreateMate) AND a
save/reopen round-trip — the GREEN gate (a solved-but-wrong ratio is a ghost).

GREEN: reopened (GearRatioNumerator, GearRatioDenominator) == (2.0, 1.0).

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_gear_pae.py
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
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components, create_mate  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_gear_orientation as go  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_gear_pae.json"

_REQ_NUM, _REQ_DEN = 2.0, 1.0


def main() -> int:
    out: dict[str, Any] = {
        "spike_id": "mech_mate_gear_pae",
        "requested": {"numerator": _REQ_NUM, "denominator": _REQ_DEN},
        "ok": False,
        "verdict": "FAIL",
    }
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass

        s1 = t1._build_shaft("gearpae_a")
        s2 = t1._build_shaft("gearpae_b")
        if "error" in s1 or "error" in s2:
            out["error"] = s1.get("error") or s2.get("error")
            raise SystemExit(_finish(out))

        asm_template = _find_assembly_template()
        asm = sw.NewDocument(asm_template, 0, 0.1, 0.1)
        if asm is None:
            out["error"] = "ASM_NEWDOC_NONE"
            raise SystemExit(_finish(out))

        components = [
            {"id": "a", "part": s1["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": s2["path"], "transform": {"xyz_mm": [50, 0, 0]}},
        ]
        placed, place_err = place_components(sw, asm, components, mod=mod)
        if place_err is not None:
            out["error"] = f"PLACE_FAILED: {place_err}"
            raise SystemExit(_finish(out))
        typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)

        # PRODUCTION handler path — face_ref {is_cylinder:true} resolves the
        # first cylindrical face on each component body.
        mate_spec = {
            "type": "gear",
            "a": {"component": "a", "face_ref": {"is_cylinder": True}},
            "b": {"component": "b", "face_ref": {"is_cylinder": True}},
            "ratio": {"numerator": _REQ_NUM, "denominator": _REQ_DEN},
        }
        mate_ret, mate_err = create_mate(asm, placed, mate_spec, mod=mod)
        out["create_mate_error"] = mate_err
        if mate_ret is None:
            out["error"] = f"create_mate returned None: {mate_err}"
            raise SystemExit(_finish(out))
        out["mate_created"] = True
        try:
            out["feature_type"] = typed(mate_ret, "IFeature", module=mod).GetTypeName2()
        except Exception:  # noqa: BLE001
            pass

        asm_path = str(Path(t1._results_tmp(), f"gearpae_{os.getpid()}.SLDASM"))
        save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        if int(save_ok) != 0:
            out["error"] = f"SAVE_FAILED({save_ok})"
            raise SystemExit(_finish(out))

        rb = go._read_gear_ratio_after_reopen(sw, mod, asm_path)
        out["reopened"] = rb
        if isinstance(rb, dict):
            green = (
                abs(rb["GearRatioNumerator"] - _REQ_NUM) < 1e-6
                and abs(rb["GearRatioDenominator"] - _REQ_DEN) < 1e-6
            )
            out["ok"] = bool(green)
            out["verdict"] = "GREEN" if green else "NO-GO"
            out["note"] = (
                "GREEN <=> reopened ratio == requested (2,1). The handler's "
                "transposed-setter compensation is correct end-to-end."
                if green
                else f"NO-GO: reopened {rb} != requested (2,1)."
            )
        else:
            out["error"] = f"readback failed: {rb}"
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{exc!r}"
        out["traceback"] = traceback.format_exc()
    return _finish(out)


def _finish(out: dict) -> int:
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"[gearpae] verdict: {out.get('verdict')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
