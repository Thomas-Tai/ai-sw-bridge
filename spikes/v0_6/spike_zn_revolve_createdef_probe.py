"""Spike ZN: probe CreateDefinition(N) for IRevolveFeatureData2.

Per Spike P precedent (swFmFillet=1 found by probing 0..59):
  - CHM enum lists swFmRevolution but no integer value.
  - Probe CreateDefinition with int 0..99 and check return.
  - For each non-None return, dispatch on its methods to identify which
    feature-data type we got. IRevolveFeatureData2 is identified by
    presence of `IsBossFeature` / `IsThinFeature` methods.

Once we find swFmRevolution's int, attempt to:
  1. Create a definition
  2. Set its properties (especially the boss/thin/cut flags -- though
     IsBossFeature/IsThinFeature appear to be read-only methods, the
     Type property may be settable)
  3. Set up selections (sketch mark=0, axis mark=16) just like the
     FeatureRevolve2 direct call required
  4. Call CreateFeature(data) -- the SW 2020+ canonical pattern that
     worked for fillet
"""

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0


def build_base_cylinder(doc):
    sm = doc.SketchManager
    fm = doc.FeatureManager
    doc.SelectByID("Top Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.0125, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Base"
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Base", "SKETCH", 0, 0, 0)
    base = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.080,
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
        0,
        0.0,
        False,
    )
    base.Name = "EX_Base"
    return base


def is_revolve_data(obj):
    """Detect IRevolveFeatureData2 by probing for distinctive members."""
    try:
        # Both should exist and not raise on attribute access
        _ = obj.IsBossFeature
        _ = obj.IsThinFeature
        return True
    except Exception:
        return False


def describe_data(obj):
    """List members that respond to attribute access."""
    sentinels = [
        "IsBossFeature",
        "IsThinFeature",
        "Type",
        "Merge",
        "ReverseDirection",
        "ThinWallType",
        "Axis",
        "FeatureScope",
        "AutoSelect",
        "DefaultRadius",  # would indicate fillet, not revolve
        "Angle",  # could be chamfer
    ]
    out = []
    for name in sentinels:
        try:
            val = getattr(obj, name)
            out.append(f"{name}={val!r}")
        except Exception as e:
            pass
    return ", ".join(out) or "<no recognized members>"


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    print("Building base cylinder...")
    build_base_cylinder(doc)
    fm = doc.FeatureManager

    revolve_id = None
    print("\nProbing CreateDefinition(0..99) for IRevolveFeatureData2...")
    for i in range(100):
        try:
            d = fm.CreateDefinition(i)
        except Exception:
            d = None
        if d is None:
            continue
        if is_revolve_data(d):
            print(f"  id {i}: REVOLVE -- {describe_data(d)}")
            if revolve_id is None:
                revolve_id = i
        else:
            # Brief id+type for other returns; comment out if too noisy
            try:
                # Cheap shape sniff
                if hasattr(d, "DefaultRadius"):
                    print(f"  id {i}: fillet-shaped data")
                elif hasattr(d, "Width"):
                    print(f"  id {i}: chamfer-ish data")
            except Exception:
                pass

    if revolve_id is None:
        print("\nNo CreateDefinition(N) returned IRevolveFeatureData2 in 0..99.")
        return

    print(f"\nswFmRevolution = {revolve_id}")
    # We have at least one. If multiple revolve-shaped ones appeared,
    # the lowest id is likely the right one. The handler can be smarter
    # later if multiple variants exist.


if __name__ == "__main__":
    main()
