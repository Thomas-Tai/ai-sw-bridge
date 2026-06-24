"""
Spike v0.16 / S-WIZHOLE-V4 — wizard hole via the REAL creation path:
``IFeatureManager.HoleWizard5`` (27-arg method), not CreateDefinition.
[authored seat-free; RUN ON A LIVE SEAT]

v2 + v3 proved that ``CreateDefinition(25) → typed_qi(IWizardHoleFeatureData2)
→ InitializeHole → CreateFeature`` reliably **no-ops** at CreateFeature, even
with a selected face (v2) or a selected sketch point (v3). The typelib shows
why: ``IFeatureManager`` exposes ``HoleWizard{,2,3,4,5}`` creation methods, and
``IWizardHoleFeatureData2`` is the **edit** interface (GetDefinition), not a
creation target. Wizard-hole *creation* is method-based — like Shell.

HoleWizard5 signature (from the typelib):
    HoleWizard5(GenericHoleType:i4, StandardIndex:i4, FastenerTypeIndex:i4,
                SSize:bstr, EndType:i2, Diameter:r8, Depth:r8, Length:r8,
                Value1..Value12:r8, ThreadClass:bstr, RevDir:bool,
                FeatureScope:bool, AutoSelect:bool, AssemblyFeatureScope:bool,
                AutoSelectComponents:bool, PropagateFeatureToParts:bool) -> Feature

Flow
----
  1. NewDocument part; 20×20×10 box.
  2. Sketch point on the top face; select it (the hole position).
  3. ``fm.HoleWizard5(...)`` for a simple Ø6 blind hole, 6 mm deep.

Verdict
-------
PASS    : HoleWizard5 returns a materialized feature → build the F2 wizhole
          handler on this METHOD (pre-select a sketch point + HoleWizard5).
PARTIAL : HoleWizard5 ran but returned no feature → arg/placement tuning needed;
          inspect the recorded call.
FAIL    : box/point build failed, or HoleWizard5 raised.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_wizhole_v4.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

PT_X = 0.003
PT_Y = 0.002

# HoleWizard5 args for a simple Ø6 mm blind hole 6 mm deep (ANSI Metric).
SW_WZD_HOLE = 2
SW_STD_ANSI_METRIC = 1
SW_FAST_ANSI_METRIC_DRILL_SIZES = 39
SSIZE = "6.0"
SW_END_BLIND = 0
DIAMETER_M = 0.006
DEPTH_M = 0.006


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
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
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _place_and_select_point(doc: Any) -> dict[str, Any]:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", 0, 0, BOX_D_M):
        return {"ok": False, "error": "could not select top face"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    rec, pt = _capture(lambda: sk.CreatePoint(PT_X, PT_Y, 0.0))
    sk.InsertSketch(True)
    if pt is None:
        return {"ok": False, "error": "CreatePoint failed", "create_point": rec}
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    sel = False
    m = getattr(pt, "Select2", None)
    if m is not None:
        srec, ok = _capture(lambda: m(False, 0))
        sel = srec["status"] == "OK" and bool(ok)
    if not sel:
        srec, ok = _capture(
            lambda: doc.SelectByID("", "SKETCHPOINT", PT_X, PT_Y, BOX_D_M)
        )
        sel = bool(ok)
    return {"ok": sel, "create_point": rec}


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "dynamic (FeatureManager.HoleWizard5)"}
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    create_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        place = _place_and_select_point(doc)
        result["place_point"] = place
        if not place.get("ok"):
            return {
                **result,
                "overall": "FAIL",
                "reason": "could not place/select point",
            }

        fm = doc.FeatureManager
        values = (0.0,) * 12
        # AutoSelect=False so SW honours the pre-selected sketch point as the
        # hole position (AutoSelect=True makes it auto-pick and ignore ours).
        base = (
            SW_WZD_HOLE,
            SW_STD_ANSI_METRIC,
            SW_FAST_ANSI_METRIC_DRILL_SIZES,
            SSIZE,
            SW_END_BLIND,
            DIAMETER_M,
            DEPTH_M,
            0.0,
            *values,
            "",
        )
        # Try AutoSelect=False first (use our point), then True as a fallback.
        attempts: list[dict[str, Any]] = []
        feat = None
        for auto in (False, True):
            args = (*base, False, True, auto, False, False, False)
            # re-assert the point selection before each attempt
            _place_and_select_point(doc)
            rec, feat = _capture(lambda a=args: fm.HoleWizard5(*a))
            rec["auto_select"] = auto
            rec["materialized"] = _materialized(feat)
            attempts.append(rec)
            if _materialized(feat):
                rec["feature_name"] = getattr(feat, "Name", None)
                rec["type_name"] = _type_name(feat)
                break
        result["hole_wizard5_args_base"] = list(base)
        result["hole_wizard5_attempts"] = attempts
        create_rec = attempts[-1]
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
        result["cleanup"] = "closed own doc (no save)"

    if create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            "HoleWizard5 materializes a wizard hole → build the F2 wizhole handler "
            "on this METHOD (select a sketch point, then HoleWizard5(...)). The "
            "data-object CreateFeature path is edit-only."
        )
    elif create_rec.get("status") == "OK":
        overall = "PARTIAL"
        interp = (
            "HoleWizard5 ran but returned no feature → tune args/placement "
            "(SSize must be valid for FastenerTypeIndex; point must be selected)."
        )
    else:
        overall = "FAIL"
        interp = f"HoleWizard5 raised: {create_rec.get('message')}"

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
