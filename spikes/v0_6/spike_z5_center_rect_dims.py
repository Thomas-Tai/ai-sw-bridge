"""Spike Z5: validate the construction-diagonal hypothesis for why
--deferred-dim produces a 'driven dim' error on rectangle sketches.

Background:
  In the per-sketch deferred-dim flow, after CreateCenterRectangle closes
  and re-opens via EditSketch, the second dim (D2 on the left edge) lands
  as a DRIVEN (reference) dim instead of a DRIVING dim. SW then refuses
  the binding equation "D2@SK_PlateSlab" = "S1B_MMP_W" with the message
  "A driven or reference dimension is not selectable as the dependent
  variable of the equation."

Hypothesis:
  CreateCenterRectangle adds 2 construction-line diagonals from corner to
  corner. These plus the midpoint-on-diagonal constraints anchor the
  rectangle's centroid AND its aspect ratio. When the sketch is closed
  via InsertSketch(True), SW may auto-add additional implicit constraints.
  When re-opened, the rectangle is now FULLY constrained -- so an
  explicit D2 added afterwards is redundant and SW makes it driven.

Test procedure:
  Phase 1: build a plain Front-plane sketch with CreateCenterRectangle.
           Close it.
  Phase 2: probe the sketch's contents -- count line segments,
           construction segments, and any sketch relations. This tells
           us what SW actually persists across close/reopen.
  Phase 3: re-open via EditSketch. Probe again. Has anything changed?
  Phase 4: add D1 (top-edge dim). Tick popup. Close, re-open.
           Probe Parameter('D1@SK_TestBox') -- is it None? Driving? Driven?
  Phase 5: add D2 (left-edge dim). Tick popup. Close.
           Probe Parameter('D2@SK_TestBox') -- this is the one we expect
           to be 'driven' under our hypothesis. Use IDimension.IsDriving
           (or equivalent) to read the dim's driving/driven status.
  Phase 6: if D2 is driven, try DELETING the construction-diagonal
           segments from the sketch and re-add D2. Does it now land
           as driving?

Decision tree:
  - D1 driving + D2 driven: hypothesis CONFIRMED. Investigate which
    segment(s) are constraining height; deletion is the right fix.
  - Both driving: hypothesis WRONG. Something else is causing the
    --deferred-dim failure (maybe a per-feature-build interaction).
  - Both driven: even D1 is being demoted -- weirder problem; full
    rectangle anchored by construction geometry alone.

Run from venv-freshtest with SW open. User ticks 2 popups during the
run.
"""

import pythoncom
import win32com.client


def probe_sketch(doc, sketch_name, label):
    """Try to read the SketchSegments and SketchRelations of a sketch.
    Returns count of (total_segments, construction_segments, relations).
    """
    doc.ClearSelection2(True)
    ok = doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    if not ok:
        print(f"  [{label}] could not select sketch {sketch_name!r}")
        return None
    # The most-recently-created sketch is FeatureByPositionReverse(0) when
    # this is the only sketch; safer to enumerate via the feature.
    feat = doc.FeatureByPositionReverse(0)
    sk = feat.GetSpecificFeature2  # IFeature::GetSpecificFeature2 -> ISketch
    if sk is None:
        print(f"  [{label}] GetSpecificFeature2 returned None")
        return None

    # Sketch segments (lines, arcs, circles, etc.)
    try:
        segs = sk.GetSketchSegments
    except Exception as e:
        print(f"  [{label}] GetSketchSegments ERR: {e!r}")
        segs = None
    n_seg, n_construction = 0, 0
    if segs is not None:
        try:
            n_seg = len(segs)
        except Exception:
            # SafeArray sometimes not iterable; ignore
            n_seg = -1
        if n_seg > 0:
            for s in segs:
                try:
                    if s.ConstructionGeometry:
                        n_construction += 1
                except Exception:
                    pass

    # Sketch relations
    try:
        rels = sk.GetSketchRelations
    except Exception as e:
        print(f"  [{label}] GetSketchRelations ERR: {e!r}")
        rels = None
    n_rel = 0
    if rels is not None:
        try:
            n_rel = len(rels)
        except Exception:
            n_rel = -1

    print(
        f"  [{label}] sketch={sketch_name!r}: "
        f"segments={n_seg} (of which construction={n_construction}), "
        f"relations={n_rel}"
    )
    return n_seg, n_construction, n_rel


