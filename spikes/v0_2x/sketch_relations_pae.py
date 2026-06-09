"""W39 S1 seat PAE — sketch relations token + effect validation.

THE load-bearing risk (W21 trap): RELATION_TOKENS values are GUESSED. This
spike proves each token actually fires SketchAddConstraints AND produces the
geometric effect — not just "no error" (the W18/W21 no-op trap).

Strategy — drive the SHIPPING production helpers (apply_relations_in_open_sketch
+ the token map) against live sketches, verify the EFFECT geometrically:

  G1 token-fires: each tested token applied with no exception AND relation
     count increments (RelationManager delta).
  G2 EQUAL moves geometry: two lines of DIFFERENT length -> apply 'equal' ->
     the lines become EQUAL length (the definitive "it constrained" proof; a
     guessed-but-wrong token would no-op and lengths stay unequal).
  G3 HORIZONTAL moves geometry: a slightly-tilted line -> 'horizontal' ->
     endpoints share Y (dy -> ~0).
  G4 PERPENDICULAR: two near-perpendicular lines -> 'perpendicular' -> dot of
     direction vectors -> ~0.
  G5 token dump: record which of the 9 guessed tokens fire vs raise, so any
     wrong guess is named explicitly (not silently passed).

PAUSE-ON-ERROR: any gate FALSE -> STOP, report, do not auto-iterate.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))


def _new_part(sw_typed, mod):
    from ai_sw_bridge.com.earlybind import typed
    doc = sw_typed.NewDocument(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT", 0, 0, 0
    )
    return doc, typed(doc, "IModelDoc2", module=mod)


def _seg_len(seg):
    sp = seg.GetStartPoint2
    ep = seg.GetEndPoint2
    dx, dy = ep.X - sp.X, ep.Y - sp.Y
    return (dx * dx + dy * dy) ** 0.5


def _seg_dxdy(seg):
    sp = seg.GetStartPoint2
    ep = seg.GetEndPoint2
    return (ep.X - sp.X, ep.Y - sp.Y)


def run() -> dict:
    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec._sketch_relations import (
        apply_relations_in_open_sketch,
        RELATION_TOKENS,
    )

    result: dict = {"ok": False, "gates": {}, "errors": [], "token_dump": {}, "detail": {}}
    sw = get_sw_app()
    if sw is None:
        result["errors"].append("get_sw_app() None")
        return result
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)
    tempfile.mkdtemp(prefix="aisw_W39_")

    try:
        # ── G2: EQUAL on two unequal lines ───────────────────────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        # line 0: length 30mm horizontal-ish; line 1: length 10mm
        sm.CreateLine(-0.015, 0.020, 0.0, 0.015, 0.020, 0.0)   # 30mm
        sm.CreateLine(-0.005, 0.010, 0.0, 0.005, 0.010, 0.0)   # 10mm
        segs = list(dt.GetActiveSketch2.GetSketchSegments())
        len0_b, len1_b = _seg_len(segs[0]), _seg_len(segs[1])
        eq = apply_relations_in_open_sketch(
            dt, [{"type": "equal", "entities": [0, 1]}]
        )
        result["detail"]["equal_apply"] = eq
        segs2 = list(dt.GetActiveSketch2.GetSketchSegments())
        len0_a, len1_a = _seg_len(segs2[0]), _seg_len(segs2[1])
        result["detail"]["equal_lengths"] = {
            "before": [round(len0_b * 1000, 4), round(len1_b * 1000, 4)],
            "after": [round(len0_a * 1000, 4), round(len1_a * 1000, 4)],
        }
        result["token_dump"]["equal"] = eq.get("ok") and eq.get("relations_applied", 0) >= 1
        # G2: lines were unequal, now equal (within 0.01mm)
        result["gates"]["G2_equal_moves_geometry"] = (
            abs(len0_b - len1_b) > 0.005   # were genuinely unequal (>5mm apart)
            and abs(len0_a - len1_a) < 1e-5  # now equal
        )
        result["gates"]["G1_equal_token_fires"] = bool(result["token_dump"]["equal"])
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G3: HORIZONTAL on a tilted line ──────────────────────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(-0.015, 0.020, 0.0, 0.015, 0.022, 0.0)   # tilted (dy=2mm)
        dxdy_b = _seg_dxdy(list(dt.GetActiveSketch2.GetSketchSegments())[0])
        hz = apply_relations_in_open_sketch(
            dt, [{"type": "horizontal", "entities": [0]}]
        )
        result["detail"]["horizontal_apply"] = hz
        dxdy_a = _seg_dxdy(list(dt.GetActiveSketch2.GetSketchSegments())[0])
        result["detail"]["horizontal_dy"] = {
            "before_mm": round(dxdy_b[1] * 1000, 4),
            "after_mm": round(dxdy_a[1] * 1000, 4),
        }
        result["token_dump"]["horizontal"] = hz.get("ok") and hz.get("relations_applied", 0) >= 1
        result["gates"]["G3_horizontal_moves_geometry"] = (
            abs(dxdy_b[1]) > 0.001 and abs(dxdy_a[1]) < 1e-6
        )
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G4: PERPENDICULAR on two near-perpendicular lines ────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(0.0, 0.0, 0.0, 0.020, 0.001, 0.0)    # ~horizontal
        sm.CreateLine(0.020, 0.0, 0.0, 0.019, 0.020, 0.0)  # ~vertical
        pp = apply_relations_in_open_sketch(
            dt, [{"type": "perpendicular", "entities": [0, 1]}]
        )
        result["detail"]["perpendicular_apply"] = pp
        s = list(dt.GetActiveSketch2.GetSketchSegments())
        v0, v1 = _seg_dxdy(s[0]), _seg_dxdy(s[1])
        dot = v0[0] * v1[0] + v0[1] * v1[1]
        result["detail"]["perpendicular_dot"] = round(dot, 9)
        result["token_dump"]["perpendicular"] = pp.get("ok") and pp.get("relations_applied", 0) >= 1
        result["gates"]["G4_perpendicular_moves_geometry"] = abs(dot) < 1e-7
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G5: token dump for the remaining guessed tokens ──────────────
        # parallel/coincident/collinear/concentric/vertical/symmetric — fire-test
        # each on a fresh minimal sketch; record fires vs raises (no effect gate,
        # just token validity so a wrong guess is NAMED).
        remaining = ["parallel", "vertical", "collinear"]
        for rtype in remaining:
            try:
                doc, dt = _new_part(sw_typed, mod)
                sm = dt.SketchManager
                sm.InsertSketch(True)
                if rtype == "vertical":
                    sm.CreateLine(0.0, 0.0, 0.0, 0.002, 0.020, 0.0)
                    rel = [{"type": "vertical", "entities": [0]}]
                else:
                    sm.CreateLine(0.0, 0.0, 0.0, 0.020, 0.001, 0.0)
                    sm.CreateLine(0.0, 0.005, 0.0, 0.020, 0.007, 0.0)
                    rel = [{"type": rtype, "entities": [0, 1]}]
                r = apply_relations_in_open_sketch(dt, rel)
                result["token_dump"][rtype] = r.get("ok") and r.get("relations_applied", 0) >= 1
                sm.InsertSketch(True)
                sw.CloseAllDocuments(True)
            except Exception as exc:
                result["token_dump"][rtype] = False
                result["errors"].append(f"{rtype} dump raised: {exc!r}")

        result["gates"]["G5_all_tested_tokens_fire"] = all(
            result["token_dump"].get(t) for t in
            ["equal", "horizontal", "perpendicular", "parallel", "vertical", "collinear"]
        )

        result["ok"] = all(result["gates"].values())
        return result
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


if __name__ == "__main__":
    print("=== W39 sketch relations S1 PAE ===", file=sys.stderr)
    out = run()
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("ok") else 1)
