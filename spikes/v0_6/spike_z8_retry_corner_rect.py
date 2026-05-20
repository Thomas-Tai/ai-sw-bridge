"""Spike Z8-RETRY: clean test of whether `CreateCornerRectangle` + manual
construction-diagonal + `SketchAddConstraints("sgMIDPOINT")` survives the
close-reopen cycle that demotes D2 to driven on `CreateCenterRectangle`.

This is a retry of the original Z8 (`spike_z8_corner_rect.py`) which hit
TWO compounding confounders:

  1. `swInputDimValOnCreate = False` toggled by main() to "match production"
     -- but Z9 (2026-05-20) empirically showed production runs with the
     popup ON. The False toggle made D1's AddDimension2 silently return
     None, leaving D2 with no anchor. Confound 1 is fixed here by leaving
     the toggle in its current state (the human will tick the popup like
     in Z9).

  2. `AddSketchRelation` / `AddRelation` / `AddSketchConstraint` were all
     AttributeError. The correct late-binding API name is
     `SketchManager.SketchAddConstraints("sgMIDPOINT")` -- a STRING-based
     method that bypasses the RelationManager object lookup. Per the
     external diagnostic (2026-05-20) and a prior session that already
     looked up the constraint names (transcript lines 3820-3827) before
     Z8 was written.

  3. Diagonal selection in Z8 original used coordinate-based pick at
     origin, which is ambiguous because perimeter-line midpoints also
     sit on the axes. Confound 3 is fixed here by capturing the
     `diag_line` object returned by `CreateLine` and calling
     `Select4(False, VARIANT(VT_DISPATCH, None))` directly -- bypasses
     SelectByID entirely.

  4. Z8 original tried to select Origin via `SelectByID("Point1@Origin",
     "EXTSKETCHPOINT", ...)`. The diagnostic confirms "EXTSKETCHPOINT" is
     the correct selection type for the origin in this context. Append=True
     for the origin selection so the diagonal stays selected.

Hypothesis: `CreateCenterRectangle` collapses to a rigid resolved-symmetric
matrix on `InsertSketch(True)` (per 2026-05-20 mechanism note from external
diagnostic). The matrix doesn't fully relax when the sketch reopens, so
D2 hits the over-constraint demotion. `CreateCornerRectangle` produces 4
plain lines with NO macro-feature relations -- if the centering invariant
is supplied via a manual midpoint relation to the origin via the
construction diagonal, the close-reopen cycle should not produce the
demotion.

Three cases:

  Z8r-a: CornerRectangle only, no centering relation. Tests whether
         CornerRectangle ALONE (with no centering, so the box can drift)
         escapes the demotion. If yes -> the macro-feature is the cause;
         centering invariant must be supplied externally.

  Z8r-b: CornerRectangle + diagonal + sgMIDPOINT relation between
         diagonal and Origin. The intended production fix.

  Z8r-c: As Z8r-b but VERIFY the relation actually applied before close.
         Re-select the diagonal post-relation, query its relations count
         via GetRelations / IsConstructionGeometry to confirm sgMIDPOINT
         landed. If the relation didn't apply, Z8r-b's result is
         uninterpretable.

Acceptance test (visual): for each case, open Equation Manager and check
whether the "D2@SK_*" binding is red (driven, fix failed) or clean
(driving, fix worked). Open the sketch tree and check whether
"Midpoint1" relation appears under the Relations folder for cases b/c.

Run from venv-freshtest with SW open. Expected popup ticks:
  - Z8r-a: 2 ticks (D1, D2)
  - Z8r-b: 2 ticks (D1, D2)
  - Z8r-c: 2 ticks (D1, D2)
  = 6 ticks total
"""
import os
import pythoncom
import win32com.client


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def add_edge_dim_with_reopen(doc, sketch_name, edge_xyz, leader_xyz, label):
    """Same pattern as Z9 -- proven to work with the popup ON. Returns
    the dim or None on segment-select failure."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", *edge_xyz)
    print(f"    [{label}] segment select {edge_xyz} -> {ok}")
    if not ok:
        sm.InsertSketch(True)
        return None
    dim = doc.AddDimension2(*leader_xyz)
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}")
    sm.InsertSketch(True)
    return dim


def try_d2_binding(doc, sketch_name, label):
    """Bind D2 to a test var and force rebuild. Returns the readback value.
    Per Z9, eq.Value(idx) is NOT a reliable success signal -- the binding
    can be accepted while D2 stays driven. Parameter readback after rebuild
    is the only programmatic signal short of UI inspection."""
    eq = doc.GetEquationMgr
    var_name = f"Z8R_TEST_VAR_{label}"
    eq.Add2(-1, f'"{var_name}" = 7.0', True)
    formula = f'"D2@{sketch_name}" = "{var_name}"'
    idx = eq.Add2(-1, formula, True)
    print(f"  [{label}] Add2({formula!r}) -> idx={idx}")
    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  [{label}] EditRebuild3 ERR: {e!r}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    p2_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(f"  [{label}] Parameter(D2@{sketch_name}) after rebuild = {p2_val!r} mm")
    # Per Z9: if p2_val tracks the TEST_VAR (7.0), binding drives D2.
    # If p2_val stays at the placeholder size (20.0 from CreateCornerRectangle
    # below), D2 is driven and the binding has no effect.
    drives = p2_val is not None and abs(p2_val - 7.0) < 0.01
    print(f"  [{label}] >>> binding drives D2: {drives}")
    return {"idx": idx, "p2_mm": p2_val, "drives": drives}


def case_a_corner_only(sw):
    """CornerRectangle, no centering relation. Box will drift off-origin
    when scaled, but tests whether the macro-feature is the demotion cause."""
    print()
    print("=== Z8r-a: CornerRectangle only, no centering ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # 20x20mm box centered visually but NOT anchored to origin via relation
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = "SK_Z8ra"
    print(f"  built sketch: {feat.Name!r}")

    add_edge_dim_with_reopen(doc, "SK_Z8ra", (0, 0.010, 0), (0, 0.015, 0), "Z8r-a.D1")
    add_edge_dim_with_reopen(doc, "SK_Z8ra", (-0.010, 0, 0), (-0.015, 0, 0), "Z8r-a.D2")

    return try_d2_binding(doc, "SK_Z8ra", "Z8r-a")


def build_centered_corner_rect(doc, sketch_name, w_half=0.010, h_half=0.010,
                                verify=False):
    """Per the 2026-05-20 external diagnostic. Returns (sketch_feature,
    diag_line) and prints diagnostics. If verify=True, queries the sketch
    relations after applying sgMIDPOINT.

    Steps:
      1. CreateCornerRectangle (-w_half, -h_half) to (+w_half, +h_half)
      2. CreateLine diagonal (-w_half, -h_half) to (+w_half, +h_half),
         capture object reference, demote to construction
      3. ClearSelection2
      4. diag_line.Select4(False, VT_DISPATCH_None)
      5. SelectByID2("Point1@Origin", "EXTSKETCHPOINT", ..., Append=True,
         VT_DISPATCH_None for Callout)
      6. SketchAddConstraints("sgMIDPOINT")
      7. ClearSelection2
      8. InsertSketch(True)
    """
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)

    # 1. Corner rectangle
    sm.CreateCornerRectangle(-w_half, -h_half, 0, w_half, h_half, 0)
    print(f"  CreateCornerRectangle ({-w_half*1000:.1f}, {-h_half*1000:.1f}) to "
          f"({w_half*1000:.1f}, {h_half*1000:.1f}) mm")

    # 2. Diagonal + construction
    diag_line = sm.CreateLine(-w_half, -h_half, 0, w_half, h_half, 0)
    if diag_line is None:
        print("  !! CreateLine returned None -- cannot build centered rect")
        return None, None
    print(f"  diagonal line created; ConstructionGeometry pre-set: "
          f"{getattr(diag_line, 'ConstructionGeometry', '?')!r}")
    try:
        diag_line.ConstructionGeometry = True
        print(f"  set ConstructionGeometry=True; readback: "
              f"{getattr(diag_line, 'ConstructionGeometry', '?')!r}")
    except Exception as e:
        print(f"  !! set ConstructionGeometry ERR: {e!r}")

    # 3. Clear selection before relation
    doc.ClearSelection2(True)

    # 4. Select diagonal via object pointer (Z9 Probe B confirmed this is
    # the only reachable selection path from late-binding for already-
    # created segments)
    vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
    ok_diag = False
    for sel_name in ("Select4", "Select2", "Select"):
        method = getattr(diag_line, sel_name, None)
        if method is None:
            continue
        try:
            if sel_name == "Select4":
                r = method(False, vt_disp_none)
            else:
                r = method(False)
            print(f"  diag_line.{sel_name}(False, ...) -> {r!r}")
            ok_diag = bool(r)
            if ok_diag:
                break
        except Exception as e:
            print(f"  diag_line.{sel_name} ERR: {type(e).__name__}: {e}")

    if not ok_diag:
        print("  !! could not select diagonal via object methods -- trying SelectByID at midpoint")
        # Fallback: the diagonal passes through (0,0); SelectByID at origin
        # MAY pick it but the perimeter line midpoints also sit there. Best
        # effort only.
        ok_diag = doc.SelectByID("", "SKETCHSEGMENT", 0, 0, 0)
        print(f"  SelectByID fallback -> {ok_diag}")

    if not ok_diag:
        print("  !! diagonal selection failed; aborting relation step")
        sm.InsertSketch(True)
        feat = doc.FeatureByPositionReverse(0)
        feat.Name = sketch_name
        return feat, diag_line

    # 5. Append Origin to selection. Try Extension.SelectByID2 first with
    # VT_DISPATCH Callout (per Z9 Probe B fix), then plain SelectByID.
    ok_orig = False
    try:
        ok_orig = doc.Extension.SelectByID2(
            "Point1@Origin", "EXTSKETCHPOINT", 0, 0, 0,
            True,   # Append
            0,      # Mark
            vt_disp_none,  # Callout
            0,      # Options
        )
        print(f"  Extension.SelectByID2('Point1@Origin', 'EXTSKETCHPOINT', append=True) -> {ok_orig}")
    except Exception as e:
        print(f"  Extension.SelectByID2 ERR: {type(e).__name__}: {e}")

    if not ok_orig:
        # Plain SelectByID has Append as 6th arg in old SW API; pywin32
        # may or may not support that overload. Try anyway.
        for try_name in ("Point1@Origin", "Origin"):
            try:
                ok_orig = doc.SelectByID(try_name, "EXTSKETCHPOINT", 0, 0, 0)
                print(f"  SelectByID({try_name!r}, 'EXTSKETCHPOINT', ...) -> {ok_orig}")
                if ok_orig:
                    break
            except Exception as e:
                print(f"  SelectByID({try_name!r}) ERR: {type(e).__name__}: {e}")

    if not ok_orig:
        print("  !! could not select Origin; aborting relation step")
        sm.InsertSketch(True)
        feat = doc.FeatureByPositionReverse(0)
        feat.Name = sketch_name
        return feat, diag_line

    # 6. Apply sgMIDPOINT relation
    try:
        r = sm.SketchAddConstraints("sgMIDPOINT")
        print(f"  SketchAddConstraints('sgMIDPOINT') -> {r!r}")
    except Exception as e:
        print(f"  !! SketchAddConstraints('sgMIDPOINT') ERR: {type(e).__name__}: {e}")
        # Try alternate constraint names just in case
        for alt in ("Midpoint", "SGMIDPOINT", "sgSYMMETRIC"):
            try:
                r = sm.SketchAddConstraints(alt)
                print(f"  SketchAddConstraints({alt!r}) -> {r!r}")
                break
            except Exception as e2:
                print(f"  SketchAddConstraints({alt!r}) ERR: {type(e2).__name__}: {e2}")

    # 7. Clear selection
    doc.ClearSelection2(True)

    # Verify relation was applied (case c only)
    if verify:
        try:
            # Sketch.GetRelations is documented; may or may not be late-binding-reachable
            sk_obj = doc.GetActiveSketch2
            if sk_obj is not None:
                rels = getattr(sk_obj, "GetRelations", None)
                if rels is not None:
                    r_list = rels()
                    print(f"  GetActiveSketch2.GetRelations() -> {r_list!r}")
                else:
                    print(f"  sketch has no GetRelations attr (late-binding hide)")
            else:
                print(f"  GetActiveSketch2 returned None")
        except Exception as e:
            print(f"  relation-verify ERR: {type(e).__name__}: {e}")

    # 8. Close sketch
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")
    return feat, diag_line


def case_b_corner_with_midpoint(sw):
    """The intended production-fix configuration."""
    print()
    print("=== Z8r-b: CornerRectangle + diagonal + sgMIDPOINT to Origin ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    feat, diag = build_centered_corner_rect(doc, "SK_Z8rb", verify=False)
    if feat is None:
        return None

    add_edge_dim_with_reopen(doc, "SK_Z8rb", (0, 0.010, 0), (0, 0.015, 0), "Z8r-b.D1")
    add_edge_dim_with_reopen(doc, "SK_Z8rb", (-0.010, 0, 0), (-0.015, 0, 0), "Z8r-b.D2")

    return try_d2_binding(doc, "SK_Z8rb", "Z8r-b")


def case_c_corner_with_midpoint_verified(sw):
    """As Z8r-b but introspect whether the midpoint relation actually
    applied. If the relation didn't land, Z8r-b's result is uninterpretable."""
    print()
    print("=== Z8r-c: Z8r-b with relation-verify pass ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    feat, diag = build_centered_corner_rect(doc, "SK_Z8rc", verify=True)
    if feat is None:
        return None

    add_edge_dim_with_reopen(doc, "SK_Z8rc", (0, 0.010, 0), (0, 0.015, 0), "Z8r-c.D1")
    add_edge_dim_with_reopen(doc, "SK_Z8rc", (-0.010, 0, 0), (-0.015, 0, 0), "Z8r-c.D2")

    return try_d2_binding(doc, "SK_Z8rc", "Z8r-c")


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    # Per 2026-05-20 integration-patch diagnostic: force the toggle to TRUE
    # before any AddDimension2 burst. If left False, AddDimension2 returns
    # None silently and bindings fail because no dim exists to bind. Restore
    # original state in finally block so spike doesn't poison the user's
    # SW environment.
    #
    # Z9 happened to run with the toggle ON by user default; this hardens
    # against the case where a prior spike (or production --deferred-dim
    # code path that swallows-then-restores) leaked the toggle to False.
    SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8
    original_toggle = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
    print(f"  original swInputDimValOnCreate = {original_toggle}")
    if original_toggle is not True:
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, True)
        readback = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
        print(f"  forced swInputDimValOnCreate to True; readback = {readback}")

    only = os.environ.get("Z8R_ONLY")  # 'a', 'b', or 'c' to run just one case
    res_a = res_b = res_c = None
    try:
        if only in (None, "a", "A"):
            res_a = case_a_corner_only(sw)
        if only in (None, "b", "B"):
            res_b = case_b_corner_with_midpoint(sw)
        if only in (None, "c", "C"):
            res_c = case_c_corner_with_midpoint_verified(sw)
    finally:
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, original_toggle)
        final = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
        print(f"  restored swInputDimValOnCreate to {original_toggle}; readback = {final}")

    print()
    print("=" * 60)
    print("=== Z8-retry summary ===")
    for tag, res in (
        ("Z8r-a (corner only)",      res_a),
        ("Z8r-b (corner+midpoint)",  res_b),
        ("Z8r-c (corner+midpoint+verify)", res_c),
    ):
        if res is None:
            print(f"  {tag}: skipped")
            continue
        print(f"  {tag}: D2={res['p2_mm']!r} mm, drives={res['drives']}")
    print()
    print(">>> Decision matrix:")
    print("    Z8r-a drives  -> macro-feature WAS the cause; centering is optional")
    print("                     (rectangle handler can switch to CornerRectangle directly)")
    print("    Z8r-b drives  -> the production fix is corner+midpoint as drafted")
    print("                     (update builder.py rectangle handler)")
    print("    Z8r-c diverges from Z8r-b -> relation didn't apply consistently;")
    print("                                 investigate sgMIDPOINT selection state")
    print("    All red       -> demotion is structural across ALL rectangle close-reopen")
    print("                     (consider Direction B' VBA fallback)")
    print()
    print(">>> Visual checks needed (no late-binding API for these):")
    print("    1. Open Equation Manager: are 'D2@SK_Z8r*' bindings red or clean?")
    print("    2. Open each sketch tree: is 'Midpoint1' under Relations in SK_Z8rb / SK_Z8rc?")
    print("    3. Drag the rectangle corner: does it stay centered on origin in SK_Z8rb / SK_Z8rc?")


if __name__ == "__main__":
    main()
