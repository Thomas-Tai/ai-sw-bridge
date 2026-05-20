"""
Spike U: empirically discover the sketch-to-part-frame transform for the
four SIDE faces (+x, -x, +y, -y) of a +z-axis extrusion.

Background:
  - For +z face (top): sketch X = part X, sketch Y = part Y. mirror_u = +1.
  - For -z face (bottom): sketch X = -part X (flipped), sketch Y = part Y.
    mirror_u = -1.
  - For side faces (+/-x, +/-y) we don't know which part axis maps to
    sketch u vs sketch v, and which (if any) is flipped.

Procedure:
  1. Build a 30x30x30mm centered box on Front Plane (axis = +z).
  2. For each of the four side faces, select the face, insert a sketch,
     and call CreateCircle(u=5mm, v=3mm, r=1mm) -- an asymmetric offset
     so we can tell u from v.
  3. After each, look at where the circle ENDED UP in part coords. We do
     this by:
       a) Closing the sketch.
       b) Finding the new edge: cut-extrude-through-all the circle, look
          at the resulting hole's centroid.
       Simpler: read the sketch's bounding box via GetBoundingBox -- but
       that's in sketch coords. Instead: query the sketch feature's
       contained entities directly via Sketch.GetSketchPoints2 or look
       at the circle's IFeature properties.
  3'. Easiest robust path: after creating the circle and closing the
      sketch, do a cut-extrude-blind 1mm INWARD. Then read GetBodies2
      to find the new hole's location: the hole creates a new cylindrical
      face whose axis we can read via IFace2.GetSurface -> IPlanarSurface
      or IFace2.GetClosestPointOn. Or just look at all the faces and
      find the new cylindrical one.

  3''. SIMPLEST: don't extrude. Use the sketch's geometry directly.
       After InsertSketch(True) closes the sketch, the sketch feature is
       on the tree. Call sketch_feat.GetSpecificFeature2.GetSketchPoints
       to get all points; the circle's center is one of them. Convert
       its sketch-local coords to part coords via the face transform.

Actually the simplest empirical test: after sketching, do a small
cut-extrude-blind and read the new face's center via GetBodies2 ->
GetFaces -> for each face, check if it's planar+small (the new bottom
of the dimple) and within bounding box. Print its centroid.

We'll use the dimple approach -- it's slow (4 features per face) but
gives unambiguous part-frame answers.

Usage:
    python spikes/v0_3/spike_u_side_face_frames.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_END_COND_THROUGH_ALL = 1


def _create_box(doc, side_mm: float) -> None:
    """Centered cube on Front Plane, axis = +z."""
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


def _list_faces_with_centers(doc) -> list:
    """Return list of (face_index, normal, center_xyz) for each face on the
    last body. Center is via GetBoxTLBR average; normal via GetSurface."""
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
    for i, face in enumerate(faces):
        try:
            box = face.GetBox
            if callable(box):
                box = box()
        except Exception:
            box = None
        cx, cy, cz = None, None, None
        if box and len(box) == 6:
            cx = (box[0] + box[3]) / 2.0
            cy = (box[1] + box[4]) / 2.0
            cz = (box[2] + box[5]) / 2.0
        try:
            normal_at_center = (
                face.GetClosestPointOn(cx, cy, cz) if cx is not None else None
            )
        except Exception:
            normal_at_center = None
        # Try IFace2.Normal property
        try:
            n = face.Normal
            if callable(n):
                n = n()
        except Exception:
            n = None
        out.append((i, n, (cx, cy, cz)))
    return out


def _probe_one_face(
    doc,
    face_name: str,
    click_point_mm,
    sketch_u_mm: float,
    sketch_v_mm: float,
    dimple_depth_mm: float = 1.0,
):
    """Sketch a small circle at (sketch_u, sketch_v) on the named face, cut
    a 1mm dimple, then find the new face the cut created and print its
    centroid in part coords.

    face_name is just for logging. click_point_mm is the part-frame point
    used to SELECT the face. sketch_u/v are sketch-frame coords for the
    circle center.
    """
    print(f"\n--- probing {face_name} ---")
    print(
        f"  click @ part ({click_point_mm[0]:+.2f}, {click_point_mm[1]:+.2f}, "
        f"{click_point_mm[2]:+.2f}) mm"
    )
    print(
        f"  sketch circle center @ sketch (u={sketch_u_mm:+.2f}, "
        f"v={sketch_v_mm:+.2f}) mm"
    )

    n_faces_before = len([f for f in _list_faces_with_centers(doc)])
    print(f"  faces before dimple: {n_faces_before}")

    doc.ClearSelection2(True)
    cx_m = click_point_mm[0] / 1000.0
    cy_m = click_point_mm[1] / 1000.0
    cz_m = click_point_mm[2] / 1000.0
    if not doc.SelectByID("", "FACE", cx_m, cy_m, cz_m):
        print(f"  ! could not select face")
        return None

    sm = doc.SketchManager
    sm.InsertSketch(True)

    u_m = sketch_u_mm / 1000.0
    v_m = sketch_v_mm / 1000.0
    r_m = 0.001  # 1mm radius
    sm.CreateCircle(u_m, v_m, 0.0, u_m + r_m, v_m, 0.0)
    sm.InsertSketch(True)

    # Cut-extrude blind
    doc.ClearSelection2(True)
    sketch_feat = doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        print("  ! no sketch produced")
        return None
    sketch_feat.Select2(False, 0)

    fm = doc.FeatureManager
    cut = fm.FeatureCut4(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        dimple_depth_mm / 1000.0,
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
        print("  ! cut returned None")
        return None

    # Now find the new cylindrical face: it's the new face that didn't
    # exist before. We'll just print all faces' centers and the user can
    # diff against the box's 6 face centers (which are at +/-15, 0, 0)/etc.
    faces_after = _list_faces_with_centers(doc)
    print(f"  faces after dimple: {len(faces_after)}")
    # Find the cylindrical face: its centroid will be roughly at the
    # circle's true part location (depth/2 inside the face). The original
    # 6 box faces are at the cube's centroids. The new dimple introduces
    # 1 cylindrical (side wall of dimple) + 1 planar (dimple bottom).
    # The planar dimple bottom should be at click_point - face_normal * depth/2
    # roughly. Print every face's center.
    for fi, normal, center in faces_after:
        if center[0] is None:
            continue
        cx_mm = center[0] * 1000
        cy_mm = center[1] * 1000
        cz_mm = center[2] * 1000
        # Skip the big box faces -- their centers are at +/-15 or 0
        # If |cx|, |cy|, |cz| matches a box face center, skip
        is_box_face = (
            (
                abs(abs(cx_mm) - 15.0) < 0.01
                and abs(cy_mm) < 0.01
                and abs(cz_mm - 15.0) < 0.01
            )
            or (
                abs(cx_mm) < 0.01
                and abs(abs(cy_mm) - 15.0) < 0.01
                and abs(cz_mm - 15.0) < 0.01
            )
            or (
                abs(cx_mm) < 0.01
                and abs(cy_mm) < 0.01
                and (abs(cz_mm) < 0.01 or abs(cz_mm - 30.0) < 0.01)
            )
        )
        marker = "  " if is_box_face else "* "
        print(
            f"    {marker}face[{fi}] center=({cx_mm:+7.2f}, {cy_mm:+7.2f}, {cz_mm:+7.2f}) mm"
        )

    return cut


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)

    print("== Spike U: side-face sketch frame discovery ==")
    print("== Test: 30mm centered cube (front plane, axis +z). ")
    print("==  CreateCircle(u=+5mm, v=+3mm) on each side face,")
    print("==  cut 1mm dimple, observe where dimple lands in part coords.")
    print("==  Expected dimple center: u=+5mm, v=+3mm in sketch frame,")
    print("==  reflected to some part-frame (a, b, c) we'll discover.")

    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    try:
        _create_box(doc, side_mm=30.0)

        # +x face: outward normal +x, click at (15, 0, 15) -- midpoint of
        # right side, mid-height z (box runs z=0..30, so mid = 15)
        _probe_one_face(
            doc, "+x face", (15.0, 0.0, 15.0), sketch_u_mm=5.0, sketch_v_mm=3.0
        )

        # -x face: outward normal -x, click at (-15, 0, 15)
        _probe_one_face(
            doc, "-x face", (-15.0, 0.0, 15.0), sketch_u_mm=5.0, sketch_v_mm=3.0
        )

        # +y face: outward normal +y, click at (0, 15, 15)
        _probe_one_face(
            doc, "+y face", (0.0, 15.0, 15.0), sketch_u_mm=5.0, sketch_v_mm=3.0
        )

        # -y face: outward normal -y, click at (0, -15, 15)
        _probe_one_face(
            doc, "-y face", (0.0, -15.0, 15.0), sketch_u_mm=5.0, sketch_v_mm=3.0
        )

        print("\n== End of probe ==")
        print("== For each face above, find the planar (non-cylindrical)")
        print("==  face among the new ones starred with *. That center")
        print("==  is the part-coord position of sketch (u=+5, v=+3).")
        return 0
    except Exception as e:
        print(f"! spike U exception: {e!r}")
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
