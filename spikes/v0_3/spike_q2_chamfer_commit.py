"""
Spike Q2: find what commits/finalizes a chamfer after InsertFeatureChamfer.

User report: after running the chamfered_box example, the chamfer feature
is created in the tree but the geometry isn't visually chamfered until the
user clicks the green tick in the Chamfer PropertyManager. So
InsertFeatureChamfer returns a non-None IFeature, but the feature isn't
consumed/finalized.

This spike builds the same box+chamfer geometry then tries a series of
finalization moves and reports which (if any) make the chamfer
visually effective without manual confirmation. We probe in order
of increasing aggressiveness:

  T1: doc.EditRebuild3                              (force full rebuild)
  T2: doc.ClearSelection2(True)                     (clears any
                                                     pending selection)
  T3: doc.Extension.RunCommand(8211, "")            (8211 ~= swCommands_OkPM
                                                     per various forum
                                                     posts; not in our CHM)
  T4: doc.Extension.RunCommand(-1, "")              (-1 historically means
                                                     "close active PM")
  T5: combinations T1+T2

For each move we report:
  - feature_count_before, feature_count_after
  - chamfer.IsSuppressed   (CHM: IFeature::IsSuppressed)
  - bbox_change (via GetPartBox(True)) -- the smoking gun for whether
    the chamfer geometrically affected the part

If bbox didn't change after any move, none of them committed the chamfer
and we need a fundamentally different approach.

Usage:
    python spikes/v0_3/spike_q2_chamfer_commit.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_CHAMFER_EQUAL_DISTANCE = 16
SW_FCO_TANGENT_PROPAGATION = 4


def _create_box(doc, side_mm: float, thick_mm: float) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        thick_mm / 1000,
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
        raise RuntimeError("box extrude returned None")
    feat.Name = "SK_Box_Extrude"


def _select_top_edges(doc) -> int:
    """Select all 4 top edges of a 20x20x10 box on Front Plane.
    Top face at z=0.01; edges run along the perimeter at z=0.01.
    Each SelectByID call appends (no ClearSelection2 between)."""
    doc.ClearSelection2(True)
    edges = [
        (0.01, 0.0, 0.01),  # +X edge midpoint
        (-0.01, 0.0, 0.01),  # -X edge midpoint
        (0.0, 0.01, 0.01),  # +Y edge midpoint
        (0.0, -0.01, 0.01),  # -Y edge midpoint
    ]
    n = 0
    for x, y, z in edges:
        if doc.SelectByID("", "EDGE", x, y, z):
            n += 1
    return n


def _bbox(doc) -> tuple:
    """Part bbox as 6-tuple (xmin, ymin, zmin, xmax, ymax, zmax) in meters."""
    box = doc.GetPartBox(True)  # CDispatch / SAFEARRAY -> Python tuple
    # box can be None for empty parts
    return tuple(box) if box is not None else None


def _bbox_changed(b1: tuple, b2: tuple, tol_m: float = 1e-6) -> bool:
    if b1 is None or b2 is None:
        return b1 is not b2
    return any(abs(a - b) > tol_m for a, b in zip(b1, b2))


def _surface_area(doc) -> float:
    """Total surface area in m^2 -- a more sensitive signal than bbox.
    A chamfer ADDS faces (the chamfer flats) so SA goes up; the cut into
    the original faces also reduces their area. Net change is non-zero
    even when bbox is unchanged."""
    try:
        # IModelDoc2::GetMassProperties returns [CenterX, CenterY, CenterZ,
        # Volume, Area, Mass, Ixx, Iyy, Izz, Ixy, Ixz, Iyz, Status]
        # Index 4 = Area.
        mp = doc.Extension.GetMassProperties(1, 0)  # accuracy=1, status OUT
        if mp is None:
            return -1.0
        return float(mp[4])
    except Exception as e:
        print(f"    (GetMassProperties failed: {e!r})")
        return -1.0


def _feature_state(feat) -> dict:
    """Diagnostic state for an IFeature: suppressed, error code, etc."""
    out = {}
    for attr in ("Name", "GetTypeName"):
        try:
            out[attr] = getattr(feat, attr)
        except Exception as e:
            out[attr] = f"<{e!r}>"
    try:
        out["IsSuppressed"] = feat.IsSuppressed
    except Exception as e:
        out["IsSuppressed"] = f"<{e!r}>"
    return out


def _make_chamfer(doc, fm) -> object:
    """Insert a 1mm equal-distance chamfer on all 4 top edges."""
    n = _select_top_edges(doc)
    if n != 4:
        raise RuntimeError(f"expected 4 edges selected, got {n}")
    f = fm.InsertFeatureChamfer(
        SW_FCO_TANGENT_PROPAGATION,
        SW_CHAMFER_EQUAL_DISTANCE,
        0.0,
        0.0,
        0.001,  # 1mm
        0.0,
        0.0,
        0.0,
    )
    if f is None:
        raise RuntimeError("InsertFeatureChamfer returned None")
    return f


def _try_strategy(label: str, doc, fm, mover) -> None:
    """Build a fresh box, add a chamfer, run the mover, report bbox change."""
    print(f"\n=== Strategy: {label} ===")
    # Clean slate: new doc each strategy
    template = win32com.client.Dispatch(
        "SldWorks.Application"
    ).GetUserPreferenceStringValue(8)
    fresh = win32com.client.Dispatch("SldWorks.Application").NewDocument(
        template, 0, 0.0, 0.0
    )
    if fresh is None:
        print("  ! could not open fresh doc; skipping")
        return
    try:
        _create_box(fresh, 20.0, 10.0)
        sa_before = _surface_area(fresh)
        print(f"  surface area after box: {sa_before:.6e} m^2")

        fm_fresh = fresh.FeatureManager
        f = _make_chamfer(fresh, fm_fresh)
        sa_after_call = _surface_area(fresh)
        state_after_call = _feature_state(f)
        print(f"  surface area after InsertFeatureChamfer: {sa_after_call:.6e} m^2")
        print(f"  chamfer feature state: {state_after_call}")

        # Run the strategy
        try:
            mover(fresh)
            print(f"  strategy executed without exception")
        except Exception as e:
            print(f"  ! strategy raised: {e!r}")

        sa_after_strategy = _surface_area(fresh)
        state_after_strategy = _feature_state(f)
        print(f"  surface area after strategy:             {sa_after_strategy:.6e} m^2")
        print(f"  chamfer feature state: {state_after_strategy}")

        # For a 1mm equal-distance chamfer on 4 top edges of a 20x20x10 box:
        # box SA = 2*(20*20) + 4*(20*10) = 1600 mm^2 = 1.6e-3 m^2
        # chamfered: each 1mm chamfer cuts 1mm off each adjacent face along
        # a 20mm edge AND adds a 1mm*sqrt(2)*20mm flat. Net delta is small
        # but nonzero (we don't need to compute exactly; any nonzero delta
        # tells us the chamfer applied).
        delta_call = sa_after_call - sa_before
        delta_strategy = sa_after_strategy - sa_after_call
        delta_total = sa_after_strategy - sa_before
        print(f"  SA delta from chamfer call:    {delta_call:+.6e}")
        print(f"  SA delta from strategy:        {delta_strategy:+.6e}")
        print(f"  SA delta total:                {delta_total:+.6e}")
        if abs(delta_call) > 1e-9:
            print("  >>> chamfer was effective IMMEDIATELY")
        elif abs(delta_strategy) > 1e-9:
            print(f"  >>> '{label}' COMMITTED the chamfer")
        else:
            print(f"  >>> '{label}' did NOT commit the chamfer")
    finally:
        # Close the doc without saving
        try:
            sw = win32com.client.Dispatch("SldWorks.Application")
            sw.CloseDoc(fresh.GetTitle)
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print("== Spike Q2: probe what commits a chamfer ==")

    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2
    fm = doc.FeatureManager  # only used to keep signatures uniform

    strategies = [
        ("T0 baseline (do nothing after chamfer)", lambda d: None),
        ("T1 EditRebuild3", lambda d: getattr(d, "EditRebuild3")),
        ("T2 ClearSelection2(True)", lambda d: d.ClearSelection2(True)),
        ("T3 RunCommand(8211, '')", lambda d: d.Extension.RunCommand(8211, "")),
        ("T4 RunCommand(-1, '')", lambda d: d.Extension.RunCommand(-1, "")),
        (
            "T5 ClearSelection2 + EditRebuild3",
            lambda d: (d.ClearSelection2(True), getattr(d, "EditRebuild3")),
        ),
    ]

    # Close the initial doc we made; each strategy opens its own.
    try:
        sw.CloseDoc(doc.GetTitle)
    except Exception:
        pass

    for label, mover in strategies:
        try:
            _try_strategy(label, doc, fm, mover)
        except Exception as e:
            print(f"  ! exception during '{label}': {e!r}")
            traceback.print_exc()

    print("\n== Spike Q2 done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
