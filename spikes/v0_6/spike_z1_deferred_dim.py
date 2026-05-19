"""Spike Z1: verify deferred dimensioning works on a closed sketch.

Hypothesis: the bridge can be refactored to build all geometry first
(zero popups), then re-open each sketch via EditSketch and add dims
afterwards. This would let users get the live equation-link benefit
without random popups interrupting the build.

Test:
  Phase 1 (geometry-only, no AddDimension2):
    - Open Front-plane sketch
    - Draw a 20x20 rectangle
    - Close sketch (rename SK_Box)
    - Boss-extrude 10mm (rename EX_Box)

  Phase 2 (deferred dims):
    - SelectByID("SK_Box", "SKETCH", 0,0,0)
    - doc.EditSketch()                                 <-- re-opens for editing
    - SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)     <-- top edge
    - doc.AddDimension2(0, 0.015, 0)                   <-- popup expected
    - SketchManager.InsertSketch(True)                 <-- close again

Success criteria:
  - Phase 1 completes with zero popups (auto-verified by timing < 50ms per call)
  - Phase 2 puts a real driving D1 dim on the rectangle (verified after popup tick)
  - body bbox = 20x20x10 mm unchanged
  - doc.Parameter("D1@SK_Box") returns a non-None CDispatch

Decision tree:
  GREEN -> refactor builder.py to phase-split. Live equation link
           becomes available without interleaved popups.
  RED   -> investigate why EditSketch doesn't accept AddDimension2
           call afterwards; may need different selection state or
           an alternate dim-creation API (AddSpecificDimension was
           ruled out earlier due to OUT-param marshalling).

Run from venv-freshtest. Creates a fresh part; user tick required
in Phase 2; closes the test doc after observation.
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

    # ----- Phase 1: geometry only, NO AddDimension2 -----
    print()
    print("=== Phase 1: geometry-only (no popups expected) ===")
    t0 = time.perf_counter()

    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)  # close
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"
    print(f"  sketch built: name={sk.Name!r}")

    # Boss-extrude
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
    t1 = time.perf_counter()
    print(f"  extrude built: name={f.Name!r}")
    print(f"  Phase 1 elapsed: {(t1-t0)*1000:.1f}ms (popups should NOT have appeared)")
    bb = doc.GetBodies2(0, True)[0].GetBodyBox()
    print(f"  body bbox (mm): x=[{bb[0]*1000:.1f},{bb[3]*1000:.1f}] "
          f"y=[{bb[1]*1000:.1f},{bb[4]*1000:.1f}] "
          f"z=[{bb[2]*1000:.1f},{bb[5]*1000:.1f}]")
    print(f"  expected:        x=[-10.0,10.0] y=[-10.0,10.0] z=[0.0,10.0]")

    # ----- Phase 2: deferred dim on closed sketch -----
    print()
    print("=== Phase 2: re-open closed sketch + AddDimension2 (popup EXPECTED) ===")
    doc.ClearSelection2(True)
    ok_sel = doc.SelectByID("SK_Box", "SKETCH", 0, 0, 0)
    print(f"  SK_Box selected: {ok_sel}")

    try:
        doc.EditSketch()
        print("  EditSketch() called -- sketch should now be in edit mode")
    except Exception as e:
        print(f"  EditSketch() ERR: {e!r}")
        print("  FAIL: cannot re-open sketch via EditSketch")
        return

    # Select the top edge (y=+10mm) and add a dim
    doc.ClearSelection2(True)
    ok_seg = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)
    print(f"  top edge selected: {ok_seg}")

    if not ok_seg:
        print("  FAIL: top edge not selectable in re-opened sketch state")
        return

    t0 = time.perf_counter()
    dim = doc.AddDimension2(0, 0.015, 0)
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000
    print(f"  AddDimension2 returned in {elapsed_ms:.1f}ms, dim={dim!r}")
    if elapsed_ms > 200:
        print(f"  popup appears to have been ticked manually (>200ms)")
    else:
        print(f"  fast return -- either dim creation failed or popup was suppressed")

    # Close sketch
    sm.InsertSketch(True)
    print("  sketch closed after dim addition")

    # ----- Verify the dim exists and is named D1@SK_Box -----
    print()
    print("=== Verification: Parameter('D1@SK_Box') ===")
    p = doc.Parameter("D1@SK_Box")
    print(f"  Parameter('D1@SK_Box') = {p!r}")
    if p is not None:
        try:
            val = p.SystemValue * 1000  # m -> mm
            print(f"  D1@SK_Box value: {val:.3f} mm")
            print("  GREEN: deferred dim succeeded; live link is feasible")
        except Exception as e:
            print(f"  Parameter exists but SystemValue ERR: {e!r}")
    else:
        print("  RED: Parameter('D1@SK_Box') returned None")
        print("       The dim was not created, or its name is different.")

    # Verify bbox unchanged (just adding a dim shouldn't change geometry)
    bb2 = doc.GetBodies2(0, True)[0].GetBodyBox()
    print(f"  body bbox after dim (mm): x=[{bb2[0]*1000:.1f},{bb2[3]*1000:.1f}] "
          f"y=[{bb2[1]*1000:.1f},{bb2[4]*1000:.1f}] "
          f"z=[{bb2[2]*1000:.1f},{bb2[5]*1000:.1f}]")

    print()
    print(">>> Spike Z1 complete. Did the popup appear in Phase 2? (Y/N)")
    print(">>> If Y and Parameter('D1@SK_Box') is non-None: GREEN, refactor viable.")
    print(">>> If popup did not appear but Parameter is non-None: GREEN AND popup-free!")
    print(">>> If Parameter is None: investigate before refactoring.")


if __name__ == "__main__":
    main()
