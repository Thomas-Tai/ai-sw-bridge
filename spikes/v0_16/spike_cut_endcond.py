"""Spike v0.16 / CUT-ENDCOND — prove FeatureCut4 mid-plane and two-direction
end conditions materialize on SW 2024, driving the REAL arg-builders.

D3 adds two cut end-condition variants (cut_extrude_midplane,
cut_extrude_two_direction). FeatureCut4 itself is proven; the narrow new risk
is the arg-shape:
  * mid-plane: T1 = swEndCondMidPlane (4), single direction.
  * two-direction: Sd = False, T2 = swEndCondBlind, D2 = depth2.

This spike builds a box, sketches a circle on the top face, and runs
FeatureCut4 with the tuples produced by builder._cut4_args_2024 (the exact
builder the handlers call) — so it validates the shipped arg-shape, not a
hand-rolled copy. PASS = both cuts materialize (feature non-None AND feature
count increments).

Non-destructive: own blank Parts, never saves, closes own docs.
Usage:  <main-venv>\python spikes\v0_16\spike_cut_endcond.py
        (run with PYTHONPATH=<worktree>/src so the worktree builder loads)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.spec import builder  # noqa: E402
from ai_sw_bridge.sw_types import (  # noqa: E402
    SW_END_COND_BLIND,
    SW_END_COND_MID_PLANE,
)
from spike_earlybind_persist import connect_running_sw  # noqa: E402

W, H, D = 0.040, 0.040, 0.020
R = 0.005
SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _feature_count(doc: Any) -> int:
    gc = doc.GetFeatureCount
    return int(gc() if callable(gc) else gc)


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-W / 2, -H / 2, 0.0, W / 2, H / 2, 0.0)
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (
        True,
        False,
        False,
        0,
        0,
        D,
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
    )
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _sketch_circle_on_top(doc: Any) -> bool:
    """Open a sketch on the +Z top face, draw a circle, close. The closed
    sketch stays selected (same flow the box's FeatureExtrusion2 relies on)."""
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", 0.0, 0.0, D):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    c = sk.CreateCircle(0.0, 0.0, D, R, 0.0, D)
    sk.InsertSketch(True)
    return c is not None


def _cut_case(sw: Any, *, args_kwargs: dict, label: str) -> dict[str, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None or not _build_box(doc):
        return {"label": label, "overall": "FAIL", "reason": "box build failed"}
    title = _title(doc)
    try:
        doc.ForceRebuild3(False)
        before = _feature_count(doc)
        if not _sketch_circle_on_top(doc):
            return {
                "label": label,
                "overall": "FAIL",
                "reason": "sketch on top face failed",
            }
        args = builder._cut4_args_2024(**args_kwargs)
        fm = doc.FeatureManager
        feat = fm.FeatureCut4(*args)
        doc.ForceRebuild3(False)
        after = _feature_count(doc)
        materialized = feat is not None and not isinstance(feat, int)
        return {
            "label": label,
            "args_len": len(args),
            "Sd": args[0],
            "T1": args[3],
            "T2": args[4],
            "D1": args[5],
            "D2": args[6],
            "materialized": materialized,
            "feature_count_delta": after - before,
            "overall": "PASS" if (materialized and after > before) else "FAIL",
        }
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {}
    try:
        report["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        report["sw_revision"] = "<unreadable>"

    report["midplane"] = _cut_case(
        sw,
        args_kwargs={"end_cond": SW_END_COND_MID_PLANE, "depth_m": D, "flip": False},
        label="cut_extrude_midplane",
    )
    report["two_direction"] = _cut_case(
        sw,
        args_kwargs={
            "end_cond": SW_END_COND_BLIND,
            "depth_m": D / 2,
            "flip": False,
            "end_cond2": SW_END_COND_BLIND,
            "depth2_m": D / 2,
        },
        label="cut_extrude_two_direction",
    )

    mp = report["midplane"]["overall"]
    td = report["two_direction"]["overall"]
    report["overall"] = (
        "PASS" if (mp == "PASS" and td == "PASS") else f"midplane={mp} two_dir={td}"
    )
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "cut_endcond.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
