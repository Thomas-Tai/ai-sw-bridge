"""
Spike C - EquationMgr.Add2 binding on a freshly-built feature.

Assumes:
- Active doc is the part containing SpikeA_Box (the 20x20x5 box).
- spike_c_locals.txt sits next to this script and declares SPIKE_C_DEPTH = 10.

We:
1. Link the locals file via EquationMgr.FilePath = ...
2. Add equation: "D1@SpikeA_Box" = "SPIKE_C_DEPTH" * 0.001  (convert mm to m -
   actually SW equations are unit-aware, the value in the file is treated as mm
   if the doc units are mm, so we just write "SPIKE_C_DEPTH")
3. Rebuild
4. Read back the dim value and verify it matches 10 mm (was 5 mm).

PASS: D1@SpikeA_Box reads 10 mm after rebuild.
FAIL: any of the above raises or value doesn't change.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


LOCALS_FILE = Path(__file__).parent / "spike_c_locals.txt"


def run_com() -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc"}

    if not LOCALS_FILE.exists():
        return {"status": "FAIL", "error": f"missing locals file: {LOCALS_FILE}"}

    eq = doc.GetEquationMgr
    if eq is None:
        return {"status": "FAIL", "error": "EquationMgr is None"}

    # Full Path C linking sequence: setting FilePath alone is NOT enough.
    # Per src/ai_sw_bridge/parameterize.py _build_link_block, we also need
    # LinkToFile=True, AutomaticRebuild=True, and a UpdateValuesFromExternalEquationFile
    # call to actually load the globals into the equation namespace.
    try:
        eq.FilePath = str(LOCALS_FILE)
        eq.LinkToFile = True
        eq.AutomaticRebuild = True
        _reload_ok = eq.UpdateValuesFromExternalEquationFile
    except Exception as e:
        return {"status": "FAIL", "error": f"could not link locals file: {e!r}"}

    linked = eq.FilePath
    link_active = eq.LinkToFile

    # Read the dim's current value before binding
    dim_before = doc.Parameter("D1@SpikeA_Box")
    if dim_before is None:
        return {"status": "FAIL", "error": "Parameter(D1@SpikeA_Box) returned None - did Spike A not produce SpikeA_Box?"}

    val_before_m = dim_before.SystemValue  # meters

    # Add equation: "D1@SpikeA_Box" = "SPIKE_C_DEPTH"
    # Add2(equationIndex, equation, solve) - returns Long.
    # -1 means append.
    formula = '"D1@SpikeA_Box" = "SPIKE_C_DEPTH"'
    idx = eq.Add2(-1, formula, True)

    # Rebuild
    rebuilt = doc.EditRebuild3

    # Read the dim back
    dim_after = doc.Parameter("D1@SpikeA_Box")
    val_after_m = dim_after.SystemValue

    return {
        "status": "PASS" if abs(val_after_m - 0.010) < 1e-6 else "FAIL",
        "linked_file": linked,
        "link_active": link_active,
        "add2_returned_index": idx,
        "dim_before_mm": val_before_m * 1000.0,
        "dim_after_mm": val_after_m * 1000.0,
        "expected_mm": 10.0,
        "rebuilt": rebuilt,
    }


def emit_vba() -> str:
    return f"""' Spike C - VBA fallback
Option Explicit
Sub main()
    Dim swApp As Object, Part As Object, eq As Object
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set eq = Part.GetEquationMgr
    eq.FilePath = "{LOCALS_FILE}"
    Dim addIdx As Long
    addIdx = eq.Add2(-1, "\"\"D1@SpikeA_Box\"\" = \"\"SPIKE_C_DEPTH\"\"", True)
    Part.EditRebuild3
    Dim dim As Object
    Set dim = Part.Parameter("D1@SpikeA_Box")
    MsgBox "D1@SpikeA_Box = " & (dim.SystemValue * 1000) & " mm  (expected 10)"
End Sub
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com", "vba"], default="com")
    args = parser.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_c.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
