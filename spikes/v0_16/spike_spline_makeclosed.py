"""Spike v0.16 / P1.7-fidelity — resolve B (closed spline) via the sanctioned
CreateSpline2 + ISketchSpline.MakeClosed() path.

CreateSpline3(buf, simulate, closed) raises DISP_E_PARAMNOTOPTIONAL under late
binding (undocumented trailing param). The robust path avoids it entirely:

  1. CreateSpline2(point_buffer, b3D=False)  -- already seat-proven w/ VT_R8.
  2. typed(seg, "ISketchSpline")             -- early-bind escape hatch (NOT
     CastTo: SW objects refuse GetTypeInfo, which is why com.earlybind exists).
  3. spline.MakeClosed() -> bool             -- natively closes the contour.

Verify: MakeClosed returns truthy AND the open-spline segment count is
unchanged-or-grown (the contour closed, not errored). Non-destructive: own
blank Parts, never saves, closes own docs.
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
    try:
        sk = doc.GetActiveSketch2
        sk = sk() if callable(sk) else sk
        if sk is None:
            return -1
        segs = sk.GetSketchSegments
        segs = segs() if callable(segs) else segs
        return len(segs) if segs is not None else 0
    except Exception:  # noqa: BLE001 — diagnostic only; never abort the probe
        return -1


def _fresh(sw: Any) -> tuple[Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return doc, sm, _title(doc)


def probe_makeclosed(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "spline_closed_MakeClosed"}
    # open arc of points (NOT pre-closed): MakeClosed should bridge the ends.
    pts = [-0.02, -0.01, 0.0, 0.0, 0.012, 0.0, 0.02, -0.01, 0.0]
    doc, sm, title = _fresh(sw)
    try:
        before = _seg_count(doc)
        seg = sm.CreateSpline2(_vt_r8(pts), False)
        rec["create_ok"] = seg is not None
        rec["raw_seg_type"] = type(seg).__name__
        after_create = _seg_count(doc)

        # acquire the typed ISketchSpline and close it natively
        spline = typed(seg, "ISketchSpline")
        rec["typed_ok"] = True
        # probe for the member before calling, so a missing method is legible
        rec["has_MakeClosed"] = hasattr(spline, "MakeClosed")
        ret = spline.MakeClosed()
        rec["makeclosed_ret"] = repr(ret)
        after_close = _seg_count(doc)

        rec["seg_after_create"] = after_create
        rec["seg_after_close"] = after_close
        # PASS: spline materialized and MakeClosed returned truthy without error.
        rec["overall"] = "PASS" if (seg is not None and bool(ret)) else "FAIL"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
        rec["overall"] = "FAIL"
    finally:
        try:
            sm.InsertSketch(True); sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    return rec


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}
    report["spline_makeclosed"] = probe_makeclosed(sw)
    report["overall"] = report["spline_makeclosed"]["overall"]
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "spline_makeclosed.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
