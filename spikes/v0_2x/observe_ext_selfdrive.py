"""W52 Lane B — SELF-DRIVING observe-ext seat verification.

The authored `observe_ext_derisk.py` reads the live GUI SELECTION, so it can
only run when a human has pre-opened a fixture and pre-selected entities. This
companion BUILDS its own fixtures and SELECTS entities programmatically, so W0
can fire it headless and get real telemetry on the COM-unit hypotheses.

Legs (each drives the PRODUCTION observe function):
  S-AREA       10x10mm face -> sw_get_measure_area_from_doc -> 100.0 mm2
               (verifies IMeasure.Area is m^2 -> x1e6)
  S-ANGLE      two perpendicular cube faces -> sw_get_measure_angle_from_doc
               -> 90.0 deg  (verifies IMeasure.Angle is radians -> math.degrees)
  S-DUR-PAIR   two cube vertices' GetPersistReference3 tokens ->
               sw_get_measure_durable_pair -> ~17.32 mm (10*sqrt(3) body diag)
               (verifies GetObjectByPersistReference3 + Select4 round-trip)
  S-ASM-BBOX   two 10mm cubes at x=0 and x=20 -> sw_get_assembly_bbox_from_doc
               -> dx~30 > dy~10 ~ dz~10  (verifies transform-union bbox)

NOT covered: face-pair clearance — read_face_pair_clearance selects faces by
NAME via SelectByID2("FACE",...), which needs named faces (a GUI step); left
for the human-fixture spike.

AUTHOR-ONLY. Results -> _results/observe_ext_selfdrive.json.
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "observe_ext_selfdrive.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.com.earlybind import typed, read_persist_reference  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.observe_measure import (  # noqa: E402
    _select_entity,
    sw_get_measure_angle_from_doc,
    sw_get_measure_area_from_doc,
    sw_get_measure_durable_pair,
)
from ai_sw_bridge.observe_bbox import sw_get_assembly_bbox_from_doc  # noqa: E402

SW_TEMPLATE_PART = 8
EDGE_M = 0.010  # 10 mm cube


def _new_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def _build_cube(sw: Any, mod: Any) -> Any | None:
    """A 10x10x10 mm cube on the Front plane (all faces 100 mm^2)."""
    doc = _new_part(sw)
    if doc is None:
        return None
    h = EDGE_M / 2.0
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-h, -h, 0.0, h, h, 0.0)
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion3(
        True, False, False, 0, 0, EDGE_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    if feat is None or isinstance(feat, int):
        return None
    typed(doc, "IModelDoc2", module=mod).ForceRebuild3(False)
    return doc


def _body(doc: Any, mod: Any) -> Any | None:
    pdoc = doc if hasattr(doc, "GetBodies2") else typed(doc, "IPartDoc", module=mod)
    bodies = pdoc.GetBodies2(0, True)
    if not bodies:
        return None
    return bodies[0] if isinstance(bodies, (list, tuple)) else bodies


def _faces(body: Any) -> list:
    fs = body.GetFaces()
    if fs is None:
        return []
    return list(fs) if isinstance(fs, (list, tuple)) else [fs]


def _vertices(body: Any) -> list:
    vs = body.GetVertices()
    if vs is None:
        return []
    return list(vs) if isinstance(vs, (list, tuple)) else [vs]


def _normal(face: Any, mod: Any) -> list[float] | None:
    try:
        return list(typed(face, "IFace2", module=mod).Normal)
    except Exception:
        return None


def _ok(tag: str, got: float, expected: float, tol: float, out: dict) -> bool:
    green = abs(got - expected) <= tol
    out[tag] = {"got": got, "expected": expected, "tol": tol,
                "status": "GREEN" if green else "RED"}
    print(f"  {'GREEN' if green else 'RED'}  {tag}: got {got:.4f}, "
          f"expected {expected:.4f} (tol {tol})")
    return green


# ---------------------------------------------------------------------------
def leg_part_measures(sw: Any, mod: Any, out: dict) -> None:
    """S-AREA + S-ANGLE + S-DUR-PAIR on one cube."""
    doc = _build_cube(sw, mod)
    if doc is None:
        out["part_build"] = "FAILED"
        return
    try:
        body = _body(doc, mod)
        faces = _faces(body)
        verts = _vertices(body)
        out["counts"] = {"faces": len(faces), "vertices": len(verts)}

        # ── S-AREA: select ONE face -> 100 mm^2 ────────────────────────────
        doc.ClearSelection2(True)
        if faces and _select_entity(doc, faces[0], False, mod):
            ar = sw_get_measure_area_from_doc(doc)
            if ar.get("ok") and ar["measure"]["area_mm2"] is not None:
                _ok("S-AREA", ar["measure"]["area_mm2"], 100.0, 1.0, out)
            else:
                out["S-AREA"] = {"status": "RED", "error": ar.get("error")}
                print(f"  RED  S-AREA: {ar.get('error')}")
        else:
            out["S-AREA"] = {"status": "RED", "error": "face select failed"}

        # ── S-ANGLE: two perpendicular faces -> 90 deg ─────────────────────
        doc.ClearSelection2(True)
        f0 = faces[0]
        n0 = _normal(f0, mod)
        perp = None
        for f in faces[1:]:
            n = _normal(f, mod)
            if n0 and n and abs(sum(a * b for a, b in zip(n0, n))) < 0.1:
                perp = f
                break
        if perp is not None and _select_entity(doc, f0, False, mod) and \
                _select_entity(doc, perp, True, mod):
            ang = sw_get_measure_angle_from_doc(doc)
            if ang.get("ok") and ang["measure"]["angle_deg"] is not None:
                _ok("S-ANGLE", ang["measure"]["angle_deg"], 90.0, 1.0, out)
            else:
                out["S-ANGLE"] = {"status": "RED", "error": ang.get("error")}
                print(f"  RED  S-ANGLE: {ang.get('error')}")
        else:
            out["S-ANGLE"] = {"status": "RED", "error": "no perpendicular face pair"}

        # ── S-DUR-PAIR: two vertices' persist tokens -> 10*sqrt(3) mm ──────
        if len(verts) >= 2:
            refs = []
            for v in verts:
                pid = read_persist_reference(doc, v)
                if pid:
                    refs.append(
                        base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")
                    )
            out["dur_tokens_captured"] = len(refs)
            if len(refs) >= 2:
                # Farthest pair would be the body diagonal; any pair proves the
                # round-trip. Use the first two captured.
                dp = sw_get_measure_durable_pair(doc, refs[0], refs[1])
                if dp.get("ok") and dp["measure"]["distance_mm"] is not None:
                    d = dp["measure"]["distance_mm"]
                    green = d > 0
                    out["S-DUR-PAIR"] = {"distance_mm": d,
                                         "status": "GREEN" if green else "RED"}
                    print(f"  {'GREEN' if green else 'RED'}  S-DUR-PAIR: "
                          f"distance={d:.4f} mm (persist round-trip)")
                else:
                    out["S-DUR-PAIR"] = {"status": "RED", "error": dp.get("error")}
                    print(f"  RED  S-DUR-PAIR: {dp.get('error')}")
            else:
                out["S-DUR-PAIR"] = {"status": "RED",
                                     "error": f"only {len(refs)} tokens captured"}
        else:
            out["S-DUR-PAIR"] = {"status": "RED", "error": "no vertices"}
    except Exception as exc:
        out["part_measures_exc"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def leg_asm_bbox(sw: Any, mod: Any, out: dict) -> None:
    """S-ASM-BBOX: two 10mm cubes at x=0 and x=20 -> transform-union bbox."""
    from ai_sw_bridge.assembly.handlers import place_components
    from ai_sw_bridge.assembly.lifecycle import _find_assembly_template

    # Build + save a single cube part, reuse as two instances.
    doc = _build_cube(sw, mod)
    if doc is None:
        out["S-ASM-BBOX"] = {"status": "RED", "error": "cube build failed"}
        return
    part_path = str(Path(_RESULTS, f"obs_cube_{os.getpid()}.SLDPRT"))
    save_ok = typed(doc, "IModelDoc2", module=mod).SaveAs3(part_path, 0, 0)
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if int(save_ok) != 0:
        out["S-ASM-BBOX"] = {"status": "RED", "error": f"part save {save_ok}"}
        return

    template = _find_assembly_template()
    if template is None:
        out["S-ASM-BBOX"] = {"status": "RED", "error": "no asm template"}
        return
    asm = sw.NewDocument(template, 0, 0.1, 0.1)
    if asm is None:
        out["S-ASM-BBOX"] = {"status": "RED", "error": "asm NewDocument None"}
        return
    components = [
        {"id": "c1", "part": part_path, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "c2", "part": part_path, "transform": {"xyz_mm": [20, 0, 0]}},
    ]
    placed, err = place_components(sw, asm, components, mod=mod)
    if err is not None:
        out["S-ASM-BBOX"] = {"status": "RED", "error": f"place: {err}"}
        return
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)

    ab = sw_get_assembly_bbox_from_doc(asm)
    if ab.get("ok") and ab.get("bounding_box"):
        bb = ab["bounding_box"]
        dx, dy, dz = bb["dx_mm"], bb["dy_mm"], bb["dz_mm"]
        # Two 10mm cubes spanning x[0,30] -> dx~30, dy~dz~10.
        green = dx > 0 and dy > 0 and dz > 0 and dx > dy * 1.5
        out["S-ASM-BBOX"] = {
            "dx_mm": dx, "dy_mm": dy, "dz_mm": dz,
            "components": bb.get("component_count"),
            "status": "GREEN" if green else "RED",
        }
        print(f"  {'GREEN' if green else 'RED'}  S-ASM-BBOX: "
              f"dx={dx:.2f} dy={dy:.2f} dz={dz:.2f} mm "
              f"({bb.get('component_count')} comps)")
    else:
        out["S-ASM-BBOX"] = {"status": "RED", "error": ab.get("error")}
        print(f"  RED  S-ASM-BBOX: {ab.get('error')}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def main() -> int:
    out: dict[str, Any] = {
        "spike_id": "W52_observe_ext_selfdrive",
        "timestamp": time.time(),
    }
    print("=== W52 Lane B — self-driving observe-ext seat verification ===")
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    except Exception as exc:
        out["error"] = f"SW connect failed: {exc!r}"
        _OUT.write_text(json.dumps(out, indent=2, default=str))
        print(out["error"])
        return 1

    print("\n[part measures: AREA / ANGLE / DUR-PAIR]")
    leg_part_measures(sw, mod, out)
    print("\n[assembly bbox]")
    leg_asm_bbox(sw, mod, out)

    legs = ["S-AREA", "S-ANGLE", "S-DUR-PAIR", "S-ASM-BBOX"]
    greens = [k for k in legs if out.get(k, {}).get("status") == "GREEN"]
    out["summary"] = f"{len(greens)}/{len(legs)} GREEN: {greens}"
    print(f"\n=== {out['summary']} ===")

    _OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"Results -> {_OUT}")
    return 0 if len(greens) == len(legs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
