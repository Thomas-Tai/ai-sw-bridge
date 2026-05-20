"""Spike ZB: VBA injector for flipping D2.DrivenState from external Python.

THE PREMISE (2026-05-20 follow-up diagnostic):
  Z9 + Z8-retry empirically proved that EVERY typelib-only-access SW API
  method is unreachable from late-bound pywin32 on SW 2024 SP1:
    - sw.SendKeys / SendKeystrokes (Z2)
    - dim.DrivenState setter (Z7 Route 1, Z9)
    - sm.MakeSelectedDriving / MakeSelectedDriven (Z9 Probe B)
    - sm.SketchAddConstraints (Z8-retry)
  Even after gencache.EnsureModule compiles the stubs (Z9 Probe C, stubs
  exist on disk), Dispatch() does not auto-upgrade. The IDispatch path
  SW exposes externally simply does not surface these methods.

  But SolidWorks' INTERNAL VBA engine has full early-bound access to the
  same typelib registry. VBA code running in-process via swApp.RunMacro
  bypasses the external-COM blindspot entirely. The architectural question
  this spike tests: can a VBA macro that flips dim.DrivenState succeed
  where external pywin32 cannot?

  If yes -> production fix is: keep CreateCenterRectangle, add a post-D2
  hook in _apply_deferred_dims that emits+runs this macro for any D2 on
  a rectangle sketch.

  If no -> deferred-dim rect limitation is genuinely structural. Ship
  the existing CLI WARN + recommend --no-dim, full stop.

NOT TESTED HERE (separate question):
  Whether SW's VBA engine can also see SketchAddConstraints. The diagnostic
  proposes a surgical use (only DrivenState flip, not relation construction),
  so we mirror that scope. If DrivenState injection works, we've solved the
  problem without needing the relation API.

PATCH NOTES vs the 2026-05-20 snippet:
  1. Macro Sub signature changed to the conventional in-process form:
       Sub main(SwApp As SldWorks.SldWorks)
     The snippet's `CreateObject("SldWorks.Application")` form may or may
     not return the running singleton; the parameter form is the
     documented SW macro recorder pattern and is guaranteed to receive
     the live swApp reference.
  2. Programmatic success signal is Parameter(D2).SystemValue * 1000 vs
     7.0 (the bound TEST_VAR). Z6 proved eq.Value(idx) is unreliable.
  3. Toggle force-True with try/finally restore (per Z8-retry's
     confirmed-working pattern).
  4. Stale-macro cleanup: remove any prior force_driving.swb before
     emitting a fresh one, to rule out RunMacro reading a cached file.

  ARTIFACT FILE EXTENSION: SW's macro engine accepts .swb (SolidWorks
  Basic plaintext) when run via RunMacro. The diagnostic used .swb; we
  keep it.

Run from venv-freshtest with SW open. Expected popup ticks: 2 (D1, D2
on the reproduction part).
"""
import os
import sys
import tempfile
import time
import pythoncom
import win32com.client


VBA_TEMPLATE_PARAM = """' Auto-emitted by spike_zb_vba_injector.py (param form)
' SW macro recorder's canonical signature: swApp passed as Sub argument.

Sub main(SwApp As SldWorks.SldWorks)
    Dim swModel As ModelDoc2
    Dim swDispDim As DisplayDimension
    Dim boolstatus As Boolean

    Set swModel = SwApp.ActiveDoc
    If swModel Is Nothing Then
        Exit Sub
    End If

    boolstatus = swModel.Extension.SelectByID2("__DIM_NAME__", "DIMENSION", _
        0, 0, 0, False, 0, Nothing, 0)

    If Not boolstatus Then
        Exit Sub
    End If

    Set swDispDim = swModel.SelectionManager.GetSelectedObject6(1, -1)

    If Not swDispDim Is Nothing Then
        swDispDim.DrivenState = 1
    End If

    swModel.ClearSelection2 True
End Sub
"""

VBA_TEMPLATE_CREATEOBJECT = """' Auto-emitted by spike_zb_vba_injector.py (CreateObject form)
' Per 2026-05-20 diagnostic original snippet. Zero-arg Sub.

Dim swApp As Object
Dim swModel As Object
Dim swDispDim As Object
Dim boolstatus As Boolean

Sub main()
    Set swApp = CreateObject("SldWorks.Application")
    Set swModel = swApp.ActiveDoc
    If swModel Is Nothing Then
        Exit Sub
    End If

    boolstatus = swModel.Extension.SelectByID2("__DIM_NAME__", "DIMENSION", _
        0, 0, 0, False, 0, Nothing, 0)

    If Not boolstatus Then
        Exit Sub
    End If

    Set swDispDim = swModel.SelectionManager.GetSelectedObject6(1, -1)

    If Not swDispDim Is Nothing Then
        swDispDim.DrivenState = 1
    End If

    swModel.ClearSelection2 True
End Sub
"""

