"""W42 deferred sub-scope: BEND LINES via a drawing-space flat-pattern view.

The W42 ``dxf_flat`` Developed Boundary Pass exports the unrolled OUTLINE via
part-space ``IModelDoc2.ExportFlatPatternView(path, options)`` — proven to emit
ONLY layer-`0` outline LINEs and NO bend layer across every option 0–7. Inner
bend lines are therefore unreachable through the part-space export API.

This spike characterizes the DEFERRED pathway: a **drawing-space flat-pattern
view** (W33 framework) where SOLIDWORKS renders bend lines as first-class
drawing entities. Pipeline:

  1. Open an L-profile base-flange part WITH ONE BEND (mirrors the W42
     export_dxf_flat_lprofile fixture EXACTLY: open contour CreateLine 0,0→
     0.060,0 then →0.060,0.030; CreateDefinition(34) base flange; thickness
     0.002, bend R 0.003; D1EndConditionType=0 + D1EndConditionDistance=0.040).
  2. B-rep GATE: faces > 6 (a flat plate is exactly 6) confirms a real bend.
  3. SaveAs3 the part (a drawing view needs a source file on disk).
  4. NewDocument(.DRWDOT) → typed_qi(IDrawingDoc).
  5. Insert a FLAT-PATTERN drawing view of the part — call shape UNVERIFIED
     (see _insert_flat_pattern_view; it tries the GUESSED
     CreateFlatPatternViewFromModelView3 first, then a documented fallback).
  6. SaveAs3 the DRAWING to DXF (the W33-proven Drawing-doc-only DXF route).
  7. Parse the DXF for BEND-LINE entities via parse_dxf_bend_lines.

GREEN (the seat criterion, NOT run here): the DXF contains bend-line entities
whose COUNT equals the part's physical bend count — exactly 1 for this
single-90°-bend L-bracket — with extracted coordinates (verify-the-EFFECT, not
a layer-name string).

NOT run by this offline author. SEAT-RUNNABLE by W0. py_compile-clean with the
production module imports resolved from src/.

Output: spikes/v0_2x/_results/dxf_flat_bendlines_drwview.json
"""
from __future__ import annotations

import glob
import json
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2] / "src"))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli.export_dxf_flat import (  # noqa: E402
    parse_dxf_bend_lines,
    _parse_dxf_entities,
)
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

# swFmBaseFlange CreateDefinition id (mirrors mutate._SW_FM_BASEFLANGE).
_SW_FM_BASEFLANGE = 34
_SW_SOLID_BODY = 0
_SW_DOC_DRAWING = 3
_THICK_M = 0.002
_BEND_R_M = 0.003
_DEPTH_M = 0.040
_FLAT_PLATE_FACES = 6
# An L-bracket with one 90° bend has exactly ONE physical bend ⇒ ONE bend line.
_PHYSICAL_BEND_COUNT = 1


def _find_drawing_template() -> str | None:
    """Locate a .DRWDOT template (mirror drawing.lifecycle._find_drawing_template)."""
    patterns = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return None


def _newest_sketch_name(doc: Any) -> str | None:
    try:
        raw = doc.GetFeatureCount
        count = raw(True) if callable(raw) else int(raw)
    except Exception:
        return None
    for i in range(count):
        try:
            feat = doc.FeatureByPositionReverse(i)
        except Exception:
            break
        if feat is None:
            break
        try:
            tn = feat.GetTypeName
            tn = tn() if callable(tn) else str(tn)
        except Exception:
            continue
        if tn in {"ProfileFeature", "Sketch"}:
            try:
                nm = feat.Name
                return nm() if callable(nm) else str(nm)
            except Exception:
                pass
    return None


