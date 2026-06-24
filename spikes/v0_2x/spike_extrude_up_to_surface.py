"""W67 P5 / Tier 2 — prove (or wall) the UP-TO-SURFACE boss end condition.

** STAGED — DO NOT FIRE until W0 authorizes (Tier 1 must pass the offline suite
   first). Requires a live SOLIDWORKS seat. **

Tier 1 shipped the *self-contained* boss end conditions (midplane / through_all /
two_direction) — their terminus is a depth or existing geometry, so they need no
reference entity. The UP-TO family (UpToSurface=4, UpToSelection=10) is a
different risk class: ``FeatureExtrusion2`` has **no explicit reference-entity
argument** — the up-to target is read off the **selection stack**. The open
question this spike answers empirically:

  1. Which selection MARK does FeatureExtrusion2 expect the up-to reference on?
     (The sketch contour is Mark 0; the reference plane/face is Mark 1 or 2 —
     we do not guess, we probe each and report which one terminates correctly.)
  2. Does T1 = swEndCondUpToSelection (10) land, or must we fall back to
     swEndCondUpToSurface (4)? (Both carry SW's "prefer UpToSelection" note, so
     10 is primary, 4 is the fallback.)

FIXTURE (per W0 spec):
  * 100 x 100 x 10 mm block (Boss base).
  * A reference plane offset 50 mm ABOVE the block's top face -> z = +60 mm.
  * A Ø20 mm circle sketched on the block's top face (z = +10 mm).

EXECUTION: select the sketch (Mark 0) + append-select the up-to target, then
fire FeatureExtrusion2 with T1 read from the selection stack. We sweep the
reference mark {0,1,2} x end-condition {10, 4} and record, for each combo,
whether the boss materialised and where its bbox top landed.

VERIFICATION (the anti-ghost witness): the resulting solid's bbox Zmax must
match the up-to TARGET height (the +60 mm ref plane), NOT the sketch's blind
depth. A boss that ignores the up-to selection would stop at its default depth
(or not grow Z at all) -> bbox Zmax != 60 mm -> NO_OP. PASS demands
``abs(bbox_zmax_mm - 60.0) < tol``.

VERDICT:
  PROVEN   — at least one (mark, end_cond) combo terminated at the target plane.
  WALLED   — every combo materialised but none honoured the up-to target.
  ERROR    — fixture / COM fault (diagnose before trusting any wall).

Non-destructive: own blank Part, never saves, CloseAllDocuments(True) in finally.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import _feature_spike_fixtures as fx  # noqa: E402

from ai_sw_bridge.sw_types import (  # noqa: E402
    SW_END_COND_UP_TO_SELECTION,
    SW_END_COND_UP_TO_SURFACE,
)

# -- Fixture geometry (metres; SW internal unit) -----------------------------
BLOCK_HALF = 0.050  # 100 mm side -> +/-50 mm
BLOCK_THICK = 0.010  # 10 mm tall  -> top face at z = +10 mm
TOP_Z = BLOCK_THICK
PLANE_OFFSET = 0.050  # ref plane 50 mm ABOVE the top face -> z = +60 mm
TARGET_Z = TOP_Z + PLANE_OFFSET  # 0.060 m
CIRCLE_R = 0.010  # Ø20 mm boss
BBOX_TOL_MM = 0.05  # bbox match tolerance
_BLIND = 0


def _null_disp() -> Any:
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _resolve(obj: Any, attr: str) -> Any:
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _build_block_100(sw: Any) -> Any:
    """100x100x10 mm solid box (Boss-Extrude1, consumes Sketch1). Returns the
    raw late-bound doc."""
    doc = sw.NewDocument(fx.PART_TEMPLATE, 0, 0, 0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(
        -BLOCK_HALF, -BLOCK_HALF, 0.0, BLOCK_HALF, BLOCK_HALF, 0.0
    )
    doc.SketchManager.InsertSketch(True)  # close Sketch1
    doc.ClearSelection2(True)
    fx._select_feature(doc, "Sketch1")
    doc.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        _BLIND,
        0,
        BLOCK_THICK,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _offset_plane(doc: Any) -> str:
    """Reference plane parallel to the top face, +50 mm above it (z = +60 mm).
    Returns the plane's feature name."""
    doc.Extension.SelectByID2("", "FACE", 0.0, 0.0, TOP_Z, False, 0, _null_disp(), 0)
    REF_DIST = 8  # swRefPlaneReferenceConstraints_Distance
    plane_feat = doc.FeatureManager.InsertRefPlane(
        REF_DIST, PLANE_OFFSET, 0, 0.0, 0, 0.0
    )
    doc.ClearSelection2(True)
    if plane_feat is None:
        raise RuntimeError("InsertRefPlane returned None")
    return _resolve(plane_feat, "Name")


