"""Spike Z2: verify SendKeys('{ENTER}') reliably dismisses the
AddDimension2 Modify-Dimension popup.

Builds on Spike Z1 (which proved EditSketch + AddDimension2 on closed
sketch works mechanically). The remaining question: can the bridge
dismiss the popup autonomously by sending ENTER, so a batch of N dims
ticks itself without human interaction?

Mechanism under test:
  1. AddDimension2 is called -- popup appears on SW UI thread, COM call
     blocks on returning.
  2. From the OUTSIDE (Python), we have no direct way to know the popup
     is up. But we CAN call sw.SendKeys('{ENTER}') -- SW's API for
     posting keyboard input to whatever has focus.
  3. If SW's popup has focus and SendKeys delivers the ENTER, the popup
     should dismiss and AddDimension2 should return.

The trick is timing. We can't call SendKeys BEFORE AddDimension2 -- the
ENTER would arrive before the popup exists. We can't call it AFTER --
the COM thread is blocked on AddDimension2 returning. The only option
is to fire SendKeys from a separate thread that wakes up a moment
after AddDimension2 starts.

Approach: spawn a daemon thread that sleeps 500ms then calls SendKeys.
Main thread calls AddDimension2. If the popup dismisses, the COM call
returns within ~500-1000ms (vs ~7800ms for manual tick in Spike Z1).

Decision tree:
  GREEN: AddDimension2 returns in <2000ms, dim is real (D1@SK_Box has value).
         Option A (autonomous batched dimming) is viable.
  PARTIAL: dim is real but takes >2000ms -- SendKeys works but unreliably.
           Option B (human ticks batch) is the safer choice.
  RED: dim is None or AddDimension2 hangs indefinitely -- SendKeys can't
       reliably dismiss the popup. Option B only.

Run from venv-freshtest with SW open and ready.
"""

import threading
import time
import pythoncom
import win32com.client


