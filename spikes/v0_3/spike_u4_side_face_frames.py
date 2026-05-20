"""
Spike U4: side-face frame discovery via OUTWARD BOSS instead of cut.

Why: in U3 only -x and -y face cuts succeeded; +x and +y returned None
regardless of the `Dir` flag. Outward bosses should work uniformly since
they extrude into empty space in the outward normal direction.

For each side face of a 30mm centered cube:
  - Fresh box, click face, sketch circle (u=+5, v=+3, r=1mm).
  - Boss-extrude 3mm OUTWARD (default direction = sketch normal, which
    is the face's outward normal -- away from body, into empty space).
  - Find the new cylindrical-side face. Its centroid in part coords tells
    us where sketch (u=+5, v=+3) actually lives.

The cylinder centroid sits at the bump's MIDPOINT in the normal direction.
The "u, v" components are perpendicular to the bump axis and identify the
sketch frame.

Usage:
    python spikes/v0_3/spike_u4_side_face_frames.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
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


def _face_data(doc) -> list[tuple[tuple[float, float, float], float]]:
    """List (center, max_extent) per face on last body."""
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
        ext = max(box[3] - box[0], box[4] - box[1], box[5] - box[2])
        out.append(((cx, cy, cz), ext))
    return out


def _probe_one_face(
    sw,
    template: str,
    face_label: str,
    click_pt_mm,
    sketch_u_mm: float,
    sketch_v_mm: float,
    boss_height_mm: float = 3.0,
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

        before = _face_data(doc)
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

        doc.ClearSelection2(True)
        sketch_feat = doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            print("  ! no sketch produced")
            return
        sketch_feat.Select2(False, 0)

        fm = doc.FeatureManager
        feat = fm.FeatureExtrusion2(
            True,
            False,
            False,
            SW_END_COND_BLIND,
            0,
            boss_height_mm / 1000.0,
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
            print("  ! boss extrude returned None (tried Dir=False, Flip=False)")
            return

        after = _face_data(doc)
        new_faces = []
        for c, ext in after:
            key = tuple(round(v * 1000, 2) for v in c)
            if key not in before_centers:
                new_faces.append((c, ext))

        print(f"  new faces: {len(new_faces)}")
        if not new_faces:
            print("  ! no new faces")
            return
        new_faces.sort(key=lambda x: x[1])
        for i, (c, ext) in enumerate(new_faces):
            print(
                f"    new[{i}] center=({c[0]*1000:+7.2f}, {c[1]*1000:+7.2f}, "
                f"{c[2]*1000:+7.2f}) mm extent={ext*1000:.2f}mm"
            )
        # Smallest extent = boss top (planar circular cap, 2mm extent).
        # That cap's center = boss axis at the OUTWARD end. We want the
        # center IN-FACE projection. Take the cap center, subtract the
        # boss height in the outward normal direction, get sketch position.
        cap = new_faces[0]
        cap_center = cap[0]
        print(f"  *** sketch (u=+5, v=+3) on {face_label} ***")
        print(
            f"  *** boss CAP center @ part ({cap_center[0]*1000:+.2f}, "
            f"{cap_center[1]*1000:+.2f}, {cap_center[2]*1000:+.2f}) mm"
        )
        print(f"  *** boss STARTED at (face_plane, ?, ?) -- the sketch circle's")
        print(f"  *** in-face center is at the same (u, v) projection as the cap.")
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

    print("== Spike U4: side-face frame discovery via OUTWARD BOSS ==")
    print("== Box: 30mm centered cube, Front Plane sketch, axis +z.")
    print("== Sketch circle r=1mm at (u=+5, v=+3) on each side face.")
    print("== Boss-extrude 3mm OUTWARD. Smallest new face = boss cap.")

    probes = [
        ("+x face", (15.0, 0.0, 15.0)),
        ("-x face", (-15.0, 0.0, 15.0)),
        ("+y face", (0.0, 15.0, 15.0)),
        ("-y face", (0.0, -15.0, 15.0)),
    ]
    for label, click_pt in probes:
        _probe_one_face(sw, template, label, click_pt, sketch_u_mm=5.0, sketch_v_mm=3.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
