"""Probe the current active doc's Equation Manager to dump every equation
and report which dim Parameters resolve / are None.

Use case: after a --deferred-dim build leaves SW in a state where one
equation is red in the UI, this script reports the equation text exactly
as SW sees it and tells us whether the Parameter the equation references
actually exists.
"""

import pythoncom
import win32com.client


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    doc = sw.ActiveDoc
    if doc is None:
        print("! No ActiveDoc. Open the test part first.")
        return

    print(f"ActiveDoc title: {doc.GetTitle if hasattr(doc, 'GetTitle') else '?'}")
    print()

    # ---- Dump every EquationManager entry ----
    print("=== Equation Manager entries ===")
    eq = doc.GetEquationMgr
    count = eq.GetCount
    print(f"  total entries: {count}")
    for i in range(count):
        try:
            text = eq.Equation(i)
        except Exception as e:
            text = f"<ERR {e!r}>"
        try:
            val = eq.Value(i)
        except Exception as e:
            val = f"<ERR {e!r}>"
        try:
            stat = eq.Status(i)
        except Exception:
            stat = "?"
        try:
            globvar = eq.GlobalVariable(i)
        except Exception:
            globvar = "?"
        # Only show interesting entries: dim equations (index>=78), or non-globalvar
        # entries (suspicious in this part), or anything not resolving to a number.
        is_dim_eq = "@" in text if isinstance(text, str) else False
        if is_dim_eq or i >= 78:
            print(f"  [{i:3d}] val={val!r}  status={stat!r}  isGlobal={globvar!r}")
            print(f"        text :: {text}")
    print()

    # ---- For each dim used in S1b MMP, see if Parameter resolves ----
    print("=== Parameter resolution for known MMP dims ===")
    for pname in [
        "D1@SK_PlateSlab",
        "D2@SK_PlateSlab",
        "D1@Extrude_Plate",
        "D1@SK_CouplerHole",
        "D1@SK_FlangeRecess",
        "D1@SK_MotorHoles",
        "D2@SK_MotorHoles",
        "D1@SK_FrameHoles",
        "D2@SK_FrameHoles",
    ]:
        p = doc.Parameter(pname)
        if p is None:
            print(
                f"  Parameter({pname!r}) = None  [RED -- dim does NOT exist on this name]"
            )
        else:
            try:
                val = p.SystemValue * 1000
                print(f"  Parameter({pname!r}) = {val:.3f} mm")
            except Exception as e:
                print(f"  Parameter({pname!r}) SystemValue ERR: {e!r}")


if __name__ == "__main__":
    main()
