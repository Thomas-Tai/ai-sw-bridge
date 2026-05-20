"""Spike W: probe IFeatureManager.SimpleHole2 via pywin32 late-binding.

Goal: determine the prerequisite selection state and verify the 23-arg
signature actually marshalls. SimpleHole2 args (per decompiled CHM):
  Dia, Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
  Dang1, Dang2, OffsetReverse1, OffsetReverse2, TranslateSurface1,
  TranslateSurface2, UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
  AutoSelectComponents, PropagateFeatureToParts

Hypothesis: needs a FACE + a SKETCHPOINT preselected (the point gives
the hole position; the face gives the orientation). Test: build a
30x30x20 block, create a sketch point on +z face at (5, 0), select
the face + point, call SimpleHole2 with Ø6 mm, BLIND, depth 5 mm.

Expected: a 6mm-diameter cylindrical hole at part (5, 0, ?), 5mm deep
into the block from the +z face. Body bbox should still be 30x30x20
(hole doesn't change envelope), but face count increases.

Run from venv-freshtest. Standalone — closes its part on exit.
"""

import pythoncom
import win32com.client

SW_END_COND_BLIND = 0


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    # Build 30x30x20 block
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.015, 0.015, 0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    fm.FeatureExtrusion2(
        True,
        False,
        False,
        0,
        0,
        0.020,
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

    bb = doc.GetBodies2(0, True)[0].GetBodyBox()
    print(
        f"box bbox: x=[{bb[0]*1000:.0f},{bb[3]*1000:.0f}] z=[{bb[2]*1000:.0f},{bb[5]*1000:.0f}]"
    )

    # Select +z face, sketch a single Point at sketch (5mm, 0), close
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0, 0, 0.020)
    print(f"+z face select: {ok}")
    sm.InsertSketch(True)
    sm.CreatePoint(0.005, 0.0, 0.0)
    sm.InsertSketch(True)

    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_HolePoint"
    print(f"after point sketch: FBPR(0)={sk.Name!r} type={sk.GetTypeName2!r}")

    # Now select FACE + SKETCHPOINT
    doc.ClearSelection2(True)
    ok_face = doc.SelectByID("", "FACE", 0, 0, 0.020)
    print(f"  +z face re-select (append=False): {ok_face}")
    # SelectByID for SKETCHPOINT at part (5mm, 0, 20mm) — point is in sketch
    # coords (5mm, 0) on +z face which lands at part (5mm, 0, 20mm)
    # Append via Extension.SelectByID2 is risky (Callout). Use mark + Select2 idiom.
    ok_pt = doc.SelectByID("", "SKETCHPOINT", 0.005, 0.0, 0.020)
    print(f"  SKETCHPOINT select (replaces): {ok_pt}")
    # That replaced the face. Try Extension.SelectByID2 with append=True
    # WITHOUT a Callout (passing None should work?)
    doc.ClearSelection2(True)
    doc.SelectByID("", "FACE", 0, 0, 0.020)
    try:
        ok2 = doc.Extension.SelectByID2(
            "",
            "SKETCHPOINT",
            0.005,
            0.0,
            0.020,
            True,  # Append
            0,  # Mark
            None,  # Callout (OUT param — usually fails)
            0,  # SelectOption
        )
        print(f"  Extension.SelectByID2 append: {ok2}")
    except Exception as e:
        print(f"  Extension.SelectByID2 ERR: {e!r}")
        # Fall back to IEntity.Select4 on the point
        # First, find the sketch's segments/points via ISketch
        doc.ClearSelection2(True)
        doc.SelectByID("SK_HolePoint", "SKETCH", 0, 0, 0)
        feat = doc.SelectionManager.GetSelectedObject6(1, -1)
        sketch_obj = feat.GetSpecificFeature2
        pts = sketch_obj.GetSketchPoints2
        print(f"  sketch points: {len(pts) if pts else 0}")
        if pts:
            for p in pts:
                # IEntity.Select4(Append, Callout) — Callout=None
                try:
                    ok3 = p.Select4(True, None)
                    print(f"    point Select4(True, None): {ok3}")
                except Exception as e2:
                    print(f"    point Select4 ERR: {e2!r}")
                    try:
                        ok3 = p.Select2(True, 0)
                        print(f"    point Select2(True, 0): {ok3}")
                    except Exception as e3:
                        print(f"    point Select2 ERR: {e3!r}")

    sel = doc.SelectionManager
    n = sel.GetSelectedObjectCount2(-1)
    print(f"  total selected: {n}")
    for i in range(1, n + 1):
        t = sel.GetSelectedObjectType3(i, -1)
        print(f"    [{i}] type={t}")

    # Now try SimpleHole2 (23 args)
    print()
    print("=== Calling SimpleHole2 ===")
    try:
        result = fm.SimpleHole2(
            0.006,  # 1  Dia (6mm)
            True,  # 2  Sd (single direction)
            False,  # 3  Flip
            False,  # 4  Dir (use sketch normal)
            SW_END_COND_BLIND,  # 5  T1
            0,  # 6  T2
            0.005,  # 7  D1 (5mm depth)
            0.0,  # 8  D2
            False,  # 9  Dchk1
            False,  # 10 Dchk2
            False,  # 11 Ddir1
            False,  # 12 Ddir2
            0.0,  # 13 Dang1
            0.0,  # 14 Dang2
            False,  # 15 OffsetReverse1
            False,  # 16 OffsetReverse2
            False,  # 17 TranslateSurface1
            False,  # 18 TranslateSurface2
            True,  # 19 UseFeatScope
            True,  # 20 UseAutoSelect
            False,  # 21 AssemblyFeatureScope
            False,  # 22 AutoSelectComponents
            False,  # 23 PropagateFeatureToParts
        )
        print(f"  SimpleHole2 result: {result}")
        if result is not None:
            print(f"  Name: {result.Name!r}")
    except Exception as e:
        print(f"  SimpleHole2 ERR: {e!r}")

    bb2 = doc.GetBodies2(0, True)[0].GetBodyBox()
    print(
        f"after hole: bbox x=[{bb2[0]*1000:.0f},{bb2[3]*1000:.0f}] z=[{bb2[2]*1000:.0f},{bb2[5]*1000:.0f}]"
    )
    faces = doc.GetBodies2(0, True)[0].GetFaces()
    print(
        f"  face count: {len(faces)} (block has 6 faces; +1 cylinder side +1 hole bottom = 8 expected for blind hole)"
    )


if __name__ == "__main__":
    main()
