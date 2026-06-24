"""Gear-ratio TRANSFORM probe — disambiguate transposed-setter vs canonicalize.

mech_mate_gear_orientation proved the (2,1)->(1,2) inversion is INDEPENDENT of
EntitiesToMate order (both A and B persist (1,2)). Two hypotheses survive:

  H1 transposed-setter: `.GearRatioNumerator=` writes the denominator slot (and
     vice versa) in the COM marshaling. Fix = value-swap (assign num<->den).
  H2 canonicalize: SW normalizes the stored ratio to numerator<=denominator;
     direction is carried elsewhere (e.g. a Reverse flag). Value-swap futile.

Discriminator — feed inputs whose persisted form differs between H1 and H2:
  set(1,2): H1 -> (2,1)   H2 -> (1,2)
  set(3,2): H1 -> (2,3)   H2 -> (3,2)
  set(2,1): control (known (1,2))

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_gear_transform.py
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
import mech_mate_gear_orientation as go  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_gear_transform.json"

_GEAR_IFACE = "IGearMateFeatureData"
_INPUTS = ((2.0, 1.0), (1.0, 2.0), (3.0, 2.0))


def _leg(sw: Any, mod: Any, enum_val: int, num: float, den: float) -> dict[str, Any]:
    r: dict[str, Any] = {"set_num": num, "set_den": den}
    ctx = cal._place_two_shafts(sw, mod, f"geartx_{int(num)}_{int(den)}")
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    asm = ctx["asm"]
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    md = typed_asm.CreateMateData(enum_val)
    ti = typed_qi(md, _GEAR_IFACE, module=mod)
    ti.EntitiesToMate = w32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (ctx["f1"], ctx["f2"])
    )
    ti.GearRatioNumerator = num
    ti.GearRatioDenominator = den
    mate = typed_asm.CreateMate(md)
    if mate is None or isinstance(mate, int):
        r["error"] = "CREATEMATE_NONE"
        return r
    asm_path = str(
        Path(t1._results_tmp(), f"geartx_{int(num)}_{int(den)}_{os.getpid()}.SLDASM")
    )
    save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
    if int(save_ok) != 0:
        r["error"] = f"SAVE_FAILED({save_ok})"
        return r
    rb = go._read_gear_ratio_after_reopen(sw, mod, asm_path)
    r["reopened"] = rb
    if isinstance(rb, dict):
        rn, rd = rb["GearRatioNumerator"], rb["GearRatioDenominator"]
        r["h1_transposed"] = abs(rn - den) < 1e-6 and abs(rd - num) < 1e-6
        r["h2_canonical"] = abs(rn - num) < 1e-6 and abs(rd - den) < 1e-6
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_gear_transform", "legs": []}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        enum_val = t1._resolve_mate_enum("swMateGEAR")
        result["gear_enum"] = enum_val
        for num, den in _INPUTS:
            leg = _leg(sw, mod, enum_val, num, den)
            result["legs"].append(leg)
            print(
                f"[tx] set=({num},{den}) reopened={leg.get('reopened')} "
                f"H1={leg.get('h1_transposed')} H2={leg.get('h2_canonical')} "
                f"err={leg.get('error')}"
            )
        h1 = [l for l in result["legs"] if isinstance(l.get("reopened"), dict)]
        if h1 and all(l.get("h1_transposed") for l in h1):
            result["verdict"] = "H1_TRANSPOSED_SETTER"
            result["fix"] = (
                "value-swap: assign GearRatioNumerator=requested_den, GearRatioDenominator=requested_num"
            )
        elif h1 and all(l.get("h2_canonical") for l in h1):
            result["verdict"] = "H2_CANONICALIZE"
            result["fix"] = (
                "ratio stored num<=den; direction not in num/den order — needs Reverse-flag investigation"
            )
        else:
            result["verdict"] = "MIXED"
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
