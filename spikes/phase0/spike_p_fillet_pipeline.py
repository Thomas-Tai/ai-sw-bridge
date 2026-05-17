"""
Spike P: ISimpleFilletFeatureData2 + CreateDefinition/CreateFeature pipeline.

The canonical SW 2020+ path for creating a constant-radius fillet feature
via the SOLIDWORKS API. Runs against the already-open SW session.

Why this spike: FeatureFillet3 (single-call) is marked obsolete for
constant-radius fillets since SW 2020 per the decompiled CHM. The
recommended path is:

  1. data = fm.CreateDefinition(swFmFillet)
  2. ok = data.Initialize(swConstRadiusFillet)
  3. set properties on `data` (default radius, edges, ...)
  4. feat = fm.CreateFeature(data)

The risky question (which is why we spike before wiring into the bridge):
- Can pywin32 late-binding manipulate a `data` CDispatch that came from
  CreateDefinition, set properties on it, and pass it BACK as an Object
  arg to CreateFeature? Prior late-binding gotchas (OUT params, COM-
  interface args fail with Type mismatch) suggest CreateFeature(data)
  may have the same class of failure as SelectByID2(Callout).

What we test:
- Build a 20x20x10 box on Front Plane (proven path).
- Try CreateDefinition with several int values for swFmFillet
  (CHM doesn't list explicit numeric values; have to probe).
- Once we find swFmFillet, call Initialize(0) for constant-radius.
- Set DefaultRadius via property assignment.
- Select an edge of the box.
- Call CreateFeature(data).
- Report whether a Fillet feature appeared in the tree.

If late binding can't pass the data object back as an Arg, this spike
will report the failure and we fall back to either:
  a. The deprecated FeatureFillet3 single-call form (works empirically)
  b. Don't ship fillets via the bridge yet; emit a VBA fragment instead

Usage:
    python spikes/phase0/spike_p_fillet_pipeline.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_CONST_RADIUS_FILLET = 0  # swSimpleFilletType_e.swConstRadiusFillet


def _create_box(doc, side_mm: float, thick_mm: float) -> None:
    """Sketch a center rectangle on Front Plane and extrude it."""
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        SW_END_COND_BLIND, 0, thick_mm / 1000, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True,
        SW_START_SKETCH_PLANE, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("box extrude returned None")
    feat.Name = "SK_Box_Extrude"


def _probe_swFmFillet_value(fm) -> int | None:
    """The swFm* enum int values are not in the decompiled CHM for this
    SW build. Probe a small window of values to find which one returns
    a usable simple-fillet data object."""
    # swFm* is alphabetical so somewhere in 0..50 most likely
    for v in range(0, 60):
        try:
            data = fm.CreateDefinition(v)
            if data is None:
                continue
            # Quick check: does it have Initialize? Only ISimpleFilletFeatureData2 does.
            # We can't probe via hasattr (late-binding side-effect risk),
            # so try the actual call and trap the failure
            try:
                ok = data.Initialize(SW_CONST_RADIUS_FILLET)
                if ok:
                    print(f"  candidate v={v}: Initialize(0) -> {ok}")
                    return v
            except Exception as e:
                # That data object is for a different feature type; skip
                pass
        except Exception:
            continue
    return None


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("could not create blank doc")
        return 2

    print("== Spike P: ISimpleFilletFeatureData2 pipeline ==")
    print(f"  doc: {doc.GetTitle}")

    try:
        # Build a box
        _create_box(doc, side_mm=20.0, thick_mm=10.0)
        print(f"  feature count after box: {doc.GetFeatureCount}")

        fm = doc.FeatureManager

        # Probe swFmFillet value
        print("  probing swFmFillet int value (0..59)...")
        fillet_type_id = _probe_swFmFillet_value(fm)
        if fillet_type_id is None:
            print("  ! could not find a CreateDefinition(int) that yields a")
            print("    data object accepting Initialize(swConstRadiusFillet).")
            print("    pipeline NOT viable via late binding.")
            return 3
        print(f"  swFmFillet candidate int = {fillet_type_id}")

        # Now do the real call with the found value
        data = fm.CreateDefinition(fillet_type_id)
        ok = data.Initialize(SW_CONST_RADIUS_FILLET)
        print(f"  Initialize(0) -> {ok}")

        # Set a default radius
        try:
            data.DefaultRadius = 0.002  # 2 mm
            print(f"  DefaultRadius set; readback = {data.DefaultRadius}")
        except Exception as e:
            print(f"  ! DefaultRadius set failed: {e!r}")

        # Select an edge of the box. SelectByID with "EDGE" requires a point
        # on the edge in part coords. Box on Front Plane (XY): edges of the
        # top face lie at z=0.01. Take a midpoint of the +X edge: (0.01, 0, 0.01)
        # is on the +X edge midpoint.
        doc.ClearSelection2(True)
        # Try a few cardinal edge midpoints
        edge_candidates = [
            (0.01, 0.0, 0.01),    # +X edge of top
            (-0.01, 0.0, 0.01),   # -X edge of top
            (0.0, 0.01, 0.01),    # +Y edge of top
            (0.0, -0.01, 0.01),   # -Y edge of top
        ]
        n_selected = 0
        for x, y, z in edge_candidates:
            doc.ClearSelection2(True)
            if doc.SelectByID("", "EDGE", x, y, z):
                # Re-select with append for the fillet; CreateFeature uses
                # the current selection set
                n_selected += 1
                doc.SelectByID("", "EDGE", x, y, z)
                # break after first hit (single-edge fillet keeps the spike simple)
                break
        if n_selected == 0:
            print("  ! could not select any edge of the box; cannot proceed")
            return 4
        print(f"  selected {n_selected} edge(s)")

        # CreateFeature
        try:
            feat = fm.CreateFeature(data)
            print(f"  CreateFeature -> {feat!r}")
            if feat is None:
                print("  ! CreateFeature returned None")
                return 5
            feat.Name = "Fillet_FromSpike"
            print(f"  Fillet feature created: {feat.Name}")
        except Exception as e:
            print(f"  ! CreateFeature raised: {e!r}")
            traceback.print_exc()
            return 6

        print(f"  feature count after fillet: {doc.GetFeatureCount}")
        print("== Spike P GREEN: pipeline works via late binding ==")
        return 0

    except Exception as e:
        print(f"! spike P exception: {e!r}")
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
