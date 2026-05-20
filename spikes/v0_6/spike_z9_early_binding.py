"""Spike Z9: try CHEAP, LATE-BINDING-COMPATIBLE leads before committing to the
typelib-stub gamble.

The deferred-dim investigation report (docs/deferred_dim_investigation.md)
lists 5 open leads. Two of them are reachable from plain late-bound pywin32
and have never been tried; one is partially-tried (EnsureDispatch by ProgID,
NOT EnsureModule by GUID). Z9 runs them in increasing cost order so we exit
early on the first hit.

ORDER OF PROBES (cheapest first):

  Probe A — cosmetic-vs-real check (open lead #4)
    Reproduce the Z5 driven-D2 case. After the build, edit the equation's
    RHS value via EquationMgr (no locals.txt needed -- we set the RHS
    directly), force EditRebuild3, then read Parameter("D2@SK_Z9") to see
    if the value actually tracks the equation. If YES, the equation drives
    D2 correctly and the "red" indicator is cosmetic-only -- the documented
    limitation collapses to a doc-only patch. NO geometry workaround needed.
    Cost: zero popup ticks beyond the 2 D1/D2 ticks; one binding write.

  Probe B — MakeSelectedDriving (open lead #5)
    After AddDimension2 returns dim2, try the documented ISketchManager
    methods 'MakeSelectedDriving' / 'MakeSelectedDriven' (after selecting
    the dim). These are late-binding-reachable per the SW API docs and have
    never been tried. If reachable AND the equation goes clean, this is a
    direct fix that doesn't need typelib stubs at all.
    Cost: a few extra COM calls per failing dim; zero extra ticks.

  Probe C — EnsureModule by explicit GUID (open lead #1, partial)
    Z2b tried EnsureDispatch("SldWorks.Application") and got
      'This COM object can not automate the makepy process'
    This is a DIFFERENT call path than EnsureModule(GUID, lcid, major, minor).
    EnsureDispatch goes ProgID -> CLSID -> TypeLib -> compile -> instantiate
    and can fail at multiple steps. EnsureModule with explicit GUID skips
    the ProgID/CLSID lookup and goes straight to the typelib compile.
    HOWEVER: the Z2b 'can not automate makepy' error may also indicate the
    compile itself fails on this typelib -- in which case feeding the GUID
    won't help either. Treat Probe C as 'genuinely untested, plausibly
    blocked by the same underlying issue'.
    Cost: ~5s compile if it works; one Dispatch retry.

  Probe D — IDisplayDimension.DrivenState (Z7 Route 1 retry, ONLY if Probe C
    succeeded AND auto-upgraded the dispatch proxy)
    Only meaningful if Probe C green. Try dim2.DrivenState = 1 under
    early binding and check whether the equation goes clean.
    Cost: included with Probe A reproduction.

EARLY EXIT: if Probe A shows the limitation is cosmetic, STOP. The user
should be told to rewrite the limitation as 'cosmetic red flag in EqMgr
UI, parameter still drives correctly' and ship a doc patch. No further
investigation needed.

EXISTING EVIDENCE WE DO NOT RE-VERIFY:
  - dir(sw) and dir(doc) raise com_error('Element not found')/'Invalid index'
    on late-binding (per Z2b). Z9 wraps EVERY dir()/getattr probe in
    try/except so this expected failure doesn't abort the probe.
  - eq.Value(idx) returns successfully even when D2 is driven (Z6 proved
    this -- idx=1, eq.Value=5.0 returned, yet D2 was driven and red).
    Z9 does NOT use eq.Value as a success signal. Visual EqMgr inspection
    + Parameter-tracks-RHS-change is the only reliable signal.
  - EquationMgr.Status(i) returns the same fallback for all entries (per
    investigation report Diagnostic Gaps row 2). Z9 does not call it.

Run from venv-freshtest with SW open. Expected popup ticks:
  - Probe A: 2 ticks (D1, D2 on the reproduction part)
  - Probe B: 0 extra ticks (operates on already-built dim)
  - Probe C: 0 ticks
  - Probe D: 0 extra ticks if Probe C green; skipped otherwise
"""
import os
import sys
import time
import pythoncom
import win32com.client

