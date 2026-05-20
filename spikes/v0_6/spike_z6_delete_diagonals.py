"""Spike Z6: test whether deleting construction diagonals from a
CreateCenterRectangle sketch makes deferred D1+D2 land as DRIVING dims.

Z5 confirmed:
  - CreateCenterRectangle produces 6 segments, 2 of which are construction.
  - After EditSketch close+reopen, adding D1 then D2 produces D1=driving,
    D2=DRIVEN. The driven D2 is what makes Add2 fail in --deferred-dim
    mode with "A driven or reference dimension is not selectable as the
    dependent variable of the equation."

Z6 hypothesis:
  - If we DELETE the 2 construction diagonals from the sketch before
    adding D1+D2, both dims will land as driving (the diagonals were
    the over-constraint).
  - Without the diagonals, the rectangle's CENTERING relationship to
    the sketch origin is gone -- it'd freely translate. But for our
    use case, we only need D1 and D2 to be driving; the rectangle's
    position is fixed once we close the sketch and the next feature
    references its (now-driven-by-dims) geometry.

Test cases (each on a fresh sketch in a fresh part):
  Z6a: build rect -> close -> reopen -> add D1 + add D2 (baseline = Z5)
       Expected: D1 driving, D2 driven. Reproduces Z5.
  Z6b: build rect -> DELETE BOTH DIAGONALS -> close -> reopen -> add D1 + D2.
       Expected (if hypothesis right): both D1 and D2 driving.
  Z6c: build rect -> DELETE 1 DIAGONAL -> close -> reopen -> add D1 + D2.
       Expected (if hypothesis right): both D1 and D2 driving. (One
       diagonal still anchors the centroid but doesn't over-constrain.)

User-visual verification for each: open the sketch and check D2's
driving/driven status (color). Driving = black, driven = grey/special.

Run from venv-freshtest with SW open. User ticks 2 popups per test
case (6 total).
"""

import pythoncom
import win32com.client


def delete_n_construction_segments(doc, sketch_name, how_many):
    """Re-open the sketch, select up to `how_many` construction-line
    segments, delete them. Returns the number actually deleted."""
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()

    feat = doc.FeatureByPositionReverse(0)
    sk = feat.GetSpecificFeature2
    segs = sk.GetSketchSegments if sk is not None else None
    deleted = 0
    if segs is not None:
        for s in segs:
            if deleted >= how_many:
                break
            try:
                if not s.ConstructionGeometry:
                    continue
            except Exception:
                continue
            # Select the segment via its IEntity, then delete. Try several
            # marshalling variants since pywin32 late-binding is fussy:
            try:
                entity = s  # ISketchSegment inherits IEntity
                doc.ClearSelection2(True)
                selected = False
                # Variant 1: Select4 with VARIANT-empty for the callout arg
                try:
                    import win32com.client

                    empty_variant = win32com.client.VARIANT(
                        win32com.client.pythoncom.VT_DISPATCH, None
                    )
                    if entity.Select4(False, empty_variant):
                        selected = True
                except Exception as e:
                    print(f"    Select4(False, VARIANT empty) ERR: {e!r}")
                # Variant 2: Select (older API, single arg)
                if not selected:
                    try:
                        if entity.Select(False):
                            selected = True
                    except Exception as e:
                        print(f"    Select(False) ERR: {e!r}")
                # Variant 3: Select2 (Append, Mark int)
                if not selected:
                    try:
                        if entity.Select2(False, 0):
                            selected = True
                    except Exception as e:
                        print(f"    Select2(False, 0) ERR: {e!r}")
                if selected:
                    doc.EditDelete()
                    deleted += 1
                else:
                    print("    no Select variant worked for this segment")
            except Exception as e:
                print(f"    delete attempt outer ERR: {e!r}")

    # Close sketch
    doc.SketchManager.InsertSketch(True)
    return deleted


def add_edge_dim(doc, sketch_name, sel_xyz, leader_xyz, label):
    """Re-open sketch, select sketch-segment at sel_xyz, AddDimension2 at
    leader_xyz, close. Returns (selected_ok, dim_not_none)."""
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    sx, sy, sz = sel_xyz
    ok = doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz)
    print(f"    [{label}] segment select={ok}")
    if not ok:
        doc.SketchManager.InsertSketch(True)
        return False, False
    lx, ly, lz = leader_xyz
    dim = doc.AddDimension2(lx, ly, lz)
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}")
    doc.SketchManager.InsertSketch(True)
    return True, dim is not None


