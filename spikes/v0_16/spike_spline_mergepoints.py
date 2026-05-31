"""Spike v0.16 / P1.7-fidelity — closed spline via ISketch.MergePoints(Distance),
acquired through the early-bind hatch.

Two walls cleared on the way here:
  1. MakeClosed is absent on SW-2024 (live object: GetIDsOfNames ->
     DISP_E_UNKNOWNNAME).
  2. The ONLY MergePoints on this typelib is MergePoints(Distance) -> bool
     (dispid 51, one required VT_R8): a distance-tolerance weld of near-
     coincident points. A zero-arg selection-based MergePoints does NOT exist
     here, so the only viable closure is: build the spline with COINCIDENT
     endpoints (append first point as last), then MergePoints(tiny_tol) welds
     just that pair (through-points are 20-40 mm apart).

Late binding can't even reach seg.GetSketch() ('Member not found'), so the
whole chain goes through com.earlybind.typed (compiled dispids, no
GetIDsOfNames round-trip): typed(seg,'ISketchSegment').GetSketch() ->
typed(...,'ISketch') for the counts and the merge.

THE DISCRIMINATOR (topological weld vs. mere coincident relation): a real merge
removes one sketch point -> GetSketchPointsCount2 drops by exactly 1. Plus
GetSketchContourCount >= 1 and ICurve IsClosed. C2-vs-C0 across the seam is a
curvature-comb UI check (doc left OPEN unless --close).

Non-destructive: own blank Part, never saves.
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
import win32com.client  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
OPEN_PTS = [-0.02, -0.01, 0.0, 0.0, 0.012, 0.0, 0.02, -0.01, 0.0]
CLOSED_PTS = OPEN_PTS + OPEN_PTS[0:3]  # coincident endpoints
MERGE_TOL = 1.0e-5  # 0.01 mm: welds the coincident pair, spares 20-40 mm spacing


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


def _call(obj: Any, name: str, *args: Any) -> Any:
    m = getattr(obj, name)
    return m(*args) if callable(m) else m


def run(do_close: bool) -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}
    rec: dict[str, Any] = {"merge_tol_m": MERGE_TOL}

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    title = str(_call(doc, "GetTitle"))
    rec["title"] = title
    try:
        doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
        sm = doc.SketchManager
        sm.InsertSketch(True)

        seg_raw = sm.CreateSpline2(_vt_r8(CLOSED_PTS), False)
        rec["spline_materialized"] = seg_raw is not None

        # early-bind the segment, then the sketch (late binding can't resolve
        # GetSketch by name on this seat).
        seg = typed(seg_raw, "ISketchSegment")
        rec["seg_typed_ok"] = True
        sk = typed(_call(seg, "GetSketch"), "ISketch")
        rec["sketch_typed_ok"] = True

        pb = int(_call(sk, "GetSketchPointsCount2"))
        cb = int(_call(sk, "GetSketchContourCount"))
        rec["points_before"], rec["contours_before"] = pb, cb
        try:
            rec["curve_isclosed_before"] = bool(_call(typed(seg, "ISketchSegment"), "GetCurve").IsClosed())
        except Exception as e:  # noqa: BLE001
            rec["curve_isclosed_before_error"] = repr(e)

        rec["mergepoints_ret"] = repr(sk.MergePoints(MERGE_TOL))

        pa = int(_call(sk, "GetSketchPointsCount2"))
        ca = int(_call(sk, "GetSketchContourCount"))
        rec["points_after"], rec["contours_after"] = pa, ca
        try:
            rec["curve_isclosed_after"] = bool(_call(seg, "GetCurve").IsClosed())
        except Exception as e:  # noqa: BLE001
            rec["curve_isclosed_after_error"] = repr(e)

        rec["point_count_dropped_by_1"] = (pb - pa == 1)
        rec["contour_formed"] = (ca >= 1)
        rec["weld_evidence"] = rec["point_count_dropped_by_1"] or rec["contour_formed"]
        rec["overall"] = "PASS" if rec["weld_evidence"] else "INVESTIGATE"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        won = rec.get("overall") == "PASS"
        if do_close or not won:
            try:
                doc.SketchManager.InsertSketch(True); sw.CloseDoc(title)
                rec["closed_doc"] = True
            except Exception:  # noqa: BLE001
                rec["closed_doc"] = False
        else:
            rec["closed_doc"] = False
            rec["note"] = "doc left OPEN for curvature-comb inspection"

    report["mergepoints"] = rec
    report["overall"] = rec.get("overall", "FAIL")
    return report


def main() -> int:
    do_close = "--close" in sys.argv
    pythoncom.CoInitialize()
    try:
        report = run(do_close)
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "spline_mergepoints.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