def _build_open_L(doc: Any) -> str | None:
    """Open L-profile (two connected lines) on the Front plane → sketch name."""
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return None
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateLine(0.0, 0.0, 0.0, 0.060, 0.0, 0.0)
    sm.CreateLine(0.060, 0.0, 0.0, 0.060, 0.030, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _newest_sketch_name(doc)


def _metrics(doc: Any, mod: Any) -> dict[str, Any]:
    out = {"vol_mm3": 0.0, "faces": 0, "bodies": 0, "cyl_faces": 0}
    try:
        pdoc = typed(doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:160]
        return out
    if not bodies:
        return out
    out["bodies"] = len(bodies)
    for b in bodies:
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                out["vol_mm3"] += float(mp[3]) * 1e9
        except Exception:
            pass
        try:
            faces = b.GetFaces() or []
            out["faces"] += len(faces)
            for f in faces:
                try:
                    surf = typed_qi(f.GetSurface(), "ISurface", module=mod)
                    if bool(surf.IsCylinder()):
                        out["cyl_faces"] += 1
                except Exception:
                    pass
        except Exception:
            pass
    out["vol_mm3"] = round(out["vol_mm3"], 3)
    return out


def _insert_flat_pattern_view(
    sw: Any,
    drawing_doc: Any,
    part_path: str,
    x: float,
    y: float,
    config_name: str | None = None,
) -> dict[str, Any]:
    """Insert a flat-pattern drawing view of ``part_path``.

    ⚠️ The flat-pattern-view COM call is UNVERIFIED — this is the load-bearing
    seat unknown. Three routes are attempted in order; the seat records which
    (if any) yields a non-None IView whose flat-pattern flag is set:

      A. GUESSED: IDrawingDoc.CreateFlatPatternViewFromModelView3(modelName,
         x, y, z, twistAngle) → IView. (Name/arity NOT confirmed against the
         SW2024 typelib; absent from our makepy stubs.)
      B. Fallback: activate the part's Flat-Pattern config, then the W33-PROVEN
         CreateDrawViewFromModelView3(modelName, "*Current", x, y, z). Whether
         "*Current" picks up the unfolded flat-pattern config is the open
         question this records.
      C. Fallback: CreateDrawViewFromModelView3 with a "*Front" view of the
         flat-pattern config — a control to see if ANY view of the flat config
         carries bend lines.

    Returns a diagnostic dict; ``view`` (the raw COM return) is included so the
    caller can typed_qi it to IView and probe IsFlatPatternView()/GetType.
    """
    report: dict[str, Any] = {"route": None, "view": None, "errors": {}}

    # Route A — TYPELIB-VERIFIED (sldworks.tlb v32):
    #   CreateFlatPatternViewFromModelView3(
    #     ModelName:BSTR, ConfigName:BSTR, LocX:R8, LocY:R8, LocZ:R8,
    #     HideBendLines:BOOL, FlipView:BOOL) -> IView
    # HideBendLines=False is the load-bearing arg: it makes SW render the
    # bend lines as first-class drawing entities (the W42 part-space export
    # has no such switch). FlipView=False. ConfigName = the config to flatten.
    config_name = config_name or "Default"
    try:
        v = drawing_doc.CreateFlatPatternViewFromModelView3(
            part_path, config_name, x, y, 0.0, False, False
        )
        if v is not None and not isinstance(v, int):
            report["route"] = "A:CreateFlatPatternViewFromModelView3(HideBendLines=False)"
            report["view"] = v
            return report
        report["errors"]["A"] = f"returned {v!r}"
    except Exception as exc:
        report["errors"]["A"] = f"{type(exc).__name__}: {exc}"[:160]

    # Route A2 — the 6-arg overload (no FlipView), same HideBendLines=False.
    try:
        v = drawing_doc.CreateFlatPatternViewFromModelView2(
            part_path, config_name, x, y, 0.0, False
        )
        if v is not None and not isinstance(v, int):
            report["route"] = "A2:CreateFlatPatternViewFromModelView2(HideBendLines=False)"
            report["view"] = v
            return report
        report["errors"]["A2"] = f"returned {v!r}"
    except Exception as exc:
        report["errors"]["A2"] = f"{type(exc).__name__}: {exc}"[:160]

    # Route B — activate flat-pattern config + *Current standard view.
    try:
        v = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Current", x, y, 0.0
        )
        if v is not None and not isinstance(v, int):
            report["route"] = "B:CreateDrawViewFromModelView3(*Current)"
            report["view"] = v
            return report
        report["errors"]["B"] = f"returned {v!r}"
    except Exception as exc:
        report["errors"]["B"] = f"{type(exc).__name__}: {exc}"[:160]

    # Route C — *Front of the (flat-pattern) config as a control.
    try:
        v = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Front", x, y, 0.0
        )
        if v is not None and not isinstance(v, int):
            report["route"] = "C:CreateDrawViewFromModelView3(*Front)"
            report["view"] = v
            return report
        report["errors"]["C"] = f"returned {v!r}"
    except Exception as exc:
        report["errors"]["C"] = f"{type(exc).__name__}: {exc}"[:160]

    return report


