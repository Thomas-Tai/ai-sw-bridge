"""Spike Z3: verify TWO deferred dims on the same closed sketch land
as real Parameters.

Why this spike exists: Spike Z2 Test 2 showed that re-entering EditSketch
on SK_Box1 and adding a second dim returned dim=True after a manual tick,
but Parameter('D2@SK_Box1') was None afterwards. That single result
could be:

  (a) Z2-specific pollution (Z2 also failed the first AddDimension2 in
      Test 1 because SendKeys raised AttributeError mid-COM-call -- might
      have left SK_Box1 in a weird state before Test 2 ran).
  (b) A real limitation: SW won't accept a SECOND deferred dim on the
      same sketch via the EditSketch + AddDimension2 path.

The deferred-dim refactor of builder.py only makes sense if (a). If (b),
we can't batch dims at all and need a different approach.

This spike runs the clean version of Z2 Test 2 without any of Z2's
SendKeys/thread machinery: pure manual-tick path, both dims on the same
sketch.

Procedure:
  1. Build 20x20x10 box, no dims (zero popups expected).
  2. EditSketch(SK_Box) -> select top edge -> AddDimension2 -> USER TICKS.
     Close sketch. Verify Parameter('D1@SK_Box').
  3. EditSketch(SK_Box) AGAIN -> select left edge -> AddDimension2 ->
     USER TICKS. Close sketch. Verify Parameter('D2@SK_Box').
  4. Report both parameters.

Decision tree:
  GREEN: both D1 and D2 resolve as real Parameters -> Z2 Test 2's None
         was Z2 pollution; deferred-dim refactor is safe to build.
  RED:   D1 lands but D2 does not -> SW won't accept multiple deferred
         dims on one sketch via this path. Need to either re-open sketch
         differently, use a per-dim sketch (1 dim per sketch), or move
         to Option B+ where dims go on different sketches.

Run from venv-freshtest with SW open. Creates a fresh part; user ticks
TWO popups during the run; closes test doc after observation.
"""
import time
import pythoncom
import win32com.client


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ----- Phase 1: build box, no dims (clean state) -----
    print()
    print("=== Phase 1: geometry only ===")
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)  # close
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"
    print(f"  sketch: {sk.Name!r}")

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0, 0, 0)
    f = fm.FeatureExtrusion2(
        True, False, False, 0, 0, 0.010, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    if f is None:
        print("  ! FeatureExtrusion2 failed")
        return
    f.Name = "EX_Box"
    print(f"  extrude: {f.Name!r}")

    bb = doc.GetBodies2(0, True)[0].GetBodyBox()
    print(f"  body bbox (mm): x=[{bb[0]*1000:.1f},{bb[3]*1000:.1f}] "
          f"y=[{bb[1]*1000:.1f},{bb[4]*1000:.1f}] "
          f"z=[{bb[2]*1000:.1f},{bb[5]*1000:.1f}]")
    print(f"  expected:        x=[-10.0,10.0] y=[-10.0,10.0] z=[0.0,10.0]")

    # ----- Phase 2: first deferred dim (top edge -> D1) -----
    print()
    print("=== Phase 2: first deferred dim D1 on SK_Box top edge ===")
    print("    (popup expected -- please TICK the green check in SW)")
    doc.ClearSelection2(True)
    ok_sel = doc.SelectByID("SK_Box", "SKETCH", 0, 0, 0)
    print(f"  SK_Box selected: {ok_sel}")
    doc.EditSketch()
    print("  EditSketch() called")
    doc.ClearSelection2(True)
    ok_seg = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)
    print(f"  top edge selected: {ok_seg}")

    t0 = time.perf_counter()
    dim1 = doc.AddDimension2(0, 0.015, 0)
    t1 = time.perf_counter()
    elapsed_ms_1 = (t1 - t0) * 1000
    print(f"  AddDimension2 returned in {elapsed_ms_1:.1f}ms, dim1={dim1 is not None}")

    sm.InsertSketch(True)  # close sketch
    print("  sketch closed")

    p1 = doc.Parameter("D1@SK_Box")
    if p1 is not None:
        try:
            val = p1.SystemValue * 1000
            print(f"  Parameter('D1@SK_Box') = {val:.3f} mm  [GREEN: D1 landed]")
        except Exception as e:
            print(f"  Parameter exists but SystemValue ERR: {e!r}")
    else:
        print("  RED: Parameter('D1@SK_Box') is None")
        print("       First deferred dim didn't land -- cannot continue Z3 meaningfully")
        return

    # ----- Phase 3: second deferred dim (left edge -> D2) on SAME sketch -----
    print()
    print("=== Phase 3: SECOND deferred dim D2 on SK_Box left edge ===")
    print("    (popup expected -- please TICK the green check in SW)")
    doc.ClearSelection2(True)
    ok_sel = doc.SelectByID("SK_Box", "SKETCH", 0, 0, 0)
    print(f"  SK_Box selected: {ok_sel}")
    doc.EditSketch()
    print("  EditSketch() called (second time)")
    doc.ClearSelection2(True)
    ok_seg = doc.SelectByID("", "SKETCHSEGMENT", -0.010, 0, 0)  # left edge
    print(f"  left edge selected: {ok_seg}")

    if not ok_seg:
        print("  RED: left edge not selectable in re-opened sketch state")
        print("       SW may not allow re-entering a sketch that already has a dim?")
        return

    t0 = time.perf_counter()
    dim2 = doc.AddDimension2(-0.015, 0, 0)
    t1 = time.perf_counter()
    elapsed_ms_2 = (t1 - t0) * 1000
    print(f"  AddDimension2 returned in {elapsed_ms_2:.1f}ms, dim2={dim2 is not None}")

    sm.InsertSketch(True)  # close
    print("  sketch closed")

    p2 = doc.Parameter("D2@SK_Box")
    if p2 is not None:
        try:
            val = p2.SystemValue * 1000
            print(f"  Parameter('D2@SK_Box') = {val:.3f} mm  [GREEN: D2 landed]")
        except Exception as e:
            print(f"  Parameter exists but SystemValue ERR: {e!r}")
    else:
        print("  RED: Parameter('D2@SK_Box') is None")
        print("       Second deferred dim did NOT land. This was Z2 Test 2's failure mode.")
        print("       Confirms (b): SW won't take multiple deferred dims on same sketch via this path.")

    # ----- Verify bbox unchanged -----
    bb2 = doc.GetBodies2(0, True)[0].GetBodyBox()
    print()
    print(f"final bbox (mm): x=[{bb2[0]*1000:.1f},{bb2[3]*1000:.1f}] "
          f"y=[{bb2[1]*1000:.1f},{bb2[4]*1000:.1f}] "
          f"z=[{bb2[2]*1000:.1f},{bb2[5]*1000:.1f}]")
    print(f"expected:        x=[-10.0,10.0] y=[-10.0,10.0] z=[0.0,10.0]")

    print()
    print(">>> Decision:")
    print("    D1 and D2 BOTH non-None -> GREEN, Z2 Test 2 was pollution; refactor is safe.")
    print("    D1 non-None, D2 None    -> RED, can't stack deferred dims on one sketch.")
    print("                               Refactor must put each dim on its own sketch,")
    print("                               or fall back to in-line dims (today's behavior).")


if __name__ == "__main__":
    main()
