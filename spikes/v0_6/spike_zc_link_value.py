"""Spike ZC: probe whether SW's "Link Values" feature can drive a driven D2.

THE PREMISE:
  Link Values is a SW feature where multiple dimensions get bound to a shared
  named value. It's a DIFFERENT code path from equations -- the "driven dim
  can't be equation dependent" rule may not apply because link values aren't
  equations.

  If LinkValue is settable on a driven dim AND geometry tracks the link
  value on rebuild, the rect-D2 limitation collapses to:
    - D1 lands driving, gets LinkValue("W")
    - D2 lands driven, ALSO gets LinkValue("W")
    - locals.txt update propagates to "W" via equation or direct write
    - Both D1 and D2 see new value, regardless of driving/driven state

  If LinkValue is unreachable (matching the pattern of every other dim-
  level setter we tested: DrivenState, MakeSelectedDriving, etc.), this
  path is dead and Solution 2 stands as the production answer.

  Pre-spike introspection (run before this spike was drafted):
    sm.LinkValue, doc.LinkAllDimensions, doc.LinkValues,
    doc.AddLinkedDimension, doc.Extension.AddLinkValue,
    doc.Extension.LinkDimensions  -- ALL AttributeError <unknown>.

  But: dir() is unreliable on late-bound SW objects (Z2b finding). The
  LinkValue property is most likely on the dim OBJECT itself, not on the
  top-level managers. We can't probe a dim object without first creating
  one, which is what this spike does.

CANDIDATE API NAMES to try on the dim2 object after AddDimension2:
  - dim.LinkVariable
  - dim.LinkedDimVariableName
  - dim.SharedValueName
  - dim.Linked / dim.IsLinked
  - dim.LinkToVariable / dim.LinkValue
  - dim.GetLinkedVariable / dim.SetLinkedVariable
  - dim.Name property (IDimension.Name is the link-value name when linked
    per some SW API docs)

PROBE STRUCTURE:
  Phase 1: reproduce the failing driven-D2 case (Z5-equivalent).
  Phase 2: introspect dim2 -- enumerate visible attrs (best-effort, dir
           may fail), and try every candidate name via getattr.
  Phase 3: if any name is reachable AND looks like a link setter, try
           setting it to "W" and check whether the dim's name changes
           or related state updates.
  Phase 4: if Phase 3 set something, also try D1 with the SAME link name
           "W", then update the link value (via equation or whatever path
           is reachable), force rebuild, check Parameter(D2) tracks.

DECISION MATRIX:
  All names AttributeError                  -> LinkValue is also typelib-
                                                hidden; Solution 2 stands.
  Some name reachable but setter blocked    -> same pattern as DrivenState;
                                                Solution 2 stands.
  Setter works, link value created visibly  -> partial win; need locals.txt
    in SW UI tree but D2 doesn't track         propagation pathway (may
                                                require equation bridge).
  Setter works AND D2 tracks updated value  -> FULL WIN; production fix
                                                is link-value-based.

Run from venv-freshtest with SW open. Expected popup ticks: 2 (D1, D2 on
the reproduction part).
"""

import os
import sys
import pythoncom
import win32com.client


def safe_dir(obj, label):
    try:
        return list(dir(obj))
    except Exception as e:
        print(
            f"  [{label}] dir() ERR (expected on late-binding): {type(e).__name__}: {e}"
        )
        return []


def safe_getattr(obj, name, label):
    try:
        return getattr(obj, name), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def make_part(sw):
    template = sw.GetUserPreferenceStringValue(8)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def add_edge_dim_with_reopen(doc, sketch_name, edge_xyz, leader_xyz, label):
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
    """Build the failing case: CenterRectangle + close-reopen-D1-close-reopen-D2."""
    print()
    print("=== Phase 1: reproduce driven-D2 ===")
    doc = make_part(sw)
    if doc is None:
        return None, None, None

    sketch_name = "SK_ZC"
    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)
    feat = doc.FeatureByPositionReverse(0)
    feat.Name = sketch_name
    print(f"  built sketch: {feat.Name!r}")

    dim1 = add_edge_dim_with_reopen(
        doc, sketch_name, (0, 0.010, 0), (0, 0.015, 0), "D1"
    )
    dim2 = add_edge_dim_with_reopen(
        doc, sketch_name, (-0.010, 0, 0), (-0.015, 0, 0), "D2"
    )
    if dim2 is None:
        return None, None, None
    return doc, dim1, dim2