def _sketch_circle_on_top(doc: Any) -> str:
    """Ø20 mm circle on the block's top face -> persists as the next Sketch.
    Returns the sketch feature name."""
    doc.Extension.SelectByID2("", "FACE", 0.0, 0.0, TOP_Z, False, 0, _null_disp(), 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCircle(0.0, 0.0, 0.0, CIRCLE_R, 0.0, 0.0)
    doc.SketchManager.InsertSketch(True)  # close (non-empty -> persists)
    doc.ClearSelection2(True)
    return fx._last_sketch_name(doc)


def _select_stack(doc: Any, sketch_name: str, plane_name: str, ref_mark: int) -> dict:
    """Build the up-to selection stack: sketch on Mark 0, ref plane on
    ``ref_mark``. Returns a dump of what the SelectionManager actually holds so
    a wall verdict stays diagnosable."""
    doc.ClearSelection2(True)
    fx._select_feature(doc, sketch_name, append=False)  # Mark 0
    # append-select the up-to reference plane at the candidate mark
    plane = doc.FeatureByName(plane_name)
    if plane is None:
        return {"error": f"FeatureByName({plane_name!r}) -> None"}
    plane.Select2(True, ref_mark)
    # Pure telemetry: must NEVER abort the experiment. The real witness is the
    # post-extrude bbox Zmax, so wrap the entire dump defensively. Proven idiom:
    # GetSelectedObjectCount2(-1) (-1 = all marks), GetSelectedObjectType3(i,-1).
    dump: dict[str, Any] = {"requested_ref_mark": ref_mark}
    try:
        sm = doc.SelectionManager
        count = int(sm.GetSelectedObjectCount2(-1))
        dump["selected_count"] = count
        marks = []
        for i in range(1, count + 1):
            try:
                marks.append(
                    {
                        "idx": i,
                        "mark": sm.GetSelectedObjectMark(i),
                        "type": sm.GetSelectedObjectType3(i, -1),
                    }
                )
            except Exception as e:  # noqa: BLE001
                marks.append({"idx": i, "error": f"{type(e).__name__}: {e}"[:120]})
        dump["marks"] = marks
    except Exception as e:  # noqa: BLE001
        dump["telemetry_error"] = f"{type(e).__name__}: {e}"[:160]
    return dump


def _fire_extrude(doc: Any, end_cond: int) -> Any:
    """FeatureExtrusion2 with T1 read off the selection stack (up-to). D1 is
    ignored for up-to end conditions but must be a valid float."""
    fm = doc.FeatureManager
    return fm.FeatureExtrusion2(
        True,
        False,
        False,
        end_cond,
        0,
        0.001,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    )


def _body_bbox_zmax_mm(doc: Any) -> float | None:
    """Zmax (mm) of the first solid body. GetBodyBox -> [xmin..zmax] in metres."""
    try:
        bodies = doc.GetBodies2(0, False)  # swSolidBody=0, visibleOnly=False
    except Exception:
        return None
    blist = (
        list(bodies)
        if isinstance(bodies, (list, tuple))
        else ([bodies] if bodies else [])
    )
    if not blist:
        return None
    try:
        box = blist[0].GetBodyBox
        box = box() if callable(box) else box
        return float(box[5]) * 1000.0
    except Exception:
        return None


def _attempt(sw: Any, ref_mark: int, end_cond: int) -> dict[str, Any]:
    """One full (mark, end_cond) fixture build + up-to fire + bbox witness on a
    fresh doc (isolation: a failed up-to could otherwise poison the next)."""
    label = f"mark={ref_mark},T1={end_cond}"
    doc = None
    try:
        doc = _build_block_100(sw)
        plane_name = _offset_plane(doc)
        sketch_name = _sketch_circle_on_top(doc)
        sel = _select_stack(doc, sketch_name, plane_name, ref_mark)
        before = _body_bbox_zmax_mm(doc)
        feat = _fire_extrude(doc, end_cond)
        doc.ForceRebuild3(False)
        after = _body_bbox_zmax_mm(doc)
        materialized = feat is not None and not isinstance(feat, int)
        hit_target = after is not None and abs(after - TARGET_Z * 1000.0) < BBOX_TOL_MM
        return {
            "label": label,
            "selection": sel,
            "materialized": materialized,
            "bbox_zmax_before_mm": before,
            "bbox_zmax_after_mm": after,
            "target_zmax_mm": TARGET_Z * 1000.0,
            "verdict": "PASS" if (materialized and hit_target) else "NO_OP",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "label": label,
            "verdict": "ERROR",
            "error": f"{type(e).__name__}: {e}"[:200],
            "trace": traceback.format_exc()[-400:],
        }
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass


def run() -> dict[str, Any]:
    out: dict[str, Any] = {
        "spike": "extrude_up_to_surface",
        "purpose": (
            "Prove (or wall) the UpToSurface/UpToSelection boss end condition by "
            "sweeping the reference selection-mark x end-condition and asserting "
            "the boss bbox terminates at the +60 mm ref plane."
        ),
        "attempts": [],
    }
    sw = fx.connect()
    rev = sw.RevisionNumber
    out["sw_revision"] = rev() if callable(rev) else rev
    # Primary end condition is UpToSelection (10); fallback UpToSurface (4).
    for end_cond in (SW_END_COND_UP_TO_SELECTION, SW_END_COND_UP_TO_SURFACE):
        for ref_mark in (0, 1, 2):
            out["attempts"].append(_attempt(sw, ref_mark, end_cond))
    verdicts = [a.get("verdict") for a in out["attempts"]]
    if any(v == "PASS" for v in verdicts):
        winners = [a["label"] for a in out["attempts"] if a.get("verdict") == "PASS"]
        out["verdict"] = "PROVEN"
        out["winning_combos"] = winners
        out["wire_recommendation"] = (
            "Wire boss_extrude_up_to_surface: select sketch (Mark 0) + up-to "
            "reference at the winning mark, FeatureExtrusion2 with the winning "
            "T1. Verify-the-effect = bbox Zmax at the target surface."
        )
    elif any(v == "ERROR" for v in verdicts):
        out["verdict"] = "ERROR"
    else:
        out["verdict"] = "WALLED"
        out["wire_recommendation"] = (
            "Up-to target ignored across all marks/end-conditions OOP -> "
            "Route-C. DEFER boss_extrude_up_to_surface; document in DEFERRED.md."
        )
    return out


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out_dir = Path(__file__).resolve().parent / "_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "extrude_up_to_surface.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
    sys.stderr.write(f"\n[up-to-surface] wrote {out_path}\n")
    sys.stderr.write(f"[up-to-surface] VERDICT: {report.get('verdict')}\n")
    return 0 if report.get("verdict") == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
