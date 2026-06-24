"""Spike v0.16 / P1.7-seat — resolve the two primitives the discovery spike
left FAIL: sketch_slot (CreateSketchSlot 'Type mismatch') and sketch_text
(CreateText absent from ISketchManager).

Discovery (spike_sketch_primitives.py) proved line/arc/ellipse/polygon/spline.
This narrows the two open ones by sweeping candidate arg-shapes, each in its own
fresh blank Part + Front-Plane sketch, recording the verbatim outcome:

  * slot  — CreateSketchSlot: vary creationType enum and the point-buffer length
            (2D pairs vs 3D triples). The VT_ARRAY|VT_R8 marshaling itself is
            already proven (spline), so the fault is enum/point-count/arg-shape.
  * text  — sketch text lives on IModelDoc2.InsertSketchText (needs the doc
            handle, not the sketch manager); sweep arg counts.

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
import win32com.client  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


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


def _sweep(
    sw: Any, label: str, candidates: list[tuple[str, Callable[[Any, Any], Any]]]
) -> dict[str, Any]:
    """Each candidate gets a fresh doc+sketch; receives (doc, sm)."""
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
                rec["result_is_none"] = result is None
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
    report: dict[str, Any] = {}
    try:
        report["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        report["sw_revision"] = "<unreadable>"

    L, Wd = 0.03, 0.01
    p3 = [-0.015, 0.0, 0.0, 0.015, 0.0, 0.0]  # two 3D points
    p2 = [-0.015, 0.0, 0.015, 0.0]  # two 2D points
    # swSketchSlotCreationType_e candidates: 0..4
    slot_cands: list[tuple[str, Callable[[Any, Any], Any]]] = []
    for ct in (1, 0, 2):
        slot_cands.append(
            (
                f"CreateSketchSlot(ct={ct}, L,W, VT_R8[3D x2], True,0,0,1,False)",
                (
                    lambda c: lambda doc, sm: sm.CreateSketchSlot(
                        c, L, Wd, _vt_r8(p3), True, 0, 0, 1, False
                    )
                )(ct),
            )
        )
        slot_cands.append(
            (
                f"CreateSketchSlot(ct={ct}, L,W, VT_R8[2D x2], True,0,0,1,False)",
                (
                    lambda c: lambda doc, sm: sm.CreateSketchSlot(
                        c, L, Wd, _vt_r8(p2), True, 0, 0, 1, False
                    )
                )(ct),
            )
        )
    # Shorter arg-count variant (some overloads omit trailing flags).
    slot_cands.append(
        (
            "CreateSketchSlot(1, L,W, VT_R8[3D x2], True, 0)",
            lambda doc, sm: sm.CreateSketchSlot(1, L, Wd, _vt_r8(p3), True, 0),
        )
    )
    report["sketch_slot"] = _sweep(sw, "sketch_slot", slot_cands)

    text_cands: list[tuple[str, Callable[[Any, Any], Any]]] = [
        (
            "doc.InsertSketchText(0,0,0,'Aa', 1,0,0.0, 0.0,0.0) [9]",
            lambda doc, sm: doc.InsertSketchText(
                0.0, 0.0, 0.0, "Aa", 1, 0, 0.0, 0.0, 0.0
            ),
        ),
        (
            "doc.InsertSketchText(0,0,0,'Aa', 1,0,0.0) [7]",
            lambda doc, sm: doc.InsertSketchText(0.0, 0.0, 0.0, "Aa", 1, 0, 0.0),
        ),
        (
            "doc.InsertSketchText(0,0,0,'Aa', 1,0,0.0, 0.01,0.005) widths>0",
            lambda doc, sm: doc.InsertSketchText(
                0.0, 0.0, 0.0, "Aa", 1, 0, 0.0, 0.01, 0.005
            ),
        ),
    ]
    report["sketch_text"] = _sweep(sw, "sketch_text", text_cands)

    report["summary"] = {
        k: report[k]["overall"] for k in ("sketch_slot", "sketch_text")
    }
    report["overall"] = (
        "PASS" if all(v == "PASS" for v in report["summary"].values()) else "PARTIAL"
    )
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "slot_text_discovery.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
