"""
Spike O - Probe whether SW creates queryable D1/D2 internal dim params on
sketches and features even when AddDimension2 was NEVER called.

Background: --no-dim mode builds correct geometry but skips AddDimension2,
so no visible dim annotations. User wants to know if we can still bind
EquationMgr.Add2 against an internally-named dim (e.g. "D1@Extrude_Body")
to recover the live link to locals.txt without re-introducing the popup.

Test (requires the cylinder from `ai-sw-build --no-dim` to be the ACTIVE
doc -- do NOT run on a fresh blank part):
1. Read doc.Parameter("D1@SK_Body").SystemValue
2. Read doc.Parameter("D1@Extrude_Body").SystemValue
3. Try doc.Parameter("Diameter@SK_Body") (some SW versions name it this)
4. Try doc.Parameter("Length@Extrude_Body")
5. Also try EquationMgr.Add2 binding a real var name and rebuild
6. Report which names exist and which return None

PASS: at least one queryable internal dim name exists -> linkable.
FAIL: every probe returns None -> linkability requires AddDimension2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


# Candidate internal parameter names. SW typically uses "D1@<feature>" for
# the first numeric param of a feature, but face-sketches sometimes use
# "Diameter1@Sketch1" or "RD1@..." historically.
PROBE_NAMES = [
    # Sketch-side (the cylinder spec named the sketch "SK_Body")
    "D1@SK_Body",
    "D2@SK_Body",
    "Diameter@SK_Body",
    "Diameter1@SK_Body",
    "Radius@SK_Body",
    # Feature-side (named "Extrude_Body")
    "D1@Extrude_Body",
    "D2@Extrude_Body",
    "Length@Extrude_Body",
    "Depth@Extrude_Body",
]


def run_com() -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc; open the --no-dim cylinder first"}

    results: list[dict] = []
    for name in PROBE_NAMES:
        try:
            p = doc.Parameter(name)
        except Exception as e:
            results.append({"name": name, "found": False, "error": repr(e)})
            continue
        if p is None:
            results.append({"name": name, "found": False, "value_mm": None})
        else:
            try:
                v = p.SystemValue
                results.append({"name": name, "found": True,
                                "value_mm": round(v * 1000.0, 4)})
            except Exception as e:
                results.append({"name": name, "found": True,
                                "value_mm": None, "value_read_error": repr(e)})

    found = [r for r in results if r["found"]]
    status = "PASS" if found else "FAIL"

    # If we found at least one bindable name, also TEST a binding round-trip:
    # set D1@whatever to 50mm via EquationMgr, rebuild, re-read.
    bind_test = None
    if found:
        target = found[0]["name"]
        eq = doc.GetEquationMgr
        if eq is not None:
            formula = f'"{target}" = 50'
            idx = eq.Add2(-1, formula, True)
            _ = doc.EditRebuild3
            after = doc.Parameter(target)
            after_val = round(after.SystemValue * 1000.0, 4) if after else None
            bind_test = {
                "tested_name": target,
                "formula": formula,
                "add2_index": idx,
                "value_after_mm": after_val,
                "binding_worked": after_val is not None and abs(after_val - 50.0) < 0.01,
            }

    return {
        "status": status,
        "probe_results": results,
        "queryable_names": [r["name"] for r in found],
        "binding_round_trip": bind_test,
        "interpretation": (
            "Internal dim names ARE queryable -- we can bind locals "
            "without AddDimension2. Patch builder.py to call Add2 against "
            "these names in no_dim mode."
            if found
            else "No queryable internal dim names. Linkability requires "
                 "AddDimension2, which means the popup toll is unavoidable "
                 "if you want a locals-linked part."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    args = parser.parse_args()
    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
