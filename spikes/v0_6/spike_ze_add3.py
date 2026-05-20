"""Spike ZE: test whether EquationMgr.Add3 with swAllConfiguration bypasses
the demotion that EquationMgr.Add2 triggers on rect-D2.

PREMISE:
  Every prior binding attempt used eq.Add2(idx, formula, solveOrder).
  Z6/Z9/ZD proved Add2 binds the equation cleanly (idx >= 0) but the
  solver demotes D2 to driven at rebuild time -- the equation has no
  effect on geometry.

  Add3 is the newer EquationMgr method with a 5-arg signature:
    Add3(Index, Equation, SolveOrder, ConfigOption, ConfigNames)
  taking a swInConfigurationOpts_e value. The hypothesis (from 2026-05-20
  follow-up info): if the binding is written with swAllConfiguration
  (=2) instead of the implicit default Add2 uses, the solver may treat
  it as a model-wide constraint rather than a per-config over-constraint,
  and the demotion may not fire.

  Probability of success: LOW per prior evidence (ZD showed the demotion
  happens at ForceRebuild3, not at the binding-write step). But the
  test is cheap and the Add3/Add2 distinction is the ONE element of the
  2026-05-20 info that was genuinely untested.

WHAT THIS DOES NOT TEST:
  - Add2 with explicit configuration via a separate call (no such API).
  - SetEquationAndConfigurationOption on an Add2-written binding -- if
    Add3 fails, also try modifying the binding via this method, which
    has a different code path again.

ENUMERATION:
  swInConfigurationOpts_e:
    1 = swThisConfiguration (default Add2 behavior, untested vs Add3 here)
    2 = swAllConfiguration
    3 = swSpecifyConfiguration

Three cases:
  ZE-a (baseline Add3): same as ZD case_c but using Add3 with
                        swAllConfiguration instead of Add2.
  ZE-b (Add3 + ThisConfig): Add3 with swThisConfiguration = 1, mimicking
                            Add2's default to isolate whether the
                            ConfigOption arg itself matters.
  ZE-c (SetEquationAndConfigurationOption retrofit): write the binding
                                                     with Add2 as before,
                                                     then re-apply via
                                                     SetEquationAndConfigurationOption.

Run from venv-freshtest with SW open. Expected popup ticks: 6 (2 per case).
"""

import os
import pythoncom
import win32com.client


