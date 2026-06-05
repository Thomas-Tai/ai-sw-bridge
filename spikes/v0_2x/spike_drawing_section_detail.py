"""Wave-19 Slice 1: Section + Detail view de-risk spike.

GOAL: Prove that section and detail child views can be created out-of-process
from an existing parent drawing view, with correct type codes and non-degenerate
geometry.

CONFIRMED typelib signatures (from W19 typelib dump):

  IDrawingDoc.CreateSectionViewAt5(X, Y, Z, SectionLabel, Options,
      ExcludedComponents, SectionDepth) → IView
    dispid=0xf8, args=(R8,R8,R8,BSTR,I4,VARIANT,R8)

  IDrawingDoc.CreateDetailViewAt4(X, Y, Z, Style, Scale1, Scale2,
      LabelIn, Showtype, FullOutline, JaggedOutline, NoOutline, ShapeIntensity)
      → IView
    dispid=0x111, args=(R8,R8,R8,I4,R8,R8,BSTR,I4,BOOL,BOOL,BOOL,I4)

  ISketchManager.CreateLine(X1,Y1,Z1,X2,Y2,Z2) → ISketchSegment
  ISketchManager.CreateCircleByRadius(XC,YC,ZC,Radius) → ISketchSegment
  ISketchSegment.Select2(Append, Mark) → BOOL
  IDrawingDoc.MakeSectionLine() → void (0 args)
  IView.Type (property, dispid=0x94) → I4

Dead path notes:
  - CreateLine2 does NOT exist on ISketchManager in this typelib (only CreateLine).
  - IDrawingDoc does NOT inherit IModelDoc2 in the typelib; SketchManager is on
    IModelDoc2, accessed via typed_qi(doc_raw, "IModelDoc2").

Known SW view type constants (empirically verified in this spike):
  swDrawingNamedView     = 0
  swDrawingSectionView   = 1
  swDrawingDetailView    = 2

Prereq: SOLIDWORKS 2024 SP1 running, PYTHONPATH=<worktree>/src.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Ensure stdout handles any Unicode chars from SW COM (won't crash on charmap)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_section_detail.json"
)

results: dict[str, Any] = {
    "spike": "w19_drawing_section_detail",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "typelib": {
        "CreateSectionViewAt5": {
            "dispid": "0xf8",
            "args": ["X:R8", "Y:R8", "Z:R8", "SectionLabel:BSTR",
                     "Options:I4", "ExcludedComponents:VARIANT", "SectionDepth:R8"],
        },
        "CreateDetailViewAt4": {
            "dispid": "0x111",
            "args": ["X:R8", "Y:R8", "Z:R8", "Style:I4", "Scale1:R8", "Scale2:R8",
                     "LabelIn:BSTR", "Showtype:I4", "FullOutline:BOOL",
                     "JaggedOutline:BOOL", "NoOutline:BOOL", "ShapeIntensity:I4"],
        },
        "CreateLine": {"dispid": "0x1b", "args": ["X1:R8","Y1:R8","Z1:R8","X2:R8","Y2:R8","Z2:R8"]},
        "CreateCircleByRadius": {"dispid": "0x1e", "args": ["XC:R8","YC:R8","ZC:R8","Radius:R8"]},
        "MakeSectionLine": {"dispid": "0x1b_on_IDrawingDoc", "args": []},
        "IView.Type": {"dispid": "0x94", "note": "property → I4"},
    },
    "routes": {},
    "gates": {},
}

# SW drawing view type constants (well-known)
SW_SECTION_VIEW_TYPE = 1
SW_DETAIL_VIEW_TYPE = 2


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


def _view_type(view: Any) -> int | None:
    """Read IView.Type property."""
    try:
        t = view.Type
        return int(t) if t is not None else None
    except Exception:
        return None


def _view_outline(view: Any) -> list[float] | None:
    """Read IView.GetOutline() → [xmin,ymin,xmax,ymax] or None."""
    try:
        ol = view.GetOutline()
        if ol is not None and len(ol) >= 4:
            return list(ol[:4])
        return None
    except Exception:
        return None


def _view_position(view: Any) -> list[float] | None:
    """Read IView.Position property → [x,y] or None."""
    try:
        pos = view.Position
        if pos is not None and len(pos) >= 2:
            return [float(pos[0]), float(pos[1])]
        return None
    except Exception:
        return None


def _view_name(view: Any) -> str:
    try:
        n = view.GetName2()
        return str(n) if n else ""
    except Exception:
        return ""


def _count_views(drawing_doc: Any) -> int:
    try:
        return int(drawing_doc.GetViewCount())
    except Exception:
        return -1


def _outline_area(outline: list[float]) -> float:
    if outline and len(outline) >= 4:
        return (outline[2] - outline[0]) * (outline[3] - outline[1])
    return 0.0


def run() -> str:
    print("=" * 70)
    print("Wave-19 Slice 1: Section + Detail view de-risk spike")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import _find_drawing_template
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Suppress dim popups (precaution from W17)
    for tid in [9, 10, 22, 23]:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass

    # Close stale docs
    try:
        for d in (sw.GetDocuments() or []):
            try:
                t = d.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
    except Exception:
        pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # ---- Build a part with INTERNAL FEATURES --------------------------------
    # Boss-extrude 40x30mm rect x 15mm deep, then cut 20x10mm pocket through
    # center (top-to-bottom) to create a U-shaped cross-section visible in
    # section view.
    print("\n--- Building part with internal features ---")
    PART_PATH = str(_tmp / f"w19sec_{_ts}.SLDPRT")
    part_spec = {
        "schema_version": 1,
        "name": "W19SectionDemo",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_BOX",
                "plane": "Front",
                "width": 40.0,   # mm
                "height": 30.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "BOSS",
                "sketch": "SK_BOX",
                "depth": 15.0,
            },
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_CUT",
                "plane": "Top",
                "width": 20.0,
                "height": 10.0,
            },
            {
                "type": "cut_extrude_blind",
                "name": "POCKET",
                "sketch": "SK_CUT",
                "depth": 15.0,
            },
        ],
    }
    r = part_build(part_spec, save_as=PART_PATH, save_format="current", no_dim=True)
    part_ok = r.ok and os.path.isfile(PART_PATH)
    gate("part_build", part_ok, f"ok={r.ok}, path={PART_PATH}")
    if not part_ok:
        results["part_error"] = str(getattr(r, "error", "unknown"))
        save_results()
        return "WALL"

    results["part_path"] = PART_PATH

    # ---- Create drawing with parent front view ------------------------------
    print("\n--- Creating drawing with parent front view ---")
    template = _find_drawing_template()
    if not template:
        gate("drawing_template", False, "no .DRWDOT found")
        save_results()
        return "WALL"
    gate("drawing_template", True, template)

    # Open part (required for view creation)
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    except Exception as exc:
        gate("open_part", False, str(exc)[:80])
        save_results()
        return "WALL"
    gate("open_part", True, "")

    # A3 sheet: 0.420 x 0.297 m
    SHEET_W, SHEET_H = 0.420, 0.297
    doc_raw = sw.NewDocument(template, 0, SHEET_W, SHEET_H)
    if doc_raw is None or isinstance(doc_raw, int):
        gate("new_drawing", False, "NewDocument returned None")
        save_results()
        return "WALL"
    gate("new_drawing", True, "")

    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    # Place parent front view at approx centre-left of sheet
    PARENT_X, PARENT_Y = 0.10, 0.14

    parent_raw = drawing_doc.CreateDrawViewFromModelView3(
        PART_PATH, "*Front", PARENT_X, PARENT_Y, 0.0
    )
    parent_ok = parent_raw is not None and not isinstance(parent_raw, int)
    gate("parent_view_placed", parent_ok, f"raw={type(parent_raw).__name__}")
    if not parent_ok:
        save_results()
        return "WALL"

    parent_view = typed_qi(parent_raw, "IView", module=mod)
    parent_name = _view_name(parent_view)
    parent_pos = _view_position(parent_view)
    parent_outline = _view_outline(parent_view)
    parent_type = _view_type(parent_view)
    parent_view_count = _count_views(drawing_doc)

    results["parent"] = {
        "name": parent_name,
        "position": parent_pos,
        "outline": parent_outline,
        "type": parent_type,
        "view_count_before_derived": parent_view_count,
    }
    print(f"    parent: name={parent_name!r}, pos={parent_pos}, "
          f"outline={parent_outline}, type={parent_type}, "
          f"total_views={parent_view_count}")

    # Record empirical parent type (assumed 0=named but verify)
    results["parent_type_empirical"] = parent_type
    gate("parent_view_has_type",
         parent_type is not None,
         f"type={parent_type} (empirical; 0=named assumed)")

    if parent_outline is None or parent_pos is None:
        gate("parent_geometry", False, "Position or GetOutline returned None")
        save_results()
        return "WALL"
    gate("parent_geometry", True,
         f"pos={[round(p*1000,1) for p in parent_pos]}mm "
         f"outline={[round(o*1000,1) for o in parent_outline]}mm")

    ol = parent_outline
    cx = (ol[0] + ol[2]) / 2   # centre X of view on sheet
    cy = (ol[1] + ol[3]) / 2   # centre Y
    half_w = (ol[2] - ol[0]) / 2
    half_h = (ol[3] - ol[1]) / 2

    # ---- ROUTE A: SECTION VIEW ----------------------------------------------
    print("\n--- SECTION route ---")
    sec_result: dict[str, Any] = {}
    section_view = None

    try:
        # Step 1: activate parent view
        drawing_doc.ActivateView(parent_name)

        # Step 2: get SketchManager from IModelDoc2 QI
        skm = mdoc2.SketchManager

        # Step 3: draw a VERTICAL cut line through the centre of the parent
        # view in sheet coordinates (same coords as GetOutline / Position).
        # Extend 5mm beyond outline bounds.
        line_x = cx
        line_y1 = ol[1] - 0.005
        line_y2 = ol[3] + 0.005
        sec_line = skm.CreateLine(line_x, line_y1, 0.0,
                                  line_x, line_y2, 0.0)
        sec_result["create_line"] = (
            "ok" if (sec_line is not None and not isinstance(sec_line, int))
            else "None"
        )
        print(f"    CreateLine -> {type(sec_line).__name__}")

        if sec_line is None or isinstance(sec_line, int):
            raise RuntimeError("CreateLine returned None/int")

        # Step 4: select the line
        sel_ok = sec_line.Select2(False, 0)
        sec_result["select_line"] = bool(sel_ok)
        print(f"    Select2 → {sel_ok}")

        # Step 5: create section view to the RIGHT of parent
        # (section line is vertical → looking from the right)
        sec_x = ol[2] + 0.10   # 100mm right of outline edge
        sec_y = cy             # same Y as parent centre
        print(f"    Calling CreateSectionViewAt5({sec_x:.4f}, {sec_y:.4f}, 0, 'A', 0, None, 0.0)")
        sec_raw = drawing_doc.CreateSectionViewAt5(
            sec_x, sec_y, 0.0,
            "A",        # SectionLabel
            0,          # Options (0 = default)
            None,       # ExcludedComponents (part has none)
            0.0,        # SectionDepth (0 = full depth)
        )
        sec_result["create_section_view_raw"] = type(sec_raw).__name__
        print(f"    CreateSectionViewAt5 → {type(sec_raw).__name__}")

        if sec_raw is not None and not isinstance(sec_raw, int):
            section_view = typed_qi(sec_raw, "IView", module=mod)
            sec_t = _view_type(section_view)
            sec_ol = _view_outline(section_view)
            sec_nm = _view_name(section_view)
            sec_area = _outline_area(sec_ol) if sec_ol else 0.0
            sec_result.update({
                "name": sec_nm,
                "type": sec_t,
                "outline": sec_ol,
                "outline_area_mm2": round(sec_area * 1e6, 2),
                # GO = non-None type that differs from parent AND non-degenerate area
                "verdict": "GO" if (sec_t is not None and sec_t != parent_type and sec_area > 0) else "NO-GO",
            })
            print(f"    section view: name={sec_nm!r}, type={sec_t}, "
                  f"outline={sec_ol}, area_mm2={sec_area*1e6:.2f}")
        else:
            sec_result["verdict"] = "NO-GO"
            sec_result["error"] = "CreateSectionViewAt5 returned None/int"
            print(f"    CreateSectionViewAt5 returned None/int → NO-GO")

    except Exception as exc:
        sec_result["verdict"] = "NO-GO"
        sec_result["exception"] = f"{type(exc).__name__}: {exc}"
        print(f"    EXCEPTION: {exc}")

    results["routes"]["section"] = sec_result
    section_count = _count_views(drawing_doc)
    results["view_count_after_section"] = section_count

    sec_go = sec_result.get("verdict") == "GO"
    gate("section_view_count_plus1",
         section_count == parent_view_count + 1,
         f"before={parent_view_count}, after={section_count}")
    gate("section_view_type_differs_from_parent",
         sec_result.get("type") is not None and sec_result.get("type") != parent_type,
         f"sec_type={sec_result.get('type')}, parent_type={parent_type}")
    gate("section_outline_nondegenerate",
         sec_result.get("outline_area_mm2", 0) > 0,
         f"area_mm2={sec_result.get('outline_area_mm2', 0)}")

    # ---- ROUTE B: DETAIL VIEW -----------------------------------------------
    print("\n--- DETAIL route ---")
    det_result: dict[str, Any] = {}
    det_count_before = _count_views(drawing_doc)

    try:
        # Re-activate parent view
        drawing_doc.ActivateView(parent_name)
        skm = mdoc2.SketchManager

        # Clear existing selection
        try:
            mdoc2.ClearSelection()
        except Exception:
            pass

        # Draw a circle centred on a feature of interest: 25% left of view
        # centre — avoids sitting exactly on the section line.
        det_cx = cx - half_w * 0.3
        det_cy = cy
        det_r = min(half_w, half_h) * 0.35   # 35% of smallest half-dim
        print(f"    CreateCircleByRadius({det_cx:.4f}, {det_cy:.4f}, 0, {det_r:.4f})")
        det_circle = skm.CreateCircleByRadius(det_cx, det_cy, 0.0, det_r)
        det_result["create_circle"] = (
            "ok" if (det_circle is not None and not isinstance(det_circle, int))
            else "None"
        )
        print(f"    CreateCircleByRadius -> {type(det_circle).__name__}")

        if det_circle is None or isinstance(det_circle, int):
            raise RuntimeError("CreateCircleByRadius returned None/int")

        sel_ok = det_circle.Select2(False, 0)
        det_result["select_circle"] = bool(sel_ok)
        print(f"    Select2 → {sel_ok}")

        # Place detail view ABOVE parent (plenty of space on A3)
        det_x = cx
        det_y = ol[3] + 0.08
        print(f"    Calling CreateDetailViewAt4({det_x:.4f}, {det_y:.4f}, ...)")
        det_raw = drawing_doc.CreateDetailViewAt4(
            det_x, det_y, 0.0,     # X, Y, Z  placement
            0,                      # Style (0 = per standard)
            2.0, 1.0,               # Scale1 / Scale2 → 2:1
            "B",                    # LabelIn
            0,                      # Showtype
            True,                   # FullOutline
            False,                  # JaggedOutline
            False,                  # NoOutline
            50,                     # ShapeIntensity
        )
        det_result["create_detail_view_raw"] = type(det_raw).__name__
        print(f"    CreateDetailViewAt4 → {type(det_raw).__name__}")

        if det_raw is not None and not isinstance(det_raw, int):
            det_view = typed_qi(det_raw, "IView", module=mod)
            det_t = _view_type(det_view)
            det_ol = _view_outline(det_view)
            det_nm = _view_name(det_view)
            det_area = _outline_area(det_ol) if det_ol else 0.0
            det_result.update({
                "name": det_nm,
                "type": det_t,
                "outline": det_ol,
                "outline_area_mm2": round(det_area * 1e6, 2),
                "verdict": "GO" if (det_t is not None and det_t != parent_type and det_area > 0) else "NO-GO",
            })
            print(f"    detail view: name={det_nm!r}, type={det_t}, "
                  f"outline={det_ol}, area_mm2={det_area*1e6:.2f}")
        else:
            det_result["verdict"] = "NO-GO"
            det_result["error"] = "CreateDetailViewAt4 returned None/int"
            print(f"    CreateDetailViewAt4 returned None/int → NO-GO")

    except Exception as exc:
        det_result["verdict"] = "NO-GO"
        det_result["exception"] = f"{type(exc).__name__}: {exc}"
        print(f"    EXCEPTION: {exc}")

    results["routes"]["detail"] = det_result
    det_count_after = _count_views(drawing_doc)
    results["view_count_after_detail"] = det_count_after

    det_go = det_result.get("verdict") == "GO"
    gate("detail_view_count_plus1",
         det_count_after == det_count_before + 1,
         f"before={det_count_before}, after={det_count_after}")
    gate("detail_view_type_differs_from_parent",
         det_result.get("type") is not None and det_result.get("type") != parent_type,
         f"det_type={det_result.get('type')}, parent_type={parent_type}")
    gate("detail_outline_nondegenerate",
         det_result.get("outline_area_mm2", 0) > 0,
         f"area_mm2={det_result.get('outline_area_mm2', 0)}")

    # ---- OVERALL VERDICT ----------------------------------------------------
    at_least_one_go = sec_go or det_go
    gate("SECTION_GO", sec_go, f"section verdict={sec_result.get('verdict')}")
    gate("DETAIL_GO", det_go, f"detail verdict={det_result.get('verdict')}")
    gate("AT_LEAST_ONE_GO", at_least_one_go,
         f"section={sec_go}, detail={det_go}")

    if at_least_one_go:
        verdict = "GO"
    else:
        verdict = "NO-GO"

    results["verdict"] = verdict
    print(f"\nSection: {sec_result.get('verdict', 'NO-GO')}")
    print(f"Detail:  {det_result.get('verdict', 'NO-GO')}")
    print(f"Overall: {verdict}")

    # Close drawing doc
    try:
        t = doc_raw.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    return verdict


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        import traceback
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        results["unexpected_traceback"] = traceback.format_exc()
        verdict = "WALL"
    finally:
        results["verdict"] = results.get("verdict", verdict)
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict in ("GO",) else 1)
