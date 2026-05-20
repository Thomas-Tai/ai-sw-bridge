"""Spike Z7: test two candidate fixes for the driven-D2 problem on
CreateCenterRectangle sketches in --deferred-dim mode.

Background (from Z5/Z6):
  When a rectangle sketch built by CreateCenterRectangle is closed via
  InsertSketch(True), re-opened via EditSketch, and then has TWO edge
  dimensions added (D1 = top edge, D2 = left edge), SW makes D2 driven.
  The binding equation "D2@SK_PlateSlab" = "S1B_MMP_W" is then rejected
  with "A driven or reference dimension is not selectable as the
  dependent variable of the equation."

  Z6 ruled out construction-diagonal deletion as a fix (deleting 1 or 2
  diagonals didn't change the result -- D2 still driven).

Candidate fixes:
  Route 1: Use IDisplayDimension.DrivenState = swDimensionDriving (1)
           on the dim returned by AddDimension2. May bypass the API
           state-machine quirk if SW will let us flip the flag.

  Route 3: After adding D1 in the re-opened sketch, immediately call
           doc.EditRebuild3 BEFORE closing/before adding D2. This
           "relaxes" the un-dimensioned lines so SW doesn't treat them
           as frozen when D2 arrives. (Replaces the close-reopen-between-
           dims pattern with a single EditSketch session containing
           a mid-edit rebuild.)

Test cases:
  Z7a (control): baseline reproduce -- build rect, close, reopen, add D1,
                 close, reopen, add D2, close. Try Add2 binding to D2.
                 Expected: binding succeeds (Add2 returns >=0) but the
                 part rebuild flags D2 as driven (red equation in UI).

  Z7b (Route 3): build rect, close, reopen, add D1, EditRebuild3 while
                 STILL IN edit-mode, add D2, close. Single re-entry per
                 sketch, mid-edit rebuild between dims.
                 Expected if hypothesis right: D2 lands driving, no red
                 equation after Add2.

  Z7c (Route 1): Z7a baseline + capture the dim2 IDisplayDimension and
                 force DrivenState = 1 after AddDimension2 returns.
                 Expected if hypothesis right: D2 ends up driving even
                 though SW initially made it driven.

Acceptance test (per case): after sketch + dims, Add2 a test binding
for D2, then doc.EditRebuild3. User checks SW UI to confirm whether
D2 equation is red (driven, fix failed) or clean (driving, fix worked).

Run from venv-freshtest with SW open. 2 popup ticks per case x 3
cases = 6 ticks total.
"""

import pythoncom
import win32com.client

SW_DIM_DRIVEN_STATE_DRIVING = 1  # swDimensionDriving (best guess)
SW_DIM_DRIVEN_STATE_DRIVEN = 2  # swDimensionDriven (best guess)


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def build_center_rect_and_close(doc, sketch_name):
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)  # close
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")
    return feat


def add_edge_dim_inline(doc, edge_sel_xyz, leader_xyz, label, fallback_picks=None):
    """Assumes sketch is already open in edit mode. Returns the dim.
    Caller is responsible for opening/closing the sketch.

    If the primary edge_sel_xyz pick fails, try each (x,y,z) in
    fallback_picks before giving up. Useful when a prior mid-edit
    rebuild has shifted segment positions slightly."""
    doc.ClearSelection2(True)
    sx, sy, sz = edge_sel_xyz
    ok = doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz)
    print(f"    [{label}] primary segment pick {(sx, sy, sz)} -> select={ok}")
    if not ok and fallback_picks:
        for fx, fy, fz in fallback_picks:
            doc.ClearSelection2(True)
            ok = doc.SelectByID("", "SKETCHSEGMENT", fx, fy, fz)
            print(f"    [{label}] fallback pick {(fx, fy, fz)} -> select={ok}")
            if ok:
                break
    if not ok:
        return None
    lx, ly, lz = leader_xyz
    dim = doc.AddDimension2(lx, ly, lz)
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}")
    return dim


