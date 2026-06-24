"""Spike v0.16 / P1.7-fidelity — discover the live APIs for the three deferred
sketch-primitive flags: construction geometry, spline `closed`, and text format
(height / font / angle).

Builds on the seat-proven Create* signatures (spike_sketch_primitives.py). Each
probe runs in its own fresh blank Part + Front-Plane sketch and records the
verbatim outcome so the handlers can wire the proven path (and any wall is
surfaced for a decision rather than fought blindly).

  A construction — ISketchSegment.ConstructionGeometry settable bool? Verify
                    read-back True after set, on a line and across a polygon's
                    multiple segments.
  B spline closed — is there a closed-spline path? Probe CreateClosedSpline,
                    and inspect what CreateSpline2 returns for a SetClosed-like
                    member. Record what actually produces a closed contour.
  C text format   — InsertSketchText(useDocFmt=0) then GetTextFormat -> set
                    CharHeight / TypeFaceName / angle -> SetTextFormat; verify
                    read-back. ITextFormat marshaling is the load-bearing risk.

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


def _prop(obj: Any, name: str) -> Any:
    """Read a possibly-callable COM property/method by name."""
    v = getattr(obj, name)
    return v() if callable(v) else v


def _fresh(sw: Any) -> tuple[Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return doc, sm, _title(doc)


def probe_construction(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "construction"}
    doc, sm, title = _fresh(sw)
    try:
        # single segment (line)
        seg = sm.CreateLine(-0.02, -0.01, 0.0, 0.02, 0.01, 0.0)
        before = _prop(seg, "ConstructionGeometry")
        seg.ConstructionGeometry = True
        after = _prop(seg, "ConstructionGeometry")
        rec["line_before"] = bool(before)
        rec["line_after_set_true"] = bool(after)
        rec["line_ok"] = bool(after) and not bool(before)
    except Exception as e:  # noqa: BLE001
        rec["line_error"] = repr(e)
        rec["line_ok"] = False
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # multi-segment (polygon returns a tuple of segments)
    doc, sm, title = _fresh(sw)
    try:
        result = sm.CreatePolygon(0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 6, True)
        segs = list(result) if not isinstance(result, (int, float, str)) else []
        marked = 0
        for s in segs:
            try:
                s.ConstructionGeometry = True
                if bool(_prop(s, "ConstructionGeometry")):
                    marked += 1
            except Exception:  # noqa: BLE001
                pass
        rec["polygon_seg_count"] = len(segs)
        rec["polygon_marked"] = marked
        rec["polygon_ok"] = marked > 0 and marked == len(segs)
    except Exception as e:  # noqa: BLE001
        rec["polygon_error"] = repr(e)
        rec["polygon_ok"] = False
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    rec["overall"] = "PASS" if rec.get("line_ok") and rec.get("polygon_ok") else "FAIL"
    return rec


def probe_spline_closed(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "spline_closed", "attempts": []}
    pts = [-0.02, -0.01, 0.0, 0.0, 0.01, 0.0, 0.02, -0.01, 0.0]

    # 1: does a CreateClosedSpline-style member exist on the sketch manager?
    doc, sm, title = _fresh(sw)
    try:
        names = [
            n
            for n in ("CreateClosedSpline", "CreateClosedSpline2", "CreateSpline3")
            if hasattr(sm, n)
        ]
        rec["sketchmgr_closed_members_present"] = names
    except Exception as e:  # noqa: BLE001
        rec["member_probe_error"] = repr(e)
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # 2: CreateSpline2 then inspect the returned segment for a SetClosed/IsClosed
    doc, sm, title = _fresh(sw)
    try:
        seg = sm.CreateSpline2(_vt_r8(pts), False)
        seg_members = [
            n
            for n in ("IGetSplineParams", "SetEnds", "Closed", "IsClosed", "SetClosed")
            if hasattr(seg, n)
        ]
        rec["spline_seg_members_present"] = seg_members
        rec["spline_seg_type"] = type(seg).__name__
    except Exception as e:  # noqa: BLE001
        rec["spline_inspect_error"] = repr(e)
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # 3: geometric close — append first point as the last point
    doc, sm, title = _fresh(sw)
    try:
        closed_pts = pts + pts[0:3]
        seg = sm.CreateSpline2(_vt_r8(closed_pts), False)
        rec["geometric_close_materialized"] = seg is not None
    except Exception as e:  # noqa: BLE001
        rec["geometric_close_error"] = repr(e)
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    rec["overall"] = "INVESTIGATE"  # decision-needed: report findings, do not auto-pick
    return rec


def probe_text_format(sw: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "text_format"}
    doc, sm, title = _fresh(sw)
    try:
        # useDocFmt=0 so a custom format can take effect.
        text = doc.InsertSketchText(0.0, 0.0, 0.0, "Aa", 0, 0.0, 0.0, 0.0, 0.0)
        rec["text_type"] = type(text).__name__
        rec["text_is_none"] = text is None
        if text is not None:
            # GetTextFormat: try property-style then call-style.
            tf = None
            for style in ("prop", "call"):
                try:
                    raw = getattr(text, "GetTextFormat")
                    tf = raw() if style == "call" else (raw() if callable(raw) else raw)
                    if tf is not None:
                        rec["gettextformat_style"] = style
                        break
                except Exception as e:  # noqa: BLE001
                    rec[f"gettextformat_{style}_error"] = repr(e)
            rec["tf_type"] = type(tf).__name__ if tf is not None else None
            if tf is not None:
                try:
                    rec["tf_charheight_before"] = float(_prop(tf, "CharHeight"))
                except Exception as e:  # noqa: BLE001
                    rec["tf_charheight_read_error"] = repr(e)
                for attr, val in (("CharHeight", 0.003), ("TypeFaceName", "Arial")):
                    try:
                        setattr(tf, attr, val)
                        rec[f"tf_set_{attr}_ok"] = True
                    except Exception as e:  # noqa: BLE001
                        rec[f"tf_set_{attr}_error"] = repr(e)
                # push the format back: SetTextFormat(which, useDoc, fmt)
                for sig, args in (
                    ("SetTextFormat(0,False,tf)", (0, False, tf)),
                    ("SetTextFormat(tf)", (tf,)),
                ):
                    try:
                        ok = text.SetTextFormat(*args)
                        rec["settextformat_sig"] = sig
                        rec["settextformat_ret"] = repr(ok)
                        break
                    except Exception as e:  # noqa: BLE001
                        rec[f"settextformat_{sig}_error"] = repr(e)
                try:
                    tf2 = getattr(text, "GetTextFormat")
                    tf2 = tf2() if callable(tf2) else tf2
                    rec["tf_charheight_after"] = float(_prop(tf2, "CharHeight"))
                except Exception as e:  # noqa: BLE001
                    rec["tf_charheight_after_error"] = repr(e)
    except Exception as e:  # noqa: BLE001
        rec["text_error"] = repr(e)
    finally:
        try:
            sm.InsertSketch(True)
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass
    height_applied = (
        rec.get("settextformat_sig") is not None
        and rec.get("tf_charheight_after") not in (None,)
        and abs(rec.get("tf_charheight_after", 0.0) - 0.003) < 1e-6
    )
    rec["overall"] = "PASS" if height_applied else "INVESTIGATE"
    return rec


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}
    report["construction"] = probe_construction(sw)
    report["spline_closed"] = probe_spline_closed(sw)
    report["text_format"] = probe_text_format(sw)
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "sketch_fidelity_discovery.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
