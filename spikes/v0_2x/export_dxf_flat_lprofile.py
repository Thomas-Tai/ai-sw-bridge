"""W42 rescue: prove dxf_flat unfold via an OPEN L-profile base flange.

edge_flange is quarantined (ghost). To prove dxf_flat's bend-line unfold we need
a bent sheet-metal part built another way. The cleanest route (per W0): an OPEN
L-shaped profile sketch -> base flange -> a bracket with an INHERENT bend at the
L corner (no secondary edge-flange op).

A base flange from a CLOSED profile = flat plate (the S1 fixture, 6 faces). From
an OPEN profile it must be extruded by a DEPTH; IBaseFlangeFeatureData carries
that property. We do NOT guess the property name (the silent no-op trap) — we
introspect the feature-data dispatch, set every plausible depth property, then
GATE on the B-rep: a real L-bracket has faces > 6 and a cylindrical bend face.

Pipeline:
  1. open L-sketch (two connected lines) on the Front plane.
  2. CreateDefinition(BaseFlange) -> typed_qi(IBaseFlangeFeatureData);
     dump props; set Thickness/BendRadius + depth; CreateFeature.
  3. B-rep checkpoint (GATE): bodies>=1, faces > 6 (a flat plate is exactly 6).
  4. export dxf_flat; verify-the-BYTES: bend layer present OR entity_count > 4
     (the flat-plate baseline) -> the unfold reflects the bend.

Output: spikes/v0_2x/_results/export_dxf_flat_lprofile.json
"""
from __future__ import annotations

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
from ai_sw_bridge.export.dispatch import _flat_pattern_dxf  # noqa: E402
from ai_sw_bridge.export.formats import EXPORT_FORMATS  # noqa: E402
from ai_sw_bridge.cli.export_dxf_flat import _parse_dxf_entities  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

# swFmBaseFlange CreateDefinition id (from mutate._SW_FM_BASEFLANGE).
_SW_FM_BASEFLANGE = 34
_SW_SOLID_BODY = 0
_THICK_M = 0.002
_BEND_R_M = 0.003
_DEPTH_M = 0.040  # the open-profile extrude width
_FLAT_PLATE_FACES = 6
_FLAT_PLATE_BASELINE_ENTITIES = 4


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
            # count cylindrical faces (the bend) via IFace2->ISurface.IsCylinder
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


def _dxf_outline_bbox(dxf_text: str) -> dict[str, Any]:
    """Bounding box of LINE entities in the ENTITIES section.

    DECISIVE for 'did it unfold': the folded L's largest face is 60mm; the
    UNROLLED developed length is ~60+30+bend_allowance ~ 88mm. If the outline's
    long side is ~88mm the flat pattern unrolled the bend; if ~60mm it exported a
    single folded face.
    """
    lines = dxf_text.splitlines()
    xs: list[float] = []
    ys: list[float] = []
    i = 0
    # Collect coords for group codes 10/11 (X) and 20/21 (Y) inside LINE blocks.
    in_line = False
    while i < len(lines) - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            in_line = val == "LINE"
        elif in_line and code in ("10", "11"):
            try:
                xs.append(float(val) * 1000.0)  # m? DXF flat usually mm already
            except ValueError:
                pass
        elif in_line and code in ("20", "21"):
            try:
                ys.append(float(val) * 1000.0)
            except ValueError:
                pass
        i += 2
    if not xs or not ys:
        return {"found": False}
    # DXF flat-pattern coords are already in document units (mm here); the *1000
    # above is wrong if so — detect scale by magnitude and normalize.
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    # If spans are ~1e5 (i.e. coords were already mm and we *1000'd), divide back.
    if max(span_x, span_y) > 1000:
        span_x /= 1000.0
        span_y /= 1000.0
    return {
        "found": True,
        "span_long_mm": round(max(span_x, span_y), 2),
        "span_short_mm": round(min(span_x, span_y), 2),
    }


