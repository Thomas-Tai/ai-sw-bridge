"""Gear-mate orientation FINALIZER — pin the EntitiesToMate order that makes the
persisted ratio equal the REQUESTED ratio.

Tier-1 observed: set (num=2, den=1) with EntitiesToMate=(f1,f2) -> reopened
(num=1, den=2). A 2:1 ratio from face-A's frame IS 1:2 from face-B's frame, so
SW persists the ratio against a canonical entity order that is the REVERSE of
the EntitiesToMate order we passed. The production fix (W0-approved): order
EntitiesToMate so the numerator binds to the user's intended Selection1, then
read-back-assert the persisted ratio == requested.

This spike tests BOTH orders against the SAME request (num=2, den=1) and reports
the reopened ratio for each, so the handler encodes the PROVEN order, not a guess:

  order_A: EntitiesToMate = (f1, f2)   -> reopened (num, den) = ?
  order_B: EntitiesToMate = (f2, f1)   -> reopened (num, den) = ?

GREEN: exactly one order yields reopened (2, 1) == requested. The handler adopts
that order + keeps the read-back assert as a fail-closed guard.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_gear_orientation.py
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
_OUT = _RESULTS / "mech_mate_gear_orientation.json"

_GEAR_IFACE = "IGearMateFeatureData"
_REQ_NUM, _REQ_DEN = 2.0, 1.0


def _read_gear_ratio_after_reopen(sw: Any, mod: Any, asm_path: str) -> Any:
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
                ti = typed_qi(defn, _GEAR_IFACE, module=mod)
                return {
                    "GearRatioNumerator": ti.GearRatioNumerator,
                    "GearRatioDenominator": ti.GearRatioDenominator,
                }
            except Exception:  # noqa: BLE001
                continue
        return "no gear mate found on reopen"
    except Exception as exc:  # noqa: BLE001
        return f"reopen raised: {exc!r}"


def _order_leg(sw: Any, mod: Any, enum_val: int, order: str) -> dict[str, Any]:
    r: dict[str, Any] = {"order": order, "requested": {"num": _REQ_NUM, "den": _REQ_DEN}}
    ctx = cal._place_two_shafts(sw, mod, f"gearorient_{order}")
    if "error" in ctx:
        r["error"] = ctx["error"]
        return r
    asm = ctx["asm"]
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    f1, f2 = ctx["f1"], ctx["f2"]
    pair = (f1, f2) if order == "A" else (f2, f1)
    md = typed_asm.CreateMateData(enum_val)
    ti = typed_qi(md, _GEAR_IFACE, module=mod)
    ti.EntitiesToMate = w32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, pair
    )
    ti.GearRatioNumerator = _REQ_NUM
    ti.GearRatioDenominator = _REQ_DEN
    mate = typed_asm.CreateMate(md)
    if mate is None or isinstance(mate, int):
        r["error"] = "CREATEMATE_NONE"
        return r
    asm_path = str(Path(t1._results_tmp(), f"gearorient_{order}_{os.getpid()}.SLDASM"))
    save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
    if int(save_ok) != 0:
        r["error"] = f"SAVE_FAILED({save_ok})"
        return r
    rb = _read_gear_ratio_after_reopen(sw, mod, asm_path)
    r["reopened"] = rb
    if isinstance(rb, dict):
        r["matches_requested"] = (
            abs(rb["GearRatioNumerator"] - _REQ_NUM) < 1e-6
            and abs(rb["GearRatioDenominator"] - _REQ_DEN) < 1e-6
        )
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_gear_orientation", "legs": []}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        enum_val = t1._resolve_mate_enum("swMateGEAR")
        result["gear_enum"] = enum_val
        for order in ("A", "B"):
            leg = _order_leg(sw, mod, enum_val, order)
            result["legs"].append(leg)
            print(f"[go] order={order} reopened={leg.get('reopened')} "
                  f"matches={leg.get('matches_requested')} err={leg.get('error')}")
        winners = [l["order"] for l in result["legs"] if l.get("matches_requested")]
        result["winning_order"] = winners[0] if len(winners) == 1 else None
        result["verdict"] = "GREEN" if len(winners) == 1 else "AMBIGUOUS"
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
