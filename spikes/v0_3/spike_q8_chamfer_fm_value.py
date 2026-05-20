"""
Spike Q8: find the correct swFmChamfer value for CreateDefinition,
and test whether InsertFeatureChamfer with Options=0 (not 4) works.

Background:
  - InsertFeatureChamfer creates a feature in the tree but geometry
    stays unchanged (6F/12E, same as unchamfered box). The PM pane
    is still open waiting for a click.
  - swFmFillet = 1: CreateDefinition(1)+Initialize(0)+CreateFeature
    auto-commits without PM interaction.
  - We need CreateDefinition(swFmChamfer)+CreateFeature to do the same.
  - Q5 probe 0..80 only found v=1 (which is Fillet, not Chamfer).

New discriminator strategy:
  Use .EqualDistance as chamfer-specific -- it's a bool property on
  IChamferFeatureData2 that doesn't exist on ISimpleFilletFeatureData2.
  Also check .EdgeChamferAngle.

Also tests InsertFeatureChamfer with Options=0 instead of 4
(user tip: C# docs show swChamferOption_None for a working call).

Usage:
    python spikes/v0_3/spike_q8_chamfer_fm_value.py
"""

from __future__ import annotations

import sys
import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0


def _create_box(doc, half_mm=10.0, depth_mm=10.0):
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    h = half_mm / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, h, h, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        depth_mm / 1000,
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
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("box extrude failed")


def _face_edge_count(doc):
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        return -1, -1
    body = bodies[-1]
    faces = body.GetFaces
    if callable(faces):
        faces = faces()
    edges = body.GetEdges
    if callable(edges):
        edges = edges()
    return len(faces) if faces else -1, len(edges) if edges else -1


def _select_top_edges(doc):
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        return 0
    body = bodies[-1]
    all_edges = body.GetEdges
    if callable(all_edges):
        all_edges = all_edges()
    doc.ClearSelection2(True)
    targets = [
        (0.01, 0.0, 0.01),
        (-0.01, 0.0, 0.01),
        (0.0, 0.01, 0.01),
        (0.0, -0.01, 0.01),
    ]
    n = 0
    for p in targets:
        best_edge, best_d2 = None, 1e18
        for e in all_edges:
            try:
                cp = e.GetClosestPointOn(*p)
            except Exception:
                continue
            if cp is None:
                continue
            d2 = sum((cp[k] - p[k]) ** 2 for k in range(3))
            if d2 < best_d2:
                best_d2, best_edge = d2, e
        if best_edge and best_d2 < 1e-10:
            if best_edge.Select2(True, 0):
                n += 1
    return n


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)

    # -------------------------------------------------------------------------
    # Part A: probe CreateDefinition(v) for swFmChamfer value
    # Use .EqualDistance as chamfer-specific discriminator
    # -------------------------------------------------------------------------
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2
    _create_box(doc)
    fm = doc.FeatureManager

    print(
        "== Part A: probe CreateDefinition(v), v=0..300, for chamfer-specific props =="
    )

    chamfer_candidates = []
    fillet_v = -1
    for v in range(0, 301):
        try:
            data = fm.CreateDefinition(v)
        except Exception:
            continue
        if data is None:
            continue

        props = {}
        for name in [
            "Type",
            "DefaultDistance",
            "DefaultRadius",
            "EdgeChamferAngle",
            "EqualDistance",
            "IsFlipped",
            "GetEdgeCount",
            "Initialize",
            "GetFaceCount",
            "AccessSelections",
        ]:
            try:
                val = getattr(data, name)
                props[name] = val
            except Exception:
                pass

        has_equal_dist = "EqualDistance" in props
        has_edge_cham_angle = "EdgeChamferAngle" in props
        has_init = "Initialize" in props
        has_default_radius = "DefaultRadius" in props

        if has_default_radius and has_init and fillet_v < 0:
            fillet_v = v
            print(f"  v={v}: FILLET (has DefaultRadius+Initialize) props={list(props)}")
        elif has_equal_dist or has_edge_cham_angle:
            print(f"  v={v}: CHAMFER candidate! props={list(props)}")
            chamfer_candidates.append(v)
        elif len(props) >= 2 and v <= 30:
            print(f"  v={v}: props={list(props)}")

    if not chamfer_candidates:
        print(
            "\nNo EqualDistance/EdgeChamferAngle hit. Printing raw props for v=0..30:"
        )
        for v in range(0, 31):
            try:
                data = fm.CreateDefinition(v)
            except Exception:
                continue
            if data is None:
                continue
            props = []
            for name in [
                "Type",
                "DefaultDistance",
                "DefaultRadius",
                "EdgeChamferAngle",
                "EqualDistance",
                "IsFlipped",
                "GetEdgeCount",
                "GetFaceCount",
                "Initialize",
                "AccessSelections",
                "Count",
            ]:
                try:
                    _ = getattr(data, name)
                    props.append(name)
                except Exception:
                    pass
            if props:
                print(f"  v={v}: {props}")
    else:
        print(f"\n  Chamfer candidates: {chamfer_candidates}")

    # -------------------------------------------------------------------------
    # Part B: test InsertFeatureChamfer with Options=0 (swChamferOption_None)
    # User tip: C# example uses Options=0 for a working call
    # -------------------------------------------------------------------------
    print("\n== Part B: InsertFeatureChamfer with Options=0 vs Options=4 ==")
    for options_val in [0, 4]:
        doc2 = sw.NewDocument(template, 0, 0.0, 0.0)
        _create_box(doc2)
        fm2 = doc2.FeatureManager
        n_sel = _select_top_edges(doc2)
        f_before, e_before = _face_edge_count(doc2)
        print(
            f"\n  Options={options_val}: selected {n_sel} edges, body={f_before}F/{e_before}E"
        )

        result = fm2.InsertFeatureChamfer(
            options_val, 16, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0
        )
        print(f"  InsertFeatureChamfer -> {type(result).__name__!r}: {result!r}")
        doc2.EditRebuild3
        f_after, e_after = _face_edge_count(doc2)
        print(
            f"  body after rebuild: {f_after}F/{e_after}E (chamfered=10F/20E, plain=6F/12E)"
        )

    # -------------------------------------------------------------------------
    # Part C: if chamfer candidate found, test its CreateFeature pipeline
    # -------------------------------------------------------------------------
    if chamfer_candidates:
        best = chamfer_candidates[0]
        print(f"\n== Part C: test CreateDefinition({best}) + CreateFeature ==")
        doc3 = sw.NewDocument(template, 0, 0.0, 0.0)
        _create_box(doc3)
        fm3 = doc3.FeatureManager

        data = fm3.CreateDefinition(best)
        print(f"  data.Type initial = {getattr(data, 'Type', 'N/A')}")
        try:
            data.DefaultDistance = 0.001
            print(f"  set DefaultDistance=0.001 OK")
        except Exception as e:
            print(f"  ! set DefaultDistance: {e!r}")

        n_sel = _select_top_edges(doc3)
        print(f"  selected {n_sel} top edges")

        f_before, _ = _face_edge_count(doc3)
        feat = fm3.CreateFeature(data)
        print(f"  CreateFeature -> {feat!r}")
        if feat:
            feat.Name = "Ch_Q8"
            f_after, e_after = _face_edge_count(doc3)
            print(f"  body: {f_before}F -> {f_after}F / {e_after}E")
            if f_after != f_before:
                print("  GREEN: geometry changed!")
            else:
                print("  RED: geometry unchanged")

    return 0


if __name__ == "__main__":
    sys.exit(main())