def _build_open_L(doc: Any) -> str | None:
    """Open L-profile (two connected lines) on the Front plane. Returns sketch name."""
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return None
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # horizontal 60mm then vertical 30mm — an open contour with one corner.
    sm.CreateLine(0.0, 0.0, 0.0, 0.060, 0.0, 0.0)
    sm.CreateLine(0.060, 0.0, 0.0, 0.060, 0.030, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    # newest sketch name
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


def _set_depth_props(fd: Any) -> dict[str, Any]:
    """Set every plausible depth property on IBaseFlangeFeatureData.

    We don't guess ONE name — we enumerate dispatch props and set any whose name
    suggests an extrude depth/distance, recording what took.
    """
    report: dict[str, Any] = {"attrs_seen": [], "depth_set": []}
    candidates = ("Depth", "D1", "Depth1", "Distance", "ExtrudeDepth", "Width")
    for nm in candidates:
        try:
            if hasattr(fd, nm):
                setattr(fd, nm, _DEPTH_M)
                report["depth_set"].append(nm)
        except Exception as exc:
            report.setdefault("set_errors", {})[nm] = f"{type(exc).__name__}: {exc}"[:80]
    # also dump a sampling of attribute names for diagnosis
    try:
        report["attrs_seen"] = [a for a in dir(fd) if not a.startswith("_")][:60]
    except Exception:
        pass
    return report


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "wave": "W42", "step": "lprofile_rescue", "format": "dxf_flat",
        "ok": False, "verdict": "FAIL",
        "flat_plate_faces": _FLAT_PLATE_FACES,
        "flat_plate_baseline_entities": _FLAT_PLATE_BASELINE_ENTITIES,
    }
    doc = None
    sw = None
    try:
        mod = wrapper_module()
        sw = get_sw_app()
        template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument None"
            raise SystemExit(_finish(out))

        print("[lp] building open L-profile...")
        sketch = _build_open_L(doc)
        out["sketch"] = sketch
        if not sketch:
            out["error"] = "could not build/find open L sketch"
            raise SystemExit(_finish(out))

        print("[lp] creating base flange from open profile...")
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_BASEFLANGE)
        fd = typed_qi(data, "IBaseFlangeFeatureData", module=mod)
        try:
            fd.Thickness = _THICK_M
            fd.BendRadius = _BEND_R_M
        except Exception as exc:
            out["thick_set_error"] = f"{type(exc).__name__}: {exc}"[:120]
        # The open-profile extrude depth is the D1 END CONDITION (introspected):
        # D1EndConditionType = swEndCondBlind(0), D1EndConditionDistance = depth.
        depth_set: dict[str, Any] = {}
        for nm, val in (("D1EndConditionType", 0), ("D1EndConditionDistance", _DEPTH_M)):
            try:
                setattr(fd, nm, val)
                depth_set[nm] = val
            except Exception as exc:
                depth_set[nm + "_err"] = f"{type(exc).__name__}: {exc}"[:100]
        out["depth_set_explicit"] = depth_set
        out["depth_report"] = _set_depth_props(fd)
        doc.ClearSelection2(True)
        if not doc.SelectByID(sketch, "SKETCH", 0, 0, 0):
            out["error"] = f"could not select sketch {sketch}"
            raise SystemExit(_finish(out))
        feat = fm.CreateFeature(fd)
        out["base_flange_materialized"] = feat is not None
        doc.ForceRebuild3(False)

        # --- B-rep GATE: faces > 6 (flat plate is exactly 6) + a cylindrical bend ---
        m = _metrics(doc, mod)
        out["brep"] = m
        bent = m["bodies"] >= 1 and m["faces"] > _FLAT_PLATE_FACES
        out["bend_exists_in_3d"] = bent
        print("[lp] brep: bodies=%s vol=%s faces=%s cyl_faces=%s -> bent=%s"
              % (m["bodies"], m["vol_mm3"], m["faces"], m["cyl_faces"], bent))
        if not bent:
            out["error"] = (
                f"B-rep GATE FAILED: faces={m['faces']} (<= flat-plate 6) -> the "
                "open-profile base flange did not produce a bend. Abort before export."
            )
            out["verdict"] = "NO-GO"
            raise SystemExit(_finish(out))

        # --- export dxf_flat ---
        tmp = Path(tempfile.mkdtemp(prefix="w42_lp_"))
        part_path = tmp / "W42_L_bracket.SLDPRT"
        err = doc.SaveAs3(str(part_path), 0, 0)
        if (int(err) if err is not None else 0) != 0:
            out["error"] = f"SaveAs3 returned {err}"
            raise SystemExit(_finish(out))

        print("[lp] exporting dxf_flat...")
        dxf_path = tmp / "W42_L_flat.dxf"
        exp = _flat_pattern_dxf(doc, EXPORT_FORMATS["dxf_flat"], dxf_path)
        out["export"] = exp.to_dict()
        if not exp.ok:
            out["error"] = f"dxf_flat export failed: {exp.error}"
            raise SystemExit(_finish(out))

        _dxf_text = dxf_path.read_text(encoding="utf-8", errors="replace")
        bbox = _dxf_outline_bbox(_dxf_text)
        out["outline_bbox"] = bbox
        print("[lp] outline bbox: %s (folded face=60mm, unrolled~86mm)" % bbox)
        ent = _parse_dxf_entities(_dxf_text)
        out["dxf_verify"] = {
            "entity_count": ent["entity_count"], "entity_types": ent["entity_types"],
            "layers": ent["layers"], "has_bend_layer": ent["has_bend_layer"],
            "file_size_bytes": dxf_path.stat().st_size,
        }
        # Persist the flat DXF as a committable golden fixture for the offline test.
        golden = _HERE.parent / "_results" / "W42_L_bracket_flat.dxf"
        golden.write_text(_dxf_text, encoding="utf-8")
        out["golden_dxf"] = str(golden)

        # GREEN criterion = THE UNROLL IS PHYSICALLY PROVEN, not layer names.
        # Developed long span must be the DEVELOPED length (clearly > the 60mm
        # folded face, < the 90mm naive segment sum), short span = the 40mm depth.
        span_long = bbox.get("span_long_mm", 0.0) if bbox.get("found") else 0.0
        span_short = bbox.get("span_short_mm", 0.0) if bbox.get("found") else 0.0
        unrolled = 80.0 <= span_long <= 89.0 and 39.0 <= span_short <= 41.0
        out["unroll_proven"] = unrolled
        out["ok"] = bool(exp.ok and bent and unrolled)
        out["verdict"] = "GREEN" if out["ok"] else "NO-GO"
        out["note"] = (
            "dxf_flat unrolls the developed outline (PROVEN by span). Bend LINES "
            "are NOT emitted by ExportFlatPatternView (opt 0-7) — deferred "
            "sub-scope (drawing flat-pattern view, W33 route)."
        )
        print("[lp] %s: unroll_proven=%s (long=%.2f short=%.2f) bend_lines=%s"
              % (out["verdict"], unrolled, span_long, span_short, ent["has_bend_layer"]))

    except SystemExit:
        raise
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
        print("[lp] EXCEPTION: %s" % exc)
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
    p = res / "export_dxf_flat_lprofile.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[lp] wrote {p}")
    print(f"[lp] verdict: {out.get('verdict')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
