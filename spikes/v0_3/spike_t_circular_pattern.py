"""
Spike T: circular pattern via FeatureCircularPattern5 (14 args).

Builds a small cylindrical hub (a disc), adds an off-center boss seed on
the +z face, then circular-patterns the boss 6x around the disc's central
axis at equal spacing.

API: IFeatureManager::FeatureCircularPattern5 -- 14 args.
  (Number, Spacing, FlipDirection, DName, GeometryPattern, EqualSpacing,
   VaryInstance, SyncSubAssemblies, BDir2, BSymmetric, Number2, Spacing2,
   DName2, EqualSpacing2)

Selection protocol (per SW API conventions, mirrors Spike R linear_pattern):
  1. Select the ROTATION AXIS -- mark = 1 (swSelPatternRefAxis).
     Easiest source on a disc: the cylindrical OUTER face carries an
     implicit axis. Selecting it with type="FACE" puts a face on the
     selection set; for circular pattern, SW actually wants an "AXIS"
     entity. Two viable paths:
       a) Pre-create a temporary axis through the disc center via
          InsertAxis2 / InsertRefAxis, then select it by name.
       b) Select a circular edge (the disc's top circular edge) -- SW
          can infer the axis of revolution from a circular edge for
          pattern features.
     Path (b) is cheaper and matches our edge-by-point idiom. If it
     fails, fall back to (a).
  2. Select the SEED FEATURE -- mark = 4 (swSelPatternBody).
     Use IFeature.Select2(append=True, mark=4) on the seed -- same as
     spike_r_linear_pattern.

Geometry: 30mm-diameter disc, 5mm thick. Seed boss = 3mm-dia cylinder
at (10, 0) on top face, extruded 2mm. Pattern: 6 instances, equal-spaced
(total 360 degrees).

Risk: if SW doesn't accept a circular edge as the rotation-axis reference,
we'll get FeatureCircularPattern5 -> None. Fallback: select a face with
implicit-axis (selecting the cylindrical outer face of the disc), or
explicitly create a temporary axis first.

Usage:
    python spikes/v0_3/spike_t_circular_pattern.py
"""

from __future__ import annotations

import math
import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0


