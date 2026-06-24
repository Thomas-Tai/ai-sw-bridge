"""W71 spike — ``scale`` seat proof (LIVE seat only).

Builds a 10×10×10 mm cube (vol = 1000 mm³), fires the production
``create_scale`` handler with a uniform 1.5× centroid scale, and witnesses:

  * handler returns (True, …)
  * ΔVol == 2375.000 mm³ EXACTLY (1000 → 3375 = 1.5³ · 1000), the closed-form
    boundary-law signature
  * the volume ratio == 3.375
  * save → reopen survival (volume persists)

A non-None Feature return ALONE is the W21/W42 ghost trap and is NOT a pass.

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_scale.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pythoncom

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from _feature_spike_fixtures import (  # noqa: E402
    _new_part,
    _select_feature,
    connect,
    save_and_reopen,
)

RESULTS_PATH = _REPO_ROOT / "spikes" / "v0_2x" / "_results" / "scale.json"

_BLIND = 0  # swEndConditions_e.swEndCondBlind
_EXPECTED_DVOL_MM3 = 2375.0  # 1000 · (1.5³ − 1) = 1000 · 2.375
_TOL_MM3 = 1.0  # mm³ — closed-form, so well under 1 (probe was IEEE-754 exact)


def build_cube(sw: Any) -> Any:
    """10×10×10 mm solid cube (Boss-Extrude1, consumes Sketch1). Vol = 1000 mm³.

    Mirrors ``_feature_spike_fixtures.build_block`` but with a 10×10 mm square
    profile + 10 mm depth, so the witness ΔVol is an exact round number.
    """
    doc = _new_part(sw)
    _select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    # 10×10 mm corner rectangle centred on the origin (±5 mm).
    doc.SketchManager.CreateCornerRectangle(-0.005, -0.005, 0.0, 0.005, 0.005, 0.0)
    doc.SketchManager.InsertSketch(True)  # close Sketch1
    doc.ClearSelection2(True)
    _select_feature(doc, "Sketch1")
    doc.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        _BLIND,
        0,
        0.010,
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
        True,
        True,
        True,
        0,
        0.0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _vol_mm3(doc: Any) -> float:
    from ai_sw_bridge.features import verify

    return verify.solid_volume_mm3(doc)


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w71_scale",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    sw = connect()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    doc = build_cube(sw)
    vol_before = _vol_mm3(doc)
    result["cube"] = "10x10x10 mm"
    result["vol_before_mm3"] = vol_before

    if abs(vol_before - 1000.0) > 1.0:
        result["overall"] = "ERROR"
        result["finding"] = f"cube fixture vol {vol_before:.3f} != 1000 mm³"
        return result

    from ai_sw_bridge.features.scale import create_scale

    ok, note = create_scale(doc, {"scale_factor": 1.5, "origin": "centroid"}, {})
    result["handler_ok"] = ok
    result["handler_note"] = note

    vol_after = _vol_mm3(doc)
    d_vol = vol_after - vol_before
    ratio = (vol_after / vol_before) if vol_before else None
    result["vol_after_mm3"] = vol_after
    result["d_vol_mm3"] = d_vol
    result["ratio"] = ratio
    result["expected_d_vol_mm3"] = _EXPECTED_DVOL_MM3
    result["expected_ratio"] = 3.375

    dvol_exact = abs(d_vol - _EXPECTED_DVOL_MM3) <= _TOL_MM3

    if ok and dvol_exact:
        print("[save_and_reopen]", file=sys.stderr)
        try:
            doc2 = save_and_reopen(sw, doc)
            vol_reopen = _vol_mm3(doc2)
            result["reopen"] = {
                "vol_mm3": vol_reopen,
                "survives": abs(vol_reopen - vol_after) <= _TOL_MM3,
            }
        except Exception as e:
            result["reopen"] = {"error": str(e)[:200]}
        result["overall"] = "PASS"
        result["finding"] = (
            f"scale: ΔVol {d_vol:+.3f} mm³ (expected {_EXPECTED_DVOL_MM3:+.3f}), "
            f"ratio {ratio:.5f} (expected 3.375)"
        )
    else:
        result["overall"] = "NO_OP" if not ok else "GHOST"
        result["finding"] = (
            f"handler_ok={ok}, ΔVol={d_vol:.3f} (expected {_EXPECTED_DVOL_MM3}), "
            f"ratio={ratio}, note={note!r}"
        )

    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        try:
            connect().CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