VBA_TEMPLATE = VBA_TEMPLATE_PARAM


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def add_edge_dim_with_reopen(doc, sketch_name, edge_xyz, leader_xyz, label):
    """Same Z9-proven pattern. Returns the dim or None on segment-select failure."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", *edge_xyz)
    print(f"    [{label}] segment select {edge_xyz} -> {ok}")
    if not ok:
        sm.InsertSketch(True)
        return None
    dim = doc.AddDimension2(*leader_xyz)
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}")
    sm.InsertSketch(True)
    return dim


def reproduce_driven_d2(sw):
    """Build the Z5-equivalent failing case: CenterRectangle + close +
    reopen + D1 + close + reopen + D2 = driven D2."""
    print()
    print("=== Phase 1: reproduce driven-D2 ===")
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None, None

    sketch_name = "SK_ZB"
    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")

    add_edge_dim_with_reopen(doc, sketch_name, (0, 0.010, 0), (0, 0.015, 0), "D1")
    dim2 = add_edge_dim_with_reopen(doc, sketch_name, (-0.010, 0, 0), (-0.015, 0, 0), "D2")
    if dim2 is None:
        print("  ! D2 AddDimension2 failed; cannot run injector")
        return None, None

    # Pre-injection baseline: confirm D2 is driven
    eq = doc.GetEquationMgr
    eq.Add2(-1, '"ZB_PREINJECT_VAR" = 5.0', True)
    pre_idx = eq.Add2(-1, f'"D2@{sketch_name}" = "ZB_PREINJECT_VAR"', True)
    print(f"  pre-injection binding Add2 -> idx={pre_idx}")
    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR: {type(e).__name__}: {e}")
    p2 = doc.Parameter(f"D2@{sketch_name}")
    pre_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(f"  pre-injection Parameter(D2@{sketch_name}) = {pre_val!r} mm "
          f"(20.0=placeholder, 5.0=binding-drives)")

    return doc, sketch_name


def emit_macro(dim_name, template=VBA_TEMPLATE, suffix=".swb"):
    """Write a fresh macro to %TEMP%. Remove any stale copy first to rule
    out RunMacro reading a cached previous file."""
    print()
    print(f"=== Phase 2: emit VBA macro ({suffix}) ===")
    temp_dir = tempfile.gettempdir()
    macro_path = os.path.join(temp_dir, f"force_driving{suffix}")
    if os.path.exists(macro_path):
        try:
            os.remove(macro_path)
            print(f"  removed stale macro at {macro_path}")
        except OSError as e:
            print(f"  could not remove stale macro: {e}")

    macro_text = template.replace("__DIM_NAME__", dim_name)
    with open(macro_path, "w", encoding="ascii") as f:
        f.write(macro_text)
    print(f"  wrote macro ({len(macro_text)} bytes) to {macro_path}")
    print(f"  targets dim: {dim_name!r}")
    return macro_path


def run_macro(sw, macro_path):
    """Execute the macro inside SW's VBA engine. RunMacro (not RunMacro2)
    -- the latter has an OUT Error param that triggers Type mismatch on
    pywin32 late-binding (same class as AddSpecificDimension)."""
    print()
    print("=== Phase 3: inject macro into SW's VBA engine ===")
    # RunMacro signature: (MacroPathname, ModuleName, ProcedureName) -> Boolean
    # ModuleName for .swb files is conventionally the filename stem.
    module = os.path.splitext(os.path.basename(macro_path))[0]
    print(f"  swApp.RunMacro({macro_path!r}, {module!r}, 'main')")

    try:
        t0 = time.perf_counter()
        result = sw.RunMacro(macro_path, module, "main")
        dt = (time.perf_counter() - t0) * 1000
        print(f"  RunMacro returned: {result!r} (in {dt:.1f}ms)")
        return bool(result)
    except Exception as e:
        print(f"  RunMacro ERR: {type(e).__name__}: {e}")
        # If the parameter-form Sub signature was wrong, try the
        # zero-arg form as a fallback. (CreateObject form per original
        # diagnostic snippet.)
        print(f"  Note: if 'wrong number of arguments', the Sub signature")
        print(f"        convention may need to be the zero-arg CreateObject form.")
        return False


def verify_injection(doc, sketch_name):
    """Bind D2 to a NEW test var, force rebuild, check Parameter readback.
    If DrivenState was successfully flipped to 1, the binding should now
    drive D2 (readback ~7.0 mm). If injection failed, D2 stays at
    placeholder/pre-injection value."""
    print()
    print("=== Phase 4: verify D2 is now driving ===")
    eq = doc.GetEquationMgr
    eq.Add2(-1, '"ZB_POSTINJECT_VAR" = 7.0', True)
    formula = f'"D2@{sketch_name}" = "ZB_POSTINJECT_VAR"'
    bind_idx = eq.Add2(-1, formula, True)
    print(f"  post-injection binding Add2 -> idx={bind_idx}")

    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR: {type(e).__name__}: {e}")

    p2 = doc.Parameter(f"D2@{sketch_name}")
    post_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(f"  post-injection Parameter(D2@{sketch_name}) = {post_val!r} mm")

    drives = post_val is not None and abs(post_val - 7.0) < 0.01
    print()
    if drives:
        print("  >>> INJECTION SUCCESS: D2 tracks the binding (~7.0 mm).")
        print("  >>> VBA reached DrivenState even though pywin32 cannot.")
        print("  >>> Production fix path is viable.")
    else:
        print("  >>> INJECTION FAILED: D2 did not change with new binding.")
        print("  >>> VBA either could not flip DrivenState, or the equation")
        print("  >>> went red again on rebuild (visual check needed).")
        print(f"  >>> Expected 7.0 mm, got {post_val!r} mm.")

    return {"drives": drives, "post_val_mm": post_val}


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    # Force-True the dim-popup toggle for the reproduction phase, restore on exit.
    # Per Z8-retry: this pattern is confirmed-working.
    SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8
    original_toggle = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
    print(f"  original swInputDimValOnCreate = {original_toggle}")
    if original_toggle is not True:
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, True)
        readback = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
        print(f"  forced to True; readback = {readback}")

    try:
        doc, sketch_name = reproduce_driven_d2(sw)
        if doc is None:
            print()
            print(">>> Could not reproduce the failing case. Spike aborted.")
            return

        dim_name = f"D2@{sketch_name}"

        # Try (1) param-form .swb, (2) CreateObject-form .swb, (3) param-form .swp.
        # RunMacro silently returns False on signature mismatch; we don't know
        # which form this build expects, so try them in order.
        attempts = [
            ("param form / .swb",        VBA_TEMPLATE_PARAM,        ".swb"),
            ("CreateObject form / .swb", VBA_TEMPLATE_CREATEOBJECT, ".swb"),
            ("param form / .swp",        VBA_TEMPLATE_PARAM,        ".swp"),
        ]
        macro_ok = False
        for label, template, suffix in attempts:
            print()
            print(f"--- attempting: {label} ---")
            macro_path = emit_macro(dim_name, template=template, suffix=suffix)
            macro_ok = run_macro(sw, macro_path)
            if macro_ok:
                print(f"--- {label} accepted ---")
                break

        if not macro_ok:
            print()
            print(">>> All 3 macro forms returned False from RunMacro.")
            print(">>> Possibilities: (a) RunMacro requires compiled .swp not .swb;")
            print(">>>                (b) Sub signature uses yet another convention;")
            print(">>>                (c) the macro engine isn't licensed/enabled on this SW seat.")
            print(">>> Check whether SW's VBA editor opened a window with the macro loaded.")
            return

        result = verify_injection(doc, sketch_name)

        print()
        print("=" * 60)
        print("=== Spike ZB summary ===")
        print(f"  RunMacro succeeded:        {macro_ok}")
        print(f"  D2 drives post-injection:  {result['drives']}")
        print(f"  D2 readback:               {result['post_val_mm']!r} mm")
        print()
        print(">>> Visual check (the only definitive signal for cosmetic state):")
        print(f"    Open Equation Manager. Is 'D2@{sketch_name} = \"ZB_POSTINJECT_VAR\"' red?")
        print( "    Open the sketch. Is D2 black (driving) or grey (driven)?")
        print()
        print(">>> Decision matrix:")
        print("    Drives=True + EqMgr clean  -> production fix path viable;")
        print("                                  emit+run macro per rectangle D2 in builder")
        print("    Drives=True + EqMgr red    -> impossible state; investigate")
        print("    Drives=False + macro ran   -> VBA injection blocked at SW solver level;")
        print("                                  the demotion is enforced post-property-write")
        print("    Drives=False + macro errored -> Sub signature wrong, try CreateObject form")
    finally:
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, original_toggle)
        final = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
        print()
        print(f"  restored swInputDimValOnCreate to {original_toggle}; readback = {final}")


if __name__ == "__main__":
    main()
