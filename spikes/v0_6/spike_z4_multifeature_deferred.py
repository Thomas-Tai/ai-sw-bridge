"""Spike Z4: end-to-end deferred dimensioning across MULTIPLE FEATURES.

Z1 proved deferred-dim works on a single closed sketch.
Z3 proved two deferred dims on the SAME sketch both land as real Parameters.
Z4 proves the realistic case: N features built first (zero popups), then
re-enter each sketch in turn and add multiple dims per sketch. This is
the actual cadence the --deferred-dim builder.py refactor will use.

Geometry plan:
    Feature A -- SK_Box on Front plane, 20x20 rectangle, extrude 10mm  -> EX_Box
    Feature B -- SK_Hole on +Z face of EX_Box at origin, circle d=8, cut-extrude through -> CT_Hole
    Feature C -- SK_Slot on +Z face of EX_Box offset, circle d=4, cut-extrude 5mm -> CT_Slot

(Feature C originally targeted the +Y side face, but SelectByID for side
faces of a multi-feature part is unreliable -- per builder.py:869 the
bridge uses a body-face-enum fallback for that. Side-face selection is
orthogonal to the deferred-dim question being spiked here, so Z4 keeps
both Features B and C on the top face.)

Deferred dims (added AFTER all geometry):
    SK_Box  : D1 = top edge length (20mm), D2 = left edge length (20mm)
    SK_Hole : D1 = diameter (8mm), D2 = horizontal position of center (0mm from sketch origin)
    SK_Slot : D1 = diameter (4mm)
Total: 5 dims across 3 sketches.

Procedure:
    Phase 1 -- geometry only, no AddDimension2 calls.  Verify bbox.
    Phase 2 -- re-enter SK_Box, add D1 and D2 (TWO user ticks).
    Phase 3 -- re-enter SK_Hole, add D1 and D2 (TWO user ticks).
    Phase 4 -- re-enter SK_Slot, add D1       (ONE user tick).
    Verify: doc.Parameter("D1@SK_Box"), D2@SK_Box, D1@SK_Hole, D2@SK_Hole, D1@SK_Slot all non-None.

Decision tree:
    All 5 Parameters non-None -> GREEN. Refactor builder.py to this cadence.
    Any None or any popup fails to take a tick -> RED. Note which one;
        constrains what the refactor can do (e.g. one-dim-per-sketch fallback).

Run from venv-freshtest with SW open. User ticks 5 popups total.
"""
import time
import pythoncom
import win32com.client

# Mirror the verified constants from sw_types.py to keep this spike
# self-contained (no import from the ai_sw_bridge package).
SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 1
SW_START_SKETCH_PLANE = 0


def _cut_args(end_cond, depth_m, flip=False):
    """Return the 27-arg tuple for IFeatureManager.FeatureCut4, mirroring
    builder.py's _call_feature_cut wrapper."""
    return (
        True,            # 1  Sd
        flip,            # 2  Flip
        False,           # 3  Dir
        end_cond,        # 4  T1
        0,               # 5  T2
        depth_m,         # 6  D1
        0.0,             # 7  D2
        False,           # 8  Dchk1
        False,           # 9  Dchk2
        False,           # 10 Ddir1
        False,           # 11 Ddir2
        0.0,             # 12 Dang1
        0.0,             # 13 Dang2
        False,           # 14 OffsetReverse1
        False,           # 15 OffsetReverse2
        False,           # 16 TranslateSurface1
        False,           # 17 TranslateSurface2
        False,           # 18 NormalCut
        True,            # 19 UseFeatScope
        True,            # 20 UseAutoSelect
        True,            # 21 AssemblyFeatureScope
        True,            # 22 AutoSelectComponents
        False,           # 23 PropagateFeatureToParts
        SW_START_SKETCH_PLANE,  # 24 T0
        0.0,             # 25 StartOffset
        False,           # 26 FlipStartOffset
        False,           # 27 OptimizeGeometry
    )


