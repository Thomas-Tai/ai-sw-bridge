"""W48 PRODUCTION PAE — dxf_flat_bends export with a real BEND layer.

Exercises the ACTUAL production export path
``export.dispatch._flat_pattern_dxf_drawing`` (the ``dxf_flat_bends`` format):
build a one-90deg-bend L-bracket base flange, export through the drawing-view
flat-pattern route + geometric classifier, then verify the EFFECT on the output
DXF:

  GREEN  ⇔  the output DXF contains exactly ONE LINE on the ``BEND`` layer
            (== the part's single physical bend) AND the developed-boundary
            perimeter LINEs remain on layer ``"0"``.

The fixture mirrors the W46 golden L-bracket EXACTLY (open L-profile base flange,
thickness 2mm, bend R 3mm, depth 40mm) so the seat output is comparable to the
committed golden fixture. Verify-the-EFFECT: the bend lands on the BEND layer,
not a layer-name string we hoped for.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/dxf_flat_bends_pae.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.export.dispatch import _flat_pattern_dxf_drawing  # noqa: E402
from ai_sw_bridge.export.formats import EXPORT_FORMATS  # noqa: E402
from ai_sw_bridge.export.dxf_bend_layers import (  # noqa: E402
    classify_bend_lines_geometric,
)

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "dxf_flat_bends_pae.json"

_SW_FM_BASEFLANGE = 34
_THICK_M = 0.002
_BEND_R_M = 0.003
_DEPTH_M = 0.040
_FLAT_PLATE_FACES = 6
_PHYSICAL_BEND_COUNT = 1


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
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return None
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateLine(0.0, 0.0, 0.0, 0.060, 0.0, 0.0)
    sm.CreateLine(0.060, 0.0, 0.0, 0.060, 0.030, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _newest_sketch_name(doc)


def _face_count(doc: Any, mod: Any) -> int:
    try:
        pdoc = typed(doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(0, True)
    except Exception:
        return 0
    n = 0
    for b in bodies or ():
        try:
            n += len(b.GetFaces() or [])
        except Exception:
            pass
    return n


def _line_layers(dxf_text: str) -> list[tuple[tuple[float, float, float, float], str]]:
    lines = dxf_text.splitlines()
    out: list[tuple[tuple[float, float, float, float], str]] = []
    cur = None
    seg: dict[str, float] = {}
    layer = "0"

    def _flush() -> None:
        if cur == "LINE" and {"10", "20", "11", "21"} <= seg.keys():
            out.append(((seg["10"], seg["20"], seg["11"], seg["21"]), layer))

    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            _flush()
            cur = val
            seg = {}
            layer = "0"
        elif cur == "LINE":
            if code in ("10", "20", "11", "21"):
                try:
                    seg[code] = float(val)
                except ValueError:
                    pass
            elif code == "8":
                layer = val
        i += 2
    _flush()
    return out


def main() -> int:
    out: dict[str, Any] = {
        "spike_id": "dxf_flat_bends_pae",
        "format": "dxf_flat_bends",
        "physical_bend_count": _PHYSICAL_BEND_COUNT,
        "ok": False,
        "verdict": "FAIL",
    }
    sw = None
    try:
        pythoncom.CoInitialize()
        mod = wrapper_module()
        sw = get_sw_app()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        # --- Build the one-bend L-bracket base flange (golden geometry) ---
        template = sw.GetUserPreferenceStringValue(8)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument(part) None"
            return _finish(out)
        sketch = _build_open_L(doc)
        out["sketch"] = sketch
        if not sketch:
            out["error"] = "could not build open-L sketch"
            return _finish(out)
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_BASEFLANGE)
        fd = typed_qi(data, "IBaseFlangeFeatureData", module=mod)
        try:
            fd.Thickness = _THICK_M
            fd.BendRadius = _BEND_R_M
            fd.D1EndConditionType = 0
            fd.D1EndConditionDistance = _DEPTH_M
        except Exception as exc:
            out["param_set_error"] = f"{type(exc).__name__}: {exc}"[:120]
        doc.ClearSelection2(True)
        if not doc.SelectByID(sketch, "SKETCH", 0, 0, 0):
            out["error"] = f"could not select sketch {sketch}"
            return _finish(out)
        feat = fm.CreateFeature(fd)
        out["base_flange_materialized"] = feat is not None
        doc.ForceRebuild3(False)

        faces = _face_count(doc, mod)
        out["faces"] = faces
        if faces <= _FLAT_PLATE_FACES:
            out["error"] = f"B-rep GATE: faces={faces} (<=6) — no bend produced"
            out["verdict"] = "NO-GO"
            return _finish(out)

        tmp = Path(tempfile.mkdtemp(prefix="w48_flatbends_pae_"))
        part_path = tmp / "W48_L_bracket.SLDPRT"
        err = doc.SaveAs3(str(part_path), 0, 0)
        if (int(err) if err is not None else 0) != 0:
            out["error"] = f"part SaveAs3 returned {err}"
            return _finish(out)
        out["part_path"] = str(part_path)

        # --- Run the PRODUCTION dxf_flat_bends export ---
        dxf_out = tmp / "W48_L_bracket_flat_bends.dxf"
        fmt = EXPORT_FORMATS["dxf_flat_bends"]
        result = _flat_pattern_dxf_drawing(doc, fmt, dxf_out)
        out["export"] = result.to_dict()
        if not result.ok:
            out["error"] = f"export failed: {result.error}"
            return _finish(out)

        # --- Verify the EFFECT on the output DXF ---
        dxf_text = dxf_out.read_text(encoding="utf-8", errors="replace")
        layered = _line_layers(dxf_text)
        bend_lines = [(s, lyr) for (s, lyr) in layered if lyr == "BEND"]
        outline_lines = [(s, lyr) for (s, lyr) in layered if lyr == "0"]
        classified = classify_bend_lines_geometric(dxf_text)
        out["dxf_line_count"] = len(layered)
        out["bend_layer_line_count"] = len(bend_lines)
        out["outline_layer_line_count"] = len(outline_lines)
        out["geometric_bend_count"] = classified["bend_line_count"]
        out["bbox"] = classified["bbox"]

        # Persist the seat DXF as committable evidence.
        golden = _RESULTS / "W48_L_bracket_flat_bends_layered.dxf"
        golden.write_text(dxf_text, encoding="utf-8")
        out["evidence_dxf"] = str(golden)

        green = len(bend_lines) == _PHYSICAL_BEND_COUNT and len(outline_lines) >= 4
        out["ok"] = bool(green)
        out["verdict"] = "GREEN" if green else "NO-GO"
        print(
            "[w48pae] %s: BEND-layer lines=%d (expected %d), outline lines=%d"
            % (
                out["verdict"],
                len(bend_lines),
                _PHYSICAL_BEND_COUNT,
                len(outline_lines),
            )
        )
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
    finally:
        if sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return _finish(out)


def _finish(out: dict) -> int:
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[w48pae] verdict: {out.get('verdict')} -> {_OUT}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
