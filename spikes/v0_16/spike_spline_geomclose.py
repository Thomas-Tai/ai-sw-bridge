"""Spike v0.16 / P1.7-fidelity — B resolved via GEOMETRIC close.

SW-2024 typelib falsified the documented closed-spline paths:
  * ISketchSpline has NO MakeClosed (only AddTangencyControl / GetSplineHandles
    / RelaxSpline).
  * CreateSpline3(PointData, Surfs, Direction, SimulateNaturalEnds, Status) is
    the spline-ON-SURFACE overload -- no `Closed` param (hence PARAMNOTOPTIONAL).

The honest, proven-primitive path: feed CreateSpline2 a point list whose LAST
point equals the FIRST. The endpoints coincide -> a closed sketch contour.

Verification (the discriminator): build an OPEN spline (last != first) and a
GEOMETRICALLY-CLOSED one (last == first) in separate fresh sketches, count the
closed sketch contours each yields. Closed must produce >= 1 closed contour
that the open one does not. Non-destructive: own blank Parts, never saves.
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

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _active_sketch(doc: Any) -> Any:
    sk = doc.GetActiveSketch2
    return sk() if callable(sk) else sk


def _closed_contour_count(doc: Any) -> int:
    """Closed sketch contours in the active sketch, or -1 if unreadable."""
    try:
        sk = _active_sketch(doc)
        if sk is None:
            return -1
        contours = sk.GetSketchContours
        contours = contours() if callable(contours) else contours
        if contours is None:
            return 0
        seq = list(contours) if not isinstance(contours, (int, float, str)) else []
        return len(seq)
    except Exception:  # noqa: BLE001
        return -1


def _fresh(sw: Any) -> tuple[Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return doc, sm, _title(doc)


def _build_spline(sw: Any, pts: list[float]) -> dict[str, Any]:
    rec: dict[str, Any] = {}
    doc, sm, title = _fresh(sw)
    try:
        seg = sm.CreateSpline2(_vt_r8(pts), False)
        rec["materialized"] = seg is not None
        rec["seg_type"] = type(seg).__name__
        # close the sketch so contours are computed, then re-read is not needed:
        # GetSketchContours is valid while the sketch is active.
        rec["closed_contours"] = _closed_contour_count(doc)
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["materialized"] = False
        rec["closed_contours"] = -1
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    return rec


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}

    open_pts = [-0.02, -0.01, 0.0, 0.0, 0.012, 0.0, 0.02, -0.01, 0.0]
    closed_pts = open_pts + open_pts[0:3]  # repeat first point as last

    report["open"] = _build_spline(sw, open_pts)
    report["closed"] = _build_spline(sw, closed_pts)

    o = report["open"].get("closed_contours", -1)
    c = report["closed"].get("closed_contours", -1)
    materialized = report["closed"].get("materialized") and report["open"].get(
        "materialized"
    )
    # PASS: closed-point spline yields a closed contour the open one does not.
    report["discriminates"] = materialized and c >= 1 and c > o
    report["overall"] = "PASS" if report["discriminates"] else "INVESTIGATE"
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "spline_geomclose.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
