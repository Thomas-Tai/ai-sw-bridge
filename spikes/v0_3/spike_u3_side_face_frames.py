"""
Spike U3: side-face frame discovery, two key fixes vs U2:

  1. Identify the new face by SET DIFFERENCE on face centers (not by
     IsCylinder, which returned False for cylindrical faces -- the
     pywin32 binding to IFace2.GetSurface().IsCylinder may not work).
  2. Reverse cut direction for outward-normal faces. FeatureCut4
     with Dir=True flips the cut direction. We'll try Dir=True so the
     cut goes INTO the body regardless of which side face we picked.
     If THROUGH_ALL bidirectional ('T1=2', not standard...) also doesn't
     work, fall back to BLIND 5mm with whichever direction works.

For each side face:
  - Fresh box.
  - Click face, sketch circle at (u=+5, v=+3, r=1).
  - Cut BLIND 5mm INTO the body (use Dir flag to flip direction toward
    body center).
  - Compare face center list to pre-cut snapshot. Any new face centers
    are the new geometry. Print those.
  - Among new face centers, the one with the SMALLEST bounding box
    is the dimple bottom (planar) -- its center tells us where the
    circle landed in part coords.

Usage:
    python spikes/v0_3/spike_u3_side_face_frames.py
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
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        SW_END_COND_BLIND, 0, side_mm / 1000, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True,
        SW_START_SKETCH_PLANE, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("box extrude returned None")
    feat.Name = "Box30"


def _face_centers_with_size(doc) -> list[tuple[tuple[float, float, float], float]]:
    """Return [(center_xyz_meters, max_extent_m)] for each face. max_extent
    is the largest of dx, dy, dz of the bounding box -- lets us tell tiny
    new faces (dimple bottom, cylinder) from the big original box faces."""
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        return []
    body = bodies[-1]
    faces = body.GetFaces
    if callable(faces):
        faces = faces()
    if not faces:
        return []
    out = []
    for face in faces:
        try:
            box = face.GetBox
            if callable(box):
                box = box()
        except Exception:
            box = None
        if not box or len(box) != 6:
            continue
        cx = (box[0] + box[3]) / 2.0
        cy = (box[1] + box[4]) / 2.0
        cz = (box[2] + box[5]) / 2.0
        ext = max(abs(box[3] - box[0]), abs(box[4] - box[1]), abs(box[5] - box[2]))
        out.append(((cx, cy, cz), ext))
    return out


def _probe_one_face(sw, template: str, face_label: str, click_pt_mm,
                    sketch_u_mm: float, sketch_v_mm: float) -> None:
    print(f"\n--- probing {face_label} ---")
    print(f"  click @ part ({click_pt_mm[0]:+.2f}, {click_pt_mm[1]:+.2f}, "
          f"{click_pt_mm[2]:+.2f}) mm")
    print(f"  sketch circle center @ sketch (u={sketch_u_mm:+.2f}, "
          f"v={sketch_v_mm:+.2f}) mm")

    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("  ! could not create doc")
        return

    try:
        _create_centered_box(doc, side_mm=30.0)

        before = _face_centers_with_size(doc)
        before_centers = {tuple(round(v * 1000, 2) for v in c) for c, _ in before}

        doc.ClearSelection2(True)
        cx_m = click_pt_mm[0] / 1000.0
        cy_m = click_pt_mm[1] / 1000.0
        cz_m = click_pt_mm[2] / 1000.0
        if not doc.SelectByID("", "FACE", cx_m, cy_m, cz_m):
            print(f"  ! could not select face")
            return

        sm = doc.SketchManager
        sm.InsertSketch(True)

        u_m = sketch_u_mm / 1000.0
        v_m = sketch_v_mm / 1000.0
        r_m = 0.001
        sm.CreateCircle(u_m, v_m, 0.0, u_m + r_m, v_m, 0.0)
        sm.InsertSketch(True)

        # Try the cut with BOTH directions until one succeeds.
        for dir_flag in (False, True):
            doc.ClearSelection2(True)
            sketch_feat = doc.FeatureByPositionReverse(0)
            if sketch_feat is None:
                print("  ! no sketch produced")
                return
            sketch_feat.Select2(False, 0)
            fm = doc.FeatureManager
            cut = fm.FeatureCut4(
                True, False, dir_flag,
                SW_END_COND_BLIND, 0,
                0.005, 0.0,  # 5mm depth
                False, False, False, False, 0.0, 0.0,
                False, False, False, False, False,
                True, True, True, True,
                False, 0, 0.0, False, False,
            )
            if cut is not None:
                print(f"  cut succeeded with Dir={dir_flag}")
                break
        else:
            print("  ! cut failed both directions")
            return

        after = _face_centers_with_size(doc)
        new_faces = []
        for c, ext in after:
            key = tuple(round(v * 1000, 2) for v in c)
            if key not in before_centers:
                new_faces.append((c, ext))

        print(f"  new faces: {len(new_faces)}")
        # Find smallest face by extent -- that's the dimple bottom (planar
        # circle, radius ~1mm so extent ~2mm). The cylindrical face's
        # extent will be 5mm in the depth direction.
        if new_faces:
            new_faces.sort(key=lambda x: x[1])
            for i, (c, ext) in enumerate(new_faces):
                cx_mm = c[0] * 1000
                cy_mm = c[1] * 1000
                cz_mm = c[2] * 1000
                print(f"    new[{i}] center=({cx_mm:+7.2f}, {cy_mm:+7.2f}, "
                      f"{cz_mm:+7.2f}) mm extent={ext*1000:.2f}mm")
            # The smallest is the dimple bottom; report its center
            smallest = new_faces[0]
            sc = smallest[0]
            print(f"  *** sketch (u=+5, v=+3) on {face_label} maps to "
                  f"part ({sc[0]*1000:+.2f}, {sc[1]*1000:+.2f}, "
                  f"{sc[2]*1000:+.2f}) mm ***")
    except Exception as e:
        print(f"  ! probe raised: {e!r}")
        traceback.print_exc()
    finally:
        try:
            sw.CloseDoc(doc.GetTitle)
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)

    print("== Spike U3: side-face frame discovery ==")
    print("== Box spans (+/-15, +/-15, 0..30). Front Plane = XY, axis +z.")
    print("== Sketch circle r=1mm at (u=+5, v=+3) on each side face.")
    print("== Cut 5mm BLIND. Find the smallest new face = dimple bottom.")

    probes = [
        ("+x face (normal +x)", (15.0, 0.0, 15.0)),
        ("-x face (normal -x)", (-15.0, 0.0, 15.0)),
        ("+y face (normal +y)", (0.0, 15.0, 15.0)),
        ("-y face (normal -y)", (0.0, -15.0, 15.0)),
    ]
    for label, click_pt in probes:
        _probe_one_face(sw, template, label, click_pt,
                        sketch_u_mm=5.0, sketch_v_mm=3.0)

    print("\n== Summary ==")
    print("== Read 'sketch (u=+5, v=+3) on FACE maps to (a, b, c) mm'.")
    print("== The face's normal axis = the constant component (a, b, or c).")
    print("== The other two are (u, v) -> (?, ?) mapping. Use the signs")
    print("== and which axis is u vs v to derive the per-face transform.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
