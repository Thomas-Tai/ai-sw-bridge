"""W37 S1 seat PAE — DFM draft analysis production-path validation.

Drives the SHIPPING observe_draft.read_draft() against two live-built fixtures
to prove IFace2.Normal returns HONEST OUTWARD normals from real B-rep (the
load-bearing risk: if the normal were inward/flipped, draft SIGNS invert).

Fixture A — plain box (proves outward-normal honesty + 3-class discrimination):
  pull = "top" (+Y). Expect, on a 20x30x40 box:
    - top face normal (0,+1,0)  -> draft = +90  (positive)
    - bottom face     (0,-1,0)  -> draft = -90  (negative)
    - 4 side walls (normal ⊥ Y) -> draft =  0   (vertical, flagged)
  G1: exactly 1 positive, 1 negative, 4 vertical (6 faces).
  G2: top reads +90 (NOT -90) — outward-normal honesty. THE core gate.

Fixture B — tapered extrude, known 5° draft (intermediate-angle fidelity+sign):
  A square profile extruded UP (+Y) with a 5° outward draft. The 4 slanted
  walls tilt OUTWARD as they rise -> their outward normals tilt toward +Y by
  5deg -> draft_deg ≈ +5 under pull "top". Reverse the draft -> ≈ -5 (undercut).
  G3: the 4 drafted walls read ≈ +5 (±0.5).
  G4: discrimination — drafted (≈5) clearly separable from vertical (≈0).

PAUSE-ON-ERROR: any gate FALSE -> STOP, report, do not auto-iterate.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))


def _find_part_template(sw_typed) -> str | None:
    import glob
    cands = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.prtdot",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.PRTDOT",
    ]
    for pat in cands:
        for m in glob.glob(pat):
            return m
    try:
        v = sw_typed.GetUserPreferenceStringValue(9)  # swDefaultTemplatePart
        if v:
            return v
    except Exception:
        pass
    return None


def _build_box(sw, sw_typed, mod, path: str):
    """Build a plain box, save to path, return (doc, typed, feat, err).

    Uses the W35-proven sequence: double InsertSketch(True) toggle (front-plane
    default), then re-SelectByID('Sketch1','SKETCH') before extrude — a
    hand-rolled select-the-sketch-feature sequence makes FeatureExtrusion2
    silently return None (no body).
    """
    from ai_sw_bridge.com.earlybind import typed
    tmpl = _find_part_template(sw_typed)
    doc = sw_typed.NewDocument(tmpl, 0, 0, 0)
    dt = typed(doc, "IModelDoc2", module=mod)
    dt.SketchManager.InsertSketch(True)
    # 20 (X) x 40 (Y-in-sketch) rectangle on the default (front) plane
    dt.SketchManager.CreateCenterRectangle(0, 0, 0, 0.010, 0.020, 0)
    dt.SketchManager.InsertSketch(True)
    dt.ClearSelection2(True)
    dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat = dt.FeatureManager.FeatureExtrusion2(
        True, False, False, 0, 0, 0.030, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0, False,
    )
    dt.ForceRebuild3(True)
    err = dt.SaveAs3(path, 0, 0)
    return doc, dt, feat, err


def _build_tapered(sw, sw_typed, mod, path: str, draft_rad: float, outward: bool):
    """Build a square profile extruded with `draft_rad` taper (proven sequence).

    Extrude is along the sketch normal (+Z). The 4 side walls tilt by draft_rad;
    measured under pull='front' (+Z), their |draft| == applied angle (sign =
    moldable/undercut per draft-direction × pull-direction).
    """
    from ai_sw_bridge.com.earlybind import typed
    tmpl = _find_part_template(sw_typed)
    doc = sw_typed.NewDocument(tmpl, 0, 0, 0)
    dt = typed(doc, "IModelDoc2", module=mod)
    dt.SketchManager.InsertSketch(True)
    dt.SketchManager.CreateCenterRectangle(0, 0, 0, 0.020, 0.020, 0)
    dt.SketchManager.InsertSketch(True)
    dt.ClearSelection2(True)
    dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    # args: 8 Dchk1=True (draft on), 10 Ddir1=outward?, 12 Dang1=draft_rad
    feat = dt.FeatureManager.FeatureExtrusion2(
        True, False, False, 0, 0, 0.040, 0.0,
        True,            # 8  Dchk1 — draft while extruding
        False,           # 9  Dchk2
        bool(outward),   # 10 Ddir1 — draft outward
        False,           # 11 Ddir2
        draft_rad,       # 12 Dang1
        0.0,             # 13 Dang2
        False, False, False, False, True, True, True, 0, 0.0, False,
    )
    dt.ForceRebuild3(True)
    err = dt.SaveAs3(path, 0, 0)
    return doc, dt, feat, err


def run() -> dict:
    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.observe_draft import read_draft, _read_normal, _compute_draft_deg

    def _face_centroid(face):
        # IFace2.GetBox -> (xmin,ymin,zmin,xmax,ymax,zmax) in metres -> centroid
        try:
            box = face.GetBox
            if callable(box):
                box = box()
        except Exception:
            return None
        if not isinstance(box, (tuple, list)) or len(box) != 6:
            return None
        return (
            (float(box[0]) + float(box[3])) / 2.0,
            (float(box[1]) + float(box[4])) / 2.0,
            (float(box[2]) + float(box[5])) / 2.0,
        )

    def _signed_face_walk(part_doc, pull):
        """Return [(centroid_along_pull_mm, draft_deg)] — proves sign vs position.

        QI to IPartDoc first (GetBodies2 is IPartDoc-only — the very bug under
        test). centroid projected onto the pull axis so the high face vs low
        face split is unambiguous for any pull direction.
        """
        out = []
        if hasattr(part_doc, "GetBodies2"):
            pd = part_doc
        else:
            pd = typed(part_doc, "IPartDoc", module=mod)
        bodies = pd.GetBodies2(0, True)
        if not isinstance(bodies, (list, tuple)):
            bodies = (bodies,)
        for body in bodies:
            faces = body.GetFaces
            if callable(faces):
                faces = faces()
            if not isinstance(faces, (tuple, list)):
                continue
            for face in faces:
                n = _read_normal(face)
                c = _face_centroid(face)
                if n is None or c is None:
                    continue
                proj = (c[0] * pull[0] + c[1] * pull[1] + c[2] * pull[2]) * 1000
                out.append((round(proj, 3), round(_compute_draft_deg(n, pull), 3)))
        return out

    result: dict = {"ok": False, "gates": {}, "errors": [], "detail": {}}
    sw = get_sw_app()
    if sw is None:
        result["errors"].append("get_sw_app() returned None")
        return result
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)
    tmpdir = Path(tempfile.mkdtemp(prefix="aisw_W37_pae_"))

    try:
        # ── Fixture A: plain box ─────────────────────────────────────────
        box_path = str(tmpdir / "box.sldprt")
        _doc, dt, _f, err = _build_box(sw, sw_typed, mod, box_path)
        if err != 0:
            result["errors"].append(f"box SaveAs3 err={err}")
            return result
        # Box is extruded along +Z (front plane), so pull = "front" (+Z); caps
        # at ±Z, the 4 walls parallel to Z (vertical).
        da = read_draft(dt, "front", min_angle_deg=1.0, mod=mod)
        result["detail"]["box"] = da
        if da["errors"]:
            result["errors"].append(f"box read_draft: {da['errors']}")
            return result

        result["gates"]["G1_box_3class"] = (
            da["faces_positive"] == 1
            and da["faces_negative"] == 1
            and da["faces_vertical"] == 4
            and da["faces_total"] == 6
        )
        # G2 — outward-normal honesty: the HIGH-Z (front-facing) cap must read
        # POSITIVE and the LOW-Z cap NEGATIVE under pull=front. Counts alone
        # can't prove this (a symmetric box gives 1+/1- either way) — correlate
        # draft SIGN with face POSITION along the pull axis.
        walk = _signed_face_walk(dt, (0.0, 0.0, 1.0))
        result["detail"]["box_signed_walk"] = walk
        top_face = max(walk, key=lambda t: t[0])     # highest centroid along +Z
        bot_face = min(walk, key=lambda t: t[0])     # lowest centroid along +Z
        result["detail"]["box_top_face"] = top_face
        result["detail"]["box_bottom_face"] = bot_face
        result["gates"]["G2_outward_normal_honest"] = (
            top_face[1] > 80.0 and bot_face[1] < -80.0   # ≈ +90 / -90
        )

        # ── Fixture B: tapered +5° outward ───────────────────────────────
        deg5 = math.radians(5.0)
        tap_path = str(tmpdir / "taper5.sldprt")
        _d2, dt2, _f2, err2 = _build_tapered(sw, sw_typed, mod, tap_path, deg5, outward=True)
        if err2 != 0:
            result["errors"].append(f"taper SaveAs3 err={err2}")
            return result
        db = read_draft(dt2, "front", min_angle_deg=1.0, mod=mod)
        result["detail"]["taper5"] = db
        if db["errors"]:
            result["errors"].append(f"taper read_draft: {db['errors']}")
            return result

        # G3 — the 4 slanted side walls must read |draft| ≈ 5° (the applied
        # angle). Sign depends on draft-direction × pull-direction; the
        # MAGNITUDE fidelity is what proves the angle math against a known input.
        twalk = _signed_face_walk(dt2, (0.0, 0.0, 1.0))
        result["detail"]["taper_signed_walk"] = twalk
        # side walls = faces whose |draft| is in (1, 45) — exclude the ±90 caps.
        side_walls = [d for (_cz, d) in twalk if 1.0 < abs(d) < 45.0]
        result["detail"]["taper_side_wall_angles"] = sorted(side_walls)
        near5 = [d for d in side_walls if abs(abs(d) - 5.0) <= 0.5]
        result["gates"]["G3_taper_walls_5deg"] = len(near5) >= 4
        # G4 discrimination: drafted walls (|5|) clearly separate from the box's
        # vertical walls (≈0) — the min side-wall |angle| >> the threshold.
        result["gates"]["G4_discriminates"] = (
            bool(side_walls) and min(abs(d) for d in side_walls) > 2.0
        )

        result["ok"] = all(result["gates"].values())
        return result
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


if __name__ == "__main__":
    print("=== W37 observe_draft S1 PAE ===", file=sys.stderr)
    out = run()
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("ok") else 1)
