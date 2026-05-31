"""Spike v0.16 / P1.7-seat — confirm CreateSketchSlot with the CORRECT signature.

The discovery + slot_text spikes failed slot with 'Type mismatch' at arg 4
because they passed a SAFEARRAY point buffer. CreateSketchSlot does NOT take a
point array — it takes 14 individual scalars:

    CreateSketchSlot(CreationType:int, LengthType:int, Width:float,
                     X1,Y1,Z1, X2,Y2,Z2, X3,Y3,Z3, AddDimension:bool, Centerline:bool)

CreationType/LengthType are swSketchSlot*_e enums (VT_I4) — must be int, not
float. P1/P2 are the centerline endpoints; P3 is the width-defining point.

This sweeps creationType x lengthType to nail the straight-slot combo.
Non-destructive: own blank Parts, never saves, closes own docs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _seg_count(doc: Any) -> int:
    sk = doc.GetActiveSketch2
    if sk is None:
        return 0
    try:
        segs = sk.GetSketchSegments
        segs = segs() if callable(segs) else segs
    except Exception:  # noqa: BLE001
        return 0
    if segs is None:
        return 0
    try:
        return len(segs)
    except TypeError:
        return 1


def _sweep(sw: Any, label: str, candidates: list[tuple[str, Callable[[Any, Any], Any]]]) -> dict[str, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    attempts: list[dict[str, Any]] = []
    overall = "FAIL"
    for desc, fn in candidates:
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            attempts.append({"call": desc, "error": "NewDocument None"})
            continue
        title = _title(doc)
        rec: dict[str, Any] = {"call": desc}
        try:
            doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
            sm = doc.SketchManager
            sm.InsertSketch(True)
            before = _seg_count(doc)
            try:
                result = fn(doc, sm)
                after = _seg_count(doc)
                rec["result_type"] = type(result).__name__
                rec["seg_delta"] = after - before
                rec["materialized"] = result is not None and (after - before) > 0
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
                rec["materialized"] = False
            try:
                sm.InsertSketch(True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                sw.CloseDoc(title)
            except Exception:  # noqa: BLE001
                pass
        attempts.append(rec)
        if rec.get("materialized"):
            overall = "PASS"
            break
    return {"label": label, "overall": overall, "attempts": attempts}


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}

    W = 0.01  # slot width
    # centerline endpoints P1,P2 along x; P3 = width point off the centerline
    x1, y1, z1 = -0.015, 0.0, 0.0
    x2, y2, z2 = 0.015, 0.0, 0.0
    x3, y3, z3 = 0.015, W / 2.0, 0.0

    cands: list[tuple[str, Callable[[Any, Any], Any]]] = []
    for ct in (0, 1):          # swSketchSlotCreationType_e
        for lt in (0, 1, 2):   # swSketchSlotLengthType_e
            cands.append((
                f"CreateSketchSlot(ct={ct}, lt={lt}, W, P1,P2,P3, AddDim=False, CL=True) [14 scalars]",
                (lambda c, l: lambda doc, sm: sm.CreateSketchSlot(
                    int(c), int(l), float(W),
                    float(x1), float(y1), float(z1),
                    float(x2), float(y2), float(z2),
                    float(x3), float(y3), float(z3),
                    False, True))(ct, lt),
            ))
    report["sketch_slot"] = _sweep(sw, "sketch_slot", cands)
    report["overall"] = report["sketch_slot"]["overall"]
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "slot_v2.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
