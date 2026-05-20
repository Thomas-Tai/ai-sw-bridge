"""Spike ZD: test 'inline dims, deferred equation bindings'.

GENUINELY NEW HYPOTHESIS (not previously tested):
  Every prior spike that adds D2 to a CenterRectangle hit the demotion
  because D2 landed in a REOPENED sketch session. Z4 showed that adding
  multiple dims WITHIN the original sketch session (before any
  InsertSketch(True) close) leaves them driving.

  This spike tests whether the demotion can be sidestepped entirely by:
    1. Creating CenterRectangle in session 1.
    2. Adding D1 in session 1.
    3. Adding D2 in session 1.
    4. Closing the sketch (FIRST close, not second).
    5. Adding EquationMgr.Add2 bindings to D1 and D2 AFTER close.
    6. EditRebuild3 to evaluate.

  If D2 stays driving and the binding drives geometry on rebuild, this is
  a NEW production fix path: builder.py's rectangle handler can add dims
  inline (in original session) and defer ONLY the equation bindings.

  The previously-tested --deferred-dim cadence defers both dim creation
  AND binding -- the dim creation in a reopened session is what fires
  the demotion. ZD keeps dim creation inline.

NOT TESTED BY PRIOR SPIKES (this is why it's novel):
  - Z4 verified multi-dim in one session works, but used a circle sketch
    (`SK_Hole`, `SK_Slot`) and a box sketch (`SK_Box`) that's not the
    same as MMP's CenterRectangle.
  - Z5 always added D2 in a separate reopen.
  - Z7 / Z8 tried mid-edit modifications but not the simple inline+post-bind.

THE OPEN QUESTION:
  Does EquationMgr.Add2 RETROACTIVELY demote a driving D2 when the
  binding is evaluated during EditRebuild3? The SW solver may treat
  the binding as adding a constraint and re-evaluate over-constraint
  status. Z6 showed Add2 accepted the binding on an ALREADY driven D2
  (no further state change). What's untested: Add2 on a DRIVING D2 --
  does the solver demote at bind time?

Three cases:
  Z8d-a (baseline): inline D1 + D2 in session 1, NO equation bindings,
                    just close and rebuild. Confirms baseline cadence
                    produces both dims driving as expected from Z4.

  Z8d-b (single bind): inline D1 + D2 in session 1, close, then add
                       Add2 binding for D1 ONLY (not D2). Tests whether
                       binding D1 alone causes any side-effect demotion
                       on D2.

  Z8d-c (full): inline D1 + D2 in session 1, close, then add Add2
                bindings for BOTH D1 and D2. The intended production
                pattern.

Acceptance signal:
  - Programmatic: Parameter("D2@SK_*") tracks the binding (7.0 mm if
    binding drives, 20.0 mm if D2 is driven and binding has no effect).
  - Visual: EqMgr 'D2' equation clean (driving target) or red (driven).

Run from venv-freshtest with SW open. Expected popup ticks: 2 per case
x 3 cases = 6 ticks total (D1 and D2 each add).
"""

