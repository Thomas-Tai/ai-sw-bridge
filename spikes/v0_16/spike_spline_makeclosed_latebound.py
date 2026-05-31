"""Spike v0.16 / P1.7-fidelity — does MakeClosed() exist on the LIVE object?

The earlier FAIL ("ISketchSpline has no MakeClosed") came from the EARLY-bound
typed wrap, which can only call members makepy compiled from the typelib. Late
binding resolves members through the live object's IDispatch::GetIDsOfNames and
can reach members the generated module lacks. Before falling back to geometric
close, test the user's exact path the late-bound way (true C2-periodic closure
is the correct intent for `closed: true`).

Four routes, each on its own fresh open spline:
  R1 raw late-bound seg.MakeClosed()           -- the untested path
  R2 win32com.client.CastTo(seg,'ISketchSpline').MakeClosed()
  R3 early-bound typed(seg,'ISketchSpline')     -- known to lack the member
  R4 _oleobj_.GetIDsOfNames('MakeClosed')       -- does the vtable name resolve?

Non-destructive: own blank Parts, never saves, closes own docs.
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
PTS = [-0.02, -0.01, 0.0, 0.0, 0.012, 0.0, 0.02, -0.01, 0.0]


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


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


def _spline(sm: Any) -> Any:
    return sm.CreateSpline2(_vt_r8(PTS), False)


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}

    # R1: raw late-bound MakeClosed on the CDispatch segment
    rec: dict[str, Any] = {}
    doc, sm, title = _fresh(sw)
    try:
        seg = _spline(sm)
        rec["seg_type"] = type(seg).__name__
        ret = seg.MakeClosed()
        rec["ret"] = repr(ret)
        rec["overall"] = "PASS" if bool(ret) else "RETURNED_FALSE"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        try:
            sm.InsertSketch(True); sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    report["R1_raw_latebound"] = rec

    # R2: CastTo then MakeClosed
    rec = {}
    doc, sm, title = _fresh(sw)
    try:
        seg = _spline(sm)
        casted = win32com.client.CastTo(seg, "ISketchSpline")
        rec["cast_type"] = type(casted).__name__
        ret = casted.MakeClosed()
        rec["ret"] = repr(ret)
        rec["overall"] = "PASS" if bool(ret) else "RETURNED_FALSE"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        try:
            sm.InsertSketch(True); sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    report["R2_castto"] = rec

    # R3: early-bound typed (expected to lack the member)
    rec = {}
    doc, sm, title = _fresh(sw)
    try:
        seg = _spline(sm)
        st = typed(seg, "ISketchSpline")
        ret = st.MakeClosed()
        rec["ret"] = repr(ret)
        rec["overall"] = "PASS" if bool(ret) else "RETURNED_FALSE"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        try:
            sm.InsertSketch(True); sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    report["R3_earlybound"] = rec

    # R4: does the dispatch resolve the name at all?
    rec = {}
    doc, sm, title = _fresh(sw)
    try:
        seg = _spline(sm)
        raw = getattr(seg, "_oleobj_", None)
        rec["has_oleobj"] = raw is not None
        if raw is not None:
            try:
                dispid = raw.GetIDsOfNames("MakeClosed")
                rec["dispid"] = repr(dispid)
                rec["name_resolves"] = True
            except Exception as e:  # noqa: BLE001
                rec["getidsofnames_error"] = repr(e)
                rec["name_resolves"] = False
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
    finally:
        try:
            sm.InsertSketch(True); sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    report["R4_getidsofnames"] = rec

    routes = ("R1_raw_latebound", "R2_castto", "R3_earlybound")
    report["any_makeclosed_works"] = any(report[r].get("overall") == "PASS" for r in routes)
    report["overall"] = "PASS" if report["any_makeclosed_works"] else "FAIL"
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "spline_makeclosed_latebound.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