def add_edge_dim_with_reopen(doc, sketch_name, edge_sel_xyz, leader_xyz, label):
    """Open sketch, add dim, close. Matches the current builder.py
    --deferred-dim flow."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()
    dim = add_edge_dim_inline(doc, edge_sel_xyz, leader_xyz, label)
    sm.InsertSketch(True)
    return dim


def try_d2_binding(doc, sketch_name, label):
    """Attempt to bind D2@<sketch> to a TEST_VAR via Add2 + force rebuild.
    Returns (idx, value_after_rebuild). The visual UI red/clean state
    must be checked by the human."""
    eq = doc.GetEquationMgr
    eq.Add2(-1, '"Z7_TEST_VAR" = 7.0', True)
    formula = f'"D2@{sketch_name}" = "Z7_TEST_VAR"'
    idx = eq.Add2(-1, formula, True)
    val = eq.Value(idx) if idx >= 0 else None
    # Force rebuild so SW evaluates the equation system
    try:
        _ = doc.EditRebuild3
    except Exception as e:
        print(f"    [{label}] EditRebuild3 ERR: {e!r}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    p2_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(f"  [{label}] Add2({formula!r}) -> idx={idx}, eq.Value={val!r}")
    print(f"  [{label}] Parameter(D2@{sketch_name}) after rebuild = {p2_val!r} mm")
    return idx, val, p2_val


def case_a_baseline(sw):
    """Z6 baseline -- close-reopen between each dim."""
    print()
    print("=== Z7a: control (baseline) -- close/reopen between D1 and D2 ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    build_center_rect_and_close(doc, "SK_A")

    # D1 via reopen-add-close
    add_edge_dim_with_reopen(doc, "SK_A", (0, 0.010, 0), (0, 0.015, 0), "Z7a.D1")
    # D2 via reopen-add-close
    add_edge_dim_with_reopen(doc, "SK_A", (-0.010, 0, 0), (-0.015, 0, 0), "Z7a.D2")

    return try_d2_binding(doc, "SK_A", "Z7a")


def case_b_mid_edit_rebuild(sw):
    """Route 3: single EditSketch session, mid-edit EditRebuild3 between
    D1 and D2."""
    print()
    print(
        "=== Z7b: Route 3 -- single EditSketch session, EditRebuild3 between D1 and D2 ==="
    )
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    build_center_rect_and_close(doc, "SK_B")
    sm = doc.SketchManager

    # Open the sketch ONCE
    doc.ClearSelection2(True)
    doc.SelectByID("SK_B", "SKETCH", 0, 0, 0)
    doc.EditSketch()

    # Add D1 inline (no close)
    add_edge_dim_inline(doc, (0, 0.010, 0), (0, 0.015, 0), "Z7b.D1")

    # Mid-edit rebuild
    print("  -- mid-edit EditRebuild3 --")
    try:
        result = doc.EditRebuild3
        print(f"    EditRebuild3 -> {result!r}")
    except Exception as e:
        print(f"    EditRebuild3 ERR: {e!r}")

    # Add D2 inline (still no close). After mid-edit rebuild the segment
    # may have shifted slightly; try a few nearby coords as fallbacks
    # (small inset, slight y offsets) before giving up.
    fallback_d2 = [
        (-0.010, 0.001, 0),
        (-0.010, -0.001, 0),
        (-0.0099, 0, 0),
        (-0.00999, 0, 0),
        (-0.010, 0.005, 0),
        (-0.010, -0.005, 0),
    ]
    add_edge_dim_inline(
        doc,
        (-0.010, 0, 0),
        (-0.015, 0, 0),
        "Z7b.D2",
        fallback_picks=fallback_d2,
    )

    # NOW close
    sm.InsertSketch(True)

    return try_d2_binding(doc, "SK_B", "Z7b")


def case_c_driven_state_override(sw):
    """Route 1: Z7a baseline + capture dim2's IDisplayDimension and
    force DrivenState = 1 after AddDimension2 returns."""
    print()
    print("=== Z7c: Route 1 -- baseline + DrivenState=1 override on D2 ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    build_center_rect_and_close(doc, "SK_C")

    # D1 via reopen-add-close (baseline)
    add_edge_dim_with_reopen(doc, "SK_C", (0, 0.010, 0), (0, 0.015, 0), "Z7c.D1")

    # D2 via reopen-add-close BUT capture the dim object and override DrivenState
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("SK_C", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    dim2 = add_edge_dim_inline(doc, (-0.010, 0, 0), (-0.015, 0, 0), "Z7c.D2")

    # Inspect what DrivenState is initially, then try to set it.
    if dim2 is not None:
        try:
            initial = dim2.DrivenState
            print(f"    initial dim2.DrivenState = {initial!r}")
        except Exception as e:
            print(f"    read dim2.DrivenState ERR: {e!r}")
        try:
            dim2.DrivenState = SW_DIM_DRIVEN_STATE_DRIVING
            after = dim2.DrivenState
            print(
                f"    after dim2.DrivenState = SW_DIM_DRIVEN_STATE_DRIVING -> read back {after!r}"
            )
        except Exception as e:
            print(f"    write dim2.DrivenState ERR: {e!r}")
    else:
        print("    dim2 is None -- can't override DrivenState")

    sm.InsertSketch(True)

    return try_d2_binding(doc, "SK_C", "Z7c")


def main():
    import os

    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    only_b = os.environ.get("Z7_ONLY_B") == "1"

    if only_b:
        print("(Z7_ONLY_B=1 -- skipping cases A and C)")
        res_a = None
        res_b = case_b_mid_edit_rebuild(sw)
        res_c = None
    else:
        res_a = case_a_baseline(sw)
        res_b = case_b_mid_edit_rebuild(sw)
        res_c = case_c_driven_state_override(sw)

    print()
    print("=== Z7 summary ===")
    for tag, res in (
        ("Z7a control", res_a),
        ("Z7b mid-edit rebuild", res_b),
        ("Z7c DrivenState override", res_c),
    ):
        if res is None:
            print(f"  {tag}: skipped / failed")
            continue
        idx, val, p2_val = res
        print(f"  {tag}: Add2 idx={idx}, eq.Value={val!r}, D2 final={p2_val!r} mm")
    print()
    print(">>> ACCEPTANCE TEST is visual:")
    print("    For each part (SK_A, SK_B, SK_C):")
    print(
        "      1. Open Equation Manager. Is 'D2@SK_*' = '\"Z7_TEST_VAR\"' red or clean?"
    )
    print("      2. Open the sketch. Is D2 driven (grey/special) or driving (black)?")
    print("    Z7a expected: red + driven (reproduces the bug).")
    print("    Z7b green = Route 3 (mid-edit rebuild) is the fix.")
    print("    Z7c green = Route 1 (DrivenState override) is the fix.")


if __name__ == "__main__":
    main()