def build_phase1_geometry(doc):
    """Build EX_Box, CT_Hole, CT_Slot with no dimensions. Return dict of
    feature/sketch names actually used."""
    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ----- Feature A: 20x20x10 box on Front plane -----
    print("  -- Feature A: SK_Box rectangle + EX_Box extrude")
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)  # close
    sk_box = doc.FeatureByPositionReverse(0)
    sk_box.Name = "SK_Box"
    print(f"     sketch: {sk_box.Name!r}")

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0, 0, 0)
    f_box = fm.FeatureExtrusion2(
        True, False, False, 0, 0, 0.010, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    if f_box is None:
        raise RuntimeError("FeatureExtrusion2 for EX_Box failed")
    f_box.Name = "EX_Box"
    print(f"     extrude: {f_box.Name!r}")

    # ----- Feature B: hole on top face -----
    # Top face of EX_Box is at z = +10mm (extruded upward from Front-plane sketch z=0)
    # Pick by world coords slightly inside the top face.
    print("  -- Feature B: SK_Hole circle + CT_Hole cut")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0, 0, 0.010)
    if not ok:
        raise RuntimeError("could not select top face of EX_Box")
    sm.InsertSketch(True)
    sm.CreateCircle(0, 0, 0, 0.004, 0, 0)  # center origin, r=4mm -> dia 8mm
    sm.InsertSketch(True)  # close
    sk_hole = doc.FeatureByPositionReverse(0)
    sk_hole.Name = "SK_Hole"
    print(f"     sketch: {sk_hole.Name!r}")

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Hole", "SKETCH", 0, 0, 0)
    f_hole = fm.FeatureCut4(*_cut_args(SW_END_COND_THROUGH_ALL, 0.010))
    if f_hole is None:
        raise RuntimeError("FeatureCut4 for CT_Hole failed")
    f_hole.Name = "CT_Hole"
    print(f"     cut:    {f_hole.Name!r}")

    # ----- Feature C: small hole on +Z (top) face, offset from CT_Hole -----
    # Top face still exists after CT_Hole (it has a circular void at origin
    # but the surrounding planar face is intact). Pick a point well away
    # from the hole.
    print("  -- Feature C: SK_Slot circle + CT_Slot cut (also on +Z top face)")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.006, 0.006, 0.010)
    if not ok:
        raise RuntimeError("could not select +Z top face for Feature C")
    sm.InsertSketch(True)
    # Circle r=2mm centered at (6mm, 6mm) on the top face sketch plane.
    sm.CreateCircle(0.006, 0.006, 0, 0.008, 0.006, 0)
    sm.InsertSketch(True)  # close
    sk_slot = doc.FeatureByPositionReverse(0)
    sk_slot.Name = "SK_Slot"
    print(f"     sketch: {sk_slot.Name!r}")

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Slot", "SKETCH", 0, 0, 0)
    f_slot = fm.FeatureCut4(*_cut_args(SW_END_COND_BLIND, 0.005))
    if f_slot is None:
        raise RuntimeError("FeatureCut4 for CT_Slot failed")
    f_slot.Name = "CT_Slot"
    print(f"     cut:    {f_slot.Name!r}")

    return {
        "SK_Box": sk_box,
        "EX_Box": f_box,
        "SK_Hole": sk_hole,
        "CT_Hole": f_hole,
        "SK_Slot": sk_slot,
        "CT_Slot": f_slot,
    }


def add_deferred_dim(doc, sketch_name, segment_pick, dim_pos, label):
    """Re-enter `sketch_name`, select a segment via SKETCHSEGMENT pick at
    `segment_pick`, call AddDimension2 at `dim_pos`. User ticks the popup.
    Returns (elapsed_ms, dim_was_returned)."""
    doc.ClearSelection2(True)
    ok_sel = doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    if not ok_sel:
        print(f"    [{label}] FAIL: could not select sketch {sketch_name!r}")
        return None, False
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok_seg = doc.SelectByID("", "SKETCHSEGMENT", *segment_pick)
    print(f"    [{label}] segment pick {segment_pick} -> selected={ok_seg}")
    if not ok_seg:
        # close edit, return failure
        doc.SketchManager.InsertSketch(True)
        return None, False
    t0 = time.perf_counter()
    dim = doc.AddDimension2(*dim_pos)
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}, "
          f"elapsed={elapsed_ms:.1f}ms")
    doc.SketchManager.InsertSketch(True)  # close sketch
    return elapsed_ms, (dim is not None)


