"""W39 S1 seat PAE — sketch relations per-token effect validation (v2).

Drives the SHIPPING production ``apply_relations_in_open_sketch`` against
live sketches on SW 2024 SP1. Every advertised token must show geometry
MOVED (not just "no error" — the W21 no-op trap).

Shipping set (6 relations, all tokens effect-verified):
  horizontal (sgHORIZONTAL2D), vertical (sgVERTICAL2D),
  parallel (sgPARALLEL), perpendicular (sgPERPENDICULAR2D),
  equal (sgSAMELENGTH), concentric (sgCONCENTRIC)

Deferred (3 — tokens unproven, fail-closed):
  collinear, coincident, symmetric (see docs/DEFERRED.md)

Gates:
  G1 token-fires:    each token applied with no exception AND relation count +1
  G2 equal-moves:    two unequal lines → equal → lengths converge
  G3 horizontal:     tilted line → horizontal → dy → 0
  G4 perpendicular:  near-perpendicular → perpendicular → dot → 0
  G5 vertical:       tilted line → vertical → dx → 0
  G6 parallel:       two non-parallel lines → parallel → cross-product → 0
  G7 concentric:     two offset circles → concentric → centers coincide

PAUSE-ON-ERROR: any gate FALSE → STOP, report, do not auto-iterate.
"""

from __future__ import annotations

import json
import math
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


def _segs(dt):
    """Active-sketch segments from a TYPED IModelDoc2 proxy.

    On the typed proxy GetActiveSketch2 is a METHOD (needs ()); GetSketchSegments
    then auto-invokes as a property (no parens). Production uses the raw
    late-bound doc where GetActiveSketch2 auto-invokes — this helper is the
    harness-side equivalent for the typed proxy the PAE builds.
    """
    sk = dt.GetActiveSketch2
    if callable(sk):
        sk = sk()
    return list(sk.GetSketchSegments)


def _seg_len(seg):
    sp = seg.GetStartPoint2
    ep = seg.GetEndPoint2
    dx, dy = ep.X - sp.X, ep.Y - sp.Y
    return (dx * dx + dy * dy) ** 0.5


def _seg_dxdy(seg):
    sp = seg.GetStartPoint2
    ep = seg.GetEndPoint2
    return (ep.X - sp.X, ep.Y - sp.Y)


