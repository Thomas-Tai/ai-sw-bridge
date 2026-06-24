"""W75b production PAE — linear_coupler through create_mate.

Exercises the shipped ``assembly.handlers.create_mate`` (dedicated
``_create_linear_coupler_mate`` population) with a declarative 1:2 ratio spec,
then save -> close -> reopen and verifies the mate persists with the ratio
intact (faithful round-trip, no gear-style transpose).

  spec {type:"linear_coupler", a:{linear_edge}, b:{linear_edge},
        ratio_numerator:1, ratio_denominator:2} -> MateLinearCoupler;
        reopened CouplerRatioNumerator==1 ∧ CouplerRatioDenominator==2.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_linear_coupler_pae.py
"""

from __future__ import annotations

import json
import os
import sys
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
from ai_sw_bridge.assembly.handlers import create_mate, place_components  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "linear_coupler_pae.json"
results: dict[str, Any] = {"pae": "w75b_linear_coupler", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        a = P._build("lcpae_a", P._cube("lcpae_a", 10.0))
        b = P._build("lcpae_b", P._cube("lcpae_b", 10.0))
        if "error" in a or "error" in b:
            gate("fixture", False, a.get("error") or b.get("error"))
            raise SystemExit(_finish())
        asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
        comps = [
            {"id": "a", "part": a["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": b["path"], "transform": {"xyz_mm": [40, 0, 0]}},
        ]
        placed, err = place_components(sw, asm, comps, mod=mod)
        if err:
            gate("place", False, err)
            raise SystemExit(_finish())
        typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
        gate("place", True, "2 components")

        mate = {
            "type": "linear_coupler",
            "a": {"component": "a", "face_ref": {"linear_edge": True}},
            "b": {"component": "b", "face_ref": {"linear_edge": True}},
            "ratio_numerator": 1.0,
            "ratio_denominator": 2.0,
            "reverse": False,
        }
        feat, mate_err = create_mate(asm, placed, mate, mod=mod)
        if feat is None:
            gate("create_mate", False, str(mate_err))
            raise SystemExit(_finish())
        ft = typed(feat, "IFeature", module=mod).GetTypeName2()
        gate("create_mate", "LinearCoupler" in ft, f"feature_type={ft}")

        path = str(Path(t1._results_tmp(), f"w75b_lc_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(path, 0, 0)

        # reopen + ratio round-trip
        tsw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)
        ro = tsw.OpenDoc6(path, 2, 0, "", 0, 0)
        rdoc = ro[0] if isinstance(ro, tuple) else ro
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        found = {"type": None, "num": None, "den": None}
        for f in rdoc.FeatureManager.GetFeatures(False) or ():
            try:
                tf = typed(f, "IFeature", module=mod)
                tn = tf.GetTypeName2()
                if "LinearCoupler" in tn:
                    lc = typed_qi(
                        tf.GetDefinition(), "ILinearCouplerMateFeatureData", module=mod
                    )
                    found = {
                        "type": tn,
                        "num": lc.CouplerRatioNumerator,
                        "den": lc.CouplerRatioDenominator,
                    }
                    break
            except Exception:
                continue
        results["reopen"] = found
        gate("reopen_persists", found["type"] is not None, f"type={found['type']}")
        gate(
            "ratio_round_trips",
            found["num"] == 1.0 and found["den"] == 2.0,
            f"num={found['num']} den={found['den']} (expect 1/2, faithful)",
        )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


def _finish() -> int:
    all_pass = all(g["ok"] for g in results["gates"].values()) and bool(
        results["gates"]
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