# Candidate property/method names to probe on the dim object
DIM_CANDIDATES_PROPERTY_GET = [
    "LinkVariable",
    "LinkedDimVariableName",
    "SharedValueName",
    "Linked",
    "IsLinked",
    "LinkValue",
    "LinkValueName",
    "GetLinkedVariable",
    "Name",  # IDimension.Name is the link-value name when linked per some docs
    "FullName",
    "Variable",
    "VariableName",
]

# Candidate set names -- some are properties (assign), some are methods (call)
DIM_CANDIDATES_PROPERTY_SET = [
    ("LinkVariable", "ZC_LINK_W"),
    ("LinkedDimVariableName", "ZC_LINK_W"),
    ("SharedValueName", "ZC_LINK_W"),
    ("LinkValue", "ZC_LINK_W"),
    ("LinkValueName", "ZC_LINK_W"),
    ("Name", "ZC_LINK_W"),
    ("Variable", "ZC_LINK_W"),
    ("VariableName", "ZC_LINK_W"),
]

DIM_CANDIDATES_METHOD = [
    ("LinkValue", ("ZC_LINK_W",)),
    ("LinkValue", (True, "ZC_LINK_W")),
    ("LinkValue", ("ZC_LINK_W", True)),
    ("SetLinkVariable", ("ZC_LINK_W",)),
    ("SetLinkedVariable", ("ZC_LINK_W",)),
    ("LinkToVariable", ("ZC_LINK_W",)),
    ("ShareValueWith", ("ZC_LINK_W",)),
]


def probe_dim_attrs(dim, label):
    """Phase 2: probe the dim object's attribute surface."""
    print()
    print(
        f"=== Phase 2: probe {label} ({type(dim).__module__}.{type(dim).__name__}) ==="
    )

    # 2a: best-effort dir() enumeration
    attrs = safe_dir(dim, label)
    relevant = [
        a for a in attrs if any(k in a.lower() for k in ("link", "shar", "var"))
    ]
    if relevant:
        print(f"  dir() showed relevant attrs: {relevant}")
    else:
        print(f"  dir() returned {len(attrs)} attrs, 0 matching link/share/var")

    # 2b: try each candidate property getter
    print(f"  property-get probe:")
    reachable_getters = []
    for name in DIM_CANDIDATES_PROPERTY_GET:
        val, err = safe_getattr(dim, name, label)
        if err is None:
            print(f"    {name}: REACHABLE -> {val!r}")
            reachable_getters.append((name, val))
        # silence the AttributeError noise -- too verbose otherwise
    if not reachable_getters:
        print(f"    (none of {len(DIM_CANDIDATES_PROPERTY_GET)} candidates reachable)")

    return reachable_getters


def probe_dim_setters(dim, label):
    """Phase 3: try setting each candidate property/method."""
    print()
    print(f"=== Phase 3: probe {label} setters ===")

    successful_sets = []

    # 3a: property setters
    print(f"  property-set probe:")
    for name, value in DIM_CANDIDATES_PROPERTY_SET:
        try:
            setattr(dim, name, value)
            # Read it back to verify
            readback, err = safe_getattr(dim, name, label)
            print(f"    {name} = {value!r} -> readback {readback!r} (err={err})")
            if err is None and readback == value:
                successful_sets.append(("property", name, value))
        except AttributeError:
            pass  # silent: expected for most
        except Exception as e:
            print(f"    {name} = {value!r} -> {type(e).__name__}: {e}")

    # 3b: method calls
    print(f"  method-call probe:")
    for name, args in DIM_CANDIDATES_METHOD:
        method, err = safe_getattr(dim, name, label)
        if method is None:
            continue
        try:
            r = method(*args)
            print(f"    {name}{args!r} -> {r!r}")
            successful_sets.append(("method", name, args, r))
        except Exception as e:
            print(f"    {name}{args!r} -> {type(e).__name__}: {e}")

    if not successful_sets:
        print(f"    (no setter accepted)")

    return successful_sets