def build_case(sw, doc, sketch_name, delete_count, label):
    """Build a center-rectangle sketch, optionally delete N construction
    segments, then add D1+D2 with close-reopen between."""
    print()
    print(f"=== {label} ===")
    sm = doc.SketchManager

    # Create the rectangle
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")

    # Probe initial segment count
    sk = feat.GetSpecificFeature2
    segs = sk.GetSketchSegments
    n_seg = len(segs) if segs is not None else -1
    n_con = sum(1 for s in (segs or []) if getattr(s, "ConstructionGeometry", False))
    print(f"  initial: segments={n_seg}, construction={n_con}")

    # Delete construction segments if requested
    if delete_count > 0:
        deleted = delete_n_construction_segments(doc, sketch_name, delete_count)
        print(f"  deleted {deleted} construction segment(s)")
        # Re-probe
        sk = feat.GetSpecificFeature2
        segs = sk.GetSketchSegments
        n_seg = len(segs) if segs is not None else -1
        n_con = sum(
            1 for s in (segs or []) if getattr(s, "ConstructionGeometry", False)
        )
        print(f"  after delete: segments={n_seg}, construction={n_con}")

    # Add D1 (top edge)
    print(f"  -- adding D1 (top edge), tick popup --")
    add_edge_dim(doc, sketch_name, (0, 0.010, 0), (0, 0.015, 0), f"{label}.D1")
    p1 = doc.Parameter(f"D1@{sketch_name}")
    print(
        f"  D1@{sketch_name} = " f"{(p1.SystemValue * 1000):.3f} mm"
        if p1 is not None
        else "None"
    )

    # Add D2 (left edge)
    print(f"  -- adding D2 (left edge), tick popup --")
    add_edge_dim(doc, sketch_name, (-0.010, 0, 0), (-0.015, 0, 0), f"{label}.D2")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    print(
        f"  D2@{sketch_name} = " f"{(p2.SystemValue * 1000):.3f} mm"
        if p2 is not None
        else "None"
    )

    # Try the binding to see if SW accepts it -- this is the actual test.
    # If D2 is driven, Add2 fails with the driven-dim error.
    eq = doc.GetEquationMgr
    # Add a dummy global to bind against
    global_eq_count_before = eq.GetCount
    eq.Add2(-1, '"TEST_VAR" = 5.0', True)
    formula_d2 = f'"D2@{sketch_name}" = "TEST_VAR"'
    idx = eq.Add2(-1, formula_d2, True)
    print(f"  Add2({formula_d2!r}) -> idx={idx}")
    val = eq.Value(idx) if idx >= 0 else None
    print(
        f"  Value({idx}) = {val!r}  (None or wrong = driven dim, "
        f"correct mm value = driving dim)"
    )
    return idx, val


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    template = sw.GetUserPreferenceStringValue(8)

    # ----- Case A: baseline (no deletions) -----
    doc_a = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc_a is None:
        print("! NewDocument failed for case A")
        return
    idx_a, val_a = build_case(sw, doc_a, "SK_A", 0, "Z6a: baseline (no deletions)")

    # ----- Case B: delete both diagonals -----
    doc_b = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc_b is None:
        print("! NewDocument failed for case B")
        return
    idx_b, val_b = build_case(sw, doc_b, "SK_B", 2, "Z6b: delete BOTH diagonals")

    # ----- Case C: delete one diagonal -----
    doc_c = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc_c is None:
        print("! NewDocument failed for case C")
        return
    idx_c, val_c = build_case(sw, doc_c, "SK_C", 1, "Z6c: delete ONE diagonal")

    # ----- Summary -----
    print()
    print("=== Z6 summary ===")
    for tag, idx, val in (
        ("Z6a baseline", idx_a, val_a),
        ("Z6b delete-both", idx_b, val_b),
        ("Z6c delete-one", idx_c, val_c),
    ):
        print(f"  {tag}: Add2 idx={idx}, Value={val!r}")
    print()
    print(">>> Reading Z6 results:")
    print("    Add2 idx >= 0 AND Value=20.0 -> D2 is DRIVING (binding works)")
    print("    Add2 idx < 0 OR Value=None  -> D2 is DRIVEN (binding rejected)")


if __name__ == "__main__":
    main()
