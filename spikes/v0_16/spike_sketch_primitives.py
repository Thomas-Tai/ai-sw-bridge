"""Spike v0.16 / P1.7-seat — discover the live ISketchManager.Create* signatures
for the seven P1.7s sketch primitives (line, arc, ellipse, polygon, slot,
spline, text).

The seven handlers ship as function stubs (builder._build_sketch_*) that assemble
an arg tuple and raise NotImplementedError. None of these Create* methods are in
the CHM-extracted api_reference.md, so the exact late-bound signatures — and
which ones hit a marshaling wall (SAFEARRAY point buffers for slot/spline, the
iFormatFlags bitfield for text) — are unknown. This spike probes each candidate
against a fresh blank Part with an open Front-Plane sketch, recording for every
primitive: the call tried, whether a segment materialized (active-sketch segment
count delta), and the verbatim exception repr on failure.

PASS for a primitive = at least one candidate call increments the active sketch's
segment count. The discovery output drives the function-style handler bodies; any
primitive that only fails (marshaling wall) is deferred with an honest note, the
same way D3 deferred the SW-2025 FeatureCut4 arity.

Non-destructive: own blank Parts via NewDocument, never saves, closes own docs.
Usage:  <main-venv>\python spikes\v0_16\spike_sketch_primitives.py
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


def _vt_r8_array(vals: list[float]) -> Any:
    """Wrap a flat list of doubles as a VT_ARRAY|VT_R8 VARIANT SAFEARRAY."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _seg_count(doc: Any) -> int:
    """Count segments in the active sketch (0 if none)."""
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
        return 1  # single segment returned unwrapped


def _probe(
    sw: Any, label: str, candidates: list[tuple[str, Callable[[Any], Any]]]
) -> dict[str, Any]:
    """Open a fresh blank Part + Front-Plane sketch, try each candidate call in
    order until one increments the segment count. Record every attempt."""
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {
            "label": label,
            "overall": "FAIL",
            "reason": "NewDocument returned None",
        }
    title = _title(doc)
    attempts: list[dict[str, Any]] = []
    overall = "FAIL"
    try:
        for desc, fn in candidates:
            # Fresh sketch per candidate so a failed call cannot pollute the next.
            if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
                attempts.append({"call": desc, "error": "could not select Front Plane"})
                continue
            sm = doc.SketchManager
            sm.InsertSketch(True)
            before = _seg_count(doc)
            rec: dict[str, Any] = {"call": desc}
            try:
                result = fn(sm)
                after = _seg_count(doc)
                rec["result_type"] = type(result).__name__
                rec["seg_delta"] = after - before
                rec["materialized"] = (after - before) > 0
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
                rec["materialized"] = False
            sm.InsertSketch(True)  # close (toggle)
            doc.ClearSelection2(True)
            attempts.append(rec)
            if rec.get("materialized"):
                overall = "PASS"
                break
        return {"label": label, "overall": overall, "attempts": attempts}
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

    # --- line: CreateLine(x1,y1,z1, x2,y2,z2) ---
    report["sketch_line"] = _probe(
        sw,
        "sketch_line",
        [
            (
                "CreateLine(x1,y1,z1,x2,y2,z2)",
                lambda sm: sm.CreateLine(-0.02, -0.01, 0.0, 0.02, 0.01, 0.0),
            ),
        ],
    )

    # --- arc: CreateArc(center, start, end, dir) [10] then Create3PointArc [9] ---
    report["sketch_arc"] = _probe(
        sw,
        "sketch_arc",
        [
            (
                "CreateArc(cx,cy,cz, sx,sy,sz, ex,ey,ez, dir=1)",
                lambda sm: sm.CreateArc(
                    0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 1
                ),
            ),
            (
                "Create3PointArc(p1,p2,p3)",
                lambda sm: sm.Create3PointArc(
                    0.01, 0.0, 0.0, -0.01, 0.0, 0.0, 0.0, 0.01, 0.0
                ),
            ),
        ],
    )

    # --- ellipse: CreateEllipse(center, majorPt, minorPt) [9] ---
    report["sketch_ellipse"] = _probe(
        sw,
        "sketch_ellipse",
        [
            (
                "CreateEllipse(cx,cy,cz, majX,majY,majZ, minX,minY,minZ)",
                lambda sm: sm.CreateEllipse(
                    0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 0.0, 0.01, 0.0
                ),
            ),
        ],
    )

    # --- polygon: CreatePolygon(center, vertexPt, sides, inscribed) [8] ---
    report["sketch_polygon"] = _probe(
        sw,
        "sketch_polygon",
        [
            (
                "CreatePolygon(cx,cy,cz, px,py,pz, sides=6, inscribed=True)",
                lambda sm: sm.CreatePolygon(0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 6, True),
            ),
        ],
    )

    # --- slot: CreateSketchSlot(creationType, length, width, ptArray, addDims,
    #     endType, centerType, instances, flip). Pt buffer = SAFEARRAY of doubles. ---
    pts_slot = [-0.015, 0.0, 0.0, 0.015, 0.0, 0.0]  # two centerline endpoints (x,y,z)
    report["sketch_slot"] = _probe(
        sw,
        "sketch_slot",
        [
            (
                "CreateSketchSlot(0,len,wid, VARIANT[pts], True,0,0,1,False)",
                lambda sm: sm.CreateSketchSlot(
                    0, 0.03, 0.01, _vt_r8_array(pts_slot), True, 0, 0, 1, False
                ),
            ),
            (
                "CreateSketchSlot(0,len,wid, tuple[pts], True,0,0,1,False)",
                lambda sm: sm.CreateSketchSlot(
                    0, 0.03, 0.01, tuple(pts_slot), True, 0, 0, 1, False
                ),
            ),
        ],
    )

    # --- spline: CreateSpline2(ptArray, simulateBspline) then CreateSpline(ptArray) ---
    pts_spline = [-0.02, -0.01, 0.0, 0.0, 0.01, 0.0, 0.02, -0.01, 0.0]
    report["sketch_spline"] = _probe(
        sw,
        "sketch_spline",
        [
            (
                "CreateSpline2(VARIANT[pts], False)",
                lambda sm: sm.CreateSpline2(_vt_r8_array(pts_spline), False),
            ),
            (
                "CreateSpline(VARIANT[pts])",
                lambda sm: sm.CreateSpline(_vt_r8_array(pts_spline)),
            ),
            (
                "CreateSpline2(tuple[pts], False)",
                lambda sm: sm.CreateSpline2(tuple(pts_spline), False),
            ),
        ],
    )

    # --- text: candidates on ISketchManager (CreateText); IModelDoc2.InsertSketchText
    #     is probed separately below if these fail. ---
    report["sketch_text"] = _probe(
        sw,
        "sketch_text",
        [
            (
                "CreateText(text, x,y,z, flags=0)",
                lambda sm: sm.CreateText("Aa", 0.0, 0.0, 0.0, 0),
            ),
            ("CreateText(text, x,y,z)", lambda sm: sm.CreateText("Aa", 0.0, 0.0, 0.0)),
        ],
    )

    keys = [
        "sketch_line",
        "sketch_arc",
        "sketch_ellipse",
        "sketch_polygon",
        "sketch_slot",
        "sketch_spline",
        "sketch_text",
    ]
    report["summary"] = {k: report[k]["overall"] for k in keys}
    report["overall"] = (
        "PASS" if all(report[k]["overall"] == "PASS" for k in keys) else "PARTIAL"
    )
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "sketch_primitives_discovery.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