def verify_link_propagation(doc, sketch_name, link_var_name):
    """Phase 4: if a setter worked, test whether D2 actually tracks the link.
    Strategy: also bind D1 to the same link, then update the link value
    via equation (locals.txt path), rebuild, check Parameter(D2)."""
    print()
    print(f"=== Phase 4: link propagation test ===")

    eq = doc.GetEquationMgr
    # Bridge: equation that defines the link variable
    eq.Add2(-1, f'"{link_var_name}" = 7.0', True)
    print(f"  added bridging equation: {link_var_name!r} = 7.0")

    try:
        doc.EditRebuild3
    except Exception as e:
        print(f"  EditRebuild3 ERR: {type(e).__name__}: {e}")

    p2 = doc.Parameter(f"D2@{sketch_name}")
    p2_val = (p2.SystemValue * 1000) if p2 is not None else None
    print(
        f"  Parameter(D2@{sketch_name}) = {p2_val!r} mm "
        f"(7.0=full win, 20.0=placeholder/unchanged)"
    )
    drives = p2_val is not None and abs(p2_val - 7.0) < 0.01
    print(f"  >>> link value drives D2: {drives}")
    return drives


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")

    SW_PREF = 8
    original_toggle = sw.GetUserPreferenceToggle(SW_PREF)
    print(f"  original swInputDimValOnCreate = {original_toggle}")
    if original_toggle is not True:
        sw.SetUserPreferenceToggle(SW_PREF, True)
        print(f"  forced to True; readback = {sw.GetUserPreferenceToggle(SW_PREF)}")

    try:
        doc, dim1, dim2 = reproduce_driven_d2(sw)
        if doc is None:
            print()
            print(">>> Could not reproduce the failing case. Spike aborted.")
            return

        # Probe dim2 (the driven one)
        probe_dim_attrs(dim2, "dim2 (driven)")
        sets_d2 = probe_dim_setters(dim2, "dim2")

        # If anything worked on dim2, also bind dim1 to the same link
        # name and test full propagation. Otherwise probe dim1 too just
        # to confirm there's no asymmetry.
        if not sets_d2:
            print()
            print("=== bonus: probe dim1 (driving) for symmetry ===")
            probe_dim_attrs(dim1, "dim1 (driving)")
            sets_d1 = probe_dim_setters(dim1, "dim1")
        else:
            print()
            print("=== bonus: apply same link to dim1 (driving) ===")
            sets_d1 = probe_dim_setters(dim1, "dim1")

        # Phase 4 only meaningful if at least one setter worked
        drives = None
        if sets_d2 or sets_d1:
            drives = verify_link_propagation(doc, "SK_ZC", "ZC_LINK_W")

        print()
        print("=" * 60)
        print("=== Spike ZC summary ===")
        print(f"  dim2 setters that accepted:    {sets_d2}")
        print(f"  dim1 setters that accepted:    {sets_d1}")
        print(f"  Phase 4 D2-tracks-link result: {drives}")
        print()
        print(">>> Visual check (definitive for partial wins):")
        print(
            "    1. Open SK_ZC. Right-click D1 or D2. Is 'Link Values...' option present?"
        )
        print(
            "    2. In Property Manager / FeatureManager tree, is there a 'Link Values'"
        )
        print("       node listing ZC_LINK_W with D1 and D2 as members?")
        print("    3. Equation Manager: is 'ZC_LINK_W = 7.0' clean or red?")
        print()
        print(">>> Decision:")
        print(
            "    All AttributeError                       -> Solution 2 stands. LinkValue is typelib-hidden."
        )
        print(
            "    Setter accepted but D2 didn't track (drives=False) -> partial mechanism; not a fix."
        )
        print(
            "    drives=True                              -> production fix path; ship Spike ZD to integrate."
        )
    finally:
        sw.SetUserPreferenceToggle(SW_PREF, original_toggle)
        print()
        print(f"  restored swInputDimValOnCreate to {original_toggle}")


if __name__ == "__main__":
    main()