# swInConfigurationOpts_e
SW_CONFIG_THIS = 1
SW_CONFIG_ALL = 2
SW_CONFIG_SPECIFY = 3


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def build_rect_with_inline_dims(doc, sketch_name):
    """Inline-dim path from ZD: dims added in original sketch session via
    captured segment pointers."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)

    segs = sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    perimeter = [s for s in segs if not s.ConstructionGeometry]
    horiz = None
    vert = None
    for s in perimeter:
        sp, ep = s.GetStartPoint2, s.GetEndPoint2
        if sp is None or ep is None:
            continue
        x1, y1, x2, y2 = sp.X, sp.Y, ep.X, ep.Y
        if abs(y1 - y2) < 1e-9:
            if horiz is None or y1 > 0:
                horiz = s
        elif abs(x1 - x2) < 1e-9:
            if vert is None or x1 < 0:
                vert = s

    vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    if horiz is None or vert is None:
        sm.InsertSketch(True)
        return None

    doc.ClearSelection2(True)
    horiz.Select4(False, vt_disp_none)
    d1 = doc.AddDimension2(0, 0.015, 0)
    print(f"  [D1 inline] AddDimension2 -> {d1 is not None}")

    doc.ClearSelection2(True)
    vert.Select4(False, vt_disp_none)
    d2 = doc.AddDimension2(-0.015, 0, 0)
    print(f"  [D2 inline] AddDimension2 -> {d2 is not None}")

    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    return feat


def case_a_add3_all_config(sw):
    """Add3 with swAllConfiguration. The headline case."""
    print()
    print("=== ZE-a: Add3 + swAllConfiguration ===")
    doc = make_part(sw)
    if doc is None:
        return None

    sketch_name = "SK_ZEa"
    feat = build_rect_with_inline_dims(doc, sketch_name)
    if feat is None:
        return None

    print(f"  ForceRebuild3 before Add3 -> {doc.ForceRebuild3(True)}")

    eq = doc.GetEquationMgr
    vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    # Probe Add3 reachability before relying on it
    try:
        meth = getattr(eq, "Add3")
        print(f"  eq.Add3 reachable: {meth!r}")
    except AttributeError as e:
        print(f"  eq.Add3 UNREACHABLE: {e}")
        return {"add3_reachable": False, "drives": False, "d2_mm": None}

    # Add3 signature: (Index, Equation, SolveOrder, ConfigOption, ConfigNames)
    # ConfigNames is unused when ConfigOption is swAllConfiguration; pass empty array.
    try:
        idx_w = eq.Add3(-1, '"ZEA_W" = 7.0', True, SW_CONFIG_ALL, vt_disp_none)
        print(f"  Add3('ZEA_W = 7.0', swAllConfiguration) -> idx={idx_w}")
        idx_h = eq.Add3(-1, '"ZEA_H" = 9.0', True, SW_CONFIG_ALL, vt_disp_none)
        print(f"  Add3('ZEA_H = 9.0', swAllConfiguration) -> idx={idx_h}")
        idx_d1 = eq.Add3(
            -1, f'"D1@{sketch_name}" = "ZEA_W"', True, SW_CONFIG_ALL, vt_disp_none
        )
        print(f"  Add3('D1 = ZEA_W', swAllConfiguration) -> idx={idx_d1}")
        idx_d2 = eq.Add3(
            -1, f'"D2@{sketch_name}" = "ZEA_H"', True, SW_CONFIG_ALL, vt_disp_none
        )
        print(f"  Add3('D2 = ZEA_H', swAllConfiguration) -> idx={idx_d2}")
    except Exception as e:
        print(f"  Add3 ERR: {type(e).__name__}: {e}")
        # Try without VT_DISPATCH for ConfigNames
        try:
            idx_d2 = eq.Add3(
                -1, f'"D2@{sketch_name}" = "ZEA_H"', True, SW_CONFIG_ALL, None
            )
            print(f"  Add3 with raw None for ConfigNames -> idx={idx_d2}")
        except Exception as e2:
            print(f"  Add3 with None ERR: {type(e2).__name__}: {e2}")
            return {
                "add3_reachable": True,
                "drives": False,
                "d2_mm": None,
                "error": str(e),
            }

    print(f"  ForceRebuild3 post-Add3 -> {doc.ForceRebuild3(True)}")

    p2 = doc.Parameter(f"D2@{sketch_name}")
    val = (p2.SystemValue * 1000) if p2 is not None else None
    drives = val is not None and abs(val - 9.0) < 0.01
    print(f"  Parameter(D2@{sketch_name}) = {val!r} mm (expected 9.0, drives={drives})")

    return {"add3_reachable": True, "drives": drives, "d2_mm": val}


def case_b_add3_this_config(sw):
    """Add3 with swThisConfiguration -- isolates whether the ConfigOption
    value matters (vs Add2's implicit default which is swThisConfiguration)."""
    print()
    print("=== ZE-b: Add3 + swThisConfiguration ===")
    doc = make_part(sw)
    if doc is None:
        return None

    sketch_name = "SK_ZEb"
    feat = build_rect_with_inline_dims(doc, sketch_name)
    if feat is None:
        return None

    print(f"  ForceRebuild3 before Add3 -> {doc.ForceRebuild3(True)}")

    eq = doc.GetEquationMgr
    vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    try:
        eq.Add3(-1, '"ZEB_W" = 7.0', True, SW_CONFIG_THIS, vt_disp_none)
        eq.Add3(-1, '"ZEB_H" = 9.0', True, SW_CONFIG_THIS, vt_disp_none)
        idx_d1 = eq.Add3(
            -1, f'"D1@{sketch_name}" = "ZEB_W"', True, SW_CONFIG_THIS, vt_disp_none
        )
        idx_d2 = eq.Add3(
            -1, f'"D2@{sketch_name}" = "ZEB_H"', True, SW_CONFIG_THIS, vt_disp_none
        )
        print(f"  D1 bind idx={idx_d1}, D2 bind idx={idx_d2}")
    except Exception as e:
        print(f"  Add3 ERR: {type(e).__name__}: {e}")
        return None

    print(f"  ForceRebuild3 post-Add3 -> {doc.ForceRebuild3(True)}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    val = (p2.SystemValue * 1000) if p2 is not None else None
    drives = val is not None and abs(val - 9.0) < 0.01
    print(f"  Parameter(D2@{sketch_name}) = {val!r} mm (expected 9.0, drives={drives})")
    return {"drives": drives, "d2_mm": val}


def case_c_set_equation_retrofit(sw):
    """Write binding with Add2 (proven path), then call
    SetEquationAndConfigurationOption to potentially rewrite it via the
    other code path. If SetEquationAndConfigurationOption is reachable
    and changes the solver behavior, D2 may end up driving."""
    print()
    print("=== ZE-c: Add2 binding + SetEquationAndConfigurationOption retrofit ===")
    doc = make_part(sw)
    if doc is None:
        return None

    sketch_name = "SK_ZEc"
    feat = build_rect_with_inline_dims(doc, sketch_name)
    if feat is None:
        return None

    print(f"  ForceRebuild3 before Add2 -> {doc.ForceRebuild3(True)}")

    eq = doc.GetEquationMgr
    eq.Add2(-1, '"ZEC_W" = 7.0', True)
    eq.Add2(-1, '"ZEC_H" = 9.0', True)
    idx_d1 = eq.Add2(-1, f'"D1@{sketch_name}" = "ZEC_W"', True)
    idx_d2 = eq.Add2(-1, f'"D2@{sketch_name}" = "ZEC_H"', True)
    print(f"  Add2 D1 idx={idx_d1}, D2 idx={idx_d2}")

    # Probe SetEquationAndConfigurationOption reachability
    try:
        meth = getattr(eq, "SetEquationAndConfigurationOption")
        print(f"  eq.SetEquationAndConfigurationOption reachable: {meth!r}")
    except AttributeError as e:
        print(f"  eq.SetEquationAndConfigurationOption UNREACHABLE: {e}")
        return {"setequation_reachable": False, "drives": False, "d2_mm": None}

    # Try the call. Signature per SW API:
    #   SetEquationAndConfigurationOption(Index, Equation, ConfigOption, ConfigNames)
    try:
        r = eq.SetEquationAndConfigurationOption(
            idx_d2,
            f'"D2@{sketch_name}" = "ZEC_H"',
            SW_CONFIG_ALL,
            win32com.client.VARIANT(pythoncom.VT_DISPATCH, None),
        )
        print(
            f"  SetEquationAndConfigurationOption(idx={idx_d2}, swAllConfiguration) -> {r!r}"
        )
    except Exception as e:
        print(f"  SetEquationAndConfigurationOption ERR: {type(e).__name__}: {e}")
        return {
            "setequation_reachable": True,
            "drives": False,
            "d2_mm": None,
            "error": str(e),
        }

    print(f"  ForceRebuild3 post-SetEquation -> {doc.ForceRebuild3(True)}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    val = (p2.SystemValue * 1000) if p2 is not None else None
    drives = val is not None and abs(val - 9.0) < 0.01
    print(f"  Parameter(D2@{sketch_name}) = {val!r} mm (expected 9.0, drives={drives})")
    return {"setequation_reachable": True, "drives": drives, "d2_mm": val}


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    SW_PREF = 8
    original = sw.GetUserPreferenceToggle(SW_PREF)
    print(f"  original swInputDimValOnCreate = {original}")
    if original is not True:
        sw.SetUserPreferenceToggle(SW_PREF, True)
        print(f"  forced to True; readback = {sw.GetUserPreferenceToggle(SW_PREF)}")

    only = os.environ.get("ZE_ONLY")
    res_a = res_b = res_c = None
    try:
        if only in (None, "a", "A"):
            res_a = case_a_add3_all_config(sw)
        if only in (None, "b", "B"):
            res_b = case_b_add3_this_config(sw)
        if only in (None, "c", "C"):
            res_c = case_c_set_equation_retrofit(sw)
    finally:
        sw.SetUserPreferenceToggle(SW_PREF, original)
        print()
        print(f"  restored swInputDimValOnCreate to {original}")

    print()
    print("=" * 60)
    print("=== Spike ZE summary ===")
    for tag, res in (
        ("ZE-a Add3+AllConfig", res_a),
        ("ZE-b Add3+ThisConfig", res_b),
        ("ZE-c Add2+SetEqRetrofit", res_c),
    ):
        print(f"  {tag}: {res}")

    drives_anywhere = any(r and r.get("drives") for r in (res_a, res_b, res_c))
    print()
    if drives_anywhere:
        print(">>> ZE GREEN: at least one method drove D2 successfully.")
        print(
            ">>> Production fix path identified. Investigate which one and integrate."
        )
    else:
        print(
            ">>> ZE RED: neither Add3 nor SetEquationAndConfigurationOption drove D2."
        )
        print(
            ">>> Solution 2 (mutate-against-template) stands as the production answer."
        )


if __name__ == "__main__":
    main()
