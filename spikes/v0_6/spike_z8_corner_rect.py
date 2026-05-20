"""Spike Z8: test whether the driven-D2 problem reproduces on a
CreateCornerRectangle sketch (vs the CreateCenterRectangle baseline
where Z5/Z6 demonstrated the failure).

Hypothesis (from external analysis):
  CreateCenterRectangle generates a macro-feature internally with 4
  lines + 2 diagonals + auto-symmetry relations. This hidden state
  may behave anomalously across the InsertSketch close/EditSketch
  re-open boundary, causing the second deferred dim to land as a
  driven (reference) dim.

  CreateCornerRectangle generates 4 plain lines with no hidden
  symmetry/diagonal baggage. If the close-reopen-add-D1-close-reopen-
  add-D2 cycle on a CornerRectangle produces both D1 and D2 as DRIVING
  dims, then the issue IS specific to CreateCenterRectangle and the
  fix is to switch primitives in --deferred-dim mode.

Two cases:
  Z8a: CornerRectangle, baseline -- close, reopen, add D1, close,
       reopen, add D2, close. Try Add2 binding to D2 + rebuild.
       If D2 ends up driving (no red equation), fix is identified.

  Z8b: CornerRectangle + a manually-drawn construction diagonal +
       a Midpoint relation between the diagonal and the sketch
       origin (to recover the centering invariant). Same close/
       reopen/add/add cycle.
       Tests whether adding the centering relation re-introduces
       the failure.

Acceptance test (visual, per case): open the Equation Manager in SW
and check whether the test binding for D2 is red. Open the sketch
and check whether D2 is driven (grey) or driving (black).

Run from venv-freshtest with SW open. 2 popups per case x 2 cases
= 4 ticks total.
"""

import os
import pythoncom
import win32com.client

# swConstraintType_e best-guess values (will probe at runtime)
SW_CONSTRAINT_MIDPOINT = 3


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def add_edge_dim_with_reopen(doc, sketch_name, edge_sel_xyz, leader_xyz, label):
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    sx, sy, sz = edge_sel_xyz
    ok = doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz)
    print(f"    [{label}] segment select={ok}")
    if not ok:
        sm.InsertSketch(True)
        return None
    lx, ly, lz = leader_xyz
    dim = doc.AddDimension2(lx, ly, lz)
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}")
    sm.InsertSketch(True)
    return dim