def _activate_flat_pattern_config(doc: Any) -> dict[str, Any]:
    """Best-effort: unsuppress the Flat-Pattern feature so a *Current view of
    the part shows the unfolded state (Route B precondition).

    Mirrors export.dispatch._flat_pattern_dxf's feature walk: find the feature
    whose GetTypeName contains "FlatPattern"/"Flat-Pattern" and SetSuppression(1)
    (unsuppress). Returns a small diagnostic dict.
    """
    out: dict[str, Any] = {"flat_found": False, "unsuppressed": False}
    try:
        raw = doc.GetFeatureCount
        count = raw(True) if callable(raw) else int(raw)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:120]
        return out
    for i in range(count):
        try:
            feat = doc.FeatureByPositionReverse(i)
        except Exception:
            break
        if feat is None:
            break
        try:
            tn = feat.GetTypeName
            tn = tn() if callable(tn) else str(tn)
        except Exception:
            tn = ""
        if "FlatPattern" in tn or "Flat-Pattern" in tn:
            out["flat_found"] = True
            try:
                feat.SetSuppression(1)
                out["unsuppressed"] = True
            except Exception as exc:
                out["unsuppress_error"] = f"{type(exc).__name__}: {exc}"[:120]
            break
    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "wave": "W42",
        "step": "bendlines_drwview",
        "format": "dxf_flat_bends",
        "physical_bend_count": _PHYSICAL_BEND_COUNT,
        "ok": False,
        "verdict": "FAIL",
    }
    doc = None
    sw = None
    try:
        mod = wrapper_module()
        sw = get_sw_app()

        # --- Step 1: build the L-bracket part (one bend) ---
        template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument(part) returned None"
            raise SystemExit(_finish(out))

        print("[bl] building open L-profile base flange...")
        sketch = _build_open_L(doc)
        out["sketch"] = sketch
        if not sketch:
            out["error"] = "could not build/find open L sketch"
            raise SystemExit(_finish(out))

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_BASEFLANGE)
        fd = typed_qi(data, "IBaseFlangeFeatureData", module=mod)
        try:
            fd.Thickness = _THICK_M
            fd.BendRadius = _BEND_R_M
        except Exception as exc:
            out["thick_set_error"] = f"{type(exc).__name__}: {exc}"[:120]
        for nm, val in (
            ("D1EndConditionType", 0),
            ("D1EndConditionDistance", _DEPTH_M),
        ):
            try:
                setattr(fd, nm, val)
            except Exception as exc:
                out.setdefault("depth_set_errors", {})[nm] = (
                    f"{type(exc).__name__}: {exc}"[:100]
                )
        doc.ClearSelection2(True)
        if not doc.SelectByID(sketch, "SKETCH", 0, 0, 0):
            out["error"] = f"could not select sketch {sketch}"
            raise SystemExit(_finish(out))
        feat = fm.CreateFeature(fd)
        out["base_flange_materialized"] = feat is not None
        doc.ForceRebuild3(False)

        # --- Step 2: B-rep GATE — faces > 6 proves a real bend ---
        m = _metrics(doc, mod)
        out["brep"] = m
        bent = m["bodies"] >= 1 and m["faces"] > _FLAT_PLATE_FACES
        out["bend_exists_in_3d"] = bent
        print(
            "[bl] brep: bodies=%s vol=%s faces=%s cyl_faces=%s -> bent=%s"
            % (m["bodies"], m["vol_mm3"], m["faces"], m["cyl_faces"], bent)
        )
        if not bent:
            out["error"] = (
                f"B-rep GATE FAILED: faces={m['faces']} (<= flat-plate 6) — "
                "no bend produced; abort before drawing."
            )
            out["verdict"] = "NO-GO"
            raise SystemExit(_finish(out))

        # --- Step 3: save the part (a drawing view needs a source on disk) ---
        tmp = Path(tempfile.mkdtemp(prefix="w42_bendlines_"))
        part_path = tmp / "W42_L_bracket.SLDPRT"
        err = doc.SaveAs3(str(part_path), 0, 0)
        if (int(err) if err is not None else 0) != 0:
            out["error"] = f"part SaveAs3 returned {err}"
            raise SystemExit(_finish(out))
        out["part_path"] = str(part_path)

        # Capture the part's active config name (the config to flatten).
        try:
            cfgmgr = doc.ConfigurationManager
            active_cfg = cfgmgr.ActiveConfiguration
            part_config = active_cfg.Name if active_cfg is not None else "Default"
        except Exception as exc:
            part_config = "Default"
            out["config_probe_error"] = f"{type(exc).__name__}: {exc}"[:120]
        out["part_config"] = part_config

        # Unsuppress flat-pattern (Route B precondition, best-effort).
        out["flat_config"] = _activate_flat_pattern_config(doc)
        doc.ForceRebuild3(False)
        doc.SaveAs3(str(part_path), 0, 0)

        # --- Step 4: create the .SLDDRW ---
        drw_template = _find_drawing_template()
        out["drawing_template"] = drw_template
        if not drw_template:
            out["error"] = "no .DRWDOT drawing template found"
            raise SystemExit(_finish(out))

        # A2-ish sheet so the unrolled bracket fits; size is not load-bearing.
        drw_raw = sw.NewDocument(drw_template, 0, 0.420, 0.297)
        if drw_raw is None or isinstance(drw_raw, int):
            out["error"] = "NewDocument(drwdot) returned None"
            raise SystemExit(_finish(out))
        drawing_doc = typed_qi(drw_raw, "IDrawingDoc", module=mod)

        # --- Step 5: insert the flat-pattern drawing view (UNVERIFIED) ---
        print("[bl] inserting flat-pattern drawing view...")
        view_report = _insert_flat_pattern_view(
            sw, drawing_doc, str(part_path), 0.15, 0.15, part_config
        )
        out["view_route"] = view_report.get("route")
        out["view_errors"] = view_report.get("errors")
        view_raw = view_report.get("view")
        if view_raw is None:
            out["error"] = (
                "no flat-pattern view route produced an IView "
                f"(errors={view_report.get('errors')})"
            )
            out["verdict"] = "NO-GO"
            raise SystemExit(_finish(out))

        # Probe the view: type + flat-pattern flag (diagnostic, not the gate).
        try:
            iview = typed_qi(view_raw, "IView", module=mod)
            try:
                out["view_name"] = iview.GetName2()
            except Exception:
                pass
            try:
                out["view_type"] = iview.Type
            except Exception:
                pass
            try:
                out["is_flat_pattern_view"] = bool(iview.IsFlatPatternView())
            except Exception as exc:
                out["is_flat_pattern_probe_error"] = (
                    f"{type(exc).__name__}: {exc}"[:120]
                )
        except Exception as exc:
            out["view_qi_error"] = f"{type(exc).__name__}: {exc}"[:120]

        drawing_doc_mdoc2 = typed_qi(drw_raw, "IModelDoc2", module=mod)
        drawing_doc_mdoc2.ForceRebuild3(False)

        # --- Step 6: SaveAs3 the DRAWING → DXF (W33-proven, drawing-only) ---
        dxf_path = tmp / "W42_L_flat_bends.dxf"
        print("[bl] exporting drawing -> DXF...")
        derr = drw_raw.SaveAs3(str(dxf_path), 0, 0)
        derr_code = int(derr) if derr is not None else 0
        if derr_code != 0:
            out["error"] = f"drawing SaveAs3(.dxf) returned {derr_code}"
            raise SystemExit(_finish(out))
        if not dxf_path.exists() or dxf_path.stat().st_size == 0:
            out["error"] = "drawing→DXF produced no file"
            raise SystemExit(_finish(out))

        # --- Step 7: parse for BEND LINES (verify-the-EFFECT) ---
        dxf_text = dxf_path.read_text(encoding="utf-8", errors="replace")
        bends = parse_dxf_bend_lines(dxf_text)
        ents = _parse_dxf_entities(dxf_text)
        out["dxf_bend_lines"] = bends
        out["dxf_entities"] = {
            "entity_count": ents["entity_count"],
            "entity_types": ents["entity_types"],
            "layers": ents["layers"],
        }
        out["dxf_file_size_bytes"] = dxf_path.stat().st_size

        # Persist the DXF as a committable golden fixture for the offline test.
        golden = _HERE.parent / "_results" / "W42_L_bracket_flat_bends.dxf"
        golden.write_text(dxf_text, encoding="utf-8")
        out["golden_dxf"] = str(golden)

        # --- GREEN criterion: bend-line COUNT == physical bend count ---
        bend_count = bends["bend_line_count"]
        out["bend_line_count"] = bend_count
        green = bend_count == _PHYSICAL_BEND_COUNT
        out["ok"] = bool(green)
        out["verdict"] = "GREEN" if green else "NO-GO"
        out["note"] = (
            "GREEN ⇔ bend-line entity count == physical bend count (1 for this "
            "single-90°-bend L-bracket), with coordinates. Layer/linetype names "
            "are corroborating only. If bend_line_count==0 the flat-pattern view "
            "did NOT emit bend lines via the attempted route — record which "
            "route produced the IView and whether is_flat_pattern_view is True."
        )
        print(
            "[bl] %s: bend_lines=%s (expected %s) route=%s"
            % (out["verdict"], bend_count, _PHYSICAL_BEND_COUNT, out.get("view_route"))
        )

    except SystemExit:
        raise
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
        print("[bl] EXCEPTION: %s" % exc)
    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return _finish(out)


def _finish(out: dict) -> int:
    res = _HERE.parent / "_results"
    res.mkdir(parents=True, exist_ok=True)
    p = res / "dxf_flat_bendlines_drwview.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[bl] wrote {p}")
    print(f"[bl] verdict: {out.get('verdict')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
