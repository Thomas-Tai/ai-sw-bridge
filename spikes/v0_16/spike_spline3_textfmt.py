"""Spike v0.16 / P1.7-fidelity — resolve B (closed spline) and C (text format)
with the corrected API paths.

B: CreateSpline3(pointBuffer, simulateBspline, closed) — 3 args; swap from
   CreateSpline2 and pass closed=True for a true periodic spline.
C: InsertSketchText(useDocFmt=0) returns an ISketchText that pywin32 wraps as a
   generic IDispatch (so GetTextFormat = "Member not found"). Force the typed
   interface via com.earlybind.typed(obj, "ISketchText") — the proven escape
   hatch that bypasses the GetTypeInfo block CastTo trips on — then
   GetTextFormat() -> mutate CharHeight/TypeFaceName -> SetTextFormat(0, tf),
   verify CharHeight read-back.

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


def _vt_r8(vals: list[float]) -> Any:
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _prop(obj: Any, name: str) -> Any:
    v = getattr(obj, name)
    return v() if callable(v) else v


def _seg_count(doc: Any) -> int:
    sk = doc.GetActiveSketch2
    if sk is None:
        return 0
    try:
        segs = sk.GetSketchSegments
        segs = segs() if callable(segs) else segs
        return len(segs) if segs is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def _fresh(sw: Any) -> tuple[Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return doc, sm, _title(doc)


def probe_spline3(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "spline_closed_CreateSpline3"}
    pts = [-0.02, -0.01, 0.0, 0.0, 0.01, 0.0, 0.02, -0.01, 0.0, 0.0, -0.02, 0.0]
    doc, sm, title = _fresh(sw)
    try:
        before = _seg_count(doc)
        seg = sm.CreateSpline3(_vt_r8(pts), False, True)  # closed=True
        after = _seg_count(doc)
        rec["result_type"] = type(seg).__name__
        rec["seg_delta"] = after - before
        rec["materialized"] = seg is not None and (after - before) > 0
        rec["overall"] = "PASS" if rec["materialized"] else "FAIL"
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
    rec: dict[str, Any] = {"feature": "text_format_typed"}
    doc, sm, title = _fresh(sw)
    try:
        raw_text = doc.InsertSketchText(0.0, 0.0, 0.0, "Aa", 0, 0.0, 0.0, 0.0, 0.0)
        rec["raw_text_type"] = type(raw_text).__name__
        # Force the typed ISketchText interface (escape hatch).
        st = typed(raw_text, "ISketchText")
        rec["typed_ok"] = True
        tf = st.GetTextFormat()
        rec["tf_type"] = type(tf).__name__
        rec["charheight_before"] = float(_prop(tf, "CharHeight"))
        # mutate — try on the returned tf directly; if it is generic, type it.
        try:
            tf.CharHeight = 0.003
            tf.TypeFaceName = "Arial"
            rec["mutate_direct_ok"] = True
        except Exception as e:  # noqa: BLE001
            rec["mutate_direct_error"] = repr(e)
            tf = typed(tf, "ITextFormat")
            tf.CharHeight = 0.003
            tf.TypeFaceName = "Arial"
            rec["mutate_typed_ok"] = True
        st.SetTextFormat(0, tf)
        # verify
        tf2 = st.GetTextFormat()
        rec["charheight_after"] = float(_prop(tf2, "CharHeight"))
        rec["typeface_after"] = str(_prop(tf2, "TypeFaceName"))
        applied = abs(rec["charheight_after"] - 0.003) < 1e-6
        rec["overall"] = "PASS" if applied else "FAIL"
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
    report["spline3"] = probe_spline3(sw)
    report["text_format"] = probe_text_format(sw)
    keys = ("spline3", "text_format")
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
    out = Path(__file__).parent / "_results" / "spline3_textfmt.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