def _create_disc(doc, dia_mm: float, thick_mm: float) -> None:
    """Disc centered on origin, axis = +z, top face at z = thick_mm."""
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    r = dia_mm / 2 / 1000
    # circle center + rim point
    sm.CreateCircle(0.0, 0.0, 0.0, r, 0.0, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        thick_mm / 1000,
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
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("disc extrude returned None")
    feat.Name = "EX_Disc"


def _create_boss_seed(
    doc, thick_mm: float, offset_mm: float, seed_dia_mm: float, seed_height_mm: float
):
    """Off-center boss on the top face of the disc. Returns IFeature."""
    fm = doc.FeatureManager
    doc.ClearSelection2(True)
    z_top = thick_mm / 1000
    if not doc.SelectByID("", "FACE", 0.0, 0.0, z_top):
        raise RuntimeError("could not select +z face for seed sketch")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    cx = offset_mm / 1000
    cy = 0.0
    r = seed_dia_mm / 2 / 1000
    sm.CreateCircle(cx, cy, 0.0, cx + r, cy, 0.0)
    sm.InsertSketch(True)

    doc.ClearSelection2(True)
    sketch_feat = doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced for seed boss")
    sketch_feat.Name = "SK_Boss_Seed"
    sketch_feat.Select2(False, 0)

    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        seed_height_mm / 1000,
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
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("seed boss extrude returned None")
    feat.Name = "Boss_Seed"
    return feat


def _face_count(doc) -> int:
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        return -1
    body = bodies[-1]
    faces = body.GetFaces
    if callable(faces):
        faces = faces()
    return len(faces) if faces else -1


def _select_circular_edge_for_axis(doc, thick_mm: float, dia_mm: float) -> bool:
    """Select a point on the disc's TOP CIRCULAR EDGE.

    The top circular edge runs at z = thick_mm along radius = dia_mm/2.
    A point on it: (r, 0, thick_mm). SelectByID with type='EDGE'.
    """
    doc.ClearSelection2(True)
    r_m = (dia_mm / 2) / 1000
    z_m = thick_mm / 1000
    ok = doc.SelectByID("", "EDGE", r_m, 0.0, z_m)
    print(f"  SelectByID(EDGE @ r={r_m*1000:.2f}, 0, z={z_m*1000:.2f}) -> {ok}")
    if not ok:
        return False
    sel_mgr = doc.SelectionManager
    ok_mark = sel_mgr.SetSelectedObjectMark(1, 1, 0)
    print(f"  SetSelectedObjectMark(1, mark=1, set) -> {ok_mark}")
    n = sel_mgr.GetSelectedObjectCount2(-1)
    if n > 0:
        sel_type = sel_mgr.GetSelectedObjectType3(1, -1)
        print(f"  selection[1] type={sel_type} (1=edge, 2=face, 4=axis)")
    return True


def _select_cylindrical_face_for_axis(doc, dia_mm: float, thick_mm: float) -> bool:
    """Fallback: select the cylindrical SIDE face of the disc.

    The side face is on the rim; a point at (dia_mm/2, 0, thick_mm/2) is
    on it. SW infers the axis of revolution from the cylindrical face.
    """
    doc.ClearSelection2(True)
    r_m = (dia_mm / 2) / 1000
    z_mid_m = (thick_mm / 2) / 1000
    ok = doc.SelectByID("", "FACE", r_m, 0.0, z_mid_m)
    print(f"  SelectByID(FACE @ side r={r_m*1000:.2f}, z={z_mid_m*1000:.2f}) -> {ok}")
    if not ok:
        return False
    sel_mgr = doc.SelectionManager
    ok_mark = sel_mgr.SetSelectedObjectMark(1, 1, 0)
    print(f"  SetSelectedObjectMark(1, mark=1, set) -> {ok_mark}")
    return True


def _try_circular_pattern(fm, count: int, total_angle_rad: float) -> int:
    print(
        f"-- FeatureCircularPattern5 (14 args), count={count},"
        f" total={math.degrees(total_angle_rad):.1f}deg --"
    )
    try:
        f = fm.FeatureCircularPattern5(
            count,  # Number
            total_angle_rad,  # Spacing (=total angle when EqualSpacing=True)
            False,  # FlipDirection
            "",  # DName
            False,  # GeometryPattern
            True,  # EqualSpacing
            False,  # VaryInstance
            False,  # SyncSubAssemblies
            False,  # BDir2
            False,  # BSymmetric
            1,  # Number2
            0.0,  # Spacing2
            "",  # DName2
            False,  # EqualSpacing2
        )
        print(f"  FeatureCircularPattern5 -> {f!r}")
        if f is None:
            return 11
        f.Name = "CP_Seed_T"
        print(f"  pattern feature: {f.Name}")
        return 0
    except Exception as e:
        print(f"  ! FeatureCircularPattern5 raised: {e!r}")
        traceback.print_exc()
        return 12


def _run_case(sw, template: str, case_name: str, axis_picker) -> int:
    print(f"\n=== {case_name} ===")
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("could not create blank doc")
        return 2
    dia_mm = 30.0
    thick_mm = 5.0
    try:
        _create_disc(doc, dia_mm=dia_mm, thick_mm=thick_mm)
        f_before_seed = _face_count(doc)
        print(f"  disc built; faces = {f_before_seed} (expect 3 = top+bottom+side)")

        seed = _create_boss_seed(
            doc, thick_mm=thick_mm, offset_mm=10.0, seed_dia_mm=3.0, seed_height_mm=2.0
        )
        f_after_seed = _face_count(doc)
        print(f"  seed boss built; faces = {f_after_seed} (expect +2)")

        if not axis_picker(doc, dia_mm, thick_mm):
            print("  ! axis selection failed -- aborting case")
            return 3

        sel_mgr = doc.SelectionManager
        ok_seed = seed.Select2(True, 4)
        print(f"  IFeature.Select2(append=True, mark=4) on seed -> {ok_seed}")
        n = sel_mgr.GetSelectedObjectCount2(-1)
        print(f"  total selected: {n}")
        for idx in range(1, n + 1):
            m = sel_mgr.GetSelectedObjectMark(idx)
            t = sel_mgr.GetSelectedObjectType3(idx, -1)
            print(f"    sel[{idx}] mark={m} type={t}")

        fm = doc.FeatureManager
        rc = _try_circular_pattern(fm, count=6, total_angle_rad=2 * math.pi)
        f_after = _face_count(doc)
        print(
            f"  faces after pattern = {f_after} (expect {f_after_seed} + 5*2 = {f_after_seed + 10})"
        )
        if rc == 0 and f_after == f_after_seed + 10:
            print(f"  GREEN: {case_name}")
            return 0
        elif rc == 0:
            print(
                f"  YELLOW: pattern feature created but face count "
                f"{f_after} != expected {f_after_seed + 10}"
            )
            return 4
        else:
            print(f"  RED: pattern returned None or raised")
            return rc
    except Exception as e:
        print(f"  ! case raised: {e!r}")
        traceback.print_exc()
        return 99


def _select_circular_edge_top(doc, dia_mm, thick_mm):
    return _select_circular_edge_for_axis(doc, thick_mm=thick_mm, dia_mm=dia_mm)


def _select_side_face(doc, dia_mm, thick_mm):
    return _select_cylindrical_face_for_axis(doc, dia_mm=dia_mm, thick_mm=thick_mm)


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)

    print("== Spike T: circular pattern via FeatureCircularPattern5 ==")

    rc_a = _run_case(
        sw, template, "Case A: top circular EDGE as axis ref", _select_circular_edge_top
    )
    rc_b = _run_case(
        sw, template, "Case B: cylindrical side FACE as axis ref", _select_side_face
    )

    print(f"\n== Summary ==")
    print(f"  Case A (circular EDGE): rc={rc_a}")
    print(f"  Case B (cylindrical FACE): rc={rc_b}")
    if rc_a == 0 or rc_b == 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
