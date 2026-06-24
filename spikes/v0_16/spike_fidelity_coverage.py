"""Spike v0.16 / P1.7-fidelity — coverage matrix for the shippable fidelity:

  A construction: for EACH segment primitive (line, arc, spline-open, slot,
    polygon, ellipse), build it with the SAME ISketchManager calls the handlers
    use, capture the return, set ConstructionGeometry=True on every segment, and
    verify read-back. (Only line+polygon were previously proven.)
  C text format: InsertSketchText -> typed(ISketchText).GetTextFormat() -> set
    CharHeight (height, metres) + TypeFaceName (font) -> SetTextFormat(0, tf) ->
    verify read-back.

Deferred-by-API (NOT spiked, proven absent earlier): spline `closed` (C0 cusp,
no MakeClosed/CreateClosedSpline/periodic on this seat) and text `angle_deg`
(no angle param on InsertSketchText / ITextFormat).

Non-destructive: own blank Parts, never saves, closes own docs.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Callable

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402
import win32com.client  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


def _prop(obj: Any, name: str) -> Any:
    v = getattr(obj, name)
    return v() if callable(v) else v


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _fresh(sw: Any) -> tuple[Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return doc, sm, _title(doc)


def _segments(result: Any) -> list[Any]:
    """Normalise a Create* return to a list of sketch segments."""
    if result is None:
        return []
    if hasattr(result, "ConstructionGeometry"):
        return [result]
    try:
        return list(result)
    except TypeError:
        return [result]


# Each builder mirrors the live handler's exact ISketchManager call.
def _mk_line(sm: Any) -> Any:
    return sm.CreateLine(-0.02, -0.01, 0.0, 0.02, 0.01, 0.0)


def _mk_arc(sm: Any) -> Any:
    return sm.CreateArc(0.0, 0.0, 0.0, 0.02, 0.0, 0.0, -0.02, 0.0, 0.0, 1)


def _mk_spline(sm: Any) -> Any:
    pts = [-0.02, -0.01, 0.0, 0.0, 0.012, 0.0, 0.02, -0.01, 0.0]
    return sm.CreateSpline2(_vt_r8(pts), False)


def _mk_slot(sm: Any) -> Any:
    return sm.CreateSketchSlot(
        0, 0, 0.01, -0.02, 0.0, 0.0, 0.02, 0.0, 0.0, 0.02, 0.005, 0.0, False, True
    )


def _mk_polygon(sm: Any) -> Any:
    return sm.CreatePolygon(0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 6, True)


def _mk_ellipse(sm: Any) -> Any:
    return sm.CreateEllipse(0.0, 0.0, 0.0, 0.03, 0.0, 0.0, 0.0, 0.015, 0.0)


def probe_construction(sw: Any, name: str, mk: Callable[[Any], Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {"primitive": name}
    doc, sm, title = _fresh(sw)
    try:
        result = mk(sm)
        segs = _segments(result)
        rec["seg_count"] = len(segs)
        marked = 0
        for s in segs:
            try:
                s.ConstructionGeometry = True
                if bool(_prop(s, "ConstructionGeometry")):
                    marked += 1
            except Exception as e:  # noqa: BLE001
                rec.setdefault("seg_errors", []).append(repr(e))
        rec["marked"] = marked
        rec["overall"] = "PASS" if segs and marked == len(segs) else "FAIL"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    return rec


def probe_text_format(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"primitive": "text"}
    doc, sm, title = _fresh(sw)
    try:
        raw = doc.InsertSketchText(0.0, 0.0, 0.0, "Aa", 0, 0, 0, 1, 1)
        st = typed(raw, "ISketchText")
        tf = st.GetTextFormat()
        rec["charheight_before"] = float(_prop(tf, "CharHeight"))
        tf.CharHeight = 0.003
        tf.TypeFaceName = "Arial"
        st.SetTextFormat(0, tf)
        tf2 = st.GetTextFormat()
        rec["charheight_after"] = float(_prop(tf2, "CharHeight"))
        rec["typeface_after"] = str(_prop(tf2, "TypeFaceName"))
        ok = (
            abs(rec["charheight_after"] - 0.003) < 1e-6
            and rec["typeface_after"] == "Arial"
        )
        rec["overall"] = "PASS" if ok else "FAIL"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
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
    cons: dict[str, Any] = {}
    for name, mk in (
        ("line", _mk_line),
        ("arc", _mk_arc),
        ("spline", _mk_spline),
        ("slot", _mk_slot),
        ("polygon", _mk_polygon),
        ("ellipse", _mk_ellipse),
    ):
        cons[name] = probe_construction(sw, name, mk)
    report["construction"] = cons
    report["text_format"] = probe_text_format(sw)

    cons_pass = [n for n, r in cons.items() if r.get("overall") == "PASS"]
    cons_fail = [n for n, r in cons.items() if r.get("overall") != "PASS"]
    report["construction_pass"] = cons_pass
    report["construction_fail"] = cons_fail
    report["overall"] = (
        "PASS"
        if not cons_fail and report["text_format"]["overall"] == "PASS"
        else "PARTIAL"
    )
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "fidelity_coverage.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