import os
import pythoncom
import win32com.client


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def build_rect_with_inline_dims(doc, sketch_name):
    """Create CenterRectangle and add D1+D2 BEFORE the first close.
    This is the structural difference from every prior spike.

    Uses the segment-pointer-from-CreateCenterRectangle approach instead
    of coordinate-based SelectByID, because the initial ZD run showed
    AddDimension2 silently returning None when SelectByID picked an
    ambiguous entity inside the still-open original sketch session."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)  # OPEN session 1

    # Create geometry -- capture the returned tuple of 6 ISketchSegments:
    # 4 perimeter lines (indices 0-3) + 2 construction diagonals (4-5).
    segs = sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    if segs is None or len(segs) < 4:
        print(f"  ! CreateCenterRectangle returned unexpected: {segs!r}")
        sm.InsertSketch(True)
        return None, None, None
    perimeter = [s for s in segs if not s.ConstructionGeometry]
    print(
        f"  CreateCenterRectangle returned {len(segs)} segs ({len(perimeter)} perimeter)"
    )

    # The four perimeter lines correspond to top/right/bottom/left edges.
    # We need ONE horizontal edge for D1 (width) and ONE vertical edge for
    # D2 (height). Identify by checking start/end y-coords:
    #   horizontal edge: y_start == y_end  (top: both +0.010; bottom: both -0.010)
    #   vertical edge:   x_start == x_end  (left: both -0.010; right: both +0.010)
    horiz_edge = None
    vert_edge = None
    for s in perimeter:
        try:
            sp = s.GetStartPoint2  # ISketchPoint
            ep = s.GetEndPoint2
            if sp is None or ep is None:
                continue
            x1, y1 = sp.X, sp.Y
            x2, y2 = ep.X, ep.Y
            if abs(y1 - y2) < 1e-9:
                # horizontal -- prefer the top edge (y > 0)
                if horiz_edge is None or y1 > 0:
                    horiz_edge = s
            elif abs(x1 - x2) < 1e-9:
                # vertical -- prefer the left edge (x < 0)
                if vert_edge is None or x1 < 0:
                    vert_edge = s
        except Exception as e:
            print(f"  seg classify ERR: {e}")
    print(f"  horiz_edge: {horiz_edge is not None}, vert_edge: {vert_edge is not None}")

    vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    # D1 inline: select horizontal edge via object pointer, add dim
    doc.ClearSelection2(True)
    if horiz_edge is not None:
        ok = horiz_edge.Select4(False, vt_disp_none)
        print(f"  [D1 inline] horiz_edge.Select4 -> {ok}")
        d1 = doc.AddDimension2(0, 0.015, 0)
        print(f"  [D1 inline] AddDimension2 -> dim={d1 is not None}")
    else:
        d1 = None
        print(f"  [D1 inline] no horiz_edge identified; skipping")

    # D2 inline: same pattern for vertical edge
    doc.ClearSelection2(True)
    if vert_edge is not None:
        ok = vert_edge.Select4(False, vt_disp_none)
        print(f"  [D2 inline] vert_edge.Select4 -> {ok}")
        d2 = doc.AddDimension2(-0.015, 0, 0)
        print(f"  [D2 inline] AddDimension2 -> dim={d2 is not None}")
    else:
        d2 = None
        print(f"  [D2 inline] no vert_edge identified; skipping")

    # Close (first and only InsertSketch(True))
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")
    return feat, d1, d2


def check_d2_state(doc, sketch_name, label, expected_val_mm):
    """Read Parameter(D2) after rebuild and compare to expected.
    expected_val_mm=20.0 means 'D2 didn't track binding (still placeholder)',
                    =7.0 means 'D2 tracks binding (driving)',
                    =None means 'no expectation, just report'."""
    try:
        r = doc.ForceRebuild3(True)
        print(f"  [{label}] ForceRebuild3(True) -> {r!r}")
    except Exception as e:
        print(f"  [{label}] ForceRebuild3 ERR: {type(e).__name__}: {e}")

    p2 = doc.Parameter(f"D2@{sketch_name}")
    val = (p2.SystemValue * 1000) if p2 is not None else None
    if expected_val_mm is None:
        print(f"  [{label}] Parameter(D2@{sketch_name}) = {val!r} mm (no expectation)")
        return val
    matches = val is not None and abs(val - expected_val_mm) < 0.01
    print(
        f"  [{label}] Parameter(D2@{sketch_name}) = {val!r} mm "
        f"(expected ~{expected_val_mm}, matches={matches})"
    )
    return val


def case_a_baseline_no_bindings(sw):
    """Baseline: inline D1+D2, NO equation bindings. Verifies Z4 holds
    on this CenterRectangle case. Both dims should land driving at the
    geometry value (20.0 mm for the 0.010 half-extent rectangle)."""
    print()
    print("=== Z8d-a: inline D1+D2, no equation bindings (Z4 verification) ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    feat, d1, d2 = build_rect_with_inline_dims(doc, "SK_ZDa")
    if d2 is None:
        print("  ! D2 inline failed; case aborted")
        return None

    val = check_d2_state(doc, "SK_ZDa", "baseline rebuild", 20.0)
    return {"d2_val_mm": val, "expected": 20.0}


def case_b_d1_only_binding(sw):
    """Bind D1 only. Tests whether binding any dim in the sketch
    side-effects D2's driving state."""
    print()
    print("=== Z8d-b: inline D1+D2, then bind D1 only ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    feat, d1, d2 = build_rect_with_inline_dims(doc, "SK_ZDb")
    if d2 is None:
        return None

    # Force-commit sketch state before Add2 (per debug probe; without this,
    # Add2 silently returns -1 because eqmgr is in uncommitted state).
    print(f"  ForceRebuild3 before Add2 -> {doc.ForceRebuild3(True)}")

    eq = doc.GetEquationMgr
    # SW equations parse RHS in DOCUMENT UNITS (mm-mode default), not SystemValue.
    # Z9 verified: '"Z9_TEST_VAR" = 5.0' produced a 5mm-driving binding.
    eq.Add2(-1, '"ZDB_W" = 7.0', True)
    idx1 = eq.Add2(-1, '"D1@SK_ZDb" = "ZDB_W"', True)
    print(f"  D1 binding Add2 -> idx={idx1}")
    val = check_d2_state(doc, "SK_ZDb", "post-D1-bind rebuild", None)

    # If D2 still driving, its parameter should equal whatever D1 binding
    # drove the geometry to (7.0 mm width -> D1 = 7.0). D2 is height, never
    # bound -- should remain at 20.0 mm (the original geometry size).
    return {"d2_val_mm": val, "d1_bind_idx": idx1}


def case_c_both_bindings(sw):
    """The full proposed pattern: inline D1+D2, then bind both."""
    print()
    print("=== Z8d-c: inline D1+D2, then bind BOTH (proposed production pattern) ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    feat, d1, d2 = build_rect_with_inline_dims(doc, "SK_ZDc")
    if d2 is None:
        return None

    # Force-commit sketch state before Add2.
    print(f"  ForceRebuild3 before Add2 -> {doc.ForceRebuild3(True)}")

    eq = doc.GetEquationMgr
    # SW equations parse RHS in document units (mm-mode = mm).
    eq.Add2(-1, '"ZDC_W" = 7.0', True)
    eq.Add2(-1, '"ZDC_H" = 9.0', True)
    idx1 = eq.Add2(-1, '"D1@SK_ZDc" = "ZDC_W"', True)
    idx2 = eq.Add2(-1, '"D2@SK_ZDc" = "ZDC_H"', True)
    print(f"  D1 binding Add2 -> idx={idx1}")
    print(f"  D2 binding Add2 -> idx={idx2}")

    val = check_d2_state(doc, "SK_ZDc", "post-both-bind rebuild", 9.0)
    drives = val is not None and abs(val - 9.0) < 0.01
    return {
        "d2_val_mm": val,
        "expected": 9.0,
        "d1_bind_idx": idx1,
        "d2_bind_idx": idx2,
        "d2_drives": drives,
    }


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    SW_PREF = 8
    original = sw.GetUserPreferenceToggle(SW_PREF)
    print(f"  original swInputDimValOnCreate = {original}")
    if original is not True:
        sw.SetUserPreferenceToggle(SW_PREF, True)
        print(f"  forced to True; readback = {sw.GetUserPreferenceToggle(SW_PREF)}")

    only = os.environ.get("ZD_ONLY")
    res_a = res_b = res_c = None
    try:
        if only in (None, "a", "A"):
            res_a = case_a_baseline_no_bindings(sw)
        if only in (None, "b", "B"):
            res_b = case_b_d1_only_binding(sw)
        if only in (None, "c", "C"):
            res_c = case_c_both_bindings(sw)
    finally:
        sw.SetUserPreferenceToggle(SW_PREF, original)
        print()
        print(f"  restored swInputDimValOnCreate to {original}")

    print()
    print("=" * 60)
    print("=== Spike ZD summary ===")
    for tag, res in (
        ("Z8d-a (baseline, no binds)", res_a),
        ("Z8d-b (D1 bind only)", res_b),
        ("Z8d-c (both bind, full)", res_c),
    ):
        if res is None:
            print(f"  {tag}: skipped/failed")
        else:
            print(f"  {tag}: {res}")
    print()
    print(">>> Visual check (definitive):")
    print("    1. Open SK_ZDa. Are D1 AND D2 black (driving)? Expected YES per Z4.")
    print(
        "    2. Open SK_ZDb Equation Manager. Is D1 equation clean? Is D2 still driving in sketch?"
    )
    print(
        "    3. Open SK_ZDc Equation Manager. Are BOTH equations clean (D1=ZDC_W and D2=ZDC_H)?"
    )
    print("       Open the sketch -- are D1 and D2 both black?")
    print()
    print(">>> Decision matrix:")
    print(
        "    Z8d-a both driving        -> Z4 generalizes to CenterRectangle inline case."
    )
    print(
        "    Z8d-c d2_drives=True      -> PRODUCTION FIX. Modify rectangle handler to add"
    )
    print(
        "                                 dims inline + defer bindings. Ship Z8d-c pattern."
    )
    print(
        "    Z8d-c d2_drives=False     -> Add2 retroactively demotes driving D2. Solution 2 stands."
    )


if __name__ == "__main__":
    main()
