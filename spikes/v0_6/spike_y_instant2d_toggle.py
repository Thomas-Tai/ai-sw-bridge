"""Spike Y: test the hypothesis that AddDimension2 popup suppression on SW
2024 SP1 requires BOTH swInputDimValOnCreate=False AND swInstant2DEnable=False.

Hypothesis (from external lead, 2026-05-19): the bridge's existing toggle-8
suppression code only kills the classic Modify-Dimension popup. A SECOND
popup pathway exists via Instant2D (the on-screen inline-input overlay
introduced in SW 2024). Toggling swInstant2DEnable=False alongside the
existing toggle 8 may close that second pathway.

See [[sw-bridge-instant2d-popup-hypothesis]] in user memory for full
context including skepticism (VBA vs external-COM gap, theory not
KB-cited, builder.py has contradictory comments about toggle 8).

Decision tree after this spike runs:

| Result | Implication |
|---|---|
| Popup suppressed when both toggles False | Theory confirmed. Patch builder.py to toggle both. |
| Popup still appears, toggle reads back False | Toggle didn't take effect via pywin32 (external-COM gap). Direction B' (VBA macro fallback) next. |
| Popup still appears, both toggles read False after Set | Theory wrong. Direction B' next, one more closed hypothesis. |

## What this spike does

1. Probe the numeric ID for swInstant2DEnable. CHM enum table is empty
   (per the existing toggle 8 comment in builder.py L48-52), so we
   either trust a known-from-the-wild value or scan a range. The codestack
   forum lists swInstant2DEnable = 433 -- we try that first, then scan
   a small range around it on failure.

2. Print readback of both toggles before any change, so we know their
   default state in the user's SW install.

3. Create a fresh part, open a sketch on Front Plane.

4. Try AddDimension2 with each of FOUR toggle configurations:
   (a) both toggles UNCHANGED (control -- pre-spike behavior)
   (b) only swInputDimValOnCreate=False
   (c) only swInstant2DEnable=False
   (d) BOTH False

5. For each config, draw a rectangle, select a side, call AddDimension2,
   and report whether the popup blocked or returned immediately. (The
   user must observe the popup visually -- this spike can't detect it
   programmatically because the popup runs on SW's UI thread; the COM
   call returns regardless.)

6. Restore original toggle values via try/finally.

## How to interpret the output

The COM call always RETURNS a CDispatch even when the popup is showing.
The user must watch SW between configs and report which configs show the
popup. The spike prints clear markers between configs so the user can
correlate.

Run from venv-freshtest with SW open and a clean state. The spike
creates its own part; doesn't depend on or modify any existing doc.
"""
import pythoncom
import win32com.client

# Known empirical IDs
SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE = 8  # confirmed in Spike I

# Hypothesised value from external lead + codestack forum reports.
# CHM enum gives no numeric value, so this is unverified -- the spike
# probes it.
SW_TOGGLE_INSTANT_2D_ENABLE_CANDIDATES = [433, 432, 434, 435, 200, 201, 202, 95]


def find_instant2d_toggle_id(sw):
    """Probe candidate toggle IDs. Returns the first ID whose Get/Set
    cycle behaves like a real toggle (reads back the value just written
    AND is not the same as toggle 8). Returns None if none of the
    candidates behave correctly."""
    for tid in SW_TOGGLE_INSTANT_2D_ENABLE_CANDIDATES:
        try:
            original = sw.GetUserPreferenceToggle(tid)
        except Exception as e:
            print(f"  toggle {tid}: GetUserPreferenceToggle ERR: {e!r}")
            continue
        # Set to the opposite value, read back, restore
        try:
            sw.SetUserPreferenceToggle(tid, not original)
            readback = sw.GetUserPreferenceToggle(tid)
            sw.SetUserPreferenceToggle(tid, original)  # restore
        except Exception as e:
            print(f"  toggle {tid}: Set/Get cycle ERR: {e!r}")
            continue
        if readback == (not original):
            print(f"  toggle {tid}: behaves as togglable (orig={original})")
            # Don't return yet -- need to differentiate from toggle 8
            # (which is also togglable). Report all togglable IDs for
            # human inspection -- the right ID has to be picked by
            # observed SW behavior (Instant2D ribbon button highlight).
        else:
            print(f"  toggle {tid}: read back {readback} after Set({not original}) -- NOT togglable")
    return None  # Decision deferred to human observation in step 4