SW_TLB_GUID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
GENCACHE_MAJOR = 32  # SW 2024 per external diagnostic. Verify via HKCR\TypeLib if EnsureModule errors.
GENCACHE_MINOR = 0
GENCACHE_LCID = 0

SW_DIM_DRIVEN_STATE_DRIVING = 1   # swDimensionDriving (best guess from enum)
SW_DIM_DRIVEN_STATE_DRIVEN = 2    # swDimensionDriven


def safe_dir(obj, label):
    """dir() that survives the late-binding com_error('Element not found') gotcha."""
    try:
        return list(dir(obj))
    except Exception as e:
        print(f"  [{label}] dir() ERR (expected on late-binding): {type(e).__name__}: {e}")
        return []


def safe_getattr(obj, name, label):
    try:
        return getattr(obj, name), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def build_center_rect_and_close(doc, sketch_name):
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")
    return feat


def add_edge_dim_with_reopen(doc, sketch_name, edge_xyz, leader_xyz, label):
    """Open sketch, select edge, add dim, close. Returns the dim object (which
    may be a CDispatch wrapping IDisplayDimension)."""
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
    type_str = type(dim).__name__ if dim is not None else None
    print(f"    [{label}] AddDimension2 -> dim={dim is not None}, type={type_str}")
    sm.InsertSketch(True)
    return dim


def reproduce_driven_d2(sw):
    """Build the Z5-equivalent failing case. Returns (doc, dim2, sketch_name)
    or (None, None, None) on failure."""
    doc = make_part(sw)
    if doc is None:
        print("  ! NewDocument failed")
        return None, None, None

    sketch_name = "SK_Z9"
    build_center_rect_and_close(doc, sketch_name)
    add_edge_dim_with_reopen(doc, sketch_name, (0, 0.010, 0), (0, 0.015, 0), "D1")
    dim2 = add_edge_dim_with_reopen(doc, sketch_name, (-0.010, 0, 0), (-0.015, 0, 0), "D2")

    if dim2 is None:
        print("  ! D2 AddDimension2 failed -- spike cannot proceed")
        return None, None, None
    return doc, dim2, sketch_name


# =====================================================================
# Probe A: cosmetic-vs-real check
# =====================================================================
def probe_a_cosmetic_check(doc, sketch_name):
    """Open lead #4 from the investigation report. Edit the equation's RHS
    via EquationMgr (no locals.txt edit needed -- direct API write), force
    rebuild, read Parameter(D2). If the value tracks the new RHS, the
    'driven' indicator is cosmetic and the equation actually drives D2."""
    print()
    print("=== Probe A: cosmetic-vs-real check (open lead #4) ===")
    eq = doc.GetEquationMgr

    # Step A1: set up the binding at value=5.0
    var_idx = eq.Add2(-1, '"Z9_TEST_VAR" = 5.0', True)
    formula = f'"D2@{sketch_name}" = "Z9_TEST_VAR"'
    bind_idx = eq.Add2(-1, formula, True)
    print(f"  var Add2 idx={var_idx}, binding Add2 idx={bind_idx}")
    if bind_idx < 0:
        print("  ! binding rejected (idx<0); cannot run cosmetic check")
        return {"cosmetic_only": None, "error": "binding rejected"}

    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR (initial): {type(e).__name__}: {e}")

    p_initial = doc.Parameter(f"D2@{sketch_name}")
    val_initial = (p_initial.SystemValue * 1000) if p_initial is not None else None
    print(f"  initial: D2 = {val_initial!r} mm (expecting 5.0 if binding drives)")

    # Step A2: change the RHS to a clearly-different value
    new_var_idx = eq.Add2(var_idx, '"Z9_TEST_VAR" = 8.5', True)
    print(f"  RHS update Add2 idx={new_var_idx}")

    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR (post-edit): {type(e).__name__}: {e}")

    p_after = doc.Parameter(f"D2@{sketch_name}")
    val_after = (p_after.SystemValue * 1000) if p_after is not None else None
    print(f"  after RHS=8.5: D2 = {val_after!r} mm")

    tracks = (val_initial is not None and val_after is not None
              and abs(val_initial - 5.0) < 0.01 and abs(val_after - 8.5) < 0.01)

    if tracks:
        print()
        print("  >>> PROBE A GREEN: the equation drives D2 even though it shows red.")
        print("  >>> The limitation is COSMETIC. Doc-patch only; no geometry workaround needed.")
        return {"cosmetic_only": True, "val_at_5": val_initial, "val_at_8_5": val_after}
    else:
        print()
        print("  >>> PROBE A RED: D2 does NOT track the RHS. The driven-D2 limitation is real.")
        print("  >>> Continue to Probe B (MakeSelectedDriving).")
        return {"cosmetic_only": False, "val_at_5": val_initial, "val_at_8_5": val_after}


