"""Phase 0 verify: did Cut_BeltGripGroove actually cut a groove?

Compares observed body face count and volume to the expected post-groove value.
Without the groove: 3 faces (top cap, bottom cap, cylinder side) — but with
the centerbore + bearing pockets the count is higher; we don't predict the
exact baseline. We compare WITH-GROOVE vs WITHOUT-GROOVE by computing the
delta if we know the baseline; otherwise we just report face count + volume.

Expected groove dimensions: 1mm radial depth × 5mm Z-width × 360°.
Predicted volume removal:
  outer_ring (R=11.5 to 12.5) × height 5
  = pi * (12.5^2 - 11.5^2) * 5
  = pi * 24 * 5
  = 376.99 mm^3

Cylinder Ø25 x 80 (no groove, no holes) volume = pi * 12.5^2 * 80 = 39269.91 mm^3
"""

from __future__ import annotations

import math

import pythoncom  # noqa: F401
import win32com.client


def main() -> int:
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    doc = sw.ActiveDoc
    if doc is None:
        print("no active doc")
        return 1
    print(f"active doc: {doc.GetTitle}")

    # Walk features, print names + types + Suppressed status
    print("\nFeatures (in tree order):")
    f = doc.FirstFeature
    while f is not None:
        try:
            name = f.Name
        except Exception:
            name = "?"
        try:
            ftype = f.GetTypeName2
        except Exception:
            ftype = "?"
        suppressed = "?"
        try:
            suppressed = f.IsSuppressed
        except Exception:
            pass
        print(f"  {name}  type={ftype}  suppressed={suppressed}")
        try:
            f = f.GetNextFeature
        except Exception:
            break

    # Mass properties via doc.Extension.CreateMassProperty
    print("\nMass properties:")
    try:
        mp = doc.Extension.CreateMassProperty
        if mp is not None:
            # m^3 → mm^3
            vol = mp.Volume * 1e9
            print(f"  Volume: {vol:.2f} mm^3")
            # Surface area: m^2 → mm^2
            sa = mp.SurfaceArea * 1e6
            print(f"  Surface area: {sa:.2f} mm^2")
        else:
            print("  CreateMassProperty None")
    except Exception as e:
        print(f"  mass error: {e}")

    # Compare against predicted volumes
    cyl = math.pi * 12.5**2 * 80
    centerbore = math.pi * 4**2 * 80  # Ø8 bore through-all
    bearing_pocket = math.pi * 11**2 * 7  # Ø22 pocket, 7 deep, x2
    groove = math.pi * (12.5**2 - 11.5**2) * 5
    expected_no_groove = cyl - centerbore - 2 * bearing_pocket
    expected_with_groove = expected_no_groove - groove
    print(f"\nPredicted volumes (assuming locals defaults):")
    print(f"  Cylinder alone: {cyl:.2f} mm^3")
    print(f"  Cyl - centerbore: {cyl - centerbore:.2f} mm^3")
    print(f"  Cyl - centerbore - 2 pockets: {expected_no_groove:.2f} mm^3")
    print(f"  Cyl - centerbore - 2 pockets - groove: {expected_with_groove:.2f} mm^3")
    print(f"  Groove alone (target delta): {groove:.2f} mm^3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
