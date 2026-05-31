"""Seat-check (PAE) — drive the SHIPPED P1.7-fidelity handler behaviour live.

Builds on _seatcheck_sketch_primitives_pae.py (which proves the 7 primitives
materialise). This proves the FULL-FIDELITY wiring end-to-end through the actual
builder handlers:

  A construction: line/arc/spline/polygon/ellipse built with construction=True
    materialise AND the resulting sketch contains a construction segment
    (re-acquire ISketch -> GetSketchSegments -> any ConstructionGeometry True).
  C text format: text built with height+font materialises; re-acquire the
    ISketchText and read back CharHeight (== 3 mm) and TypeFaceName (== Arial).
  Rejections: spline closed / slot construction / text construction / text
    angle_deg each raise NotImplementedError (the handler tripwire), never fake.

Non-destructive: own blank Part via NewDocument, never saves, closes own doc.
Run with PYTHONPATH=<worktree>/src so the worktree handlers load.
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.spec import builder  # noqa: E402
from ai_sw_bridge.spec._build_context import BuildContext  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8

CONSTRUCTION_FEATURES: list[dict[str, Any]] = [
    {"type": "sketch_line", "name": "CF_Line", "plane": "Front",
     "start": {"x": 0.0, "y": 0.0}, "end": {"x": 20.0, "y": 20.0}, "construction": True},
    {"type": "sketch_arc", "name": "CF_Arc", "plane": "Front",
     "center": {"x": 30.0, "y": 0.0}, "start": {"x": 40.0, "y": 0.0},
     "end": {"x": 30.0, "y": 10.0}, "construction": True},
    {"type": "sketch_spline", "name": "CF_Spline", "plane": "Front",
     "points": [{"x": 0.0, "y": 30.0}, {"x": 10.0, "y": 35.0}, {"x": 20.0, "y": 30.0}],
     "construction": True},
    {"type": "sketch_polygon", "name": "CF_Polygon", "plane": "Front",
     "center": {"x": 50.0, "y": 30.0}, "sides": 6, "radius": 8.0, "construction": True},
    {"type": "sketch_ellipse", "name": "CF_Ellipse", "plane": "Front",
     "center": {"x": 70.0, "y": 30.0}, "major_radius": 10.0, "minor_radius": 5.0,
     "construction": True},
]

TEXT_FEATURE = {"type": "sketch_text", "name": "CF_Text", "plane": "Front",
                "position": {"x": 0.0, "y": 50.0}, "content": "AaBb",
                "height": 3.0, "font": "Arial"}

REJECTIONS: list[dict[str, Any]] = [
    {"type": "sketch_spline", "name": "RJ_SplineClosed", "plane": "Front",
     "points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 5.0}], "closed": True},
    {"type": "sketch_slot", "name": "RJ_SlotCons", "plane": "Front",
     "center": {"x": 30.0, "y": 30.0}, "width": 6.0, "length": 20.0, "construction": True},
    {"type": "sketch_text", "name": "RJ_TextCons", "plane": "Front",
     "position": {"x": 0.0, "y": 0.0}, "content": "x", "height": 3.0, "construction": True},
    {"type": "sketch_text", "name": "RJ_TextAngle", "plane": "Front",
     "position": {"x": 0.0, "y": 0.0}, "content": "x", "height": 3.0, "angle_deg": 45.0},
]


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _feature_count(doc: Any) -> int:
    gc = doc.GetFeatureCount
    return int(gc() if callable(gc) else gc)


def _sketch_of(sw_object: Any) -> Any:
    """Early-bound ISketch from a BuiltFeature's sw_object (the sketch IFeature).

    The late-bound chain (feature.GetSpecificFeature2 -> sketch) trips
    'Member not found' on this seat; typed IFeature.GetSpecificFeature2()
    (compiled dispid) clears it, then typed ISketch.
    """
    feat = typed(sw_object, "IFeature")
    return typed(feat.GetSpecificFeature2(), "ISketch")


def _sketch_has_construction(sw_object: Any) -> bool | str:
    """Report whether any of the sketch's segments is construction geometry."""
    try:
        sk = _sketch_of(sw_object)
        segs = sk.GetSketchSegments()
        seq = list(segs) if segs is not None else []
        flags = [bool(typed(s, "ISketchSegment").ConstructionGeometry) for s in seq]
        return any(flags) if flags else "no-segments"
    except Exception as e:  # noqa: BLE001
        return f"read-error: {e!r}"