# =====================================================================
# Probe B: MakeSelectedDriving
# =====================================================================
def probe_b_make_driving(doc, dim2, sketch_name):
    """Open lead #5: try ISketchManager.MakeSelectedDriving after selecting
    the dim. Documented SW method, never tried per investigation report."""
    print()
    print("=== Probe B: MakeSelectedDriving (open lead #5) ===")
    sm = doc.SketchManager

    # B1: enumerate candidate method names on SketchManager (best-effort -- dir()
    # may error on late-binding per Z2b finding)
    sm_attrs = safe_dir(sm, "SketchManager")
    candidates = [n for n in sm_attrs
                  if any(k in n for k in ("Driving", "Driven", "MakeSelected"))]
    print(f"  SketchManager candidate attrs: {candidates if candidates else '(dir empty -- expected on late-binding)'}")

    # B2: try the two documented names regardless of dir() result.
    # The dim object's selection state is what matters; we need to put dim2
    # back into the active selection. The IDisplayDimension itself may not
    # support Select() -- it's a wrapper around the underlying IDimension /
    # IFeature. Try several paths.

    # Path 1: dim2 may expose a 'Select' or 'Select2' method directly
    selected = False
    for sel_name in ("Select", "Select2", "Select4"):
        method, err = safe_getattr(dim2, sel_name, "dim2")
        if method is None:
            print(f"    dim2.{sel_name}: {err}")
            continue
        try:
            # IDisplayDimension.Select4 signature is (Append, Mark) per SW API
            result = method(False, 0) if sel_name == "Select4" else method(False)
            print(f"    dim2.{sel_name}(...) -> {result!r}")
            selected = True
            break
        except Exception as e:
            print(f"    dim2.{sel_name}(...) ERR: {type(e).__name__}: {e}")

    # Path 2: if dim2 doesn't self-select, try selecting D2 by its parameter name.
    # Use VARIANT(VT_DISPATCH, None) for the Callout param -- passing raw None
    # triggers 'Type mismatch' on late-binding (known_gotchas.md).
    if not selected:
        doc.ClearSelection2(True)
        vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
        try:
            ok = doc.Extension.SelectByID2(f"D2@{sketch_name}", "DIMENSION", 0, 0, 0, False, 0, vt_disp_none, 0)
            print(f"    SelectByID2('D2@{sketch_name}','DIMENSION',...) -> {ok}")
            selected = bool(ok)
        except Exception as e:
            print(f"    SelectByID2 ERR: {type(e).__name__}: {e}")
            # Try plain SelectByID as last resort (no Mark/Callout/Options args)
            try:
                ok = doc.SelectByID(f"D2@{sketch_name}", "DIMENSION", 0, 0, 0)
                print(f"    SelectByID('D2@{sketch_name}','DIMENSION',...) -> {ok}")
                selected = bool(ok)
            except Exception as e2:
                print(f"    SelectByID ERR: {type(e2).__name__}: {e2}")

    if not selected:
        print("  ! Could not select D2 -- Probe B cannot proceed")
        return {"reachable": None, "error": "could not select D2"}

    # B3: try MakeSelectedDriving and MakeSelectedDriven
    results = {}
    for method_name in ("MakeSelectedDriving", "MakeSelectedDriven"):
        method, err = safe_getattr(sm, method_name, "SketchManager")
        if method is None:
            print(f"  sm.{method_name}: {err}")
            results[method_name] = ("unreachable", err)
            continue
        try:
            r = method()
            print(f"  sm.{method_name}() -> {r!r}")
            results[method_name] = ("called", r)
        except Exception as e:
            print(f"  sm.{method_name}() ERR: {type(e).__name__}: {e}")
            results[method_name] = ("err", str(e))

    # B4: if MakeSelectedDriving was reachable, force rebuild and re-check
    if results.get("MakeSelectedDriving", (None,))[0] == "called":
        try:
            doc.EditRebuild3
        except Exception as e:
            print(f"  EditRebuild3 ERR: {type(e).__name__}: {e}")
        p = doc.Parameter(f"D2@{sketch_name}")
        val = (p.SystemValue * 1000) if p is not None else None
        print(f"  D2 after MakeSelectedDriving + rebuild = {val!r} mm")
        print(f"  >>> VISUAL CHECK NEEDED: open EqMgr, is 'D2@{sketch_name}' still red?")
        results["d2_after_mm"] = val

    return results


