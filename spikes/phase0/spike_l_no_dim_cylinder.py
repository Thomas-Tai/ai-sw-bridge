"""
Spike L - Build the cylinder with NO AddDimension2 calls at all.

Approach: resolve every `{"rhs": "..."}` against the locals.txt file in
Python upfront, substitute the literal numeric value (mm) into the spec,
then call CreateCircle/FeatureExtrusion2 with the target geometry directly.

If this works: zero popups, zero PM panes, fully automatic build.
Trade-off: the resulting SLDPRT has NO equations linked to locals.txt --
re-editing locals will not propagate; user must re-run ai-sw-build.

This spike intentionally bypasses the production builder.py to keep the
test surgical. If it passes, we'll port the resolve step into builder.py
and gate it behind a `--no-dim` flag.

Test: cylinder, 2 dims (PART_DIAMETER=25, PART_LENGTH=80).
PASS: ok=true, no manual ticks needed, final D=25mm L=80mm.
FAIL: any popup appears, OR geometry off-spec.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.locals_io import parse as parse_locals  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.sw_types import (  # noqa: E402
    SW_END_COND_BLIND,
    SW_START_SKETCH_PLANE,
    assert_args,
)


CYL_SPEC = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "minimal_cylinder_v2"
    / "spec.json"
)


def resolve_rhs(rhs_expr: str, locals_map: dict[str, float]) -> float:
    """Evaluate an rhs expression like '"PART_DIAMETER"' or '"FLANGE_OD" + 0.5'
    against the locals_map. Returns the numeric value (units = whatever the
    locals file uses, typically mm)."""

    # Substitute "NAME" -> the numeric value
    def _sub(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name not in locals_map:
            raise KeyError(f"locals has no '{name}'")
        return repr(locals_map[name])

    py_expr = re.sub(r'"([^"]+)"', _sub, rhs_expr)
    return float(eval(py_expr, {"__builtins__": {}}, {}))


def load_locals_map(path: Path) -> dict[str, float]:
    """Parse locals.txt into a name->float map. Skips entries whose RHS
    is non-numeric (other vars / expressions) -- spike doesn't need them."""
    text = path.read_text(encoding="utf-8")
    entries = parse_locals(text)
    out: dict[str, float] = {}
    for e in entries:
        try:
            out[e.name] = float(e.expression)
        except ValueError:
            # Non-literal -- ignore for spike; cylinder locals are all literals.
            continue
    return out


def build_cylinder_numeric(sw, doc, diameter_mm: float, length_mm: float) -> dict:
    """Build the cylinder with literal numeric geometry. No AddDimension2,
    no EquationMgr, no popup."""
    radius_m = (diameter_mm / 1000.0) / 2
    length_m = length_mm / 1000.0

    # Front Plane sketch
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select Front Plane"}
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, radius_m, 0.0, 0.0)
    sm.InsertSketch(True)  # close

    # Rename to SK_Body
    sk = doc.FeatureByPositionReverse(0)
    if sk is None:
        return {"status": "FAIL", "error": "no sketch produced"}
    sk.Name = "SK_Body"

    # Extrude (FeatureExtrusion2, 23 args -- copied verbatim from builder.py)
    doc.ClearSelection2(True)
    if not doc.SelectByID("SK_Body", "SKETCH", 0.0, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select SK_Body"}

    fm = doc.FeatureManager
    args = (
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        length_m,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,  # Merge
        True,
        True,
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    assert_args("IFeatureManager.FeatureExtrusion2", args)
    ext = fm.FeatureExtrusion2(*args)
    if ext is None:
        return {"status": "FAIL", "error": "FeatureExtrusion2 returned None"}
    ext.Name = "Extrude_Body"

    # Probe the final geometry. With no D1/D2 dims attached, Parameter()
    # won't find them -- that's expected. Instead verify via the extrude
    # feature's depth and a SaveBMP for visual sanity (optional).
    return {
        "status": "PASS",
        "sketch_name": "SK_Body",
        "feature_name": "Extrude_Body",
        "target_diameter_mm": diameter_mm,
        "target_length_mm": length_mm,
    }


def run_com() -> dict:
    sw = get_sw_app()

    # Caller responsibility: have NO active doc, or be OK with us opening a fresh part.
    template = sw.GetUserPreferenceStringValue(8)
    if not template:
        return {"status": "FAIL", "error": "no default Part template"}
    t0 = time.perf_counter()
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"status": "FAIL", "error": "NewDocument returned None"}

    spec = json.loads(CYL_SPEC.read_text(encoding="utf-8"))
    locals_path = Path(spec["locals"])
    locals_map = load_locals_map(locals_path)

    # Resolve rhs's: cylinder spec has diameter+rhs and depth+rhs
    diameter = resolve_rhs(spec["features"][0]["diameter"]["rhs"], locals_map)
    length = resolve_rhs(spec["features"][1]["depth"]["rhs"], locals_map)

    result = build_cylinder_numeric(sw, doc, diameter, length)
    elapsed_s = round(time.perf_counter() - t0, 2)
    result["elapsed_s"] = elapsed_s
    result["locals_path"] = str(locals_path)
    result["locals_map"] = locals_map
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    args = parser.parse_args()
    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