def try_d2_binding(doc, sketch_name, label):
    eq = doc.GetEquationMgr
    # Use a unique global name per case to avoid collision across NewDocs
    eq.Add2(-1, f'"Z8_TEST_VAR_{label}" = 7.0', True)
    formula = f'"D2@{sketch_name}" = "Z8_TEST_VAR_{label}"'
    idx = eq.Add2(-1, formula, True)
    val = eq.Value(idx) if idx >= 0 else None
    try:
        _ = doc.EditRebuild3
    except Exception as e:
        print(f"    [{label}] EditRebuild3 ERR: {e!r}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    p2_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(f"  [{label}] Add2({formula!r}) -> idx={idx}, eq.Value={val!r}")
    print(f"  [{label}] Parameter(D2@{sketch_name}) after rebuild = {p2_val!r} mm")
    return idx, val, p2_val


def case_a_corner_rectangle(sw):
    print()
    print("=== Z8a: CreateCornerRectangle baseline, close/reopen between D1 and D2 ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # CornerRectangle (-10, -10) to (+10, +10) -- a 20x20 box centered visually
    # but NOT auto-anchored to centroid. Args: (x1, y1, z1, x2, y2, z2)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = "SK_A"
    print(f"  built corner rectangle sketch: {feat.Name!r}")

    # Probe segment count -- should be just 4 lines, no construction
    sk = feat.GetSpecificFeature2
    segs = sk.GetSketchSegments
    n_seg = len(segs) if segs is not None else -1
    n_con = sum(1 for s in (segs or []) if getattr(s, "ConstructionGeometry", False))
    print(f"  initial: segments={n_seg}, construction={n_con}")

    add_edge_dim_with_reopen(doc, "SK_A", (0, 0.010, 0), (0, 0.015, 0), "Z8a.D1")
    add_edge_dim_with_reopen(doc, "SK_A", (-0.010, 0, 0), (-0.015, 0, 0), "Z8a.D2")

    return try_d2_binding(doc, "SK_A", "Z8a")


def case_b_corner_plus_midpoint(sw):
    print()
    print(
        "=== Z8b: CornerRectangle + construction diagonal + Midpoint(origin) relation ==="
    )
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)

    # Draw construction diagonal from (-10,-10) to (+10,+10)
    diag = sm.CreateLine(-0.010, -0.010, 0, 0.010, 0.010, 0)
    if diag is None:
        print("  ! CreateLine returned None")
    else:
        print(
            f"  diagonal line created, ConstructionGeometry before set: "
            f"{getattr(diag, 'ConstructionGeometry', '?')!r}"
        )
        try:
            diag.ConstructionGeometry = True
            print(
                f"  set ConstructionGeometry=True; read back: "
                f"{getattr(diag, 'ConstructionGeometry', '?')!r}"
            )
        except Exception as e:
            print(f"  set ConstructionGeometry ERR: {e!r}")

    # Try to add a Midpoint relation between the diagonal and the origin.
    # The Origin in a sketch is a special EXTERNALPOINT / SKETCHPOINT entity
    # named "Point1@Origin" or accessible via SelectByID("Origin", "EXTSKETCHPOINT", ...).
    # We need to: select diagonal + origin, then call AddSketchRelation
    # (or sm.MakeSymmetric / sm.AddMidpoint -- API name varies by SW version).
    doc.ClearSelection2(True)
    # Select the diagonal
    ok_diag = doc.SelectByID(
        "", "SKETCHSEGMENT", 0, 0, 0
    )  # midpoint of diagonal at origin
    print(f"  select diagonal via SKETCHSEGMENT @ origin: {ok_diag}")
    # Add origin to selection
    ok_orig = doc.SelectByID("Point1@Origin", "EXTSKETCHPOINT", 0, 0, 0)
    print(f"  add Origin to selection: {ok_orig}")
    if not ok_orig:
        # Try alternate origin selection paths
        for try_name, try_type in (
            ("Origin", "EXTSKETCHPOINT"),
            ("", "EXTSKETCHPOINT"),
            ("Point", "SKETCHPOINT"),
        ):
            ok_orig = doc.SelectByID(try_name, try_type, 0, 0, 0)
            print(
                f"  fallback SelectByID({try_name!r}, {try_type!r}, 0,0,0): {ok_orig}"
            )
            if ok_orig:
                break

    # AddSketchRelation: try a few names since the API surface varies.
    relation_applied = False
    for attr in ("AddSketchRelation", "AddRelation", "AddSketchConstraint"):
        try:
            fn = getattr(sm, attr, None)
            if fn is None:
                continue
            print(
                f"  calling sm.{attr}(swConstraintType_MIDPOINT={SW_CONSTRAINT_MIDPOINT})"
            )
            try:
                fn(SW_CONSTRAINT_MIDPOINT)
                relation_applied = True
                print(f"    {attr} returned (no exception)")
                break
            except Exception as e:
                print(f"    {attr}({SW_CONSTRAINT_MIDPOINT}) ERR: {e!r}")
                # Try string form
                try:
                    fn("Midpoint")
                    relation_applied = True
                    print(f"    {attr}('Midpoint') returned (no exception)")
                    break
                except Exception as e2:
                    print(f"    {attr}('Midpoint') ERR: {e2!r}")
        except Exception as e:
            print(f"  {attr} getattr ERR: {e!r}")

    if not relation_applied:
        print("  !! could not apply Midpoint relation -- continuing anyway")

    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = "SK_B"
    print(f"  built sketch: {feat.Name!r}")

    sk = feat.GetSpecificFeature2
    segs = sk.GetSketchSegments
    n_seg = len(segs) if segs is not None else -1
    n_con = sum(1 for s in (segs or []) if getattr(s, "ConstructionGeometry", False))
    print(f"  initial: segments={n_seg}, construction={n_con}")

    add_edge_dim_with_reopen(doc, "SK_B", (0, 0.010, 0), (0, 0.015, 0), "Z8b.D1")
    add_edge_dim_with_reopen(doc, "SK_B", (-0.010, 0, 0), (-0.015, 0, 0), "Z8b.D2")

    return try_d2_binding(doc, "SK_B", "Z8b")


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    # Match production behavior: builder.py sets this to False during
    # build() so AddDimension2 doesn't open the floating Modify popup.
    # The dim is added silently; user (or side pane) handles confirmation
    # at the end.
    SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8
    prev = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, False)
    print(
        f"  swInputDimValOnCreate was {prev}, set to False to match production --deferred-dim path"
    )

    only = os.environ.get("Z8_ONLY")
    res_a = None
    res_b = None
    if only in (None, "a", "A"):
        res_a = case_a_corner_rectangle(sw)
    if only in (None, "b", "B"):
        res_b = case_b_corner_plus_midpoint(sw)

    # Restore toggle
    sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, prev)
    print(f"  swInputDimValOnCreate restored to {prev}")

    print()
    print("=== Z8 summary ===")
    for tag, res in (
        ("Z8a corner-rect baseline", res_a),
        ("Z8b corner-rect + midpoint", res_b),
    ):
        if res is None:
            print(f"  {tag}: skipped")
            continue
        idx, val, p2_val = res
        print(f"  {tag}: Add2 idx={idx}, eq.Value={val!r}, D2 final={p2_val!r} mm")
    print()
    print(">>> Visual check: open Equation Manager and the sketch for SK_A (and SK_B).")
    print("    Z8a clean (no red, D2 driving) -> CornerRectangle is the fix")
    print("    Z8a red (D2 driven)             -> bug is structural across rectangles;")
    print(
        "                                       Z8b's midpoint may or may not change it"
    )


if __name__ == "__main__":
    main()