# =====================================================================
# Probe C: EnsureModule by explicit GUID
# =====================================================================
def probe_c_typelib_bootstrap():
    """Open lead #1 (partial). Z2b tried EnsureDispatch by ProgID; this tries
    EnsureModule by explicit GUID -- different call path. May still hit the
    same underlying compile failure if the 'can not automate makepy' error
    was about the compile, not the lookup."""
    print()
    print("=== Probe C: EnsureModule by explicit GUID (open lead #1, partial) ===")
    gen_py_dir = win32com.client.gencache.GetGeneratePath()
    print(f"  gen_py cache dir: {gen_py_dir}")

    try:
        t0 = time.perf_counter()
        mod = win32com.client.gencache.EnsureModule(
            SW_TLB_GUID, GENCACHE_LCID, GENCACHE_MAJOR, GENCACHE_MINOR
        )
        dt = (time.perf_counter() - t0) * 1000
    except Exception as e:
        print(f"  EnsureModule ERR: {type(e).__name__}: {e}")
        print(f"  If wrong-major: check HKCR\\TypeLib\\{SW_TLB_GUID} for the registered version")
        print(f"  If compile-fails-same-as-Z2b: typelib path is dead-end on this build")
        return {"bootstrap": False, "error": str(e)}

    if mod is None:
        print(f"  EnsureModule returned None ({dt:.1f}ms) -- typelib not registered at v{GENCACHE_MAJOR}.{GENCACHE_MINOR}")
        return {"bootstrap": False, "error": "module is None"}

    print(f"  EnsureModule OK ({dt:.1f}ms) -- module: {mod!r}")

    # Verify auto-upgrade by re-Dispatching
    sw = win32com.client.Dispatch("SldWorks.Application")
    cls = type(sw).__name__
    mod_name = type(sw).__module__
    is_early = "gen_py" in mod_name or cls != "CDispatch"
    print(f"  post-bootstrap Dispatch type: {mod_name}.{cls}")
    print(f"  auto-upgrade to early binding: {is_early}")

    if not is_early:
        print()
        print("  >>> EnsureModule compiled stubs BUT Dispatch did not auto-upgrade.")
        print("  >>> Per memory caveat: live IDispatch returned by SW may not match")
        print("  >>> typelib at runtime (GetTypeInfo 'Invalid index' on this build).")
        print("  >>> Probe D is meaningless -- skip it.")

    return {"bootstrap": True, "is_early": is_early, "sw_early": sw if is_early else None}


# =====================================================================
# Probe D: DrivenState write under early binding
# =====================================================================
def probe_d_drivenstate(sw_early):
    """Z7 Route 1 retry. ONLY meaningful if Probe C upgraded the proxy."""
    print()
    print("=== Probe D: IDisplayDimension.DrivenState write (early-bound) ===")
    doc = make_part(sw_early)
    if doc is None:
        print("  ! NewDocument failed")
        return None

    sketch_name = "SK_Z9D"
    build_center_rect_and_close(doc, sketch_name)
    add_edge_dim_with_reopen(doc, sketch_name, (0, 0.010, 0), (0, 0.015, 0), "D1")
    dim2 = add_edge_dim_with_reopen(doc, sketch_name, (-0.010, 0, 0), (-0.015, 0, 0), "D2")
    if dim2 is None:
        return None

    print(f"  dim2 type: {type(dim2).__module__}.{type(dim2).__name__}")

    initial, err = safe_getattr(dim2, "DrivenState", "dim2")
    if err is not None:
        print(f"  read DrivenState ERR: {err}")
        return {"readable": False, "writable": False}
    print(f"  initial DrivenState = {initial!r}")

    try:
        dim2.DrivenState = SW_DIM_DRIVEN_STATE_DRIVING
    except Exception as e:
        print(f"  write DrivenState ERR: {type(e).__name__}: {e}")
        return {"readable": True, "writable": False, "initial": initial}

    after, err2 = safe_getattr(dim2, "DrivenState", "dim2")
    print(f"  after write: DrivenState = {after!r}")
    write_ok = (after == SW_DIM_DRIVEN_STATE_DRIVING)

    # Bind D2 and force rebuild to check if solver respects the override
    eq = doc.GetEquationMgr
    eq.Add2(-1, '"Z9D_TEST_VAR" = 5.0', True)
    bind_idx = eq.Add2(-1, f'"D2@{sketch_name}" = "Z9D_TEST_VAR"', True)
    print(f"  binding Add2 -> idx={bind_idx}")
    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR: {type(e).__name__}: {e}")

    final_state, _ = safe_getattr(dim2, "DrivenState", "dim2")
    print(f"  DrivenState after rebuild = {final_state!r} (1=driving, 2=driven)")
    print(f"  >>> VISUAL CHECK: open EqMgr -- is the equation still red?")

    return {
        "readable": True,
        "writable": write_ok,
        "initial": initial,
        "after_write": after,
        "after_rebuild": final_state,
    }