def report_dim_status(doc, param_name, label):
    p = doc.Parameter(param_name)
    if p is None:
        print(f"  [{label}] Parameter({param_name!r}) = None")
        return
    try:
        val = p.SystemValue * 1000
    except Exception as e:
        print(f"  [{label}] Parameter({param_name!r}) SystemValue ERR: {e!r}")
        return
    # IDimension has IsDriving (bool) — try several variants.
    try:
        # p is IDimension; SystemValue and FullName work via late-binding.
        # IsDriving may need to be accessed as a property.
        is_driving = getattr(p, "IsDriving", None)
        print(
            f"  [{label}] Parameter({param_name!r}) = {val:.3f} mm, "
            f"IsDriving={is_driving!r}"
        )
    except Exception as e:
        print(
            f"  [{label}] Parameter({param_name!r}) = {val:.3f} mm, "
            f"IsDriving access ERR: {e!r}"
        )


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

    # ----- Phase 1: create center rectangle, close -----
    print()
    print("=== Phase 1: CreateCenterRectangle on Front plane, then close ===")
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(
        0, 0, 0, 0.010, 0.010, 0
    )  # center at origin, corner at (10,10)
    sm.InsertSketch(True)  # close
    sk_feat = doc.FeatureByPositionReverse(0)
    sk_feat.Name = "SK_TestBox"
    print(f"  sketch closed and named: {sk_feat.Name!r}")

    # ----- Phase 2: probe sketch state right after close -----
    print()
    print("=== Phase 2: probe sketch state after close ===")
    probe_sketch(doc, "SK_TestBox", "after-close")

    # ----- Phase 3: re-open and probe -----
    print()
    print("=== Phase 3: re-open via EditSketch and probe ===")
    doc.ClearSelection2(True)
    doc.SelectByID("SK_TestBox", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    probe_sketch(doc, "SK_TestBox", "after-reopen")
    sm.InsertSketch(True)  # close again

    # ----- Phase 4: add D1 (top edge) and report status -----
    print()
    print("=== Phase 4: add D1 (top edge), tick popup, close, report ===")
    doc.ClearSelection2(True)
    doc.SelectByID("SK_TestBox", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)  # top edge
    print(f"  top edge selected: {ok}")
    dim1 = doc.AddDimension2(0, 0.015, 0)
    print(f"  AddDimension2 D1 returned: {dim1 is not None}")
    sm.InsertSketch(True)
    report_dim_status(doc, "D1@SK_TestBox", "after-D1")

    # ----- Phase 5: add D2 (left edge) and report status -----
    print()
    print("=== Phase 5: add D2 (left edge), tick popup, close, report ===")
    doc.ClearSelection2(True)
    doc.SelectByID("SK_TestBox", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", -0.010, 0, 0)  # left edge
    print(f"  left edge selected: {ok}")
    dim2 = doc.AddDimension2(-0.015, 0, 0)
    print(f"  AddDimension2 D2 returned: {dim2 is not None}")
    sm.InsertSketch(True)
    report_dim_status(doc, "D2@SK_TestBox", "after-D2")

    # ----- Phase 6: print final equation manager + sketch state -----
    print()
    print("=== Phase 6: final probe ===")
    probe_sketch(doc, "SK_TestBox", "final")
    report_dim_status(doc, "D1@SK_TestBox", "final-D1")
    report_dim_status(doc, "D2@SK_TestBox", "final-D2")

    print()
    print(">>> Z5 decision:")
    print("    D1 IsDriving=True, D2 IsDriving=False -> hypothesis CONFIRMED.")
    print("       Construction-line deletion approach is worth pursuing.")
    print("    Both IsDriving=True -> hypothesis WRONG; something else causes")
    print("       MMP's --deferred-dim failure. Look elsewhere.")
    print("    Both IsDriving=False -> ???")


if __name__ == "__main__":
    main()
