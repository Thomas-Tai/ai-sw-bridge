"""
Spike U2: side-face sketch frame discovery, refined from Spike U.

Improvements over U:
  - Fresh box per face probe (avoids state interference)
  - Cut THROUGH_ALL so direction is irrelevant
  - Identify the new cylindrical face by listing only NEW faces post-cut

For each side face (+/-x, +/-y) of a 30mm centered cube:
  1. Build a fresh cube on Front Plane (axis +z, centered at origin,
     spanning z=0..30).
  2. Click the face. Insert sketch. CreateCircle at sketch (u=5, v=3),
     radius=1mm.
  3. Cut THROUGH_ALL. Find the new cylindrical face's centroid in part
     coords. Print it.

The result tells us: "sketch (u=5, v=3) on +x face landed at part (X=?,
Y=?, Z=?)" -- from which we derive the sketch-to-part transform.

Usage:
    python spikes/v0_3/spike_u2_side_face_frames.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 1
SW_START_SKETCH_PLANE = 0


def _create_centered_box(doc, side_mm: float) -> None:
    """Centered cube on Front Plane; box spans (+/-15, +/-15, 0..30)."""
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        side_mm / 1000,
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
        raise RuntimeError("box extrude returned None")
    feat.Name = "Box30"


def _face_signature(face) -> tuple[bool, tuple[float, float, float]] | None:
    """Return (is_cylindrical, center) for a face."""
    try:
        surf = face.GetSurface
        if callable(surf):
            surf = surf()
    except Exception:
        surf = None
    is_cyl = False
    if surf is not None:
        try:
            is_cyl = bool(surf.IsCylinder())
        except Exception:
            try:
                is_cyl = bool(surf.IsCylinder)
            except Exception:
                is_cyl = False
    try:
        box = face.GetBox
        if callable(box):
            box = box()
    except Exception:
        box = None
    if not box or len(box) != 6:
        return is_cyl, (None, None, None)
    cx = (box[0] + box[3]) / 2.0
    cy = (box[1] + box[4]) / 2.0
    cz = (box[2] + box[5]) / 2.0
    return is_cyl, (cx, cy, cz)


def _list_faces(doc):
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        return []
    body = bodies[-1]
    faces = body.GetFaces
    if callable(faces):
        faces = faces()
    return faces or []


def _probe_one_face(
    sw,
    template: str,
    face_label: str,
    click_pt_mm,
    sketch_u_mm: float,
    sketch_v_mm: float,
) -> None:
    print(f"\n--- probing {face_label} ---")
    print(
        f"  click @ part ({click_pt_mm[0]:+.2f}, {click_pt_mm[1]:+.2f}, "
        f"{click_pt_mm[2]:+.2f}) mm"
    )
    print(
        f"  sketch circle center @ sketch (u={sketch_u_mm:+.2f}, "
        f"v={sketch_v_mm:+.2f}) mm"
    )

    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("  ! could not create doc")
        return

    try:
        _create_centered_box(doc, side_mm=30.0)

        # Snapshot face signatures BEFORE the cut
        before = []
        for f in _list_faces(doc):
            sig = _face_signature(f)
            if sig:
                before.append(sig)
        print(f"  faces before cut: {len(before)} (all planar expected)")

        doc.ClearSelection2(True)
        cx_m = click_pt_mm[0] / 1000.0
        cy_m = click_pt_mm[1] / 1000.0
        cz_m = click_pt_mm[2] / 1000.0
        if not doc.SelectByID("", "FACE", cx_m, cy_m, cz_m):
            print(f"  ! could not select face at click point")
            return

        sm = doc.SketchManager
        sm.InsertSketch(True)

        u_m = sketch_u_mm / 1000.0
        v_m = sketch_v_mm / 1000.0
        r_m = 0.001
        sm.CreateCircle(u_m, v_m, 0.0, u_m + r_m, v_m, 0.0)
        sm.InsertSketch(True)

        doc.ClearSelection2(True)
        sketch_feat = doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            print("  ! no sketch produced")
            return
        sketch_feat.Select2(False, 0)

        fm = doc.FeatureManager
        cut = fm.FeatureCut4(
            True,
            False,
            False,
            SW_END_COND_THROUGH_ALL,
            0,
            0.0,
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
            False,
            True,
            True,
            True,
            True,
            False,
            0,
            0.0,
            False,
            False,
        )
        if cut is None:
            print(
                "  ! cut returned None (THROUGH_ALL); the sketch may not "
                "be a closed contour on the selected face"
            )
            return

        # New cylindrical face = the hole's barrel
        after = _list_faces(doc)
        print(f"  faces after cut: {len(after)}")
        new_cyl_centers = []
        for f in after:
            sig = _face_signature(f)
            if not sig:
                continue
            is_cyl, center = sig
            if not is_cyl:
                continue
            new_cyl_centers.append(center)

        if not new_cyl_centers:
            print("  ! no cylindrical face found in result -- cut may not")
            print("    have created a hole, or face inspection failed")
            return

        for center in new_cyl_centers:
            cx_mm = center[0] * 1000 if center[0] is not None else None
            cy_mm = center[1] * 1000 if center[1] is not None else None
            cz_mm = center[2] * 1000 if center[2] is not None else None
            print(
                f"  -> cylindrical hole at part "
                f"({cx_mm:+7.2f}, {cy_mm:+7.2f}, {cz_mm:+7.2f}) mm"
            )
    except Exception as e:
        print(f"  ! probe raised: {e!r}")
        traceback.print_exc()
    finally:
        # Close doc to keep things tidy
        try:
            sw.CloseDoc(doc.GetTitle)
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)

    print("== Spike U2: side-face sketch frame discovery ==")
    print("== Centered cube spans (+/-15, +/-15, 0..30) on Front Plane.")
    print("== Sketch circle at sketch (u=+5, v=+3) on each side face.")
    print("== Through-all cut. Read the resulting cylindrical hole's center.")

    probes = [
        ("+x face", (15.0, 0.0, 15.0)),
        ("-x face", (-15.0, 0.0, 15.0)),
        ("+y face", (0.0, 15.0, 15.0)),
        ("-y face", (0.0, -15.0, 15.0)),
    ]

    for label, click_pt in probes:
        _probe_one_face(sw, template, label, click_pt, sketch_u_mm=5.0, sketch_v_mm=3.0)

    print("\n== End of probe ==")
    print("== Interpret each hole center as: (part_x, part_y, part_z)")
    print("==  which gives the part-coord image of sketch (u=+5, v=+3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