def open_sketch(doc):
    """Open a fresh Front-plane sketch. Returns the SketchManager."""
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    return sm


def draw_and_dim(doc, sm, label):
    """Draw a 20mm rectangle, select its top edge, call AddDimension2.
    The user watches SW to see if the popup appears. Returns the COM
    return value (whose presence/absence is NOT a reliable popup
    indicator -- AddDimension2 returns a CDispatch even when popup is up)."""
    print(f"  [{label}] drawing 20x20 rect + AddDimension2...")
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    doc.ClearSelection2(True)
    # Select top edge (y=+10mm)
    ok = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)
    print(f"  [{label}] edge select: {ok}")
    dim = doc.AddDimension2(0, 0.015, 0)
    print(f"  [{label}] AddDimension2 returned: {dim!r}")
    print(f"  [{label}] >>> USER: did the popup appear? (Y/N)")
    return dim


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    print(f"SW build: {sw.RevisionNumber}")
    print()
    print("=== Step 1: probe candidate IDs for swInstant2DEnable ===")
    find_instant2d_toggle_id(sw)
    print()
    print("=== Step 2: report initial toggle state ===")
    initial_dim_val = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    print(f"  toggle 8 (swInputDimValOnCreate) initial: {initial_dim_val}")
    # We'll capture Instant2D candidate states too -- the most likely ID first
    instant2d_id = SW_TOGGLE_INSTANT_2D_ENABLE_CANDIDATES[0]  # 433
    initial_instant2d = sw.GetUserPreferenceToggle(instant2d_id)
    print(f"  toggle {instant2d_id} (likely swInstant2DEnable) initial: {initial_instant2d}")

    print()
    print("=== Step 3: test 4 toggle configurations ===")
    # Each config: open a fresh part to avoid sketch-state contamination
    configs = [
        ("CONTROL (both unchanged)",       None, None),
        ("only toggle 8 = False",          False, None),
        ("only toggle 433 = False",        None, False),
        ("BOTH = False",                   False, False),
    ]

    try:
        for label, dim_val_set, instant2d_set in configs:
            print()
            print(f"--- Config: {label} ---")
            # Open fresh part for clean state
            doc = sw.NewDocument(template, 0, 0.0, 0.0)
            if doc is None:
                print("  ! NewDocument failed; skipping config")
                continue

            # Apply config
            if dim_val_set is not None:
                sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dim_val_set)
                print(f"  set toggle 8 = {dim_val_set}, readback = {sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)}")
            else:
                print(f"  toggle 8 unchanged = {sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)}")
            if instant2d_set is not None:
                sw.SetUserPreferenceToggle(instant2d_id, instant2d_set)
                print(f"  set toggle {instant2d_id} = {instant2d_set}, readback = {sw.GetUserPreferenceToggle(instant2d_id)}")
            else:
                print(f"  toggle {instant2d_id} unchanged = {sw.GetUserPreferenceToggle(instant2d_id)}")

            sm = open_sketch(doc)
            draw_and_dim(doc, sm, label)
            # Don't close the popup automatically; user observes, then ticks manually
            # Wait for user input before next config so observation isn't blurred
            input(f"  Press ENTER after observing config '{label}' to continue...")

            # Reset for next config (close the active part without saving)
            sm.InsertSketch(True)  # close sketch
            sw.CloseDoc(doc.GetTitle if hasattr(doc, "GetTitle") else "")
    finally:
        # Always restore original toggle values
        print()
        print("=== Cleanup: restore original toggle values ===")
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, initial_dim_val)
        sw.SetUserPreferenceToggle(instant2d_id, initial_instant2d)
        print(f"  toggle 8 restored to {initial_dim_val}")
        print(f"  toggle {instant2d_id} restored to {initial_instant2d}")

    print()
    print(">>> Spike Y complete. Report observations:")
    print("    - CONTROL: popup? Y/N")
    print("    - only toggle 8 = False: popup? Y/N")
    print("    - only toggle 433 = False: popup? Y/N")
    print("    - BOTH = False: popup? Y/N")
    print()
    print("    Then check Instant2D ribbon button state in SW UI during each")
    print("    config to verify which toggle ID actually controls Instant2D.")
    print("    If 433 isn't right, try the other candidates from the probe.")


if __name__ == "__main__":
    main()
