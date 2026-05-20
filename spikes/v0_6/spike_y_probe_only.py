"""Spike Y probe-only variant: runs the toggle probe + AddDimension2 timing
test WITHOUT human-observation pauses.

Reports auto-detectable signals:
  - Which candidate toggle IDs behave like real togglables (Get/Set/Get cycle)
  - Whether SetUserPreferenceToggle "sticks" via pywin32 (the external-COM-gap test)
  - How long AddDimension2 takes to return in each config (proxy for blocking-popup)

A short COM-call duration means the popup is NOT blocking the COM thread --
i.e. it's purely a UI-thread phenomenon. A long duration (>1s) suggests
AddDimension2 is waiting for the popup to dismiss.

The human-observation step (does the popup VISIBLY appear) still needs the
full interactive spike. This probe just gives us auto-detectable evidence
to either narrow the search or rule out hypotheses cheaply.

Run from venv-freshtest with SW open. Creates its own part; closes it
without saving on exit.
"""

import time
import pythoncom
import win32com.client

SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE = 8
SW_TOGGLE_INSTANT_2D_CANDIDATES = [433, 432, 434, 435, 200, 201, 202, 95]


def probe_toggle_ids(sw):
    """Return list of (toggle_id, initial_value, set_to_opposite_worked) tuples
    for each candidate. set_to_opposite_worked=True means GetUserPreferenceToggle
    read back the value just written -- proves the toggle is a real
    togglable preference on this build."""
    results = []
    for tid in SW_TOGGLE_INSTANT_2D_CANDIDATES:
        try:
            original = sw.GetUserPreferenceToggle(tid)
        except Exception as e:
            results.append((tid, None, False, f"Get ERR: {e!r}"))
            continue
        try:
            sw.SetUserPreferenceToggle(tid, not original)
            readback = sw.GetUserPreferenceToggle(tid)
            sw.SetUserPreferenceToggle(tid, original)  # restore
            worked = readback == (not original)
            results.append((tid, original, worked, "OK"))
        except Exception as e:
            results.append((tid, original, False, f"Set/Get cycle ERR: {e!r}"))
    return results


def time_addim(sw, doc, label):
    """Open a fresh sketch, draw a rect, call AddDimension2, measure how
    long the COM call took."""
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)
    t0 = time.perf_counter()
    dim = doc.AddDimension2(0, 0.015, 0)
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000
    print(
        f"  [{label}] edge select={ok}, AddDimension2 returned in {elapsed_ms:.1f}ms, dim={dim is not None}"
    )
    # Close the sketch without committing the dim (avoid stuck popup
    # blocking subsequent SW operations)
    sm.InsertSketch(True)
    return elapsed_ms


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    print()

    # ---------------- Step 1: probe candidate toggle IDs ----------------
    print("=== Step 1: probe candidate toggle IDs (Get/Set/Get cycle) ===")
    probe_results = probe_toggle_ids(sw)
    togglable_ids = []
    for tid, orig, worked, status in probe_results:
        marker = "TOGGLABLE" if worked else "----------"
        print(f"  [{marker}] toggle {tid}: orig={orig}, status={status}")
        if worked:
            togglable_ids.append(tid)
    print()

    # toggle 8 is known to be togglable -- confirm so we have a baseline
    orig_8 = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, not orig_8)
    rb_8 = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, orig_8)
    print(
        f"  [baseline] toggle 8 (swInputDimValOnCreate): orig={orig_8}, "
        f"toggles via Set/Get? {rb_8 == (not orig_8)}"
    )
    print()

    if not togglable_ids:
        print("!! No candidate toggle ID behaved as togglable -- can't proceed.")
        print("   Possible causes: all candidates are read-only on this build,")
        print("   or swInstant2DEnable has a different numeric ID than tried.")
        print("   Next: scan a wider range, or look up the ID via SW UI experiment.")
        return

    # Use the first togglable candidate (most likely 433)
    instant2d_id = togglable_ids[0]
    print(f"=== Step 2: using toggle {instant2d_id} as swInstant2DEnable candidate ===")
    print()

    # ---------------- Step 3: time AddDimension2 in 4 configs ----------------
    print("=== Step 3: time AddDimension2 in 4 toggle configurations ===")
    print()
    template = sw.GetUserPreferenceStringValue(8)
    initial_dim_val = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    initial_instant2d = sw.GetUserPreferenceToggle(instant2d_id)
    print(f"  initial toggle 8 = {initial_dim_val}")
    print(f"  initial toggle {instant2d_id} = {initial_instant2d}")
    print()

    configs = [
        ("CONTROL (both unchanged)", None, None),
        ("only toggle 8 = False", False, None),
        (f"only toggle {instant2d_id} = False", None, False),
        ("BOTH = False", False, False),
    ]

    docs_to_close = []
    try:
        for label, dim_val_set, instant2d_set in configs:
            print(f"--- {label} ---")
            # Apply toggle config
            if dim_val_set is not None:
                sw.SetUserPreferenceToggle(
                    SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dim_val_set
                )
            if instant2d_set is not None:
                sw.SetUserPreferenceToggle(instant2d_id, instant2d_set)
            actual_8 = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
            actual_i2d = sw.GetUserPreferenceToggle(instant2d_id)
            print(
                f"  toggle 8 now = {actual_8}, toggle {instant2d_id} now = {actual_i2d}"
            )
            # Fresh part for clean state
            doc = sw.NewDocument(template, 0, 0.0, 0.0)
            if doc is None:
                print("  ! NewDocument failed")
                continue
            docs_to_close.append(doc)
            time_addim(sw, doc, label)
            print()
            # Reset toggles to initial before next config (so each is independent)
            sw.SetUserPreferenceToggle(
                SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, initial_dim_val
            )
            sw.SetUserPreferenceToggle(instant2d_id, initial_instant2d)
    finally:
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, initial_dim_val)
        sw.SetUserPreferenceToggle(instant2d_id, initial_instant2d)
        print("=== Cleanup ===")
        print(f"  restored toggle 8 to {initial_dim_val}")
        print(f"  restored toggle {instant2d_id} to {initial_instant2d}")
        # Close the test parts without saving
        for d in docs_to_close:
            try:
                title = d.GetTitle if hasattr(d, "GetTitle") else ""
                sw.CloseDoc(title)
            except Exception as e:
                print(f"  CloseDoc ERR: {e!r}")

    print()
    print(">>> Auto-detectable summary:")
    print("    - AddDimension2 timing tells us if popup BLOCKS the COM thread.")
    print("    - If all 4 configs return in <50ms, popup is a UI-only phenomenon")
    print("      (COM call returns regardless). Visual observation needed.")
    print("    - If CONTROL takes >1s but BOTH=False takes <50ms, the hypothesis")
    print("      is confirmed without needing visual observation.")


if __name__ == "__main__":
    main()