def _read_text_format(sw_object: Any) -> dict[str, Any]:
    try:
        sk = _sketch_of(sw_object)
        texts = sk.GetSketchTextSegments()
        seq = list(texts) if texts is not None else []
        if not seq:
            return {"error": "no text segments"}
        st = typed(seq[0], "ISketchText")
        tf = st.GetTextFormat()
        return {"char_height": float(tf.CharHeight),
                "typeface": str(tf.TypeFaceName),
                "text_count": len(seq)}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber)}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None"}
    title = _title(doc)
    ctx = BuildContext(sw=sw, doc=doc, no_dim=True)
    try:
        # A — construction
        cons: list[dict[str, Any]] = []
        for feat in CONSTRUCTION_FEATURES:
            rec: dict[str, Any] = {"type": feat["type"], "name": feat["name"]}
            before = _feature_count(doc)
            try:
                bf = builder.HANDLERS[feat["type"]](ctx, feat)
                doc.ForceRebuild3(False)
                rec["count_delta"] = _feature_count(doc) - before
                rec["has_construction"] = _sketch_has_construction(bf.sw_object)
                rec["overall"] = "PASS" if (rec["count_delta"] > 0 and rec["has_construction"] is True) else "FAIL"
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
                rec["overall"] = "FAIL"
            cons.append(rec)
            doc.ClearSelection2(True)
        report["construction"] = cons

        # C — text format
        trec: dict[str, Any] = {"name": TEXT_FEATURE["name"]}
        before = _feature_count(doc)
        try:
            bf_text = builder.HANDLERS["sketch_text"](ctx, TEXT_FEATURE)
            doc.ForceRebuild3(False)
            trec["count_delta"] = _feature_count(doc) - before
            fmt = _read_text_format(bf_text.sw_object)
            trec["format"] = fmt
            ch_ok = isinstance(fmt.get("char_height"), float) and abs(fmt["char_height"] - 0.003) < 1e-6
            tn_ok = fmt.get("typeface") == "Arial"
            trec["overall"] = "PASS" if (trec["count_delta"] > 0 and ch_ok and tn_ok) else "FAIL"
        except Exception as e:  # noqa: BLE001
            trec["error"] = repr(e)
            trec["overall"] = "FAIL"
        report["text_format"] = trec
        doc.ClearSelection2(True)

        # Rejections
        rej: list[dict[str, Any]] = []
        for feat in REJECTIONS:
            r: dict[str, Any] = {"name": feat["name"]}
            try:
                builder.HANDLERS[feat["type"]](ctx, feat)
                r["overall"] = "FAIL"  # should have raised
                r["note"] = "no exception raised"
            except NotImplementedError as e:
                r["overall"] = "PASS"
                r["raised"] = str(e)[:80]
            except Exception as e:  # noqa: BLE001
                r["overall"] = "FAIL"
                r["wrong_exception"] = repr(e)
            rej.append(r)
            doc.ClearSelection2(True)
        report["rejections"] = rej

        a_ok = all(r["overall"] == "PASS" for r in cons)
        c_ok = trec["overall"] == "PASS"
        r_ok = all(r["overall"] == "PASS" for r in rej)
        report["overall"] = "PASS" if (a_ok and c_ok and r_ok) else "PARTIAL"
        return report
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "sketch_fidelity_pae.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
