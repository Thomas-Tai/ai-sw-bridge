"""
Spike W45-B — UNDERCUT DETECTION DFM probe (read-only).

SEAT-RUNNABLE BY W0. NOT run by the offline author (no seat access).

Builds TWO discriminating fixtures from scratch, runs
``observe.sw_undercut_faces`` against each along a +Y pull, and writes a
single structured JSON verdict to ``_results/undercut_w45.json``.

Fixtures (the flag MUST discriminate):
  CLEAN    : a simple boss extruded UP the +Y pull (a rectangular prism on
             the Top plane, extruded +Y). Along +Y every face is releasable
             (+Y top cap), a side wall (the four vertical walls), or the
             bottom (-Y) seat. NOTE: the bottom cap's outward normal is -Y,
             which IS opposite the pull -> for a strict single-direction +Y
             pull the seat counts as an undercut. So the "CLEAN" reference is
             actually "exactly ONE back face (the seat)".
  UNDERCUT : the same boss PLUS a cut that creates an overhang ledge whose
             face points back along -Y (a true mold-trap undercut beyond the
             seat). Expected undercut_count strictly GREATER than CLEAN.

GREEN criterion (verify-the-effect, discrimination):
  - both probes return ok=True
  - undercut.undercut_count  >  clean.undercut_count
  - the extra flagged face has dot_pull < 0 (genuinely back-facing)

The probe reuses the W37 draft machinery (IFace2.Normal vs pull dot product),
so the only new seat dependency is GetBodies2/GetFaces enumeration on the
part -- both PROVEN reachable late-bound (spec/_face_geometry.py).

Usage (on the seat):
    python spikes/v0_2x/undercut_w45.py
Exit 0 only if the discrimination GREEN criterion holds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.observe import sw_undercut_faces  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "_results" / "undercut_w45.json"

SW_END_COND_BLIND = 0

# Boss on the Top plane (XZ), extruded +Y. The pull direction is +Y.
PULL = (0.0, 1.0, 0.0)
BOSS_W = 0.040  # 40 mm (X)
BOSS_D = 0.040  # 40 mm (Z)
BOSS_H = 0.030  # 30 mm extrude up +Y


def _new_part(sw):
    template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    if not template:
        raise RuntimeError("no default Part template configured")
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    return doc


def _boss_up(doc) -> None:
    """Extrude a centered boss on the Top plane up the +Y pull axis."""
    if not doc.SelectByID("Top Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select Top Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    hx, hz = BOSS_W / 2.0, BOSS_D / 2.0
    sm.CreateCornerRectangle(-hx, -hz, 0.0, hx, hz, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        BOSS_H,
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
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 returned None")


def _cut_overhang(doc) -> None:
    """Add an undercut: a horizontal slot cut into a +Y-facing side wall that
    leaves a downward (-Y) facing ledge -- a face the +Y mold half cannot
    release.

    Implementation: sketch a rectangle on the +Z side wall and cut INWARD a
    shallow pocket whose TOP face points -Y (overhang). We sketch on the +Z
    face plane (z = BOSS_D/2) and cut along -Z.
    """
    doc.ClearSelection2(True)
    # Select the +Z side wall (face center at z = +BOSS_D/2, mid height).
    z_face = BOSS_D / 2.0
    if not doc.SelectByID("", "FACE", 0.0, BOSS_H / 2.0, z_face):
        raise RuntimeError("could not select +Z side wall for undercut cut")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # A small rectangle near the top of the wall; cutting it leaves a
    # downward-facing overhang ledge.
    # Sketch coords on this face: SW maps the wall's local frame; a centered
    # small rect suffices to create the overhang regardless of exact mapping.
    sm.CreateCornerRectangle(-0.010, 0.005, 0.0, 0.010, 0.012, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    # FeatureCut4 (27-arg verified form -- mirrors spec/builder.py).
    cut = fm.FeatureCut4(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,  # 1-5
        0.008,
        0.0,
        False,
        False,
        False,
        False,  # 6-11
        0.0,
        0.0,
        False,
        False,
        False,
        False,  # 12-17
        False,
        True,
        True,
        True,
        True,
        False,  # 18-23
        0,
        0.0,
        False,
        False,  # 24-27
    )
    if cut is None:
        raise RuntimeError("FeatureCut4 returned None (undercut cut failed)")


def _run_one(sw, *, with_undercut: bool) -> dict:
    doc = _new_part(sw)
    _boss_up(doc)
    if with_undercut:
        _cut_overhang(doc)
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    return sw_undercut_faces(pull_x=PULL[0], pull_y=PULL[1], pull_z=PULL[2])


def run_com() -> dict:
    sw = get_sw_app()
    clean = _run_one(sw, with_undercut=False)
    dirty = _run_one(sw, with_undercut=True)

    clean_n = clean.get("undercut_count")
    dirty_n = dirty.get("undercut_count")

    extra_back_facing = False
    if dirty.get("undercut_faces"):
        extra_back_facing = all(
            f.get("dot_pull", 0.0) < 0 for f in dirty["undercut_faces"]
        )

    checks = {
        "clean_ok": bool(clean.get("ok")),
        "dirty_ok": bool(dirty.get("ok")),
        "dirty_gt_clean": (
            clean_n is not None and dirty_n is not None and dirty_n > clean_n
        ),
        "flagged_faces_back_facing": extra_back_facing,
    }
    overall = all(checks.values())
    return {
        "overall": "PASS" if overall else "FAIL",
        "checks": checks,
        "pull_dir": list(PULL),
        "clean_undercut_count": clean_n,
        "undercut_undercut_count": dirty_n,
        "clean_probe": clean,
        "undercut_probe": dirty,
        "fixture": {
            "boss_mm": [BOSS_W * 1000.0, BOSS_D * 1000.0, BOSS_H * 1000.0],
        },
    }


def main() -> int:
    result = run_com()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