def dismiss_after_delay(sw, delay_ms, label):
    """Sleep, then SendKeystrokes ENTER to whatever has focus in SW.

    Note: the docstring at top of file says SendKeys; the actual ISldWorks
    method is SendKeystrokes. First run of Z2 hit AttributeError on SendKeys
    -- this is the corrected call.
    """
    time.sleep(delay_ms / 1000.0)
    try:
        sw.SendKeystrokes("{ENTER}")
        print(f"  [{label}] SendKeystrokes('{{ENTER}}') called at +{delay_ms}ms")
    except Exception as e:
        print(f"  [{label}] SendKeystrokes ERR: {e!r}")


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw.RevisionNumber}")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ----- Build a part with TWO sketches we can dim deferred -----
    print()
    print("=== Setup: build 20x20x10 box with two sketches ===")
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)
    sm.InsertSketch(True)  # close
    sk1 = doc.FeatureByPositionReverse(0)
    sk1.Name = "SK_Box1"
    print(f"  sketch 1: {sk1.Name!r}")

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box1", "SKETCH", 0, 0, 0)
    f = fm.FeatureExtrusion2(
        True,
        False,
        False,
        0,
        0,
        0.010,
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
    if f is None:
        print("  ! FeatureExtrusion2 failed")
        return
    f.Name = "EX_Box1"
    print(f"  extrude 1: {f.Name!r}")

    # ----- Test 1: deferred-dim with SendKeys ENTER auto-dismiss -----
    print()
    print("=== Test 1: deferred dim on SK_Box1 + SendKeys auto-dismiss ===")
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box1", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", 0, 0.010, 0)
    print(f"  top edge selected: {ok}")

    # Spawn dismissal thread, then call AddDimension2 from main thread
    t = threading.Thread(
        target=dismiss_after_delay, args=(sw, 500, "test1"), daemon=True
    )
    t.start()
    t0 = time.perf_counter()
    dim = doc.AddDimension2(0, 0.015, 0)
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000
    t.join(timeout=2.0)
    print(f"  AddDimension2 returned in {elapsed_ms:.1f}ms, dim={dim is not None}")

    if elapsed_ms < 100:
        verdict_1 = (
            "INSTANT (popup likely never opened OR dim creation failed silently)"
        )
    elif elapsed_ms < 2000:
        verdict_1 = "FAST (SendKeys likely dismissed the popup)"
    elif elapsed_ms < 6000:
        verdict_1 = "MEDIUM (SendKeys may have worked but slowly)"
    else:
        verdict_1 = "SLOW (SendKeys did not dismiss; you likely ticked manually)"
    print(f"  verdict: {verdict_1}")

    sm.InsertSketch(True)  # close

    # Verify the dim was actually created (not just popup-dismissed-empty)
    p = doc.Parameter("D1@SK_Box1")
    if p is not None:
        try:
            val = p.SystemValue * 1000
            print(f"  Parameter('D1@SK_Box1') = {val:.3f} mm -- dim is REAL")
        except Exception as e:
            print(f"  Parameter exists but SystemValue ERR: {e!r}")
    else:
        print("  Parameter('D1@SK_Box1') is None -- dim NOT created")

    # ----- Test 2: try shorter delay (250ms) to see if SendKeys still works -----
    # Add a SECOND sketch to dim, this time with shorter SendKeys delay
    print()
    print("=== Test 2: same procedure with shorter (200ms) SendKeys delay ===")

    # We need a second sketch. Easiest: re-dim SK_Box1's left edge (D2 will get auto-created).
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box1", "SKETCH", 0, 0, 0)
    doc.EditSketch()
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", -0.010, 0, 0)  # left edge
    print(f"  left edge selected: {ok}")

    t = threading.Thread(
        target=dismiss_after_delay, args=(sw, 200, "test2"), daemon=True
    )
    t.start()
    t0 = time.perf_counter()
    dim2 = doc.AddDimension2(-0.015, 0, 0)
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000
    t.join(timeout=2.0)
    print(f"  AddDimension2 returned in {elapsed_ms:.1f}ms, dim={dim2 is not None}")
    if elapsed_ms < 100:
        verdict_2 = (
            "INSTANT (popup likely never opened OR dim creation failed silently)"
        )
    elif elapsed_ms < 2000:
        verdict_2 = "FAST (SendKeys likely dismissed the popup)"
    elif elapsed_ms < 6000:
        verdict_2 = "MEDIUM (SendKeys may have worked but slowly)"
    else:
        verdict_2 = "SLOW (SendKeys did not dismiss; you likely ticked manually)"
    print(f"  verdict: {verdict_2}")

    sm.InsertSketch(True)  # close

    p2 = doc.Parameter("D2@SK_Box1")
    if p2 is not None:
        try:
            val = p2.SystemValue * 1000
            print(f"  Parameter('D2@SK_Box1') = {val:.3f} mm -- dim is REAL")
        except Exception as e:
            print(f"  Parameter exists but SystemValue ERR: {e!r}")
    else:
        print("  Parameter('D2@SK_Box1') is None -- dim NOT created")

    # ----- Verify bbox unchanged -----
    bb = doc.GetBodies2(0, True)[0].GetBodyBox()
    print()
    print(
        f"final bbox (mm): x=[{bb[0]*1000:.1f},{bb[3]*1000:.1f}] "
        f"y=[{bb[1]*1000:.1f},{bb[4]*1000:.1f}] "
        f"z=[{bb[2]*1000:.1f},{bb[5]*1000:.1f}]"
    )
    print(f"expected:        x=[-10.0,10.0] y=[-10.0,10.0] z=[0.0,10.0]")

    print()
    print(">>> Decision:")
    print(
        "    Both tests FAST (<2s) AND both dims REAL -> Option A viable (autonomous batching)"
    )
    print("    Either test SLOW (>6s) -> Option B (human ticks at end)")
    print("    Either dim None -> SendKeys broke dim creation; investigate")


if __name__ == "__main__":
    main()