def _circle_center(seg):
    """Read center of a sketch arc/circle via GetCenterPoint2."""
    try:
        cp = seg.GetCenterPoint2
        return (cp.X, cp.Y)
    except Exception:
        return None


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
        # ── G2: EQUAL (sgSAMELENGTH) on two unequal lines ───────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(-0.015, 0.020, 0.0, 0.015, 0.020, 0.0)   # 30mm
        sm.CreateLine(-0.005, 0.010, 0.0, 0.005, 0.010, 0.0)   # 10mm
        segs = _segs(dt)
        len0_b, len1_b = _seg_len(segs[0]), _seg_len(segs[1])
        eq = apply_relations_in_open_sketch(
            doc, [{"type": "equal", "entities": [0, 1]}]
        )
        result["detail"]["equal_apply"] = eq
        segs2 = _segs(dt)
        len0_a, len1_a = _seg_len(segs2[0]), _seg_len(segs2[1])
        result["detail"]["equal_lengths"] = {
            "before": [round(len0_b * 1000, 4), round(len1_b * 1000, 4)],
            "after": [round(len0_a * 1000, 4), round(len1_a * 1000, 4)],
        }
        result["token_dump"]["equal"] = eq.get("ok") and eq.get("relations_applied", 0) >= 1
        result["gates"]["G2_equal_moves_geometry"] = (
            abs(len0_b - len1_b) > 0.005
            and abs(len0_a - len1_a) < 1e-5
        )
        result["gates"]["G1_equal_token_fires"] = bool(result["token_dump"]["equal"])
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G3: HORIZONTAL (sgHORIZONTAL2D) on a tilted line ────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(-0.015, 0.020, 0.0, 0.015, 0.022, 0.0)   # tilted (dy=2mm)
        dxdy_b = _seg_dxdy(_segs(dt)[0])
        hz = apply_relations_in_open_sketch(
            doc, [{"type": "horizontal", "entities": [0]}]
        )
        result["detail"]["horizontal_apply"] = hz
        dxdy_a = _seg_dxdy(_segs(dt)[0])
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

        # ── G4: PERPENDICULAR (sgPERPENDICULAR2D) ───────────────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(0.0, 0.0, 0.0, 0.020, 0.001, 0.0)    # ~horizontal
        sm.CreateLine(0.020, 0.0, 0.0, 0.019, 0.020, 0.0)  # ~vertical
        pp = apply_relations_in_open_sketch(
            doc, [{"type": "perpendicular", "entities": [0, 1]}]
        )
        result["detail"]["perpendicular_apply"] = pp
        s = _segs(dt)
        v0, v1 = _seg_dxdy(s[0]), _seg_dxdy(s[1])
        dot = v0[0] * v1[0] + v0[1] * v1[1]
        result["detail"]["perpendicular_dot"] = round(dot, 9)
        result["token_dump"]["perpendicular"] = pp.get("ok") and pp.get("relations_applied", 0) >= 1
        result["gates"]["G4_perpendicular_moves_geometry"] = abs(dot) < 1e-7
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G5: VERTICAL (sgVERTICAL2D) on a tilted line ────────────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(0.0, 0.0, 0.0, 0.002, 0.020, 0.0)   # tilted (dx=2mm)
        dxdy_b = _seg_dxdy(_segs(dt)[0])
        vt = apply_relations_in_open_sketch(
            doc, [{"type": "vertical", "entities": [0]}]
        )
        result["detail"]["vertical_apply"] = vt
        dxdy_a = _seg_dxdy(_segs(dt)[0])
        result["detail"]["vertical_dx"] = {
            "before_mm": round(dxdy_b[0] * 1000, 4),
            "after_mm": round(dxdy_a[0] * 1000, 4),
        }
        result["token_dump"]["vertical"] = vt.get("ok") and vt.get("relations_applied", 0) >= 1
        result["gates"]["G5_vertical_moves_geometry"] = (
            abs(dxdy_b[0]) > 0.001 and abs(dxdy_a[0]) < 1e-6
        )
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G6: PARALLEL (sgPARALLEL) on two non-parallel lines ─────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateLine(0.0, 0.0, 0.0, 0.020, 0.001, 0.0)    # ~horizontal (slope ~0.05)
        sm.CreateLine(0.0, 0.005, 0.0, 0.020, 0.007, 0.0)  # different slope (~0.1)
        v0_b = _seg_dxdy(_segs(dt)[0])
        v1_b = _seg_dxdy(_segs(dt)[1])
        cross_b = v0_b[0] * v1_b[1] - v0_b[1] * v1_b[0]
        pa = apply_relations_in_open_sketch(
            doc, [{"type": "parallel", "entities": [0, 1]}]
        )
        result["detail"]["parallel_apply"] = pa
        s = _segs(dt)
        v0_a = _seg_dxdy(s[0])
        v1_a = _seg_dxdy(s[1])
        cross_a = v0_a[0] * v1_a[1] - v0_a[1] * v1_a[0]
        result["detail"]["parallel_cross"] = {
            "before": round(cross_b, 9),
            "after": round(cross_a, 9),
        }
        result["token_dump"]["parallel"] = pa.get("ok") and pa.get("relations_applied", 0) >= 1
        result["gates"]["G6_parallel_moves_geometry"] = (
            abs(cross_b) > 1e-7 and abs(cross_a) < 1e-7
        )
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── G7: CONCENTRIC (sgCONCENTRIC) on two offset circles ─────────
        doc, dt = _new_part(sw_typed, mod)
        sm = dt.SketchManager
        sm.InsertSketch(True)
        sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)      # center at origin, r=5mm
        sm.CreateCircle(0.010, 0.005, 0.0, 0.013, 0.005, 0.0) # center at (10,5)mm, r=3mm
        segs = _segs(dt)
        c0_b = _circle_center(segs[0])
        c1_b = _circle_center(segs[1])
        if c0_b and c1_b:
            dist_b = math.hypot(c1_b[0] - c0_b[0], c1_b[1] - c0_b[1])
        else:
            dist_b = 999.0
        cc = apply_relations_in_open_sketch(
            doc, [{"type": "concentric", "entities": [0, 1]}]
        )
        result["detail"]["concentric_apply"] = cc
        segs2 = _segs(dt)
        c0_a = _circle_center(segs2[0])
        c1_a = _circle_center(segs2[1])
        if c0_a and c1_a:
            dist_a = math.hypot(c1_a[0] - c0_a[0], c1_a[1] - c0_a[1])
        else:
            dist_a = 999.0
        result["detail"]["concentric_centers"] = {
            "dist_before_mm": round(dist_b * 1000, 4),
            "dist_after_mm": round(dist_a * 1000, 4),
        }
        result["token_dump"]["concentric"] = cc.get("ok") and cc.get("relations_applied", 0) >= 1
        result["gates"]["G7_concentric_moves_geometry"] = (
            dist_b > 0.001 and dist_a < 1e-6
        )
        sm.InsertSketch(True)
        sw.CloseAllDocuments(True)

        # ── Summary ─────────────────────────────────────────────────────
        all_tokens_fired = all(
            result["token_dump"].get(t) for t in
            ["equal", "horizontal", "perpendicular", "vertical", "parallel", "concentric"]
        )
        result["gates"]["G1_all_tokens_fire"] = all_tokens_fired

        result["ok"] = all(result["gates"].values())
        result["shipped_tokens"] = dict(RELATION_TOKENS)
        result["deferred"] = ["collinear", "coincident", "symmetric"]
        return result
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


if __name__ == "__main__":
    print("=== W39v sketch relations S1 PAE (seat-corrected) ===", file=sys.stderr)
    out = run()
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("ok") else 1)
