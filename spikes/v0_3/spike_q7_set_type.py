"""
Spike Q7: try alternative ways to SET .Type on IChamferFeatureData2,
given that data.Type = 1 raises AttributeError under pywin32 late-binding.

pywin32 dynamic dispatch can fail to set a property when it doesn't know
whether the setter is PROPPUT (assignment by value) or PROPPUTREF
(assignment by reference). Strategies:

  S1: standard `data.Type = value` -- confirmed RED in Q6
  S2: data._oleobj_.Invoke(dispid, lcid, DISPATCH_PROPERTYPUT, ..., value)
      via the underlying _oleobj_ handle and a lookup of the DISPID
  S3: win32com.client.DispatchWithEvents trick (unlikely to help)
  S4: Just don't set Type -- use the default (equal_distance) for
      distance_angle, and accept that ONLY equal_distance mode works
      via the CreateDefinition pipeline. Distance_angle would have to
      fall back to InsertFeatureChamfer (which has the PM-tab issue).
  S5: Some method-call variant we missed -- look for SetType or similar

Try S2 (DISPID-based PROPPUT) since that's the canonical pywin32 workaround.
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client
from win32com.client import constants


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_FM_CHAMFER = 1


def _create_box(doc, half_mm=10.0, depth_mm=10.0):
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    h = half_mm / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, h, h, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        SW_END_COND_BLIND, 0, depth_mm / 1000, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True,
        SW_START_SKETCH_PLANE, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("box extrude failed")


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    _create_box(doc)
    fm = doc.FeatureManager
    data = fm.CreateDefinition(SW_FM_CHAMFER)

    print("== Spike Q7: try alternative ways to set data.Type ==")
    print(f"  initial data.Type = {data.Type}")

    # Strategy S2: invoke via _oleobj_
    # Look up DISPID of 'Type' via IDispatch.GetIDsOfNames
    try:
        dispid = data._oleobj_.GetIDsOfNames(0, "Type")
        print(f"  DISPID('Type') = {dispid}")
    except Exception as e:
        print(f"  ! GetIDsOfNames failed: {e!r}")
        return 3

    # Invoke as PROPERTYPUT (4) with the value
    DISPATCH_PROPERTYPUT = 4
    target_value = 16  # swChamferEqualDistance
    try:
        # Invoke signature (pywin32): Invoke(dispid, lcid, wFlags, bResultWanted, *args)
        result = data._oleobj_.Invoke(dispid, 0, DISPATCH_PROPERTYPUT, False, target_value)
        print(f"  Invoke PROPERTYPUT Type={target_value} -> {result!r}")
        readback = data.Type
        print(f"  readback Type = {readback}")
        if readback == target_value:
            print("  >>> S2 GREEN: setting Type via raw Invoke works")
            # Try the other direction
            for v in (1, 2, 3, 16):
                data._oleobj_.Invoke(dispid, 0, DISPATCH_PROPERTYPUT, False, v)
                rb = data.Type
                print(f"    set Type={v}, readback={rb}")
            return 0
    except Exception as e:
        print(f"  ! S2 Invoke raised: {e!r}")
        traceback.print_exc()

    return 3


if __name__ == "__main__":
    sys.exit(main())