def report_param(doc, name):
    p = doc.Parameter(name)
    if p is None:
        print(f"  Parameter({name!r}) = None  [RED]")
        return False
    try:
        val = p.SystemValue * 1000
        print(f"  Parameter({name!r}) = {val:.3f} mm  [GREEN]")
        return True
    except Exception as e:
        print(f"  Parameter({name!r}) SystemValue ERR: {e!r}  [RED]")
        return False


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    # ----- Phase 1: geometry only (NO popups) -----
    print()
    print("=== Phase 1: build all 3 features (no dims, no popups) ===")
    t0 = time.perf_counter()
    try:
        names = build_phase1_geometry(doc)
    except Exception as e:
        print(f"  ! Phase 1 failed: {e!r}")
        return
    t1 = time.perf_counter()
    print(f"  Phase 1 elapsed: {(t1-t0)*1000:.1f}ms")

    body = doc.GetBodies2(0, True)[0]
    bb = body.GetBodyBox()
    print(f"  body bbox (mm): x=[{bb[0]*1000:.1f},{bb[3]*1000:.1f}] "
          f"y=[{bb[1]*1000:.1f},{bb[4]*1000:.1f}] "
          f"z=[{bb[2]*1000:.1f},{bb[5]*1000:.1f}]")

    # ----- Phase 2: SK_Box dims (D1 top edge, D2 left edge) -----
    print()
    print("=== Phase 2: SK_Box deferred dims (2 popups expected) ===")
    add_deferred_dim(
        doc, "SK_Box",
        segment_pick=(0, 0.010, 0),   # top edge (y=+10mm in sketch)
        dim_pos=(0, 0.015, 0),
        label="SK_Box.D1 top edge",
    )
    add_deferred_dim(
        doc, "SK_Box",
        segment_pick=(-0.010, 0, 0),  # left edge (x=-10mm)
        dim_pos=(-0.015, 0, 0),
        label="SK_Box.D2 left edge",
    )

    # ----- Phase 3: SK_Hole dims (D1 diameter, D2 ... try a second segment) -----
    print()
    print("=== Phase 3: SK_Hole deferred dims (2 popups expected) ===")
    # For a circle there's only one segment, but AddDimension2 on it twice
    # in different positions can create a diameter dim then something else.
    # Simpler: just add one dim per re-entry, twice.
    # Pick the circle edge at its rightmost point (x=+4mm, since r=4mm).
    add_deferred_dim(
        doc, "SK_Hole",
        segment_pick=(0.004, 0, 0),
        dim_pos=(0.008, 0, 0),
        label="SK_Hole.D1 diameter",
    )
    # Try a second dim on the same circle, picked from top (y=+4mm).
    add_deferred_dim(
        doc, "SK_Hole",
        segment_pick=(0, 0.004, 0),
        dim_pos=(0, 0.008, 0),
        label="SK_Hole.D2 second-pick",
    )

    # ----- Phase 4: SK_Slot dim (D1 diameter, 1 popup) -----
    print()
    print("=== Phase 4: SK_Slot deferred dim (1 popup expected) ===")
    # SK_Slot is on +Z top face. Circle center=(6mm,6mm), r=2mm.
    # Pick the circle edge at its rightmost point (x=8mm, y=6mm).
    add_deferred_dim(
        doc, "SK_Slot",
        segment_pick=(0.008, 0.006, 0),
        dim_pos=(0.012, 0.006, 0),
        label="SK_Slot.D1 diameter",
    )

    # ----- Verification -----
    print()
    print("=== Verification: Parameter readback ===")
    results = {
        "D1@SK_Box":  report_param(doc, "D1@SK_Box"),
        "D2@SK_Box":  report_param(doc, "D2@SK_Box"),
        "D1@SK_Hole": report_param(doc, "D1@SK_Hole"),
        "D2@SK_Hole": report_param(doc, "D2@SK_Hole"),
        "D1@SK_Slot": report_param(doc, "D1@SK_Slot"),
    }
    landed = sum(1 for v in results.values() if v)
    total = len(results)

    bb2 = doc.GetBodies2(0, True)[0].GetBodyBox()
    print()
    print(f"final bbox (mm): x=[{bb2[0]*1000:.1f},{bb2[3]*1000:.1f}] "
          f"y=[{bb2[1]*1000:.1f},{bb2[4]*1000:.1f}] "
          f"z=[{bb2[2]*1000:.1f},{bb2[5]*1000:.1f}]")

    print()
    print(f">>> Z4 result: {landed}/{total} deferred dims landed as real Parameters")
    if landed == total:
        print("    GREEN: all dims landed. --deferred-dim refactor pattern is verified")
        print("           for multi-feature builds.")
    else:
        print("    PARTIAL or RED. Missing parameters constrain what the refactor can do.")
        for name, ok in results.items():
            if not ok:
                print(f"      - {name} did NOT land")


if __name__ == "__main__":
    main()