# =====================================================================
# Main
# =====================================================================
def main():
    pythoncom.CoInitialize()

    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    print(f"Dispatch type: {type(sw).__module__}.{type(sw).__name__} (late-binding for probes A/B)")

    # Reproduce the failing case ONCE; reuse the doc for Probes A and B
    print()
    print("=== Reproducing Z5 driven-D2 case ===")
    doc, dim2, sketch_name = reproduce_driven_d2(sw)
    if doc is None:
        print()
        print(">>> Could not reproduce the failing case. Spike aborted.")
        return

    # --- Probe A (cheapest) ---
    a = probe_a_cosmetic_check(doc, sketch_name)

    if a.get("cosmetic_only") is True:
        print()
        print("=== Z9 EARLY EXIT: limitation is cosmetic ===")
        print("Recommended action: update docs/known_limitations.md §3 second workaround")
        print("to reframe rectangle D2 as 'shows red in EqMgr but parameter drives correctly'.")
        print("No geometry workaround or typelib spike needed.")
        return

    # --- Probe B ---
    b = probe_b_make_driving(doc, dim2, sketch_name)

    b_called = b.get("MakeSelectedDriving", (None,))[0] == "called" if isinstance(b, dict) else False
    if b_called:
        print()
        print(">>> Probe B called MakeSelectedDriving successfully.")
        print(">>> Manual visual check on the current part: is D2 still red in EqMgr?")
        print(">>> If clean: ship a builder patch calling this after each rectangle's D2.")
        print(">>> If still red: continue to Probe C.")
        # Continue to C anyway -- visual check happens out-of-band

    # --- Probe C ---
    c = probe_c_typelib_bootstrap()

    # --- Probe D (only if C green) ---
    d = None
    if c.get("bootstrap") and c.get("is_early") and c.get("sw_early") is not None:
        d = probe_d_drivenstate(c["sw_early"])

    # --- Summary ---
    print()
    print("=" * 60)
    print("=== Z9 summary ===")
    print(f"  Probe A (cosmetic check):     cosmetic_only={a.get('cosmetic_only')}")
    if isinstance(b, dict):
        print(f"  Probe B (MakeSelectedDriving):")
        for k, v in b.items():
            print(f"    {k}: {v}")
    print(f"  Probe C (typelib bootstrap):  {c}")
    if d is not None:
        print(f"  Probe D (DrivenState write):  {d}")
    print()
    print(">>> VISUAL CHECKS still needed (no late-binding API exposes this):")
    print("    For each part open in SW, open Equation Manager and check if")
    print("    'D2@SK_*' = '\"Z9*_TEST_VAR\"' shows red (driven) or clean (driving).")
    print()
    print(">>> Decision matrix:")
    print("    A green        -> ship doc patch. STOP.")
    print("    A red, B clean -> ship MakeSelectedDriving builder patch. STOP.")
    print("    A red, B red, C+D green -> early-binding migration is the fix (large.)")
    print("    All red        -> Z8-retry (CornerRectangle + SketchAddConstraints('sgMIDPOINT'))")


if __name__ == "__main__":
    main()
